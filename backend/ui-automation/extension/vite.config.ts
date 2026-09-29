import { defineConfig } from 'vite';
import { resolve } from 'path';
import { copyFileSync, mkdirSync, existsSync } from 'fs';

export default defineConfig({
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        background: resolve(__dirname, 'src/service-worker.ts'),
        content: resolve(__dirname, 'src/content-script.ts'),
        popup: resolve(__dirname, 'src/popup/popup.html'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]',
      },
    },
    target: 'esnext',
    minify: false,
  },
  plugins: [
    {
      name: 'copy-manifest',
      writeBundle() {
        // Copy manifest.json to dist/
        const src = resolve(__dirname, 'manifest.json');
        const dest = resolve(__dirname, 'dist/manifest.json');
        if (existsSync(src)) {
          copyFileSync(src, dest);
        }
        // Move popup.html from dist/src/popup/ to dist/ if needed
        const popupSrc = resolve(__dirname, 'dist/src/popup/popup.html');
        const popupDest = resolve(__dirname, 'dist/popup.html');
        if (existsSync(popupSrc) && !existsSync(popupDest)) {
          copyFileSync(popupSrc, popupDest);
        }
      }
    }
  ]
});
