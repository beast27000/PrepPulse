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
    page.getByRole("button", { name: "Previous patients", exact: true }),
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
  await page
    .getByLabel("Message PrepPulse")
    .fill("Can you generate me the charts for this patient?");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".conversation-chart")).toBeVisible();
  await page
    .getByLabel("Message PrepPulse")
    .fill("Plot it for the last two years");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Session charts · 2", exact: true }),
  ).toBeVisible();
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
  ).toHaveCount(0);
  await expect(page.getByLabel("Add checklist instruction")).toHaveCount(0);
  await page
    .getByRole("checkbox", { name: "Visit checklist 1", exact: true })
    .check();
  await expect(
    page.getByRole("checkbox", { name: "Card checklist 1", exact: true }),
  ).toBeChecked();
  await page.getByLabel("Care pathway language").selectOption("hi");
  await expect(page.locator(".care-card-preview")).toContainText(
    "घर का रिकॉर्ड लाएँ",
  );
  await page.getByLabel("Care pathway language").selectOption("en");
  await page.screenshot({
    path: info.outputPath("simple-patient-checklist.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Edit pathway", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("checkbox", { name: "Pathway checklist 1", exact: true }),
  ).toBeChecked();
  await expect(
    page.getByLabel("Checklist item 1", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Edit checklist item 1", exact: true })
    .click();
  await page
    .getByLabel("Checklist item 1", { exact: true })
    .fill("Bring the updated home log");
  await page.getByRole("button", { name: "Done editing", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Pathway checklist 1", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit checklist item 1", exact: true })
    .click();
  await page.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Card checklist 1", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator(".care-card-preview")).toContainText(
    "No checklist instructions yet",
  );
  await page
    .getByRole("button", { name: "Edit pathway", exact: true })
    .last()
    .click();
  await page
    .getByLabel("Add checklist instruction")
    .fill("Bring the updated home log");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page
    .getByLabel("Add checklist instruction")
    .fill("Bring the current prescription");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await expect(page.locator(".care-card-preview")).toContainText(
    "Bring the current prescription",
  );
  await expect(page.getByLabel("Add checklist instruction")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Care pathways", exact: true })
    .click();
  await expect(page.locator(".care-item-view")).toContainText([
    "Bring the updated home log",
    "Bring the current prescription",
  ]);
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
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Card checklist 1", exact: true }),
  ).toBeChecked({ timeout: 15000 });
  await expect(
    page.getByRole("button", {
      name: "Download pathway · English",
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("signed-patient-checklist.png"),
    fullPage: false,
  });
  await context.close();
});

test("admin accounts, caregiver assignment, two-row appointments and editable directory", async ({
  page,
}, info) => {
  await login(page, "admin");
  await page.getByRole("button", { name: "Accounts", exact: true }).click();
  await page.getByLabel("Full name", { exact: true }).fill("Review Nurse");
  await page.getByLabel("Username", { exact: true }).fill("nurse");
  await page
    .getByLabel("Temporary password, minimum 12 characters", { exact: true })
    .fill("review-test-password");
  await page
    .getByRole("combobox", { name: "Role", exact: true })
    .selectOption("caregiver");
  await page
    .getByRole("combobox", { name: "Caregiver type", exact: true })
    .selectOption("professional");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Created Review Nurse");
  await page.getByLabel("Search accounts", { exact: true }).fill("nurse");
  await expect(page.locator(".admin-scroll-list code")).toContainText("CGV-");
  await page.getByRole("button", { name: "Caregivers", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Register caregiver", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "Caregiver type", exact: true })
    .selectOption("professional");
  const nurseOption = page
    .getByRole("combobox", {
      name: "Registered professional caregiver",
      exact: true,
    })
    .locator("option")
    .filter({ hasText: "Review Nurse" });
  await page
    .getByRole("combobox", {
      name: "Registered professional caregiver",
      exact: true,
    })
    .selectOption((await nurseOption.getAttribute("value"))!);
  await page
    .getByRole("combobox", { name: "Patient", exact: true })
    .selectOption("PRP-REVIEW");
  await page
    .getByRole("button", { name: "Assign patient", exact: true })
    .click();
  await expect(
    page.getByText("Patient assignment saved", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Availability for nurse", { exact: true })
    .selectOption("active");
  await expect(
    page.getByLabel("Availability for nurse", { exact: true }),
  ).toHaveValue("active");
  await page.screenshot({
    path: info.outputPath("caregiver-administration.png"),
    fullPage: false,
  });

  await page
    .getByRole("button", { name: "Patient appointments", exact: true })
    .click();
  const todayPanel = page
    .getByRole("heading", { name: "Today’s appointments", exact: true })
    .locator("..");
  await expect(todayPanel.locator(".appointment-history")).toHaveCount(0);
  await page.getByLabel("Search appointment history").fill("Review Patient");
  await expect(page.locator(".appointment-history")).toContainText(
    "Review Patient",
  );
  await page.screenshot({
    path: info.outputPath("appointment-grid.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Expand appointments", exact: true })
    .click();
  await expect(page.locator(".history-full-page")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "New appointment", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Back to workspace", exact: true })
    .click();

  await page
    .getByRole("button", { name: "Patient directory", exact: true })
    .click();
  await page
    .getByRole("button", {
      name: "View admin details for Review Patient",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", { name: "Edit patient details", exact: true })
    .click();
  await page.getByLabel("Recorded age", { exact: true }).fill("46");
  await page
    .getByRole("button", { name: "Save patient details", exact: true })
    .click();
  await expect(
    page.getByText("Patient details saved", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Directory records by visit")).toHaveValue(
    "all",
  );
  const editorButton = page
    .locator(".directory-overview .record-row")
    .filter({ hasText: "review_lab.pdf" })
    .getByRole("button", { name: "Edit record", exact: true });
  await editorButton.click();
  await page
    .getByLabel("Display title", { exact: true })
    .fill("Reviewed laboratory record");
  await page
    .getByRole("button", { name: "Save record metadata", exact: true })
    .click();
  await expect(
    page.getByText("Reviewed laboratory record", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Add record", exact: true }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "admin-follow-up.pdf",
    mimeType: "application/pdf",
    buffer: (await import("node:fs")).readFileSync(
      "../.tmp/care-browser/review_lab.pdf",
    ),
  });
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Upload record", exact: true })
    .last()
    .click();
  await expect(
    page.getByText("admin-follow-up.pdf", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await page.screenshot({
    path: info.outputPath("editable-patient-directory.png"),
    fullPage: false,
  });
});

test("dictation shows listening and transcribing before reviewed text is submitted", async ({
  page,
}, info) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: {
        getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }),
      },
      configurable: true,
    });
    Object.defineProperty(window, "MediaRecorder", {
      value: class {
        mimeType = "audio/webm";
        ondataavailable?: (event: { data: Blob }) => void;
        onstop?: () => void;
        start() {}
        stop() {
          this.ondataavailable?.({ data: new Blob(["synthetic audio"]) });
          this.onstop?.();
        }
      },
      configurable: true,
    });
  });
  let transcription: import("@playwright/test").Route | undefined;
  await page.route("**/api/voice/transcribe", (route) => {
    transcription = route;
  });
  await login(page, "doctor");
  await page
    .getByRole("button", { name: "Open full chat workspace", exact: true })
    .click();
  await page
    .getByRole("button", { name: "New chat session", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Dictate request", exact: true })
    .click();
  await expect(page.locator(".dictation-status")).toContainText("Listening");
  await expect(page.locator(".dictation-status .process-dots i")).toHaveCount(
    3,
  );
  await page.screenshot({
    path: info.outputPath("dictation-listening.png"),
    fullPage: false,
  });
  await page
    .getByRole("button", { name: "Stop dictation", exact: true })
    .click();
  await expect(page.locator(".dictation-status")).toContainText("Transcribing");
  await expect.poll(() => !!transcription).toBe(true);
  await transcription!.fulfill({
    json: { transcript: "Plot HbA1c for two years" },
  });
  await expect(page.getByLabel("Message PrepPulse")).toHaveValue(
    "Plot HbA1c for two years",
  );
  await expect(page.locator(".dictation-status")).toHaveCount(0);
  await expect(page.locator(".conversation-message.user")).toHaveCount(0);
});
