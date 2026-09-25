import { defineConfig, devices } from "@playwright/test";

/**
 * E2E runs the production build against the SYNTHETIC mock API (e2e/mock-api). No basemap tiles are
 * fetched (empty VITE_MAP_STYLE_URL), so runs are offline and deterministic apart from the clock.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:4173", channel: "chrome", trace: "retain-on-failure" },
  projects: [
    { name: "desktop-1440", use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 1440, height: 900 } } },
    { name: "mobile-360", use: { ...devices["Pixel 5"], channel: "chrome", viewport: { width: 360, height: 780 } } },
  ],
  webServer: [
    { command: "node e2e/mock-api/server.mjs", port: 8787, reuseExistingServer: true },
    {
      command: "npx vite build && npx vite preview --port 4173 --strictPort",
      port: 4173,
      timeout: 120_000,
      reuseExistingServer: true,
      env: { VITE_API_BASE_URL: "http://localhost:8787", VITE_MAP_STYLE_URL: "" },
    },
  ],
});
