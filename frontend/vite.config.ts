import { existsSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// pixi-live2d-display@0.4.0 声明 @pixi/* ^6 依赖，npm 将其提升到根 node_modules/@pixi（v6），
// 与 pixi.js@7.4.3 形成双实例：模型 extends v6 Container → v7 EventBoundary 调其
// isInteractive() 崩溃，v7 渲染器也画不出 v6 对象。仅将该插件的 @pixi/* 导入重写到
// pixi.js 的嵌套 v7 副本（pixi.js 自身导入不动，保持 npm 原生解析）。
const pixiV7Dir = fileURLToPath(new URL('./node_modules/pixi.js/node_modules/@pixi/', import.meta.url))

function live2dPixiV7Alias() {
  return {
    name: 'live2d-pixi-v7-alias',
    // vite 6 的 vite:resolve 是 enforce:'pre'，普通 resolveId 抢不到裸导入
    enforce: 'pre' as const,
    resolveId(source: string, importer?: string) {
      if (!source.startsWith('@pixi/') || !importer?.includes('pixi-live2d-display')) return null
      const nested = pixiV7Dir + source.slice('@pixi/'.length)
      const entry = nested + '/lib/index.mjs'
      return existsSync(entry) ? entry : null
    },
  }
}

export default defineConfig({
  plugins: [vue(), live2dPixiV7Alias()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) }
  },
  optimizeDeps: {
    // 插件若被 esbuild 预打包会绕过上面的 resolveId、仍捆到根目录 v6：排除预打包
    exclude: ['pixi-live2d-display']
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true } }
  }
})
