import solid from "@solidjs/vite-plugin";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // A production build without the real Turnstile site key would ship a page that can
  // never get a token, so fail the build instead.
  if (mode === "production" && !loadEnv(mode, ".").VITE_TURNSTILE_SITE_KEY) {
    throw new Error("VITE_TURNSTILE_SITE_KEY must be set for a production build.");
  }
  return {
    plugins: [solid()],
    server: {
      // The local service: uv run python -m climate_chat.service.local
      proxy: { "/api": "http://127.0.0.1:8000" },
    },
  };
});
