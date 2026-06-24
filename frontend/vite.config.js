import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Source lives in frontend/; the production bundle is emitted into the package
// at icp_engine/web_console/ so web.py can serve it as static assets (it
// auto-detects that dir and falls back to the legacy web_assets/ SPA when it is
// absent). During development `npm run dev` proxies /api to the local engine.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../icp_engine/web_console',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.ICP_API_TARGET || 'http://127.0.0.1:8799',
        changeOrigin: true,
      },
    },
  },
})
