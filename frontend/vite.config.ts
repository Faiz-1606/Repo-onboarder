import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    // In development the app runs on :5173 while the API runs on :8000.
    // Proxying the API routes keeps requests same-origin, so CORS does not
    // need configuring just to work locally.
    proxy: {
      "/index": "http://127.0.0.1:8000",
      "/chat": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
