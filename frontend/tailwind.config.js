/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#FAFAF7",
        ink: {
          DEFAULT: "#14181F",
          soft: "#3C4552",
          faint: "#6B7280",
        },
        navy: {
          DEFAULT: "#1F3A5F",
          dark: "#152941",
          light: "#2E4F7D",
        },
        brass: {
          DEFAULT: "#A6762C",
          light: "#C99A4F",
          soft: "#F3E7D3",
        },
        line: "#E4E2DC",
        risk: {
          high: "#B3261E",
          highBg: "#FBEAE9",
          medium: "#B7791F",
          mediumBg: "#FBF1E1",
          low: "#2F6B4F",
          lowBg: "#E9F3EE",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(20,24,31,0.04), 0 1px 12px rgba(20,24,31,0.05)",
      },
      borderRadius: {
        sm: "4px",
        md: "6px",
        lg: "10px",
      },
    },
  },
  plugins: [],
};
