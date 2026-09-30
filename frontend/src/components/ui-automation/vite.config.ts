import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  appType: 'spa',
  plugins: [react()],
  cacheDir: path.resolve(__dirname, '../../../node_modules/.vite/ui-automation'),
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
      '@': path.resolve(__dirname, './src'),
    },
  },
});
