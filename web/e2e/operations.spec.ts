import { expect, test } from "@playwright/test";

test.skip(process.env.PREPPULSE_CARE_FIXTURE !== "1", "Isolated fixture only");
async function login(page: import("@playwright/test").Page, role: string) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(role);
  await page.getByLabel("Password", { exact: true }).fill("review-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("appointment autocomplete and directory delete confirmation", async ({ page }) => {
  await login(page, "admin");
  await page.getByRole("button", { name: "Patient appointments", exact: true }).click();
  const input = page.getByRole("combobox", { name: "Find appointment patient", exact: true });
  await input.fill("Rev");
  const choice = page.getByRole("option").filter({ hasText: "Review Patient" }).filter({ has: page.locator("strong") });
  await expect(choice).toBeVisible();
  await input.press("ArrowDown");
  await input.press("Enter");
  await expect(page.getByRole("combobox", { name: "Patient", exact: true })).toHaveValue("PRP-REVIEW");
  await page.getByRole("button", { name: "Patient directory", exact: true }).click();
  await page.getByRole("combobox", { name: "Search patient directory" }).fill("Rev");
  await page.getByRole("option").filter({ has: page.locator("strong") }).first().click();
  await expect(page.getByRole("button", { name: "Edit patient details", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Delete patient", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Delete patient confirmation" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Permanently delete patient" })).toBeDisabled();
  await dialog.getByRole("textbox").fill("PRP-REVIEW");
  await expect(dialog.getByRole("button", { name: "Permanently delete patient" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toHaveCount(0);
});

test("doctor upcoming page and provider status render on desktop and phone", async ({ page }) => {
  await login(page, "doctor");
  await page.getByRole("button", { name: "Upcoming appointments", exact: true }).click();
  await expect(page.getByLabel("Appointment date", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Provider availability" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Test providers", exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Upcoming appointments", exact: true }).click();
  await expect(page.getByLabel("Appointment date", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
