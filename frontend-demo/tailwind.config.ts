import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Spec §1 visual palette
        bg: {
          base: '#0a0a0c',
          gradient: '#14141a',
          card: '#16161d',
          elevated: '#1c1c25',
        },
        border: {
          default: 'rgba(255, 255, 255, 0.06)',
          active: 'rgba(255, 255, 255, 0.12)',
        },
        accent: {
          // Brand palette per Integrity Indonesia identity (merah-putih).
          // - `red` is primary CTA + brand. Deep crimson — distinct from
          //   error red so a Translate button can't be confused with a
          //   failure banner.
          // - `rose` pairs with red for gradients only (CTA fills).
          // - `amber` carries warnings (lang mismatch) so they read as
          //   "caution" not "fatal".
          // - `crimson` reserved for true error/failure state (translation
          //   failed, agent crashed) — bright red, sparingly used.
          // - `emerald` stays for success / "agent completed" states.
          red: '#b91c1c',
          rose: '#f43f5e',
          amber: '#f59e0b',
          emerald: '#10b981',
          crimson: '#ef4444',
        },
        fg: {
          primary: '#ffffff',
          body: '#d4d4d8',
          muted: '#71717a',
          placeholder: '#52525b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        shake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '25%': { transform: 'translateX(-4px)' },
          '75%': { transform: 'translateX(4px)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s linear infinite',
        shake: 'shake 200ms ease-in-out',
      },
      backgroundImage: {
        'gradient-radial':
          'radial-gradient(ellipse at top, #14141a 0%, #0a0a0c 70%)',
        'red-rose': 'linear-gradient(135deg, #b91c1c 0%, #f43f5e 100%)',
      },
    },
  },
  plugins: [],
}

export default config
