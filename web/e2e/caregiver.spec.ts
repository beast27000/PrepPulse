import { expect, test } from "@playwright/test";

test.skip(
  process.env.PREPPULSE_CARE_FIXTURE !== "1",
  "Run against the in-memory care_browser_app fixture only.",
);
async function login(page: import("@playwright/test").Page, role: string) {
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(role);
  await page
    .getByLabel("Password", { exact: true })
    .fill("review-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("doctor checklist, signed plan, caregiver ticks, records and charts", async ({
  page,
  browser,
}, info) => {
  await login(page, "doctor");
  await expect(
    page.getByRole("button", { name: "Guidance library", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "− PrepPulse assistant", exact: true }),
  ).toBeVisible();
  const assistant = page.getByRole("button", {
    name: "− PrepPulse assistant",
    exact: true,
  });
  const sourceHeading = page.getByRole("button", {
    name: "− Source Proof",
    exact: true,
  });
  expect((await assistant.boundingBox())!.y).toBeLessThan(
    (await sourceHeading.boundingBox())!.y,
  );
  await page.screenshot({
    path: info.outputPath("patient-panels.png"),
    fullPage: false,
  });
  await assistant.click();
  await expect(
    page.getByRole("button", { name: "+ PrepPulse assistant", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Collapse right panels", exact: true })
    .click();
  await expect(page.locator(".workspace-grid")).toHaveClass(/rail-collapsed/);
  await page
    .getByRole("button", { name: "Show assistant / care panels", exact: true })
    .click();
  await page
    .getByRole("button", { name: "+ PrepPulse assistant", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Open full chat workspace", exact: true })
    .click();
  await page.getByLabel("Message PrepPulse").fill("Chart HbA1c");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".conversation-chart")).toBeVisible();
  await page.locator(".inline-citation").first().click();
  await expect(
    page.locator(".conversation-source .proof-highlight"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Back to Patients", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Start visit", exact: true })
    .first()
    .click();
  await expect(
    page.getByLabel("Checklist item 1", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Checklist item 1", { exact: true })
    .fill("Bring the updated home log");
  await page
    .getByRole("button", { name: "Care pathways", exact: true })
    .click();
  await expect(
    page.getByLabel("Checklist item 1", { exact: true }),
  ).toHaveValue("Bring the updated home log");
  await page
    .getByRole("button", { name: "+ Add medication / treatment", exact: true })
    .click();
  await page
    .getByLabel("Medication name 1", { exact: true })
    .fill("Test medicine");
  await page
    .getByLabel("Medication dose 1", { exact: true })
    .fill("One tablet");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByText("Unsaved changes", { exact: false })).toHaveCount(
    0,
  );
  await page.screenshot({
    path: info.outputPath("doctor-care-plan.png"),
    fullPage: false,
  });
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Sign off and end session", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Patient records", exact: true }),
  ).toBeVisible();

  const context = await browser.newContext();
  const carePage = await context.newPage();
  await login(carePage, "caregiver");
  await expect(
    carePage.getByRole("button", { name: "My care plans", exact: true }),
  ).toBeVisible();
  await expect(
    carePage.getByRole("button", { name: "Records", exact: true }),
  ).toHaveCount(0);
  await carePage.getByRole("checkbox").first().check();
  await carePage
    .getByLabel("Caregiver note for doctor")
    .fill("The home log is ready for review.");
  await carePage
    .getByRole("button", { name: "Send note", exact: true })
    .click();
  await expect(
    carePage.getByText("The home log is ready for review.", { exact: true }),
  ).toBeVisible();
  await carePage.reload();
  await expect(carePage.getByRole("checkbox").first()).toBeChecked();
  await carePage.screenshot({
    path: info.outputPath("caregiver-follow-up.png"),
    fullPage: false,
  });
  await carePage.getByLabel("Care pathway language").selectOption("hi");
  const download = carePage.waitForEvent("download");
  await carePage
    .getByRole("button", { name: "Download pathway · हिन्दी", exact: true })
    .click();
  expect((await download).suggestedFilename()).toContain("-hi.pdf");
  await page
    .getByText("Previous caregiver pathways and follow-up", { exact: true })
    .click();
  await expect(
    page.getByText("The home log is ready for review.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Browse patient records", exact: true })
    .click();
  await expect(page.locator(".record-file-list button")).toHaveCount(2);
  await context.close();
});

test("admin unified intake, demographics, caregiver registration and history filters", async ({
  page,
}, info) => {
  await login(page, "admin");
  await expect(
    page.getByRole("heading", {
      name: "Patient details and records",
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Upload patient folder", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Patient full name").fill("Browser Registered Patient");
  await page.getByLabel("Patient age", { exact: true }).fill("47");
  await page
    .getByRole("button", { name: "Register patient", exact: true })
    .click();
  await expect(
    page.getByText("Saved patient: Browser Registered Patient", {
      exact: false,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("unified-intake.png"),
    fullPage: false,
  });
  await page.getByRole("button", { name: "Caregivers", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Register caregiver", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Patient appointments", exact: true })
    .click();
  await page.getByLabel("Search appointment history").fill("Review Patient");
  await expect(page.locator(".appointment-history")).toContainText(
    "Review Patient",
  );
  await page
    .getByRole("button", { name: "Expand appointments", exact: true })
    .click();
  await expect(page.locator(".history-expanded")).toBeVisible();
  await page
    .getByRole("button", { name: "Close expanded view", exact: true })
    .click();
});
