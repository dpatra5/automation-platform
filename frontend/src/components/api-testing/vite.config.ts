import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.APIT_PROXY_TARGET || 'http://127.0.0.1:8002';

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      // 5173 = platform shell, 5174 = ui-automation, 5175 = load-testing.
      port: 5176,
      strictPort: true,
      proxy: { '/api': { target: apiTarget, changeOrigin: false } },
    },
    preview: {
      port: 4176,
      proxy: { '/api': { target: apiTarget, changeOrigin: false } },
    },
    build: { target: 'es2022' },
    test: { environment: 'node' },
  };
});
