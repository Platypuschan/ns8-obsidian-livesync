import { test, expect, configuration } from "./helpers.mjs";

test("native credential visibility does not submit unsaved configuration", async ({
  ns8,
}) => {
  const f = await ns8.open({ hash: "#/apps/livesync1?page=settings" });
  const task = await ns8.task("get-configuration");
  await ns8.complete("get-configuration", task.eventId, configuration);
  await f.locator("form input[type=text]").first().fill("unsaved.example.org");
  for (const username of ["alice", "carol"]) {
    const input = f.locator(`#account-password-${username}`);
    const reveal = input.locator("..").getByRole("button");
    await expect(reveal).toHaveAttribute("type", "button");
    await reveal.click();
    await expect(input).toHaveAttribute("type", "text");
    await expect(input).toHaveValue(
      username === "alice" ? "fixture-password" : "manual-password",
    );
    await reveal.click();
    await expect(input).toHaveAttribute("type", "password");
  }
  expect(
    ns8.requests.filter((r) => r.payload.action === "configure-module"),
  ).toHaveLength(0);
  await expect(f.locator("form input[type=text]").first()).toHaveValue(
    "unsaved.example.org",
  );
  expect(ns8.problems).toEqual([]);
});
