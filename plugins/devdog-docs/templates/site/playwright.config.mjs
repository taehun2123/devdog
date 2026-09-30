import { defineConfig } from '@playwright/test';
import { loadConfig } from './scripts/site/config.mjs';
const base = loadConfig().site.base.replace(/\/?$/, '/');
export default defineConfig({
  testDir: './tests/browser', timeout: 45000, workers: 1,
  use: { baseURL: `http://127.0.0.1:4173${base}`, headless: true, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  webServer: { command: 'npm run docs:preview', url: `http://127.0.0.1:4173${base}`, reuseExistingServer: !process.env.CI }
});
