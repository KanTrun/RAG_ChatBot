import { expect, test } from "@playwright/test";

const userEmail = process.env.E2E_USER_EMAIL ?? "viewer@example.com";
const userPassword = process.env.E2E_USER_PASSWORD ?? "Password123!";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(userEmail);
  await page.getByLabel(/password/i).fill(userPassword);
  await page.getByRole("button", { name: /sign in|login/i }).click();
  await expect(page).toHaveURL(/chat/);
});

test("sends a chat message and renders assistant response", async ({ page }) => {
  await page.getByPlaceholder(/ask a question/i).fill("What does AlphaProject use?");
  await page.getByRole("button", { name: /send message/i }).click();

  await expect(page.getByText("What does AlphaProject use?")).toBeVisible();
  await expect(page.locator('[aria-live="polite"]')).toContainText(/./, { timeout: 30_000 });
});
