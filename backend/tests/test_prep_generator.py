# 工单编号：人工智能NLP-Agent数字人项目-教育智能体-智能备课任务(17)
"""备课生成服务测试：prompt 组装、JSON 校验、温度参数（不依赖真实 API）。"""
import pytest

from app.core.exceptions import BizError
from app.services.prep_generator import (
    generate_case,
    generate_courseware,
    generate_exercises,
    generate_lesson_plan,
    generate_monthly_exam,
    validate_case,
    validate_courseware,
    validate_exam,
    validate_exercises,
    validate_lesson_plan,
)

LESSON_PLAN = {
    "标题": "梯度下降教案",
    "教学目标": ["理解梯度下降原理", "掌握学习率作用"],
    "教学重点": ["梯度下降迭代公式"],
    "教学难点": ["学习率选择"],
    "教学过程": [{"环节": "导入", "内容": "回顾线性回归", "时长": "5分钟"}],
    "作业": "完成课后习题1-3",
    "板书设计": "迭代公式与示意图",
}

COURSEWARE = {
    "标题": "机器学习基础课件",
    "幻灯片": [
        {"标题": "梯度下降", "要点": ["沿负梯度方向迭代", "学习率控制步长"],
         "讲稿": "同学们好，今天我们来学习梯度下降。它的核心思想是沿负梯度方向一步步迭代，让损失函数不断下降。"},
        {"标题": "线性回归", "要点": ["拟合直线", "房价预测"],
         "讲稿": "接下来看线性回归。我们用一条直线拟合数据，最典型的应用就是房价预测。"},
    ],
}

EXERCISES = {
    "习题": [
        {"题干": "梯度下降中控制步长的参数是", "选项": ["A.学习率", "B.批量大小", "C.迭代次数", "D.正则系数"],
         "答案": "A", "解析": "学习率控制步长", "知识点": "梯度下降", "难度": "易"},
    ]
}

EXAM = {
    "试卷标题": "人工智能导论月考试卷",
    "大题": [
        {"题型": "选择题", "知识点": "梯度下降",
         "题目": [{"题干": "梯度下降中控制步长的参数是", "选项": ["A.学习率", "B.批量大小"],
                   "答案": "A", "解析": "学习率控制步长", "知识点": "梯度下降", "难度": "易"}]},
    ]
}

CASE = {
    "标题": "垃圾邮件分类教学案例",
    "案例背景": "某电商平台每日收到大量垃圾邮件，影响客服效率。",
    "案例描述": "使用朴素贝叶斯对邮件进行二分类，训练集包含 5000 封标注邮件。",
    "问题": "如何设计特征并评估模型效果？",
    "案例分析": "提取词频特征，使用交叉验证评估准确率与召回率。",
    "结论": "朴素贝叶斯在小样本文本分类中效果良好，垃圾邮件召回率达 95%。",
}


class FakeLLM:
    """记录调用并返回预设 JSON。"""
    def __init__(self, result):
        self.result = result
        self.calls = []

    def chat_json(self, messages, temperature=0.3):
        self.calls.append({"messages": messages, "temperature": temperature})
        return self.result


def _gw():
    return FakeLLM(LESSON_PLAN)


def test_generate_lesson_plan_prompt_and_temperature():
    llm = FakeLLM(LESSON_PLAN)
    result = generate_lesson_plan(
        course_name="人工智能导论", subject="人工智能", chapter="第3章 机器学习基础",
        objectives="理解梯度下降", hours="2课时", resources="[1] 来源：教材.pdf\n梯度下降通过沿负梯度方向迭代更新参数。", llm=llm,
    )
    assert result == LESSON_PLAN
    prompt_text = llm.calls[0]["messages"][-1]["content"]
    assert "人工智能导论" in prompt_text and "第3章 机器学习基础" in prompt_text
    assert "理解梯度下降" in prompt_text and "2课时" in prompt_text
    assert "[1] 来源：教材.pdf" in prompt_text          # 资源上下文拼入 prompt
    assert "JSON" in prompt_text                         # 结构化输出要求
    assert llm.calls[0]["temperature"] == 0.7            # 教案用 0.7


def test_generate_exercises_uses_low_temperature():
    llm = FakeLLM(EXERCISES)
    result = generate_exercises(
        course_name="人工智能导论", subject="人工智能", chapter="第3章",
        knowledge_points=["梯度下降", "线性回归"], count=5, llm=llm,
    )
    assert result == EXERCISES
    assert "梯度下降" in llm.calls[0]["messages"][-1]["content"]
    assert "5" in llm.calls[0]["messages"][-1]["content"]      # 数量要求
    assert llm.calls[0]["temperature"] == 0.3                  # 习题用 0.3（JSON 严格）


def test_generate_courseware_and_exam():
    gw1 = FakeLLM(COURSEWARE)
    assert generate_courseware("人工智能导论", "人工智能", "第3章", "目标", "2课时", llm=gw1) == COURSEWARE
    gw2 = FakeLLM(EXAM)
    assert generate_monthly_exam(
        "人工智能导论", "人工智能", [{"知识点": "梯度下降", "占比": "30%"}], llm=gw2) == EXAM
    assert "30%" in gw2.calls[0]["messages"][-1]["content"]


def test_generate_case():
    llm = FakeLLM(CASE)
    result = generate_case(
        "人工智能导论", "人工智能", "第4章 朴素贝叶斯", "理解分类器原理", llm=llm)
    assert result == CASE
    prompt = llm.calls[0]["messages"][-1]["content"]
    assert "第4章 朴素贝叶斯" in prompt and "理解分类器原理" in prompt
    assert llm.calls[0]["temperature"] == 0.7     # 案例用 0.7


def test_validators_accept_valid_and_reject_missing_keys():
    validate_lesson_plan(LESSON_PLAN)
    validate_courseware(COURSEWARE)
    validate_exercises(EXERCISES)
    validate_exam(EXAM)
    validate_case(CASE)
    with pytest.raises(BizError):
        validate_lesson_plan({"标题": "缺字段"})
    with pytest.raises(BizError):
        validate_exercises({"习题": [{"题干": "缺答案"}]})
    with pytest.raises(BizError):
        validate_exam({"试卷标题": "缺大题"})
    with pytest.raises(BizError):
        validate_case({"标题": "缺案例描述"})


COURSEWARE_NO_SCRIPT = {
    "标题": "机器学习基础课件",
    "幻灯片": [{"标题": "梯度下降", "要点": ["沿负梯度方向迭代"]}],
}


def test_validate_courseware_requires_script_per_slide():
    """每页必须含非空讲稿：缺失或纯空白均 502；齐全则通过。"""
    with pytest.raises(BizError):
        validate_courseware(COURSEWARE_NO_SCRIPT)
    with pytest.raises(BizError):
        validate_courseware({"标题": "课件", "幻灯片": [{"标题": "梯度下降", "要点": [], "讲稿": "   "}]})
    validate_courseware(COURSEWARE)  # 每页含讲稿 → 通过


def test_generate_courseware_prompt_asks_for_script():
    llm = FakeLLM(COURSEWARE)
    generate_courseware("人工智能导论", "人工智能", "第3章", "目标", "2课时", llm=llm)
    prompt_text = llm.calls[0]["messages"][-1]["content"]
    assert "讲稿" in prompt_text
    assert "口语化" in prompt_text
