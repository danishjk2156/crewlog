/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      // Theme tokens live in src/index.css (":root") so the whole UI re-skins in one place.
      colors: {
        paper: 'rgb(var(--paper) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        rule: 'rgb(var(--rule) / <alpha-value>)',
        safety: 'rgb(var(--safety) / <alpha-value>)',
        alarm: 'rgb(var(--alarm) / <alpha-value>)',
        panel: 'rgb(var(--panel) / <alpha-value>)',
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Arial Narrow', 'sans-serif'],
        body: ['Archivo', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
