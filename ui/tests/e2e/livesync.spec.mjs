import { test, expect, configuration } from "./helpers.mjs";

test("navigation discards delayed repository completion", async ({
  page,
  ns8,
}) => {
  await ns8.open();
  const repository = await ns8.task("list-backup-repositories");
  await page
    .locator("#module")
    .evaluate((iframe) =>
      iframe.contentWindow.dispatchEvent(
        new CustomEvent("changeRoute", { detail: "about" }),
      ),
    );
  await ns8.task("list-installed-modules");
  const before = ns8.requests.length;
  await ns8.complete("list-backup-repositories", repository.eventId, {
    repositories: [],
  });
  await page.waitForTimeout(150);
  expect(ns8.requests).toHaveLength(before);
  expect(ns8.problems).toEqual([]);
});

test("settings preserves CouchDB and AD configuration", async ({ ns8 }) => {
  const f = await ns8.open({ hash: "#/apps/livesync1?page=settings" });
  const task = await ns8.task("get-configuration");
  await ns8.complete("get-configuration", task.eventId, configuration);
  const domains = await ns8.task("list-user-domains");
  await ns8.complete("list-user-domains", domains.eventId, {
    domains: [{ schema: "ad", name: "ad.example.org" }],
  });
  await expect(f.locator("#ad-group")).toHaveValue("obsidian-users");
  await expect(f.locator("#account-password-alice")).toHaveValue(
    "fixture-password",
  );
  await f.getByRole("button", { name: "Save", exact: true }).click();
  const save = await ns8.task("configure-module");
  expect(save.payload.data).toEqual({
    host: "sync.example.org",
    lets_encrypt: true,
    http2https: true,
    ad_enabled: true,
    ad_domain: "ad.example.org",
    ad_group: "obsidian-users",
    ad_nested_groups: true,
  });
  expect(save.headers.authorization).toBe("Bearer fixture-token");
  expect(ns8.problems).toEqual([]);
});
