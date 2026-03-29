const TEST_PASSWORD = 'Test1234!';

const USERS = {
  parent1: { email: 'parent1@test.be', password: TEST_PASSWORD },
  parent2: { email: 'parent2@test.be', password: TEST_PASSWORD },
  animateur: { email: 'anim1@test.be', password: TEST_PASSWORD },
  staff: { email: 'staff1@test.be', password: TEST_PASSWORD },
};

async function login(page, userKey) {
  const user = USERS[userKey];
  await page.goto('/accounts/login/');
  await page.fill('#id_login', user.email);
  await page.fill('#id_password', user.password);
  await page.click('button[type="submit"]');
  // Wait for redirect away from login page
  await page.waitForURL((url) => !url.pathname.includes('/accounts/login/'), { timeout: 15000 });
}

module.exports = { login, USERS, TEST_PASSWORD };
