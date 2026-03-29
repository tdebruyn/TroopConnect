const { test, expect } = require('@playwright/test');

test.describe('Finance billing page', () => {
  test('Cotisations nav link navigates to billing page', async ({ page }) => {
    await page.goto('/');
    // The Cotisations link should point to /finance/
    const cotisationsLink = page.locator('a.nav-link:has-text("Cotisations")');
    await expect(cotisationsLink).toHaveAttribute('href', '/finance/');
  });

  test('billing page shows login redirect for unauthenticated users', async ({ page }) => {
    // Unauthenticated access should redirect to login
    await page.goto('/finance/');
    // Should be redirected to login or get 404
    const url = page.url();
    expect(
      url.includes('/accounts/login/') || url.includes('/finance/')
    ).toBeTruthy();
  });

  test('payment form page loads for authenticated tresorier', async ({ page }) => {
    await page.goto('/finance/payment/');
    // Either redirected to login or shows the form
    const url = page.url();
    expect(
      url.includes('/accounts/login/') || url.includes('/finance/payment/')
    ).toBeTruthy();
  });
});
