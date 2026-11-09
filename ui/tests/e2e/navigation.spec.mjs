import { test, expect, configuration } from "./helpers.mjs";

for (const [locale, title, save] of [
  ["de-DE", "Einstellungen", "Speichern"],
  ["fr-FR", "Settings", "Save"],
]) {
  test.describe(`language ${locale}`, () => {
    test.use({ locale });
    test(`renders translated or fallback settings without startup warnings`, async ({
      ns8,
      page,
    }) => {
      const warnings = [];
      page.on("console", (m) => {
        if (m.type() === "warning") warnings.push(m.text());
      });
      const f = await ns8.open({ hash: "#/apps/livesync1?page=settings" });
      const task = await ns8.task("get-configuration");
      await ns8.complete("get-configuration", task.eventId, configuration);
      await expect(
        f.getByRole("heading", { name: title, exact: true }),
      ).toBeVisible();
      await expect(
        f.getByRole("button", { name: save, exact: true }),
      ).toBeVisible();
      expect(warnings).toEqual([]);
      expect(ns8.problems).toEqual([]);
    });
  });
}

test("desktop menu delegates navigation to host and highlights host URL changes", async ({
  ns8,
  page,
}) => {
  const f = await ns8.open();
  await f
    .locator("#app-side-nav")
    .getByText("Settings", { exact: true })
    .click();
  expect((await ns8.pushed()).at(-1)).toBe("/apps/livesync1?page=settings");
  await page.evaluate(() => {
    location.hash = "#/apps/livesync1?page=settings";
  });
  await ns8.task("get-configuration");
  await expect(
    f.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  await expect(f.locator("#app-side-nav a.current-page")).toContainText(
    "Settings",
  );
  await page.evaluate(() => {
    location.hash = "#/apps/livesync1?page=about";
  });
  await ns8.task("list-installed-modules");
  await expect(
    f.getByRole("heading", { name: "About", exact: true }),
  ).toBeVisible();
  expect(ns8.problems).toEqual([]);
});

test("mobile menu opens from the host event once and routes through the host", async ({
  ns8,
  page,
}) => {
  await page.setViewportSize({ width: 600, height: 900 });
  const f = await ns8.open();
  await ns8.task("get-status");
  await page
    .locator("#module")
    .evaluate((iframe) =>
      iframe.contentWindow.dispatchEvent(
        new CustomEvent("toggleMobileSideMenu"),
      ),
    );
  await expect(f.locator(".mobile-side-menu")).toBeVisible();
  await f
    .locator(".mobile-side-menu")
    .getByText("About", { exact: true })
    .click();
  expect((await ns8.pushed()).at(-1)).toBe("/apps/livesync1?page=about");
  await expect(f.locator(".mobile-side-menu")).toHaveCount(0);
  expect(ns8.problems).toEqual([]);
});

test("Vue3 mount has exactly one app root and does not inherit loader layout", async ({
  ns8,
}) => {
  const f = await ns8.open();
  await ns8.task("get-status");
  await expect(f.locator("#ns8-app")).toHaveCount(1);
  await expect(
    f.getByRole("heading", { name: "Status", exact: true }),
  ).toBeVisible();
  expect(ns8.problems).toEqual([]);
});
