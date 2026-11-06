import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

test.skip(process.env.PREPPULSE_DEPLOYMENT_E2E !== "1", "Requires the private deployed pilot credentials.");

test("live cloud pages, sessions, charts and evidence", async ({ page }, info) => {
  const access = JSON.parse(readFileSync(resolve("../.tmp/azure_pilot/pilot_access.json"), "utf8"));
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500 && response.url().includes("/api/")) failures.push(`${response.status()} ${response.url()}`);
  });
  async function login(role: string) {
    await page.context().clearCookies();
    await page.goto("/");
    await page.getByLabel("Username", { exact: true }).fill(access[role].username);
    await page.getByLabel("Password", { exact: true }).fill(access[role].password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
  }
  await login("doctor");
  for (const name of ["Today", "Records", "Care pathways", "Settings", "Patients"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("main")).toBeVisible();
    await page.screenshot({ path: info.outputPath(`doctor-${name.replaceAll(" ", "-")}.png`), fullPage: false });
  }
  await page.getByRole("button", { name: "Open full chat workspace", exact: true }).click();
  await page.getByLabel("Message PrepPulse").fill("Plot HbA1c for the past 3 years.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".conversation-chart")).toBeVisible({ timeout: 120000 });
  await expect(page.locator(".inline-citation").first()).toBeVisible();
  await page.locator(".inline-citation").first().click();
  await expect(page.locator(".proof-highlight").first()).toBeVisible();
  await page.screenshot({ path: info.outputPath("live-chart-and-source.png"), fullPage: false });
  await login("admin");
  for (const name of ["New patient intake", "Patient appointments", "Patient directory", "Caregivers", "Accounts", "Settings"]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator("main")).toBeVisible();
    await page.screenshot({ path: info.outputPath(`admin-${name.replaceAll(" ", "-")}.png`), fullPage: false });
  }
  await expect(page.getByRole("heading", { name: "Provider availability" })).toBeVisible();
  await login("caregiver");
  await expect(page.getByRole("button", { name: "My care plans", exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath("caregiver-portal.png"), fullPage: false });
  expect(failures).toEqual([]);
});
