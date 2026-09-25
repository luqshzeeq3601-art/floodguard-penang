/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // `--mode mock` points the dev server at the synthetic test API in e2e/mock-api. Never used for builds.
  if (mode === "mock") {
    process.env.VITE_API_BASE_URL ??= "http://localhost:8787";
    process.env.VITE_MAP_STYLE_URL ??= "https://tiles.openfreemap.org/styles/positron";
    process.env.VITE_TERRAIN_URL ??= "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
  }
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
        "/health": {
          target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
        "/ready": {
          target: process.env.VITE_API_BASE_URL || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    // MapLibre v6 loads its worker as a separate module; pre-bundling breaks that path.
    optimizeDeps: { exclude: ["maplibre-gl"] },
    worker: { format: "es" },
    build: {
      // MapLibre is ~1 MB and only loaded lazily on map views.
      chunkSizeWarningLimit: 1100,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes("maplibre-gl")) return "maplibre";
            if (id.includes("recharts") || id.includes("d3-")) return "recharts";
            return undefined;
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
      css: false,
    },
  };
});
