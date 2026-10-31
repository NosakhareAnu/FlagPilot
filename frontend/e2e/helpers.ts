import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Cookie, type Page } from "@playwright/test";

/** Reads the generated local credentials from the git-ignored root .env (never hard-coded). */
function loadEnv(): Record<string, string> {
  const vars: Record<string, string> = {};
  const file = path.resolve(__dirname, "../../.env");
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && m[1] && m[2] !== undefined) vars[m[1]] = m[2].trim();
  }
  return vars;
}

const env = loadEnv();
export const ADMIN_EMAIL = process.env.ADMIN_EMAIL ?? env.ADMIN_EMAIL ?? "admin@flagpilot.local";
export const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD ?? env.ADMIN_PASSWORD ?? "";

// The backend limits logins to 10/minute per client address. Signing in through the UI once and reusing that
// session cookie keeps the suite repeatable (back-to-back runs) without weakening the limit.
let cachedSession: Cookie[] | null = null;

export async function login(page: Page) {
  if (cachedSession) {
    await page.context().addCookies(cachedSession);
    await page.goto("/");
  } else {
    await page.goto("/login");
    await page.getByLabel("Email").fill(ADMIN_EMAIL);
    await page.getByLabel("Password").fill(ADMIN_PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
    cachedSession = (await page.context().cookies()).filter((c) => c.name === "fp_session");
  }
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await expect(page).toHaveURL(/\/login/);
  cachedSession = null; // the server-side session is gone; the next login() signs in again
}
