import { expect, test } from "@playwright/test";

test("landing page renders and navigates to the new-analysis form", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "Orbital Earth Observation Platform",
    }),
  ).toBeVisible();

  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "New analysis" })
    .click();

  await expect(page).toHaveURL(/\/analyses\/new$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "New analysis" }),
  ).toBeVisible();
  // The form (or its loading/error state) must render without crashing.
  await expect(page.locator("main#main")).toBeVisible();
});
