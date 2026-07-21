import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        pale: "#BDD8E9",
        sky: "#7BBDE8",
        teal: "#6EA2B3",
        "teal-mid": "#4E8EA2",
        "blue-mid": "#49769F",
        "navy-mid": "#0A4174",
        ink: "#001D39",
      },
      fontFamily: {
        system: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Inter",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
export default config;
