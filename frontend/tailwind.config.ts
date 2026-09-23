import type { Config } from 'tailwindcss'

const lightTheme = {
  '--color-canvas': '#EFE9D9', '--color-surface': '#fffdf7', '--color-surface-muted': '#f6f0e2', '--color-surface-raised': '#fffaf0', '--color-text': '#153B50', '--color-muted': '#527080', '--color-line': '#d9d1bd', '--color-line-strong': '#aca28d', '--color-accent': '#3FCCD0', '--color-accent-strong': '#2C7D80', '--color-accent-muted': '#dff5f3', '--color-danger': '#a43b45', '--color-danger-muted': '#fdebed', '--color-code': '#f0ece0', '--color-overlay': '#153B50cc', '--shadow': '0 12px 28px #153B501a',
}

const darkTheme = {
  '--color-canvas': '#102f42', '--color-surface': '#153B50', '--color-surface-muted': '#1d4c62', '--color-surface-raised': '#194359', '--color-text': '#fffdf7', '--color-muted': '#c4d6d5', '--color-line': '#356074', '--color-line-strong': '#63889a', '--color-accent': '#3FCCD0', '--color-accent-strong': '#76e5e5', '--color-accent-muted': '#1d5b68', '--color-danger': '#ff9ca5', '--color-danger-muted': '#60313b', '--color-code': '#214b5d', '--color-overlay': '#071d2ae0', '--shadow': '0 12px 28px #071d2a80',
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
