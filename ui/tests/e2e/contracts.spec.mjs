// Real LiveSync bundles; simulated NS8 backend/event boundary, real pinned host CSS.
import { test, expect, configuration, status } from "./helpers.mjs";

async function settings(ns8, config = configuration) {
  const f = await ns8.open({ hash: "#/apps/livesync1?page=settings" });
  const c = await ns8.task("get-configuration");
  await ns8.complete("get-configuration", c.eventId, config);
  const domains = await ns8.task("list-user-domains");
  await ns8.complete("list-user-domains", domains.eventId, {
    domains: [
      { schema: "ad", name: "ad.example.org" },
      { schema: "ldap", name: "not-ad.example.org" },
    ],
  });
  return f;
}
async function navigate(page, target) {
  await page
    .locator("#module")
    .evaluate(
      (iframe, view) =>
        iframe.contentWindow.dispatchEvent(
          new CustomEvent("changeRoute", { detail: view }),
        ),
      target,
    );
}
async function listeners(page, eventId) {
  return page.evaluate(
    (id) => window.__taskListeners().filter((e) => e.endsWith(id)),
    eventId,
  );
}

for (const action of ["get-configuration", "list-user-domains"]) {
  test(`${action} completion drops all sibling listeners`, async ({
    ns8,
    page,
  }) => {
    await settings(ns8);
    const task = await ns8.task(action);
    expect(await listeners(page, task.eventId)).toEqual([]);
    expect(ns8.problems).toEqual([]);
  });
}

for (const outcome of ["completed", "aborted", "validation-failed"]) {
  test(`save ${outcome} is handled exactly once`, async ({ ns8, page }) => {
    const f = await settings(ns8);
    await f.getByRole("button", { name: "Save", exact: true }).click();
    const save = await ns8.task("configure-module");
    if (outcome === "completed") {
      await ns8.complete("configure-module", save.eventId, {});
      const refresh = await ns8.task("get-configuration", { nth: 1 });
      await ns8.complete("get-configuration", refresh.eventId, configuration);
    } else if (outcome === "aborted")
      await ns8.abort("configure-module", save.eventId);
    else {
      await ns8.validationFailed("configure-module", save.eventId, [
        { parameter: "host", error: "invalid_fqdn" },
      ]);
      await expect(f.locator(".bx--form-requirement")).toContainText("valid");
    }
    expect(await listeners(page, save.eventId)).toEqual([]);
    const before = ns8.requests.length;
    await ns8.complete("configure-module", save.eventId, {});
    await page.waitForTimeout(100);
    expect(ns8.requests).toHaveLength(before);
    expect(ns8.problems).toEqual([]);
  });
}

test("AD fields are required and focus the first invalid field without saving", async ({
  ns8,
}) => {
  const f = await settings(ns8, {
    ...configuration,
    ad_domain: "",
    ad_group: "",
  });
  await f.getByRole("button", { name: "Save", exact: true }).click();
  await expect(f.locator(".ns-combo-box input")).toBeFocused();
  expect(
    ns8.requests.filter((r) => r.payload.action === "configure-module"),
  ).toHaveLength(0);
  expect(ns8.problems).toEqual([]);
});

test("native toggle state roundtrips every configuration switch", async ({
  ns8,
}) => {
  const f = await settings(ns8);
  const switches = f.locator("input.bx--toggle-input");
  await expect(switches).toHaveCount(4);
  for (let i = 0; i < 4; i++) await expect(switches.nth(i)).toBeChecked();
  await switches.nth(0).uncheck({ force: true });
  await switches.nth(1).uncheck({ force: true });
  await switches.nth(3).uncheck({ force: true });
  await f.getByRole("button", { name: "Save", exact: true }).click();
  const save = await ns8.task("configure-module");
  expect(save.payload.data).toEqual({
    host: configuration.host,
    lets_encrypt: false,
    http2https: false,
    ad_enabled: true,
    ad_domain: configuration.ad_domain,
    ad_group: configuration.ad_group,
    ad_nested_groups: false,
  });
});

