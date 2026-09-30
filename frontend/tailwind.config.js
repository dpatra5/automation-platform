/** @type {import('tailwindcss').Config} */
export default {
  content: {
    relative: true,
    files: [
      './index.html',
      './src/components/sprintguard/**/*.{ts,tsx}',
      './src/pages/ProjectPlanPage.tsx',
    ],
  },
  theme: {
    extend: {},
  },
  plugins: [],
}
