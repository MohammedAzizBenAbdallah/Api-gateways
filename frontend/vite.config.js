// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://fastapi_backend:3000",
        changeOrigin: true,
        rewrite: (path) => path,
      },
      "/ai": {
        target: "http://fastapi_backend:3000",
        changeOrigin: true,
        rewrite: (path) => path,
      },
    },
    allowedHosts: ["localhost", "127.0.0.1", "::1", "frontend", "197.14.4.163"],
    watch: {
      usePolling: true,
    },
  },
});
