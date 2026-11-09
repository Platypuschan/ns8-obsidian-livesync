import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const pkg = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url)),
);
test("coordinated Vue3 stack has no Vue2 bridge or compiler", () => {
  assert.match(pkg.dependencies.vue, /3\./);
  assert.match(pkg.dependencies["@carbon/vue"], /3\./);
  assert.equal(pkg.dependencies["@nethserver/ns8-ui-lib"], undefined);
  assert.equal(pkg.devDependencies["@vitejs/plugin-vue2"], undefined);
});
