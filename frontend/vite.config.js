// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    include: [
      "axios",
      "keycloak-js",
      "react",
      "react-dom",
      "react-dom/client",
      "react-markdown",
      "remark-gfm",
      "styled-components",
    ],
    noDiscovery: true,
    holdUntilCrawlEnd: false,
  },
  server: {
    warmup: {
      clientFiles: ["./src/**/*.jsx", "./src/**/*.tsx", "./src/main.jsx"],
    },
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
