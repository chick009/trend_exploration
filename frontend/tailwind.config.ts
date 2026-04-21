import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", '"Segoe UI"', "sans-serif"],
      },
      colors: {
        app: {
          bg: "var(--bg)",
          "bg-elevated": "var(--bg-elevated)",
          panel: "var(--panel-solid)",
          border: "var(--border)",
          text: "var(--text)",
          muted: "var(--muted)",
          accent: "var(--accent)",
          accentAlt: "var(--accent-alt)",
        },
      },
      boxShadow: {
        panel: "0 20px 50px rgba(2, 8, 23, 0.42)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
    },
  },
} satisfies Config;
