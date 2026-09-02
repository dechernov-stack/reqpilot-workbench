import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#172033',
        navy: '#15263a',
        steel: '#526274',
        line: '#d9e0e7',
        canvas: '#f4f6f8',
        panel: '#ffffff',
        cyan: {
          50: '#ecfeff',
          100: '#cffafe',
          300: '#67e8f9',
          950: '#083344',
          DEFAULT: '#0d7180',
        },
        'cyan-dark': '#07535f',
        ok: '#24734a',
        warn: '#9a5c00',
        danger: '#ae2e24',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(18, 35, 52, 0.08)',
      },
      fontFamily: {
        sans: ['Inter', 'IBM Plex Sans', 'Segoe UI', 'Arial', 'sans-serif'],
        mono: ['IBM Plex Mono', 'SFMono-Regular', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config;
