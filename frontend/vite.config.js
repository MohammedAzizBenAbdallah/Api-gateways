// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://waf:8080",
        changeOrigin: true,
        rewrite: (path) => path,
      },
      "/ai": {
        target: "http://waf:8080",
        changeOrigin: true,
        rewrite: (path) => path,
      },
    },
    allowedHosts: ["localhost", "127.0.0.1", "::1", "frontend"],
    watch: {
      usePolling: true,
    },
  },
});
