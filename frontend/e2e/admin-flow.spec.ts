import { expect, test } from "@playwright/test";

const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "admin@example.com";
const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? "Password123!";

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(adminEmail);
  await page.getByLabel(/password/i).fill(adminPassword);
  await page.getByRole("button", { name: /sign in|login/i }).click();
});

test("admin dashboard shows stats and upload area", async ({ page }) => {
  await page.goto("/admin");

  await expect(page.getByText("Total Documents")).toBeVisible();
  await expect(page.getByText("Upload Documents")).toBeVisible();
  await expect(page.getByText(/Drag files here/i)).toBeVisible();
});
