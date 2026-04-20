/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Editorial display + technical body — distinct from generic SaaS
        display: ["'Fraunces'", "serif"],
        sans: ["'Geist Sans'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      colors: {
        // Dark-first palette, warm accents — not another "blue SaaS"
        ink: {
          DEFAULT: "#0a0a0b",
          50: "#f7f7f8",
          100: "#e8e8eb",
          200: "#cdcdd3",
          300: "#9e9ea8",
          400: "#6e6e7a",
          500: "#4a4a55",
          600: "#2e2e37",
          700: "#1c1c24",
          800: "#12121a",
          900: "#0a0a0b",
        },
        // Sinal vital, não corporate-blue
        pulse: {
          DEFAULT: "#ff6b35",  // âmbar-laranja
          soft: "#ff9570",
          deep: "#c7421a",
        },
        emerald: { 500: "#10b981", 600: "#059669" },
        rose:    { 500: "#f43f5e", 600: "#e11d48" },
        amber:   { 500: "#f59e0b", 600: "#d97706" },
      },
      boxShadow: {
        "elev-1": "0 1px 2px rgba(0,0,0,0.4), 0 1px 1px rgba(0,0,0,0.2)",
        "elev-2": "0 4px 12px rgba(0,0,0,0.5), 0 2px 4px rgba(0,0,0,0.3)",
        "elev-3": "0 12px 32px rgba(0,0,0,0.6), 0 4px 8px rgba(0,0,0,0.35)",
        "glow-pulse": "0 0 0 1px rgba(255,107,53,0.3), 0 0 24px rgba(255,107,53,0.15)",
      },
      animation: {
        "fade-up": "fadeUp 0.4s cubic-bezier(0.2, 0.8, 0.2, 1)",
        "shimmer": "shimmer 2s linear infinite",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          from: { backgroundPosition: "200% 0" },
          to:   { backgroundPosition: "-200% 0" },
        },
      },
    },
  },
  plugins: [],
};
