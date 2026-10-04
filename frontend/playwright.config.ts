import { defineConfig, devices } from '@playwright/test';

/**
 * Runs the real production build against a real backend.
 *
 * VITE_API_BASE must point at a running API. Locally:
 *   uvicorn app:app --port 8000        (from the repository root)
 *   npm run test:e2e                   (from frontend/)
 */
const API_BASE = process.env.VITE_API_BASE ?? 'http://127.0.0.1:8000/api';

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    // vite preview binds to ::1 only, so address it as localhost, not 127.0.0.1.
    baseURL: 'http://localhost:4173',
    ...devices['Desktop Chrome'],
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    // Serves the production bundle — the same artefact that gets deployed,
    // not a dev server. Build it first, with the API base baked in:
    //   $env:VITE_API_BASE="http://127.0.0.1:8000/api"; npm run build
    command: 'npx vite preview --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { VITE_API_BASE: API_BASE },
  },
});
