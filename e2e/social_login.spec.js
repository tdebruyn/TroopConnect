const { test, expect } = require('@playwright/test');

test.describe('Social login buttons', () => {
  test('login page Facebook button links to OAuth flow', async ({ page }) => {
    await page.goto('/accounts/login/');
    const fbLink = await page.locator('a:has-text("Facebook")');
    await expect(fbLink).toBeVisible();
    const href = await fbLink.getAttribute('href');
    // Should NOT be a dead link
    expect(href).not.toBe('#!');
    // Should contain the allauth provider login URL
    expect(href).toContain('/accounts/facebook/login');
  });

  test('login page Google button links to OAuth flow', async ({ page }) => {
    await page.goto('/accounts/login/');
    const googleLink = await page.locator('a:has-text("Google")');
    await expect(googleLink).toBeVisible();
    const href = await googleLink.getAttribute('href');
    expect(href).toContain('/accounts/google/login');
  });

  test('signup page Facebook button links to OAuth flow', async ({ page }) => {
    await page.goto('/accounts/signup/');
    const fbLink = await page.locator('a:has-text("Facebook")');
    await expect(fbLink).toBeVisible();
    const href = await fbLink.getAttribute('href');
    expect(href).not.toBe('#!');
    expect(href).toContain('/accounts/facebook/login');
  });

  test('signup page Google button links to OAuth flow', async ({ page }) => {
    await page.goto('/accounts/signup/');
    const googleLink = await page.locator('a:has-text("Google")');
    await expect(googleLink).toBeVisible();
    const href = await googleLink.getAttribute('href');
    expect(href).toContain('/accounts/google/login');
  });
});
