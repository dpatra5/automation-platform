import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiPort = env.VITE_API_PORT ?? '8000'
  return {
    plugins: [react()],
    // The tool UIs share frontend/node_modules, so each app keeps its own pre-bundle cache.
    cacheDir: 'node_modules/.vite/shell',
    optimizeDeps: { entries: ['index.html'] },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: `http://localhost:${apiPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
