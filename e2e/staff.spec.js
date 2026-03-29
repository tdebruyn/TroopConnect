const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

test.describe('Staff admin flows', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'staff');
  });

  test('admin list loads with persons table', async ({ page }) => {
    await page.goto('/users/adminlist');
    await expect(page.locator('table')).toBeVisible();
    const rowCount = await page.locator('table tbody tr').count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('admin list supports sorting', async ({ page }) => {
    await page.goto('/users/adminlist?sort=last_name&direction=asc');
    await expect(page.locator('table')).toBeVisible();
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toBeVisible();
  });

  test('admin update page loads from list', async ({ page }) => {
    await page.goto('/users/adminlist');
    const updateLink = page.locator('a[href*="/users/adminupdate/"]').first();
    await updateLink.click();
    await expect(page.locator('input[name="first_name"]')).toBeVisible();
    await expect(page.locator('input[name="last_name"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();
  });

  test('admin update page shows correct role badge', async ({ page }) => {
    await page.goto('/users/adminlist');
    const updateLink = page.locator('a[href*="/users/adminupdate/"]').first();
    await updateLink.click();

    // Badge is in the <p> tag inside the hat_text block
    const badgeText = await page.locator('p').first().textContent();
    const trimmed = badgeText.trim();
    expect(['Parent', 'Enfant', 'Animateur', 'Membre']).toContain(trimmed);
  });

  test('admin update has submit button', async ({ page }) => {
    await page.goto('/users/adminlist');
    const updateLink = page.locator('a[href*="/users/adminupdate/"]').first();
    await updateLink.click();
    await expect(page.locator('button:has-text("Confirmer")')).toBeVisible();
  });
});
