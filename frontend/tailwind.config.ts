import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        civic: {
          green: "#2E7D32",
          "green-light": "#4CAF50",
          "green-pale": "#E8F5E9",
          blue: "#1565C0",
          "blue-light": "#42A5F5",
          "blue-pale": "#E3F2FD",
        },
        warm: {
          50: "#FAFAF5",
          100: "#F5F5F0",
          200: "#E8E8E0",
          300: "#D4D4CC",
        },
        status: {
          renovated: "#2E7D32",
          occupied: "#1565C0",
          partial: "#F57F17",
          vacant: "#E65100",
          demolished: "#B71C1C",
          inconclusive: "#4A148C",
        },
        detection: {
          occupied: "#2E7D32",
          vacant: "#E65100",
          demolished: "#B71C1C",
        },
      },
      fontFamily: {
        heading: ["var(--font-heading)", "Georgia", "serif"],
        body: ["var(--font-body)", "-apple-system", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
