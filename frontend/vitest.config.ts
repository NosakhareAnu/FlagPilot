import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  // Next's tsconfig uses jsx:"preserve"; tests need the automatic runtime transform instead.
  oxc: { jsx: { runtime: "automatic" } },
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"], globals: false },
});
