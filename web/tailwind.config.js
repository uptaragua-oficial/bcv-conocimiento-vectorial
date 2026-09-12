/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bcv: {
          navy: '#0f2a4a',
          blue: '#1d5fa8',
          steel: '#2c6fbb',
          gold: '#c79a2e',
          soft: '#f2f6fb',
        },
      },
    },
  },
  plugins: [],
}
