import { expect, test } from "@playwright/test";
import path from "node:path";
import { login } from "./helpers";

// Captures genuine screenshots of the running application for the README / portfolio.
// Run with:  npm run screenshots   (stack must be up and seeded with the demo flags)
const OUT = path.resolve(__dirname, "../../portfolio/screenshots");

test.use({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });

test("capture portfolio screenshots", async ({ page, browser }) => {
  await login(page);
  await expect(page.getByTestId("stat-total-flags")).not.toHaveText("");
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(OUT, "01-overview.png") });

  await page.goto("/flags");
  await expect(page.getByTestId("flag-row-new-dashboard")).toBeVisible();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, "02-feature-flags.png") });

  // Playground: a real 50% development rollout with included/excluded users, evaluated by the backend
  await page.goto("/playground?flag=new-dashboard&env=development");
  await page.getByRole("button", { name: "Bob", exact: true }).click();
  await expect(page.getByTestId("result-enabled")).toBeVisible();
  await expect(page.getByTestId("cohort").getByText("on").first()).toBeVisible();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, "03-evaluation-playground.png") });

  await page.goto("/flags/new-dashboard");
  await expect(page.getByTestId("flag-key")).toBeVisible();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(OUT, "04-flag-editor.png") });

  const demo = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })).newPage();
  await demo.goto("/demo");
  await demo.getByLabel("Signed in user").selectOption("alice");
  await expect(demo.getByTestId("new-dashboard")).toBeVisible();
  await demo.waitForTimeout(400);
  await demo.screenshot({ path: path.join(OUT, "05-demo-app.png") });
  await demo.context().close();
});
