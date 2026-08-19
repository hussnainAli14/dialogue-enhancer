import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0A0F1E",
        surface: "#111827",
        "surface-raised": "#1A2235",
        border: "#1E2D45",
        "border-bright": "#2D4A6B",
        accent: "#1E5FA8",
        "accent-hover": "#2570C4",
        "accent-light": "#3B82F6",
        "text-primary": "#F0F4F8",
        "text-secondary": "#8A9BB5",
        "text-muted": "#4A5568",
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#EF4444",
        info: "#6366F1",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
