const { test, expect } = require('@playwright/test');

test.describe('Agenda page', () => {
  test('agenda page loads and shows heading', async ({ page }) => {
    await page.goto('/agenda/');
    await expect(page.locator('h2')).toContainText('Agenda');
  });

  test('agenda page shows empty state when no events', async ({ page }) => {
    await page.goto('/agenda/');
    await expect(page.locator('text=Aucun événement')).toBeVisible();
  });

  test('agenda page has correct structure', async ({ page }) => {
    await page.goto('/agenda/');
    // Page should extend base.html with container
    await expect(page.locator('.container')).toBeVisible();
    // Should have the card header
    await expect(page.locator('.card h2')).toContainText('Agenda');
  });
});
