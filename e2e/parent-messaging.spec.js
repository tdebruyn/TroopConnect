const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

test.describe('Parent with secondary role messaging', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'parent2');
  });

  test('can access compose-all', async ({ page }) => {
    await page.goto('/messaging/animateurs/compose-all/');
    await expect(page.locator('input[name="subject"]')).toBeVisible();
  });

  test('section compose returns 404', async ({ page }) => {
    const response = await page.goto('/messaging/animateurs/compose/');
    expect(response.status()).toBe(404);
  });

  test('navbar shows messaging tools but not section compose', async ({ page }) => {
    await page.goto('/');
    // Should see the messaging dropdown
    const dropdown = page.locator('text=Outils Animateur');
    await expect(dropdown).toBeVisible();
    await page.click('text=Outils Animateur');
    // Should see compose-all but NOT section compose
    await expect(page.locator('a[href*="/messaging/animateurs/compose-all/"]')).toBeVisible();
    await expect(page.locator('a[href*="/messaging/animateurs/compose/"]')).not.toBeVisible();
  });
});
