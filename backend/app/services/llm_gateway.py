# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-公共底座(16-20)
"""LLM 网关：统一封装 DeepSeek 调用。
功能：超时/限流指数退避重试、JSON 结构化输出与修复重试、流式输出、用量日志。
各功能模块只调网关，不直接碰 OpenAI SDK。
"""
import json
import logging
import re
import time
from typing import Iterator

import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from ..config import settings

logger = logging.getLogger("llm")

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


class LLMError(Exception):
    """LLM 调用失败（重试耗尽/未配置密钥等）。"""


class LLMGateway:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        backoff_base: float = 0.5,
        http_client: httpx.Client | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.deepseek_api_key
        self.backoff_base = backoff_base
        kwargs = {}
        if http_client is not None:
            kwargs["http_client"] = http_client
        self.client = OpenAI(
            api_key=self.api_key or "sk-empty",
            base_url=base_url or settings.deepseek_base_url,
            timeout=60.0,
            max_retries=0,  # 重试由网关自管
            **kwargs,
        )

    def _check_key(self):
        if not self.api_key:
            raise LLMError("未配置 DEEPSEEK_API_KEY，请在 backend/.env 中配置")

    def _create(self, messages, temperature, response_format=None, stream=False):
        self._check_key()
        kwargs = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format:
            kwargs["response_format"] = response_format
        last_exc = None
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(**kwargs)
            except RETRYABLE as exc:
                last_exc = exc
                retry_after = getattr(exc, "response", None)
                retry_after = retry_after.headers.get("retry-after") if retry_after is not None else None
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = self.backoff_base * (2 ** attempt)
                time.sleep(min(delay, 8.0))
            except Exception as exc:
                # 非可重试错误（错 key 401、参数 400 等）直接包成 LLMError，不再空转重试（台账 A-2）
                raise LLMError(f"大模型调用失败：{exc}") from exc
        raise LLMError(f"大模型调用失败（已重试3次）：{last_exc}")

    @staticmethod
    def _log_usage(resp):
        usage = getattr(resp, "usage", None)
        if usage is not None:
            logger.info("LLM用量 prompt=%s completion=%s", usage.prompt_tokens, usage.completion_tokens)

    def chat(self, messages: list[dict], temperature: float = 0.7) -> str:
        """普通对话，返回文本。"""
        resp = self._create(messages, temperature)
        self._log_usage(resp)
        return resp.choices[0].message.content or ""

    def chat_json(self, messages: list[dict], temperature: float = 0.3) -> dict:
        """结构化输出：要求模型返回 JSON，解析失败自动修复重试一次。"""
        msgs = [dict(m) for m in messages]
        if "JSON" not in msgs[-1].get("content", ""):
            msgs[-1]["content"] += "\n请以 JSON 格式输出，不要输出其他内容。"
        for attempt in range(2):
            resp = self._create(
                msgs, temperature, response_format={"type": "json_object"}
            )
            self._log_usage(resp)
            content = resp.choices[0].message.content or ""
            parsed = self._parse_json(content)
            if parsed is not None:
                return parsed
            # 修复重试：把错误反馈给模型
            msgs.append({"role": "assistant", "content": content})
            msgs.append({"role": "user", "content": "上次输出不是合法 JSON，请重新只输出合法 JSON。"})
        raise LLMError("大模型 JSON 输出解析失败")

    @staticmethod
    def _parse_json(content: str) -> dict | None:
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        # 去掉 markdown 代码围栏再试
        m = re.search(r"```(?:json)?\s*(.*?)```", content, re.S)
        if m:
            try:
                data = json.loads(m.group(1))
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def chat_stream(self, messages: list[dict], temperature: float = 0.7, *,
                    first_token_timeout: float | None = None,
                    overall_timeout: float | None = None,
                    silence_timeout: float | None = None) -> Iterator[str]:
        """流式输出，逐段 yield 文本。

        三段超时保护（评测 §5.5，实测曾出现单题 103s 极端抖动、生成段 ~82s）：
          · 首字超时：第一个内容块迟迟不来 → 报错（上游异常/连接失败）；
          · 整体超时：生成总时长越限 → 报错（防长回答无限拖拽）；
          · 静默超时：两内容块间隔越限 → 报错（防中途卡死）。
        超时按 LLMError 抛出，answer_events 按协议转 error 事件（SSE/语音链路共用），
        用户看到"请稍后重试"而非无限等待。静默阈值同时收紧 SDK 读超时，
        连接卡死不必等 60s 默认值才被发现。
        """
        if first_token_timeout is None:
            first_token_timeout = settings.llm_first_token_timeout
        if overall_timeout is None:
            overall_timeout = settings.llm_overall_timeout
        if silence_timeout is None:
            silence_timeout = settings.llm_silence_timeout
        self._check_key()
        start = time.monotonic()
        last_token_at: float | None = None
        create_kwargs: dict = {
            "model": settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if silence_timeout > 0:
            create_kwargs["timeout"] = httpx.Timeout(timeout=self.client.timeout, read=silence_timeout)
        try:
            stream = self.client.chat.completions.create(**create_kwargs)
            for chunk in stream:
                if not (chunk.choices and chunk.choices[0].delta.content):
                    continue
                now = time.monotonic()
                if last_token_at is None:
                    if now - start > first_token_timeout:
                        raise LLMError(f"大模型响应超时（首字超时 {first_token_timeout:g}s），请稍后重试")
                elif now - last_token_at > silence_timeout:
                    raise LLMError(f"大模型响应超时（静默超时 {silence_timeout:g}s），请稍后重试")
                if now - start > overall_timeout:
                    raise LLMError(f"大模型响应超时（整体超时 {overall_timeout:g}s），请稍后重试")
                last_token_at = now
                yield chunk.choices[0].delta.content
        except LLMError:
            raise
        except APITimeoutError as exc:
            raise LLMError("大模型响应超时，请稍后重试") from exc
        except Exception as exc:
            raise LLMError(f"大模型调用失败：{exc}") from exc


_gateway: LLMGateway | None = None


def get_gateway() -> LLMGateway:
    """懒加载单例。"""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
