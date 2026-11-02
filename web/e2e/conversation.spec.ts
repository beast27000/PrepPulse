import { expect, test } from "@playwright/test";

test.skip(
  !process.env.PREPPULSE_E2E_USER || !process.env.PREPPULSE_E2E_PASSWORD,
  "Use an isolated validation workspace with a test doctor account.",
);
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.PREPPULSE_E2E_USER!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.PREPPULSE_E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Analyze records", exact: true }),
  ).toBeVisible();
});

test("record history and requested chart, citation, session layout", async ({
  page,
}, testInfo) => {
  await expect(page.locator(".history-record")).toHaveCount(10);
  await expect(page.locator(".consultation-heading")).not.toContainText(
    "/ None",
  );
  await expect
    .poll(() =>
      page
        .locator(".proof-preview img")
        .evaluate((image: HTMLImageElement) => image.naturalWidth),
    )
    .toBeGreaterThan(0);
  await page.screenshot({
    path: testInfo.outputPath("patient-history.png"),
    fullPage: false,
  });
  await page
    .getByRole("button", { name: "Collapse navigation", exact: true })
    .click();
  await expect(page.locator(".app-shell")).toHaveClass(/sidebar-collapsed/);
  await page
    .getByRole("button", { name: "Open full chat workspace", exact: true })
    .click();
  await expect(
    page.locator(".patient-conversation.is-workspace"),
  ).toBeVisible();
  await expect(page.locator(".conversation-source")).toHaveCount(0);
  await expect(page.locator(".conversation-chart")).toHaveCount(0);
  await page
    .getByRole("button", { name: "New chat session", exact: true })
    .click();
  await page
    .getByLabel("Message PrepPulse")
    .fill(
      "Show this patient's diabetes journey over the last 10 years as a chart",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".process-bubble")).toBeVisible();
  await expect(page.locator(".conversation-chart")).toBeVisible({
    timeout: 150_000,
  });
  await expect(page.locator(".artifact-series")).toHaveCount(2);
  const chartBounds = await page.locator(".conversation-chart").boundingBox();
  const threadBounds = await page.locator(".conversation-thread").boundingBox();
  expect(chartBounds!.y).toBeLessThan(threadBounds!.y);
  const composerBounds = await page
    .locator(".conversation-composer")
    .boundingBox();
  expect(composerBounds!.y + composerBounds!.height).toBeLessThanOrEqual(1000);
  await expect(page.locator(".reply-markdown table").first()).toBeVisible();
  await expect(page.locator(".reply-markdown")).not.toContainText(
    "cannot create a visual chart",
  );
  await expect(page.locator(".reply-markdown")).not.toContainText("**");
  await expect(page.locator(".inline-citation").first()).toBeVisible();
  await page.locator(".inline-citation").first().click();
  await expect(page.locator(".conversation-source")).toBeVisible();
  await expect(
    page.locator(".conversation-source .proof-highlight"),
  ).toBeVisible();
  const dimensions = await page
    .locator(".conversation-source .proof-highlight")
    .evaluate((el) => ({
      height: el.getBoundingClientRect().height,
      parent: el.parentElement!.getBoundingClientRect().height,
    }));
  expect(dimensions.height / dimensions.parent).toBeLessThan(0.15);
  await expect
    .poll(async () => {
      const highlight = await page
        .locator(".conversation-source .proof-highlight")
        .boundingBox();
      const viewport = await page.locator(".source-dock-scroll").boundingBox();
      return (
        !!highlight &&
        !!viewport &&
        highlight.y >= viewport.y &&
        highlight.y + highlight.height <= viewport.y + viewport.height
      );
    })
    .toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("chart-and-source.png"),
    fullPage: false,
  });
  await page
    .getByRole("button", { name: "Close source proof", exact: true })
    .click();
  await expect(page.locator(".conversation-source")).toHaveCount(0);
  await page
    .locator('.recharts-line-dots circle[role="button"]')
    .first()
    .click();
  await expect(page.locator(".conversation-source")).toBeVisible();
  await page
    .getByRole("button", { name: "Open full record workspace", exact: true })
    .click();
  await expect(page.locator(".record-workspace-grid")).toBeVisible();
  await expect(page.locator(".record-file-list button")).toHaveCount(15);
  await page
    .getByRole("button", { name: "Back to workspace", exact: true })
    .click();
  await expect(page.locator(".conversation-source")).toHaveCount(0);
  await page.locator(".message-artifacts button").first().click();
  await page
    .getByRole("button", { name: "Collapse chart", exact: true })
    .click();
  await expect(page.locator(".conversation-chart-scroll")).toHaveCount(0);
  await page.getByRole("button", { name: "Close chart", exact: true }).click();
  await expect(page.locator(".conversation-chart")).toHaveCount(0);
  await page.locator(".message-artifacts button").first().click();
  await expect(page.locator(".conversation-chart")).toBeVisible();
  await page
    .getByLabel("Message PrepPulse")
    .fill("Create a new eGFR trend chart");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Session charts · 2", exact: true }),
  ).toBeVisible({ timeout: 150_000 });
  await page.reload();
  await page
    .getByRole("button", { name: "Open full chat workspace", exact: true })
    .click();
  await expect(page.locator(".conversation-message.assistant")).toHaveCount(2);
  await expect(
    page.getByRole("button", { name: "Session charts · 2", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".conversation-source")).toHaveCount(0);
  const previousSession = await page
    .getByLabel("Chat session", { exact: true })
    .inputValue();
  await page
    .getByRole("button", { name: "New chat session", exact: true })
    .click();
  await expect(page.locator(".conversation-empty")).toBeVisible();
  await page
    .getByLabel("Chat session", { exact: true })
    .selectOption(previousSession);
  await expect(page.locator(".conversation-message.assistant")).toHaveCount(2);
  await page.setViewportSize({ width: 1000, height: 850 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
});

test("readable clinical synthesis uses formatted citations", async ({
  page,
}, testInfo) => {
  await page
    .getByRole("button", { name: "Open full chat workspace", exact: true })
    .click();
  await page
    .getByRole("button", { name: "New chat session", exact: true })
    .click();
  await page
    .getByLabel("Message PrepPulse")
    .fill(
      "Summarize the documented cardiac admission and procedure. Use short sections and cite each key fact.",
    );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".conversation-message.assistant")).toHaveCount(1, {
    timeout: 150_000,
  });
  await expect(page.locator(".reply-markdown p").first()).toBeVisible();
  expect(await page.locator(".inline-citation").count()).toBeGreaterThan(0);
  await expect(page.locator(".reply-markdown")).not.toContainText("###");
  await expect(page.locator(".conversation-source")).toHaveCount(0);
  await page.screenshot({
    path: testInfo.outputPath("formatted-clinical-response.png"),
    fullPage: false,
  });
});
