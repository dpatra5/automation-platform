/** @type {import('tailwindcss').Config} */
export default {
  // Relative to this file: the dev server now runs from frontend/.
  content: {
    relative: true,
    files: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  },
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // Flat pastel light theme. Tints (50/100) are backgrounds, 500/600 are
        // text and icons: every 500 clears 4.5:1 on its own 50 and on white.
        canvas: '#F6F7FB',
        surface: '#FFFFFF',
        line: '#E6E8F1',
        ink: {
          DEFAULT: '#1F2537',
          soft: '#4A5468',
          muted: '#6E7789',
        },
        primary: {
          50: '#EFF0FE', 100: '#E1E3FC', 200: '#C6CAF8',
          500: '#5A61CE', 600: '#4950B4', 700: '#3B4194',
        },
        mint: { 50: '#E9F7F1', 100: '#D3EFE3', 500: '#1F8F68', 600: '#177355' },
        rose: { 50: '#FDEEF0', 100: '#FBDDE1', 500: '#C0405A', 600: '#A13049' },
        sky:  { 50: '#EAF2FD', 100: '#D5E5FB', 500: '#2E72CC', 600: '#245BA6' },
        amber:{ 50: '#FDF3E6', 100: '#FAE7CD', 500: '#A66F14', 600: '#875A10' },
        lilac:{ 50: '#F4F0FB', 100: '#E8E1F7', 500: '#6F52B8', 600: '#5A4197' },
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.125rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(31, 37, 55, 0.04), 0 1px 3px rgba(31, 37, 55, 0.06)',
        lift: '0 4px 12px rgba(31, 37, 55, 0.08)',
        pop: '0 12px 32px rgba(31, 37, 55, 0.14)',
      },
    },
  },
  plugins: [],
}
