// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://kong-dp:80",
        changeOrigin: true,
        rewrite: (path) => path,
      },
      "/ai": {
        target: "http://kong-dp:80",
        changeOrigin: true,
        rewrite: (path) => path,
      },
    },
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      "::1",
      "frontend",
      "197.14.4.163",
      "frontend.ai-gateway.svc.cluster.local",
    ],
    watch: {
      usePolling: true,
    },
  },
});
