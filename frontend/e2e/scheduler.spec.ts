import { test, expect } from '@playwright/test';

/**
 * End-to-end coverage for the scheduling comparison.
 *
 * The repository previously had no browser tests at all, so UI regressions and
 * runtime errors were invisible. These run against a real backend and a real
 * production build — no mocking — so they fail if the API contract drifts.
 */

/** Fail loudly on console errors; a silently-broken React page still renders. */
function trackConsole(page: import('@playwright/test').Page) {
  const errors: string[] = [];
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push(String(e)));
  return errors;
}

test('scheduler page loads and runs a comparison', async ({ page }) => {
  const errors = trackConsole(page);

  await page.goto('/scheduler');
  await expect(page.getByRole('heading', { name: 'Live Scheduling Comparison' }))
    .toBeVisible();

  // The comparison auto-runs on mount.
  await expect(page.getByText(/driver requests$/)).toBeVisible({ timeout: 45_000 });

  // Output section renders with the agent's schedule.
  await expect(page.getByText('EV NEXUS Agent').first()).toBeVisible();
  await expect(page.locator('svg[aria-label="Charging schedule"]').first())
    .toBeVisible();

  // Two schedules are drawn: the agent and the chosen baseline.
  expect(await page.locator('svg[aria-label="Charging schedule"]').count())
    .toBeGreaterThanOrEqual(2);

  expect(errors).toEqual([]);
});

test('delta cards report the agent against a baseline', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText('Deadlines met').first()).toBeVisible({ timeout: 45_000 });
  await expect(page.getByText('Urgent deadlines met')).toBeVisible();
  await expect(page.getByText('Average wait')).toBeVisible();
  await expect(page.getByText('Worst-case wait (p95)')).toBeVisible();

  // Every policy, including the ablations, is listed on the same input.
  await expect(page.getByText('Every policy on this same input')).toBeVisible();
  await expect(
    page.getByRole('table').getByText('Agent (no deadlines)')
  ).toBeVisible();
});

test('switching the baseline recomputes the comparison', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText('Deadlines met').first()).toBeVisible({ timeout: 45_000 });

  const agentVs = page.getByText(/^agent vs /).first();
  const before = await agentVs.textContent();

  await page.getByRole('button', { name: 'FIFO', exact: true }).click();
  await expect(page.getByText(/^agent vs FIFO$/).first()).toBeVisible();
  expect(await agentVs.textContent()).not.toBe(before);
});

test('clicking a request reveals the decision behind it', async ({ page }) => {
  const errors = trackConsole(page);

  await page.goto('/scheduler');
  await expect(page.getByText(/driver requests$/)).toBeVisible({ timeout: 45_000 });

  await page.locator('.req-row').first().click();

  await expect(page.getByText('1 · Extracted from language')).toBeVisible();
  await expect(page.getByText('2 · Checked against telemetry')).toBeVisible();
  await expect(page.getByText('3 · Scheduled result')).toBeVisible();

  expect(errors).toEqual([]);
});

test('per-port view renders without breaking', async ({ page }) => {
  const errors = trackConsole(page);

  await page.goto('/scheduler');
  await expect(page.getByText('The schedule', { exact: true }))
    .toBeVisible({ timeout: 45_000 });

  await page.getByRole('button', { name: 'Per port' }).click();
  await expect(page.locator('svg[aria-label="Charging schedule"]').first())
    .toContainText('PORT 1');

  expect(errors).toEqual([]);
});

test('changing demand re-runs the schedule', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText(/driver requests$/)).toBeVisible({ timeout: 45_000 });

  const count = page.getByText(/driver requests$/);
  const before = await count.textContent();

  await page.getByRole('button', { name: 'Overloaded' }).click();
  await expect(page.getByRole('button', { name: /RUN COMPARISON/ }))
    .toBeEnabled({ timeout: 45_000 });

  // A different demand level uses a different window, so the count must change.
  await expect.poll(async () => await count.textContent(), { timeout: 20_000 })
    .not.toBe(before);
});

test('all navigation routes render', async ({ page }) => {
  const errors = trackConsole(page);

  for (const [path, heading] of [
    ['/scheduler', 'Live Scheduling Comparison'],
    ['/overview', 'Charging Command Center'],
    ['/charging', 'Charging Monitor'],
    ['/analytics', 'Analytics'],
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole('heading', { name: heading })).toBeVisible({
      timeout: 30_000,
    });
  }

  // Benchmarks and architecture pages load their own content.
  await page.goto('/benchmarks');
  await expect(page.locator('body')).toContainText(/Benchmark|Phase 5|benchmark/i, {
    timeout: 30_000,
  });

  await page.goto('/architecture');
  await expect(page.locator('body')).toContainText(/app\.py|FastAPI|Architecture/i, {
    timeout: 30_000,
  });

  expect(errors).toEqual([]);
});

test('backend health indicator reflects a reachable API', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText('System Online')).toBeVisible({ timeout: 30_000 });
});

test('no Gemini credential is exposed to the browser', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText(/driver requests$/)).toBeVisible({ timeout: 45_000 });

  const html = await page.content();
  expect(html).not.toMatch(/AIza[0-9A-Za-z_-]{20,}/);

  const scripts = await page.evaluate(async () => {
    const urls = Array.from(document.querySelectorAll('script[src]'))
      .map(s => (s as HTMLScriptElement).src);
    const bodies = await Promise.all(urls.map(u => fetch(u).then(r => r.text())));
    return bodies.join('\n');
  });
  expect(scripts).not.toMatch(/AIza[0-9A-Za-z_-]{20,}/);
  expect(scripts).not.toMatch(/GEMINI_API_KEY\s*[:=]\s*["'][^"']+["']/);
});
