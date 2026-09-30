import { fileURLToPath } from 'node:url'
import autoprefixer from 'autoprefixer'
// Tailwind v4 is the default install for the load/API testing UIs; this app stays on v3.
import tailwindcss from 'tailwindcss-v3'

export default {
  plugins: [
    tailwindcss({ config: fileURLToPath(new URL('./tailwind.config.js', import.meta.url)) }),
    autoprefixer(),
  ],
}
