const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

// Children (Animé, primary_role 'e') can log in but have restricted access:
// a reduced profile form (AnimeProfileForm), no staff/animateur tooling, and
// no access to member management or the messaging compose/history views.

test.describe('Child (Animé) user flows', () => {
  test.beforeEach(async ({ page }) => {
    await login(page, 'child');
  });

  test('profile loads with the child-restricted form', async ({ page }) => {
    await page.goto('/');
    const profileLink = page.locator('a[href*="/users/profile/"]').first();
    await profileLink.click();

    // AnimeProfileForm exposes totem, phone, email
    await expect(page.locator('input[name="totem"]')).toBeVisible();
    await expect(page.locator('input[name="phone"]')).toBeVisible();
    await expect(page.locator('input[name="email"]')).toBeVisible();

    // first_name / last_name are NOT editable for children
    await expect(page.locator('input[name="first_name"]')).toHaveCount(0);
    await expect(page.locator('input[name="last_name"]')).toHaveCount(0);
  });

  test('navbar does not show the Administration dropdown', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('a.dropdown-toggle:has-text("Administration")')).toHaveCount(0);
  });

  test('navbar does not show the Outils Animateur dropdown', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('a.dropdown-toggle:has-text("Outils Animateur")')).toHaveCount(0);
  });

  test('cannot reach member management (admin list)', async ({ page }) => {
    // AdminListView.test_func requires is_staff → child gets 403 Forbidden;
    // the members table (with its admin-update links) must never render.
    await page.goto('/users/adminlist');
    await expect(page.locator('a[href*="/users/adminupdate/"]')).toHaveCount(0);
  });

  test('messaging compose returns 404', async ({ page }) => {
    // compose_message raises Http404 for anyone not authorized to send.
    const response = await page.goto('/messaging/compose/');
    expect(response.status()).toBe(404);
  });

  test('messaging history returns 404', async ({ page }) => {
    const response = await page.goto('/messaging/history/');
    expect(response.status()).toBe(404);
  });
});
