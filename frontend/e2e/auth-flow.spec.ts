import { expect, test } from "@playwright/test";

const userEmail = process.env.E2E_USER_EMAIL ?? "viewer@example.com";
const userPassword = process.env.E2E_USER_PASSWORD ?? "Password123!";

test("protected chat redirects to login and accepts credentials", async ({ page }) => {
  await page.goto("/chat");
  await expect(page).toHaveURL(/login/);

  await page.getByLabel(/email/i).fill(userEmail);
  await page.getByLabel(/password/i).fill(userPassword);
  await page.getByRole("button", { name: /sign in|login/i }).click();

  await expect(page).toHaveURL(/chat/);
});
