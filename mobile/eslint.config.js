// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", ".expo/*"],
  },
  {
    // Test probe components copy a hook's value into an outer variable so the test can call it; that is the point of a
    // probe, and the "pure render" rules are about app code.
    files: ["__tests__/**"],
    linterOptions: { reportUnusedDisableDirectives: "off" },
    rules: {
      // tests load a screen after setting a mock or a switch, so they require() it inside the test
      "@typescript-eslint/no-require-imports": "off",
      "react-hooks/globals": "off",
      "react-hooks/immutability": "off",
      "react/display-name": "off",
    },
  }
]);
