const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

test.describe('Animateur messaging flows', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'animateur');
  });

  test('animateur can access compose section message', async ({ page }) => {
    await page.goto('/messaging/animateurs/compose/');
    await expect(page.locator('input[name="subject"]')).toBeVisible();
    await expect(page.locator('textarea[name="body"]')).toBeVisible();
  });

  test('compose shows parent checkboxes', async ({ page }) => {
    await page.goto('/messaging/animateurs/compose/');
    // Should have checkboxes for parents
    const checkboxes = page.locator('input[type="checkbox"][name^="parent_"]');
    await expect(checkboxes.first()).toBeVisible();
  });

  test('animateur can access compose-all', async ({ page }) => {
    await page.goto('/messaging/animateurs/compose-all/');
    await expect(page.locator('input[name="subject"]')).toBeVisible();
    await expect(page.locator('textarea[name="body"]')).toBeVisible();
  });

  test('animateur history page loads', async ({ page }) => {
    await page.goto('/messaging/animateurs/history/');
    await expect(page.locator('table')).toBeVisible();
  });

  test('navbar shows animateur tools dropdown', async ({ page }) => {
    await page.goto('/');
    // Look for "Outils Animateur" or similar dropdown in navbar
    const dropdown = page.locator('text=Outils Animateur');
    await expect(dropdown).toBeVisible();
  });

  test('navbar shows compose links in dropdown', async ({ page }) => {
    await page.goto('/');
    await page.click('text=Outils Animateur');
    await expect(page.locator('a[href*="/messaging/animateurs/compose/"]')).toBeVisible();
    await expect(page.locator('a[href*="/messaging/animateurs/history/"]')).toBeVisible();
  });
});
