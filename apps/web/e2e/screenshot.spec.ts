import { test } from "@playwright/test";

/**
 * Captures documentation screenshots into docs/images at the repository
 * root. Run with the web app (and ideally the API) up:
 *
 *   DEMO_ANALYSIS_ID=<uuid> pnpm test:e2e e2e/screenshot.spec.ts
 */

const OUT_DIR = "../../docs/images";

test.use({ viewport: { width: 1440, height: 900 } });

test("capture landing dashboard screenshot", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.screenshot({
    path: `${OUT_DIR}/screenshot-dashboard.png`,
    fullPage: false,
  });
});

test("capture analysis detail screenshot", async ({ page }) => {
  const demoAnalysisId = process.env.DEMO_ANALYSIS_ID;
  test.skip(!demoAnalysisId, "DEMO_ANALYSIS_ID is not set");

  await page.goto(`/analyses/${demoAnalysisId}`);
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.screenshot({
    path: `${OUT_DIR}/screenshot-analysis-detail.png`,
    fullPage: false,
  });
});
