import type { Config } from 'tailwindcss'

const lightTheme = {
  '--color-canvas': '#EFE9D9', '--color-surface': '#fffdf7', '--color-surface-muted': '#f6f0e2', '--color-surface-raised': '#fffaf0', '--color-text': '#153B50', '--color-muted': '#527080', '--color-line': '#d9d1bd', '--color-line-strong': '#aca28d', '--color-accent': '#3FCCD0', '--color-accent-strong': '#2C7D80', '--color-accent-muted': '#dff5f3', '--color-danger': '#a43b45', '--color-danger-muted': '#fdebed', '--color-code': '#f0ece0', '--color-overlay': '#153B50cc', '--shadow': '0 12px 28px #153B501a',
}

const darkTheme = {
  '--color-canvas': '#181A1B',
  '--color-surface': '#202324',
  '--color-surface-muted': '#292D2E',
  '--color-surface-raised': '#252829',

  '--color-text': '#F5F5F2',
  '--color-muted': '#AEB5B5',

  '--color-line': '#3A3F40',
  '--color-line-strong': '#5A6263',

  '--color-accent': '#42C7C7',
  '--color-accent-strong': '#75DEDC',
  '--color-accent-muted': '#254B4B',

  '--color-danger': '#F08E96',
  '--color-danger-muted': '#543035',

  '--color-code': '#272B2C',
  '--color-overlay': '#101112E6',

  '--shadow': '0 12px 28px #00000066',
}

export default {
  theme: {
    extend: {
      colors: {
        canvas: 'var(--color-canvas)',
        surface: 'var(--color-surface)',
        'surface-muted': 'var(--color-surface-muted)',
        text: 'var(--color-text)',
        muted: 'var(--color-muted)',
        line: 'var(--color-line)',
        accent: 'var(--color-accent)',
        'accent-strong': 'var(--color-accent-strong)',
        danger: 'var(--color-danger)',
      },
    },
  },
  plugins: [({ addBase }) => addBase({ ':root': lightTheme, ':root[data-theme="dark"]': darkTheme })],
} satisfies Config
