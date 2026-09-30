import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// https://vitejs.dev/config/
export default defineConfig({
  appType: 'spa',
  plugins: [react()],
  cacheDir: fileURLToPath(new URL('../../../node_modules/.vite/ui-automation', import.meta.url)),
  server: {
    port: 5174,
    strictPort: true,
    middlewareMode: false,
    proxy: {
      '/api': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
      // Screenshots, video, trace and log files are served by the backend.
      '/artifacts': {
        target: 'http://localhost:8003',
        changeOrigin: true,
      },
    },
  },
  preview: {},
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
});
