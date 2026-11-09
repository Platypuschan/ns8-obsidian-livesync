import { test, expect } from "./helpers.mjs";
const backupCases = [
  { name: "success then pending", values: [true, null], kind: "warning" },
  { name: "pending then success", values: [null, true], kind: "warning" },
  { name: "all successful", values: [true, true], kind: "success" },
  { name: "all pending", values: [null, null], kind: "warning" },
  ...[
    [true, null, false],
    [true, false, null],
    [null, true, false],
    [null, false, true],
    [false, true, null],
    [false, null, true],
  ].map((values, index) => ({
    name: `failure precedence permutation ${index + 1}`,
    values,
    kind: "error",
  })),
  {
    name: "success then absent status",
    values: [true, undefined],
    kind: "warning",
  },
  {
    name: "absent status then success",
    values: [undefined, true],
    kind: "warning",
  },
  {
    name: "success then missing success field",
    values: [true, {}],
    kind: "warning",
  },
  {
    name: "missing success field then success",
    values: [{}, true],
    kind: "warning",
  },
  {
    name: "failure then absent status",
    values: [false, undefined],
    kind: "error",
  },
  {
    name: "absent status then failure",
    values: [undefined, false],
    kind: "error",
  },
  { name: "single missing success field", values: [{}], kind: "warning" },
  { name: "single absent status", values: [undefined], kind: "warning" },
  { name: "no backups", values: [], kind: "none" },
];

for (const { name, values, kind } of backupCases) {
  test(`Backup summary: ${name}`, async ({ ns8 }) => {
    const frame = await ns8.open();
    const repository = await ns8.task("list-backup-repositories");
    await ns8.complete("list-backup-repositories", repository.eventId, {
      repositories: [],
    });
    const task = await ns8.task("list-backups");
    await ns8.complete("list-backups", task.eventId, {
      backups: values.map((success, index) => ({
        id: `backup-${index}`,
        name: `backup-${index}`,
        enabled: true,
        instances: [
          {
            module_id: "livesync1",
            ...(success === undefined
              ? {}
              : {
                  status:
                    typeof success === "object" && success !== null
                      ? success
                      : { success },
                }),
          },
        ],
      })),
    });
    const card = frame.locator(".ns-backup-card");
    if (kind === "none")
      await expect(
        card.getByText("No backup configured", { exact: true }),
      ).toBeVisible();
    else await expect(card.locator(`.status > .status-${kind}`)).toBeVisible();
    if (kind !== "success")
      await expect(card.locator(".status-success")).toHaveCount(0);
    expect(ns8.problems).toEqual([]);
  });
}
