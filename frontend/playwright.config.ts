import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(frontendDirectory, '..');
const backendPort = process.env.REQPILOT_E2E_BACKEND_PORT ?? '18080';
const backendUrl = `http://127.0.0.1:${backendPort}`;
const defaultPython = path.join(
  repositoryRoot,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const python = process.env.REQPILOT_PYTHON ?? defaultPython;
const backendCommand = `${JSON.stringify(python)} ${JSON.stringify(
  path.join(repositoryRoot, 'tools/e2e_server.py'),
)}`;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],
  webServer: [
    {
      command: backendCommand,
      url: `${backendUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      env: { REQPILOT_BACKEND_URL: backendUrl },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  use: {
    baseURL: process.env.REQPILOT_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    viewport: { width: 1600, height: 1000 },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        ...(process.env.CI ? {} : { channel: 'chrome' }),
      },
    },
  ],
  expect: { timeout: 10_000 },
});
