/** Tailwind for SolveSpace / PracticeForge. Palette from the CDN kit (material/dark). */
module.exports = {
  content: ["./**/templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        ui: {
          surface: "var(--ui-surface)",
          "on-surface": "var(--ui-on-surface)",
          variant: "var(--ui-surface-variant)",
          "on-variant": "var(--ui-on-surface-variant)",
          outline: "var(--ui-outline)",
          primary: "var(--ui-primary)",
          error: "var(--ui-error)",
        },
      },
    },
  },
  plugins: [],
};
