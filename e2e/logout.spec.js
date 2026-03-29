const { test, expect } = require('@playwright/test');
const { login } = require('./helpers/auth');

test.describe('Logout flow', () => {
  test('user can log out', async ({ page }) => {
    await login(page, 'parent1');

    // Find and click logout - could be in navbar dropdown or direct link
    // Look for logout link/form in the page
    const logoutLink = page.locator('a[href*="/accounts/logout"], a:has-text("Déconnexion"), a:has-text("Se déconnecter")').first();

    if (await logoutLink.isVisible()) {
      await logoutLink.click();
    } else {
      // Try the allauth logout URL directly
      await page.goto('/accounts/logout/');
      // Confirm logout if there's a form
      const confirmBtn = page.locator('button[type="submit"]').first();
      if (await confirmBtn.isVisible()) {
        await confirmBtn.click();
      }
    }

    // Should be logged out - homepage should show login link
    await page.goto('/');
    await expect(page.locator('a[href*="/accounts/login/"]')).toBeVisible();
  });
});
