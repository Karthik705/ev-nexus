import { test, expect } from '@playwright/test';

/**
 * Screenshot capture, used to review the UI and to produce the images embedded
 * in the README. Run with:  npx playwright test shots --update-snapshots
 */

test.use({ viewport: { width: 1480, height: 1000 } });

test('capture scheduler', async ({ page }) => {
  await page.goto('/scheduler');
  await expect(page.getByText(/driver requests$/)).toBeVisible({ timeout: 45_000 });
  await page.waitForTimeout(700);
  await page.screenshot({ path: '../screenshots/scheduler.png' });

  // The app scrolls inside <main>, so fullPage cannot expand it; capture the
  // schedule panel as an element instead.
  const schedule = page.locator('.panel').filter({ hasText: 'The schedule' }).first();
  await schedule.scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await schedule.screenshot({ path: '../screenshots/schedule-gantt.png' });

  // Decision drill-down
  await page.locator('.req-row').nth(2).click();
  await expect(page.getByText('1 · Extracted from language')).toBeVisible();
  await page.getByText('1 · Extracted from language').scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);
  await page.screenshot({ path: '../screenshots/decision-detail.png' });
});

test('capture other pages', async ({ page }) => {
  for (const [path, name] of [
    ['/overview', 'overview'],
    ['/charging', 'charging'],
    ['/benchmarks', 'benchmarks'],
    ['/architecture', 'architecture'],
  ] as const) {
    await page.goto(path);
    await page.waitForTimeout(2200);
    await page.screenshot({ path: `../screenshots/${name}.png` });
  }
});
