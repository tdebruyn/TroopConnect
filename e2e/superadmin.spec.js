const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

// The superadmin is a Django superuser (is_staff + is_superuser). In addition
// to everything a staff user can do, it reaches the Django admin at /admin/
// with full model permissions.

test.describe('Superadmin user flows', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'superadmin');
  });

  test('reaches the Django admin index without re-logging in', async ({ page }) => {
    // Already authenticated as a superuser with is_staff → not bounced to
    // /admin/login/.
    await page.goto('/admin/');
    await expect(page).toHaveURL(/\/admin\/$/);
    await expect(page.locator('#site-name')).toBeVisible();
  });

  test('Django admin shows model groups (full permissions)', async ({ page }) => {
    // A superuser sees app/module links; a permissionless staff user would
    // instead see "You don't have permission to view or edit anything."
    await page.goto('/admin/');
    await expect(page.locator('.module').first()).toBeVisible();
  });

  test('navbar shows the Administration dropdown', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('a.dropdown-toggle:has-text("Administration")')).toBeVisible();
  });

  test('can access member management list', async ({ page }) => {
    await page.goto('/users/adminlist');
    await expect(page.locator('table')).toBeVisible();
    const rowCount = await page.locator('table tbody tr').count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('can open the admin update page from the list', async ({ page }) => {
    await page.goto('/users/adminlist');
    const updateLink = page.locator('a[href*="/users/adminupdate/"]').first();
    await updateLink.click();
    await expect(page.locator('input[name="first_name"]')).toBeVisible();
    await expect(page.locator('input[name="last_name"]')).toBeVisible();
  });
});
