/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        robot: {
          950: '#05080e',
          900: '#090e17',
          850: '#0d131f',
          800: '#121a2a',
          750: '#182338',
          700: '#1e2c46',
          border: '#1e293b',
          cyan: '#00f0ff',
          glow: '#38bdf8',
          purple: '#a855f7',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