test("account credentials, locked accounts and destructive controls retain policy", async ({
  ns8,
}) => {
  const f = await settings(ns8);
  await expect(f.locator("#livesync-uri")).toHaveValue(configuration.url);
  await expect(f.locator("#account-username-alice")).toHaveValue("alice");
  await expect(f.locator("#account-password-alice")).toHaveAttribute(
    "type",
    "password",
  );
  await expect(f.locator("#account-database-alice")).toHaveValue("alice_db");
  await expect(f.locator("#account-password-bob")).not.toHaveValue("");
  const alice = f
    .locator(".account")
    .filter({ has: f.locator("#account-username-alice") });
  await expect(
    alice.getByRole("button", { name: "Delete", exact: true }),
  ).toHaveCount(0);
  const bob = f
    .locator(".account")
    .filter({ has: f.locator("#account-username-bob") });
  await expect(
    bob.getByRole("button", { name: "Reset database", exact: true }),
  ).toHaveCount(0);
  await expect(
    bob.getByRole("button", { name: "Delete", exact: true }),
  ).toBeVisible();
  expect(ns8.problems).toEqual([]);
});

test("add account modal validates, submits once, stays busy and refreshes credentials", async ({
  ns8,
}) => {
  const f = await settings(ns8);
  await f.getByRole("button", { name: "Add account", exact: true }).click();
  const dialog = f.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Create", exact: true }).click();
  expect(
    ns8.requests.filter((r) => r.payload.action === "add-account"),
  ).toHaveLength(0);
  await dialog.locator("#new-account-username").fill("dave");
  await dialog.locator("#new-account-database").fill("dave_db");
  await dialog.getByRole("button", { name: "Create", exact: true }).click();
  const task = await ns8.task("add-account");
  expect(task.payload.data).toEqual({ username: "dave", database: "dave_db" });
  await expect(dialog.getByRole("button", { name: /Create/ })).toBeDisabled();
  await dialog.press("Escape");
  await expect(dialog).toBeVisible();
  await ns8.complete("add-account", task.eventId, {});
  await ns8.task("get-configuration", { nth: 1 });
  await expect(dialog).toHaveCount(0);
  expect(ns8.problems).toEqual([]);
});

for (const deleteDatabase of [false, true]) {
  test(`remove manual account confirms delete_database=${deleteDatabase}`, async ({
    ns8,
  }) => {
    const f = await settings(ns8);
    const account = f
      .locator(".account")
      .filter({ has: f.locator("#account-username-carol") });
    await account.getByRole("button", { name: "Delete", exact: true }).click();
    const dialog = f.getByRole("dialog");
    if (deleteDatabase)
      await dialog.locator("#remove-account-database").check({ force: true });
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    const task = await ns8.task("remove-account");
    expect(task.payload.data).toEqual({
      username: "carol",
      delete_database: deleteDatabase,
    });
    await ns8.complete("remove-account", task.eventId, {});
    await ns8.task("get-configuration", { nth: 1 });
    expect(ns8.problems).toEqual([]);
  });
}

test("reset is scoped to the chosen account and cancellation does not submit", async ({
  ns8,
}) => {
  const f = await settings(ns8);
  const account = f
    .locator(".account")
    .filter({ has: f.locator("#account-username-alice") });
  await account
    .getByRole("button", { name: "Reset database", exact: true })
    .click();
  let dialog = f.getByRole("dialog");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(
    ns8.requests.filter((r) => r.payload.action === "reset-database"),
  ).toHaveLength(0);
  await account
    .getByRole("button", { name: "Reset database", exact: true })
    .click();
  dialog = f.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Reset database", exact: true })
    .click();
  const task = await ns8.task("reset-database");
  expect(task.payload.data).toEqual({ username: "alice" });
  await ns8.complete("reset-database", task.eventId, {});
  await expect(dialog).toHaveCount(0);
  expect(
    ns8.requests.filter((r) => r.payload.action === "configure-module"),
  ).toHaveLength(0);
  expect(ns8.problems).toEqual([]);
});

