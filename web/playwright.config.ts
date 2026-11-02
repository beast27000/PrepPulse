import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  outputDir: process.env.PREPPULSE_E2E_OUTPUT || "test-results",
  use: {
    baseURL: process.env.PREPPULSE_E2E_URL || "http://127.0.0.1:5174",
    channel: "msedge",
    headless: true,
    viewport: { width: 1600, height: 1000 },
    screenshot: "only-on-failure",
  },
});
