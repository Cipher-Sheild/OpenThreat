/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: '#0f172a',
        panel: '#1e293b',
        primary: '#3b82f6',
        accent: '#10b981',
        warning: '#f59e0b',
        danger: '#ef4444'
      }
    },
  },
  plugins: [],
}
