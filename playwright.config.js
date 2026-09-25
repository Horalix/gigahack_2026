import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/ui",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4173",
    headless: true,
    channel: process.platform === "win32" ? "msedge" : "chromium",
    viewport: { width: 720, height: 480 },
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
  },
});
