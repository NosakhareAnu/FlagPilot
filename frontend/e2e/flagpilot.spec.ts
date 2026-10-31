import { expect, test, type Page } from "@playwright/test";
import { login, logout } from "./helpers";

const FLAG = `e2e-rollout-${Date.now().toString(36)}`;
const FLAG_NAME = "E2E rollout flag";
const KEY_NAME = `e2e key ${Date.now().toString(36)}`; // unique per run so reruns on a used stack stay unambiguous

async function evaluate(page: Page, user: string) {
  await page.getByRole("textbox", { name: "User identifier" }).fill(user);
  await page.getByRole("button", { name: "Evaluate", exact: true }).click();
}

async function openPlayground(page: Page, env: "Development" | "Production" = "Development") {
  await page.goto(`/playground?flag=${FLAG}`);
  await expect(page.getByRole("heading", { name: "Evaluation playground" })).toBeVisible();
  await page.getByRole("radio", { name: env }).click();
}

test.describe.configure({ mode: "serial" });

test("protected routes redirect signed-out visitors to the login page", async ({ page }) => {
  for (const route of ["/", "/flags", "/flags/anything", "/playground", "/audit", "/api-keys"]) {
    await page.goto(route);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("protected API endpoints reject unauthenticated requests", async ({ request }) => {
  expect((await request.get("/api/v1/admin/flags")).status()).toBe(401);
  expect((await request.get("/api/v1/admin/stats")).status()).toBe(401);
});

test("login shows a helpful error for wrong credentials", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("admin@flagpilot.local");
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect email or password.")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("administrator can log in and sees live overview data", async ({ page }) => {
  await login(page);
  await expect(page.getByTestId("stat-total-flags")).not.toHaveText("");
  await expect(page.getByText("Recent configuration changes")).toBeVisible();
});

test("create a flag, configure rollout, evaluate in the playground, change it, observe the new result", async ({ page }) => {
  await login(page);

  // 1. create
  await page.goto("/flags");
  await page.getByRole("button", { name: /New flag/ }).first().click();
  await page.getByLabel("Name").fill(FLAG_NAME);
  await page.getByLabel("Key").fill(FLAG);
  await page.getByLabel("Description").fill("Created by the Playwright end-to-end test");
  await page.getByRole("button", { name: "Create flag" }).click();
  await expect(page).toHaveURL(new RegExp(`/flags/${FLAG}$`));
  await expect(page.getByTestId("flag-key")).toHaveText(FLAG);

  // duplicate keys are rejected with a clear message
  await page.goto("/flags");
  await page.getByRole("button", { name: /New flag/ }).first().click();
  await page.getByLabel("Name").fill("Duplicate");
  await page.getByLabel("Key").fill(FLAG);
  await page.getByRole("button", { name: "Create flag" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("already exists");
  await page.keyboard.press("Escape");

  // 2. configure: enabled in development at 0%
  await page.goto(`/flags/${FLAG}`);
  await page.getByRole("switch", { name: "Enabled in development" }).click();
  await page.getByRole("spinbutton", { name: "Rollout percentage" }).fill("0");
  await page.getByRole("button", { name: "Save development changes" }).click();
  await expect(page.getByText("Saved development configuration")).toBeVisible();

  // 3. playground: real backend evaluation, user is outside a 0% rollout
  await openPlayground(page);
  await evaluate(page, "carol");
  await expect(page.getByTestId("result-enabled")).toContainText("DISABLED");
  await expect(page.getByTestId("result-reason")).toHaveText("default_disabled");

  // 4. raise the rollout to 100% from the playground and re-evaluate
  await page.getByLabel("Playground rollout slider").fill("100");
  await page.getByRole("button", { name: /Apply & re-evaluate/ }).click();
  await expect(page.getByTestId("result-enabled")).toContainText("ENABLED");
  await expect(page.getByTestId("result-reason")).toHaveText("percentage_rollout");
  await expect(page.getByText("changed since last evaluation")).toBeVisible();

  // 5. exclude carol in the editor, re-evaluate in the playground
  await page.goto(`/flags/${FLAG}`);
  await page.getByRole("textbox", { name: "Excluded users" }).fill("carol");
  await page.getByRole("textbox", { name: "Excluded users" }).press("Enter");
  await page.getByRole("button", { name: "Save development changes" }).click();
  await expect(page.getByText("Saved development configuration")).toBeVisible();
  await openPlayground(page);
  await evaluate(page, "carol");
  await expect(page.getByTestId("result-reason")).toHaveText("user_excluded");
  await evaluate(page, "bob");
  await expect(page.getByTestId("result-reason")).toHaveText("percentage_rollout");

  // 6. emergency kill switch overrides everything
  await page.goto(`/flags/${FLAG}`);
  await page.getByRole("switch", { name: "Kill switch in development" }).click();
  await page.getByRole("button", { name: "Save development changes" }).click();
  await expect(page.getByText("Saved development configuration")).toBeVisible();
  await openPlayground(page);
  await evaluate(page, "bob");
  await expect(page.getByTestId("result-enabled")).toContainText("DISABLED");
  await expect(page.getByTestId("result-reason")).toHaveText("kill_switch");

  // 7. production configuration is untouched (independent environments)
  await openPlayground(page, "Production");
  await evaluate(page, "bob");
  await expect(page.getByTestId("result-reason")).toHaveText("flag_disabled");
});

test("audit history shows the real changes made above", async ({ page }) => {
  await login(page);
  await page.goto("/audit");
  await page.getByLabel("Filter by flag").selectOption(FLAG);
  const rows = page.getByTestId("audit-row");
  await expect(rows.first()).toBeVisible();
  const text = (await rows.allInnerTexts()).join("\n");
  expect(text).toContain("Flag created");
  expect(text).toContain("Rollout changed");
  expect(text).toContain("Targeting updated");
  expect(text).toContain("Kill switch activated");
  expect(text).toContain("Rollout 0% → 100%");
});

test("overview reflects the flag list and the flags page shows environments independently", async ({ page }) => {
  await login(page);
  await page.goto("/flags");
  const row = page.getByTestId(`flag-row-${FLAG}`);
  await expect(row).toBeVisible();
  await expect(row.getByTestId(`cell-${FLAG}-development`)).toContainText("Kill switch");
  await expect(row.getByTestId(`cell-${FLAG}-production`)).toContainText("Off");
  // quick toggle in the table works and reports success
  await row.getByRole("switch", { name: new RegExp(`Enable ${FLAG} in production`) }).click();
  await expect(page.getByText(/enabled in production/)).toBeVisible();
  await expect(row.getByTestId(`cell-${FLAG}-production`)).toContainText("On");
  await expect(row.getByTestId(`cell-${FLAG}-development`)).toContainText("Kill switch");
});

test("API keys: create shows the secret once, revoke disables it", async ({ page }) => {
  await login(page);
  await page.goto("/api-keys");
  await page.getByRole("button", { name: /New key/ }).click();
  await page.getByLabel("Name").fill(KEY_NAME);
  await page.getByRole("button", { name: "Create key" }).click();
  const secret = await page.getByRole("dialog").locator("code").innerText();
  expect(secret).toMatch(/^fpk_development_/);
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("api-key-row").filter({ hasText: KEY_NAME })).toHaveCount(1);
  expect(await page.content()).not.toContain(secret); // the secret is gone once dismissed
  const ok = await page.request.post("http://localhost:8000/api/v1/evaluate", {
    headers: { Authorization: `Bearer ${secret}` },
    data: { flag_key: FLAG, user_id: "bob" },
  });
  expect(ok.status()).toBe(200);
  await page.getByTestId("api-key-row").filter({ hasText: KEY_NAME }).getByRole("button", { name: "Revoke" }).click();
  await page.getByRole("button", { name: "Revoke key" }).click();
  await expect(page.getByText(`Revoked ${KEY_NAME}`)).toBeVisible();
  const denied = await page.request.post("http://localhost:8000/api/v1/evaluate", {
    headers: { Authorization: `Bearer ${secret}` },
    data: { flag_key: FLAG, user_id: "bob" },
  });
  expect(denied.status()).toBe(401);
});

test("demo app visibly changes when a flag changes in FlagPilot", async ({ page, browser }) => {
  // The demo is a separate "customer app" page that is public; flags are changed from an admin session.
  const demo = await (await browser.newContext()).newPage();
  await demo.goto("/demo");
  await demo.getByLabel("Signed in user").selectOption("alice");
  // seeded: new-dashboard is enabled for alice (included user) in development
  await expect(demo.getByTestId("new-dashboard")).toBeVisible();

  await login(page);
  await page.goto("/flags/new-dashboard");
  await page.getByRole("switch", { name: "Kill switch in development" }).click();
  await page.getByRole("button", { name: "Save development changes" }).click();
  await expect(page.getByText("Saved development configuration")).toBeVisible();

  // no reload on the demo page: polling picks the change up
  await expect(demo.getByTestId("legacy-dashboard")).toBeVisible({ timeout: 15_000 });
  await expect(demo.getByTestId("demo-evaluations")).toContainText("kill_switch");

  // restore
  await page.getByRole("switch", { name: "Kill switch in development" }).click();
  await page.getByRole("button", { name: "Save development changes" }).click();
  await expect(page.getByText("Saved development configuration")).toBeVisible();
  await expect(demo.getByTestId("new-dashboard")).toBeVisible({ timeout: 15_000 });
  await demo.context().close();
});

test("logout ends the session and protected routes are inaccessible afterwards", async ({ page }) => {
  await login(page);
  await logout(page);
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  await page.goto("/flags");
  await expect(page).toHaveURL(/\/login/);
  await page.goBack();
  await expect(page).toHaveURL(/\/login/);
});

test("cleanup: archive the e2e flag", async ({ page }) => {
  await login(page);
  await page.goto(`/flags/${FLAG}`);
  await page.getByRole("button", { name: "Archive", exact: true }).click();
  await page.getByRole("button", { name: "Archive flag" }).click();
  await expect(page.getByText("Flag archived")).toBeVisible();
});
