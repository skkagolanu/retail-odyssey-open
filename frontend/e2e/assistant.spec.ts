import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("real catalogue API: conversation, sourced cards, reload, isolation and complete clear", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Clear conversation" }),
  ).toBeEnabled();
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("A classic business outfit under £100");
  await page.getByRole("button", { name: "Find my look" }).click();
  await expect(page.locator(".product-card")).toHaveCount(2);
  await expect(page.getByLabel("Saved preferences")).toContainText("classic");
  await expect(page.getByLabel("Saved preferences")).toContainText("£100");
  await expect(
    page.getByRole("link", { name: "View source listing" }),
  ).toHaveCount(0);
  await expect(page.locator(".catalogue-notice")).toContainText(
    "Fictional pieces",
  );
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("cook a recipe in this outfit");
  await page.getByRole("button", { name: "Find my look" }).click();
  await expect(page.getByRole("log")).toContainText(
    "outside this assistant's scope",
  );
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto("/");
  await expect(
    otherPage.getByRole("button", { name: "Clear conversation" }),
  ).toBeEnabled();
  await expect(otherPage.getByLabel("Saved preferences")).not.toContainText(
    "classic",
  );
  await expect(otherPage.getByRole("log")).not.toContainText("cook a recipe");
  await other.close();
  await page.reload();
  await expect(page.getByRole("log")).toContainText("cook a recipe");
  await page.getByRole("button", { name: "Clear conversation" }).click();
  await expect(page.getByRole("log")).not.toContainText("cook a recipe");
  await expect(page.getByLabel("Saved preferences")).not.toContainText(
    "classic",
  );
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "What are you dressing for?" }),
  ).toBeVisible();
});

test("catalogue image limitation is explicit, no fake image generated", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Clear conversation" }),
  ).toBeEnabled();
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("visualize a casual outfit");
  await page.getByRole("button", { name: "Find my look" }).click();
  await expect(page.locator(".capability-notice")).toContainText(
    "not an AI-generated photo",
  );
  await expect(page.locator(".generated-image")).toHaveCount(0);
});

test("desktop and mobile accessibility, no horizontal overflow, keyboard focus", async ({
  page,
}) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 950 });
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: "Clear conversation" }),
    ).toBeEnabled();
    await page
      .getByRole("textbox", { name: "Your message" })
      .fill("casual minimalist outfit under £70");
    await page.getByRole("button", { name: "Find my look" }).click();
    await expect(page.locator(".product-card").first()).toBeVisible();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(result.violations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/catalogue-${width}.png`,
      fullPage: true,
    });
    await page.getByRole("textbox", { name: "Your message" }).focus();
    await expect(
      page.getByRole("textbox", { name: "Your message" }),
    ).toBeFocused();
  }
});

test("API failure preserves editable question and exposes retryable message", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Clear conversation" }),
  ).toBeEnabled();
  await page.route("**/api/chat", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Assistant is busy; try again shortly" },
    }),
  );
  await page
    .getByRole("textbox", { name: "Your message" })
    .fill("casual outfit");
  await page.getByRole("button", { name: "Find my look" }).click();
  await expect(page.getByRole("alert")).toContainText("try again");
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "casual outfit",
  );
});
