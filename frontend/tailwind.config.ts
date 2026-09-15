import type { Config } from 'tailwindcss'

const lightTheme = {
  '--color-canvas': '#f6f8fa', '--color-surface': '#fff', '--color-surface-muted': '#f0f4f6', '--color-surface-raised': '#fbfcfd', '--color-text': '#152935', '--color-muted': '#627782', '--color-line': '#d7e0e4', '--color-line-strong': '#aebfc6', '--color-accent': '#087c83', '--color-accent-strong': '#045d63', '--color-accent-muted': '#e1f1f0', '--color-danger': '#b42335', '--color-danger-muted': '#fff0f1', '--color-code': '#edf3f5', '--color-overlay': '#0b202dcc', '--shadow': '0 12px 28px #1529350d',
}

const darkTheme = {
  '--color-canvas': '#10191e', '--color-surface': '#162228', '--color-surface-muted': '#1d2b32', '--color-surface-raised': '#1a272e', '--color-text': '#e5eef0', '--color-muted': '#a9bdc4', '--color-line': '#31434b', '--color-line-strong': '#59707a', '--color-accent': '#55c4c5', '--color-accent-strong': '#91e1dc', '--color-accent-muted': '#163b40', '--color-danger': '#ff8d99', '--color-danger-muted': '#42232a', '--color-code': '#223239', '--color-overlay': '#02090de0', '--shadow': '0 12px 28px #0000003b',
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
