import solid from "@solidjs/vite-plugin";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [solid()],
  server: {
    // The local service: uv run python -m climate_chat.service.local
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
