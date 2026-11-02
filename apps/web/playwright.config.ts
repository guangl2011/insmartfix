import { defineConfig, devices } from '@playwright/test';

/**
 * Web E2E (TEST_PLAN §2): Pixel 7, iPhone 14 and desktop projects.
 *
 * - E2E_BASE_URL set (CI, local-stack): run against that server, e.g. the compose stack on :3000.
 * - unset: build-once `next start` on :3000 is launched for you (DATA_SOURCE=mock).
 * - PW_IPHONE_ENGINE=chromium emulates the iPhone 14 viewport in Chromium for hosts without
 *   WebKit installed; CI installs WebKit so iPhone 14 runs on the real Safari engine.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const iphoneOnChromium = process.env.PW_IPHONE_ENGINE === 'chromium';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }], ['github']] : 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'pixel7', use: { ...devices['Pixel 7'] } },
    {
      name: 'iphone14',
      use: {
        ...devices['iPhone 14'],
        ...(iphoneOnChromium
          ? { browserName: 'chromium' as const, defaultBrowserType: 'chromium' as const }
          : {}),
      },
    },
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: 'pnpm start',
        url: `${baseURL}/api/healthz`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: { DATA_SOURCE: process.env.DATA_SOURCE ?? 'mock' },
      },
});