test("AD sync error refreshes saved error state without duplicate handling", async ({
  ns8,
}) => {
  const f = await settings(ns8);
  await f
    .getByRole("button", { name: "Sync with AD now", exact: true })
    .click();
  const task = await ns8.task("sync-accounts");
  await ns8.abort("sync-accounts", task.eventId);
  const refresh = await ns8.task("get-configuration", { nth: 1 });
  await ns8.complete("get-configuration", refresh.eventId, {
    ...configuration,
    ad_last_sync: { ok: false, error: "Fixture AD failure" },
  });
  await expect(f.getByText("Fixture AD failure")).toBeVisible();
  expect(ns8.problems).toEqual([]);
});

test("status displays CouchDB, images, volumes, logs, backups and instance identity", async ({
  ns8,
}) => {
  const f = await ns8.open();
  const name = await ns8.task("get-name");
  await ns8.complete("get-name", name.eventId, { name: "My Notes" });
  const st = await ns8.task("get-status");
  await ns8.complete("get-status", st.eventId, status);
  const repos = await ns8.task("list-backup-repositories");
  await ns8.complete("list-backup-repositories", repos.eventId, {
    repositories: [],
  });
  const backups = await ns8.task("list-backups");
  await ns8.complete("list-backups", backups.eventId, { backups: [] });
  await expect(f.getByText("Node one", { exact: true })).toBeVisible();
  await expect(f.getByText("couchdb", { exact: true })).toBeVisible();
  await expect(f.getByText("couchdb:3.5", { exact: true })).toBeVisible();
  await expect(f.getByText("/data", { exact: true })).toBeVisible();
  await f
    .getByRole("button", { name: "Go to System logs", exact: true })
    .click();
  expect((await ns8.pushed()).at(-1)).toMatch(/system-logs/);
  await f.getByRole("button", { name: "Go to backup", exact: true }).click();
  expect((await ns8.pushed()).at(-1)).toBe("/backup");
  expect(ns8.problems).toEqual([]);
});

for (const view of ["status", "settings", "about"]) {
  test(`${view} HTTP failure releases all task listeners and shows error`, async ({
    ns8,
    page,
  }) => {
    ns8.setApi(() => ({ status: 403, body: "{}" }));
    const f = await ns8.open({ hash: `#/apps/livesync1?page=${view}` });
    const actions =
      view === "status"
        ? ["get-status", "list-backup-repositories"]
        : view === "settings"
          ? ["get-configuration", "list-user-domains"]
          : ["list-installed-modules"];
    for (const action of actions) {
      const task = await ns8.task(action);
      await expect.poll(() => listeners(page, task.eventId)).toEqual([]);
    }
    await expect(f.locator(".bx--inline-notification").first()).toBeVisible();
    expect(ns8.problems).toEqual([]);
  });
}

test("About lazy route retains all metadata and installed module version", async ({
  ns8,
  page,
}) => {
  const f = await ns8.open({ hash: "#/apps/livesync1?page=about" });
  const task = await ns8.task("list-installed-modules");
  await ns8.complete("list-installed-modules", task.eventId, {
    modules: [{ id: "livesync1", version: "0.4.0" }],
  });
  await expect(f.getByText("0.4.0", { exact: true })).toBeVisible();
  await expect(f.locator("img[alt*=logo]")).toBeVisible();
  await expect(f.locator("a[href*=github]").first()).toBeVisible();
  expect(await listeners(page, task.eventId)).toEqual([]);
  expect(ns8.problems).toEqual([]);
});

for (const view of ["settings", "about"]) {
  test(`leaving ${view} discards delayed task completions`, async ({
    ns8,
    page,
  }) => {
    await ns8.open({ hash: `#/apps/livesync1?page=${view}` });
    const action =
      view === "settings" ? "get-configuration" : "list-installed-modules";
    const task = await ns8.task(action);
    await navigate(page, "status");
    await ns8.task("get-status");
    expect(await listeners(page, task.eventId)).toEqual([]);
    await ns8.complete(action, task.eventId, {});
    expect(ns8.problems).toEqual([]);
  });
}
