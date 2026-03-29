const { test, expect } = require('@playwright/test');

test.describe('Anonymous user flows', () => {
  test('homepage loads', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL('/');
  });

  test('login page shows email and password fields', async ({ page }) => {
    await page.goto('/accounts/login/');
    await expect(page.locator('input[name="login"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('signup page shows required fields', async ({ page }) => {
    await page.goto('/accounts/signup/');
    await expect(page.locator('input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password1"]')).toBeVisible();
    await expect(page.locator('input[name="password2"]')).toBeVisible();
  });

  test('profile redirects to login when unauthenticated', async ({ page }) => {
    await page.goto('/users/profile/00000000-0000-0000-0000-000000000000/');
    // Should redirect to login page
    await expect(page).toHaveURL(/\/accounts\/login/);
  });

  test('admin list redirects to login when unauthenticated', async ({ page }) => {
    await page.goto('/users/adminlist');
    await expect(page).toHaveURL(/\/accounts\/login/);
  });
});
