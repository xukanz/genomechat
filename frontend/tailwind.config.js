/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        brand: {
          blue: "#0066CC",
          darkBlue: "#004080",
          lightGrey: "#F5F5F5",
        }
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      typography: ({ theme }) => ({
        DEFAULT: {
          css: {
            '--tw-prose-body': theme('colors.foreground'),
            '--tw-prose-headings': theme('colors.foreground'),
            '--tw-prose-bold': theme('colors.foreground'),
            '--tw-prose-links': theme('colors.primary.DEFAULT'),
            '--tw-prose-counters': theme('colors.muted.foreground'),
            '--tw-prose-bullets': theme('colors.muted.foreground'),
            '--tw-prose-hr': theme('colors.border'),
            '--tw-prose-quotes': theme('colors.foreground'),
            '--tw-prose-quote-borders': theme('colors.brand.blue'),
            '--tw-prose-captions': theme('colors.muted.foreground'),
            '--tw-prose-code': theme('colors.primary.DEFAULT'),
            maxWidth: '100%',
            pre: {
              backgroundColor: '#1E1E1E',
              color: '#F5F5F5',
              padding: theme('spacing.4'),
              borderRadius: theme('borderRadius.lg'),
              borderWidth: '1px',
              borderColor: theme('colors.border'),
            },
            code: {
              backgroundColor: theme('colors.muted.DEFAULT'),
              color: theme('colors.primary.DEFAULT'),
              borderRadius: theme('borderRadius.sm'),
              padding: '0.15rem 0.35rem',
            },
          },
        },
        invert: {
          css: {
            '--tw-prose-body': theme('colors.foreground'),
            '--tw-prose-headings': theme('colors.foreground'),
            '--tw-prose-bold': theme('colors.foreground'),
            '--tw-prose-links': theme('colors.primary.foreground'),
            '--tw-prose-counters': theme('colors.muted.foreground'),
            '--tw-prose-bullets': theme('colors.muted.foreground'),
            '--tw-prose-hr': theme('colors.border'),
            '--tw-prose-quotes': theme('colors.foreground'),
            '--tw-prose-quote-borders': theme('colors.brand.blue'),
            '--tw-prose-captions': theme('colors.muted.foreground'),
            '--tw-prose-code': theme('colors.primary.foreground'),
            pre: {
              backgroundColor: '#111827',
              color: '#F5F5F5',
              borderColor: theme('colors.border'),
            },
            code: {
              backgroundColor: 'rgba(255,255,255,0.08)',
              color: theme('colors.primary.foreground'),
              padding: '0.15rem 0.35rem',
              borderRadius: theme('borderRadius.sm'),
            },
          },
        },
      }),
      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
        spotlight: {
          "0%": {
            opacity: 0,
            transform: "translate(-72%, -62%) scale(0.5)",
          },
          "100%": {
            opacity: 1,
            transform: "translate(-50%, -40%) scale(1)",
          },
        },
        "pulse-dot": {
          "0%, 80%, 100%": {
            opacity: "0.3",
            transform: "scale(0.8)",
          },
          "40%": {
            opacity: "1",
            transform: "scale(1.1)",
          },
        },
        "text-shimmer": {
          "0%": { backgroundPosition: "100% 50%" },
          "100%": { backgroundPosition: "-100% 50%" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        spotlight: "spotlight 2s ease 0.75s 1 forwards",
        "pulse-dot": "pulse-dot 1.4s ease-in-out infinite",
        "text-shimmer": "text-shimmer 5s ease-in-out infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
}
