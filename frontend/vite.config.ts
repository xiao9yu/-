import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// pixi-live2d-display@0.4.0 声明 @pixi/* ^6 依赖（npm 提升到根 node_modules/@pixi → v6），
// 与 pixi.js@7.4.3 形成双实例：模型 extends v6 Container → v7 EventBoundary 调其
// isInteractive() 崩溃，v7 渲染器也画不出 v6 对象。解法=把这四个包的精确 id 别名到
// pixi.js 的嵌套 v7 副本（lib/index.mjs）：
//   - build（rollup）与 dev（源码服务）统一走 resolve.alias
//   - dev 预打包入口（optimizeDeps.include）也经 vite:resolve 解析 → 入口即 v7 文件
//     （esbuildOptions.alias 不行：它只改包内裸导入，改不了 vite 已解析好的入口）
//   - pixi.js 自身的 @pixi/* 导入本就解析到嵌套副本，别名后指向同一文件，无副作用
const pixiV7Dir = fileURLToPath(new URL('./node_modules/pixi.js/node_modules/@pixi/', import.meta.url))
const PLUGIN_PIXI_PKGS = ['core', 'display', 'math', 'utils'] as const

const pixiV7Alias = Object.fromEntries(
  PLUGIN_PIXI_PKGS.map((p) => [`@pixi/${p}`, `${pixiV7Dir}${p}/lib/index.mjs`]))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      ...pixiV7Alias
    }
  },
  optimizeDeps: {
    // 插件被排除预打包：其主入口含 cubism2 代码，打包后模块求值即抛运行时错误，
    // 须按源码服务 /cubism4 子路径；插件源码里的 @pixi/* 裸导入由预打包好的 v7 分块承接
    exclude: ['pixi-live2d-display'],
    // url：@pixi/utils v7 的 lib/url.mjs 引用 npm 的 CJS url 包（被 node 内置名遮蔽、
    // 依赖扫描发现不了）；不预打包时 CJS 按源码服务，命名导出解析失败
    include: [...Object.keys(pixiV7Alias), 'url']
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, ws: true } }
  }
})
