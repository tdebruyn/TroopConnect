const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

test.describe('Parent user flows', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'parent1');
  });

  test('profile page loads with form fields', async ({ page }) => {
    // Navigate to profile - first get the user's PK from the page
    await page.goto('/');
    // Find profile link in navbar
    const profileLink = page.locator('a[href*="/users/profile/"]').first();
    await profileLink.click();
    await expect(page.locator('input[name="first_name"]')).toBeVisible();
    await expect(page.locator('input[name="last_name"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
  });

  test('profile page shows Enregistrer button', async ({ page }) => {
    await page.goto('/');
    const profileLink = page.locator('a[href*="/users/profile/"]').first();
    await profileLink.click();
    await expect(page.locator('button:has-text("Enregistrer")')).toBeVisible();
  });

  test('profile edit saves changes', async ({ page }) => {
    await page.goto('/');
    const profileLink = page.locator('a[href*="/users/profile/"]').first();
    await profileLink.click();

    // Clear and fill first name
    const firstNameInput = page.locator('input[name="first_name"]');
    await firstNameInput.fill('ParentUpdated');
    await page.click('button:has-text("Enregistrer")');

    // Wait for page reload
    await page.waitForLoadState('networkidle');
    await expect(firstNameInput).toHaveValue('ParentUpdated');

    // Restore original value
    await firstNameInput.fill('Parent');
    await page.click('button:has-text("Enregistrer")');
    await page.waitForLoadState('networkidle');
  });

  test('child list loads via HTMX', async ({ page }) => {
    await page.goto('/');
    const profileLink = page.locator('a[href*="/users/profile/"]').first();
    await profileLink.click();

    // Child list loads via HTMX, wait for it
    await page.waitForSelector('.child-row', { timeout: 10000 });
    const childCount = await page.locator('.child-row').count();
    expect(childCount).toBeGreaterThanOrEqual(1);
    await expect(page.locator('.child-row').first().locator('td').first()).toHaveText('Child');
  });

  test('section history page loads', async ({ page }) => {
    await page.goto('/messaging/history/');
    await expect(page.locator('table')).toBeVisible();
  });
});
