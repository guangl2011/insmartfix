import { expect, test } from '@playwright/test';

// M0 scaffold smoke: the app shell renders on every project. Feature E2E (T-* IDs) arrives in M4.
test('home renders the app shell @smoke', async ({ page }) => {
  const res = await page.goto('/');
  expect(res?.status()).toBe(200);
  await expect(page.getByRole('heading', { level: 1, name: 'InsmartFix' })).toBeVisible();
  await expect(page).toHaveTitle('InsmartFix');
});

test('web server reaches the API when DATA_SOURCE=live @smoke', async ({ page }) => {
  test.skip(process.env.E2E_EXPECT_LIVE !== '1', 'only meaningful against the compose stack');
  await page.goto('/');
  await expect(page.getByTestId('data-source')).toHaveText('live');
  await expect(page.getByTestId('api-status')).toHaveText('API connected');
});
