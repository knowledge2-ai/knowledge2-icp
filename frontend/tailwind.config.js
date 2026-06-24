import tailwindcssAnimate from 'tailwindcss-animate'

/** @type {import('tailwindcss').Config}
 * Ported from k2_mvp/console_frontend so this dashboard shares the K2 console's
 * visual language (dark-first, blue primary, Space Grotesk / Inter / Fragment
 * Mono, 14px card radius). Semantic tokens reference CSS variables in index.css.
 */
export default {
  darkMode: 'media',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        border: 'var(--border)',
        input: 'var(--input)',
        ring: 'var(--ring)',
        background: 'var(--background)',
        foreground: 'var(--foreground)',
        primary: { DEFAULT: 'var(--primary)', foreground: 'var(--primary-foreground)' },
        secondary: { DEFAULT: 'var(--secondary)', foreground: 'var(--secondary-foreground)' },
        destructive: { DEFAULT: 'var(--destructive)', foreground: 'var(--destructive-foreground)' },
        muted: { DEFAULT: 'var(--muted)', foreground: 'var(--muted-foreground)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)' },
        popover: { DEFAULT: 'var(--popover)', foreground: 'var(--popover-foreground)' },
        card: { DEFAULT: 'var(--card)', foreground: 'var(--card-foreground)' },
        k2: {
          background: '#0a0a0f',
          surface: '#12121a',
          'surface-soft': '#1a1a24',
          'surface-strong': '#22222e',
          border: '#2a2a3a',
          'border-strong': '#3a3a4a',
          text: '#fafafa',
          'text-muted': '#71717a',
          primary: '#3b82f6',
          'primary-dark': '#2563eb',
          'primary-glow': 'rgba(59, 130, 246, 0.15)',
          footer: '#0a0a0f',
        },
        score: {
          high: '#22c55e',
          'high-bg': 'rgba(34, 197, 94, 0.15)',
          medium: '#eab308',
          'medium-bg': 'rgba(234, 179, 8, 0.15)',
          low: '#ef4444',
          'low-bg': 'rgba(239, 68, 68, 0.15)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        heading: ['Space Grotesk', 'Inter', 'sans-serif'],
        mono: ['Fragment Mono', 'SFMono-Regular', 'monospace'],
        numeric: ['Space Grotesk', 'Fragment Mono', 'sans-serif'],
      },
      borderRadius: {
        '4xl': '28px',
        '3xl': '20px',
        '2xl': '14px',
      },
      boxShadow: {
        card: '0 30px 80px rgba(0, 0, 0, 0.4)',
        soft: '0 18px 40px rgba(0, 0, 0, 0.3)',
        glow: '0 0 40px rgba(59, 130, 246, 0.15)',
        'glow-sm': '0 0 20px rgba(59, 130, 246, 0.1)',
      },
      backgroundImage: {
        'k2-grid': 'radial-gradient(circle at 1px 1px, rgba(42, 42, 58, 0.5) 1px, transparent 0)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
      },
      keyframes: {
        'accordion-down': { from: { height: '0' }, to: { height: 'var(--radix-accordion-content-height)' } },
        'accordion-up': { from: { height: 'var(--radix-accordion-content-height)' }, to: { height: '0' } },
      },
    },
  },
  plugins: [tailwindcssAnimate],
}
