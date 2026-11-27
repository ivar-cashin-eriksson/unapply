import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { defineConfig, devices } from '@playwright/test'

// End-to-end tests of the demos (`npm run e2e`). Playwright starts the API and the
// dev server itself, and stops both when the run ends, so nothing is left running.
//
// The API gets its own empty data folder in the temporary folder, so the run never
// touches data/. Paid model calls stay off: the demos replay recordings.

const API_PORT = 8766
const WEB_PORT = 5174
// The API's data folder, emptied at the start of each run. Playwright reads this
// config again in each worker; the environment variable says it was emptied already,
// so a worker never empties it under the running API. It isn't removed at the end,
// as the API still holds the database file then; the next run empties it.
const DATA_DIR = path.join(os.tmpdir(), 'unapply-e2e')
if (!process.env.UNAPPLY_E2E_DATA) {
  process.env.UNAPPLY_E2E_DATA = DATA_DIR
  fs.rmSync(DATA_DIR, { recursive: true, force: true })
  fs.mkdirSync(DATA_DIR, { recursive: true })
}

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  // The demos share one server and database, so one test at a time.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    trace: 'retain-on-failure',
    viewport: { width: 1280, height: 900 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 900 } } }],
  webServer: [
    {
      name: 'API',
      command: `uv run unapply api --port ${API_PORT}`,
      cwd: '..',
      url: `http://127.0.0.1:${API_PORT}/health`,
      env: {
        UNAPPLY_DATA: DATA_DIR,
        // Set explicitly, so a database URL in the shell can't point the run elsewhere.
        UNAPPLY_DATABASE_URL: `sqlite:///${DATA_DIR.replaceAll('\\', '/')}/unapply.db`,
        UNAPPLY_ALLOW_API_CALLS: '0',
      },
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe',
    },
    {
      name: 'Web',
      // Its own port and process: --bypass-lock lets it run beside a developer's dev server.
      command: `npx vite --port ${WEB_PORT} --strictPort --host 127.0.0.1 --bypass-lock`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { UNAPPLY_API_URL: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
