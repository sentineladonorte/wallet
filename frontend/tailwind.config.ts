import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#0d0d0d',
        surface: '#1a1a19',
        raised: '#242422',
        line: '#383835',
        ink: '#f0efec',
        soft: '#c3c2b7',
        muted: '#98978d',
        accent: '#3987e5',
        gain: '#2fb82f',
        loss: '#e66767',
        warn: '#fab219',
      },
    },
  },
  plugins: [],
}
export default config
