// Run inside the pinned official Renovate image; exercise native RE2 and engine APIs.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base = '/usr/local/renovate/dist/';
const { resolveConfigPresets } = await import(base + 'config/presets/index.js');
const { applyPackageRules } = await import(base + 'util/package-rules/index.js');
const { extractPackageFile } = await import(base + 'modules/manager/custom/regex/index.js');
const { bumpVersions } = await import(base + 'workers/repository/update/branch/bump-versions.js');
const { GlobalConfig } = await import(base + 'config/global.js');
const { setPlatformScmApi } = await import(base + 'modules/platform/scm.js');
const raw = JSON.parse(await fs.readFile('renovate.json', 'utf8'));
const { config } = await resolveConfigPresets(raw);
assert.equal(config.automerge, false, 'merges must remain manual');
assert.equal(config.rebaseWhen, 'behind-base-branch');
assert.equal(config.prConcurrentLimit, 2);
console.log('PASS manual merge, rebase and concurrency policy');
const managers = config.customManagers;
for (const [id, file, name, sourcePattern] of [
  ['COUCHDB_TAG', 'build-images.sh', 'couchdb', /COUCHDB_TAG="([^"]+)"/],
  ['NODE_IMAGE', 'build-images.sh', 'node', /NODE_IMAGE="docker.io\/library\/node:([^"]+)"/],
  ['PyYAML|ldap3', '.github/workflows/validate.yml', 'PyYAML', /PyYAML==([0-9.]+)/],
  ['PyYAML|ldap3', '.github/workflows/validate.yml', 'ldap3', /ldap3==([0-9.]+)/],
  ['RUNNER_IMAGE', 'test-module.sh', 'ghcr.io/marketsquare/robotframework-browser/rfbrowser-stable', /RUNNER_IMAGE="[^":]+(?:\/[^":]+)*:([^"]+)"/],
  ['robotframework-sshlibrary', 'test-module.sh', 'robotframework-sshlibrary', /robotframework-sshlibrary==([0-9.]+)/],
]) {
  const version = (await fs.readFile(file, 'utf8')).match(sourcePattern)[1].split('@')[0];
  const manager = managers.find(m => JSON.stringify(m).includes(id));
  assert.ok(manager, `missing manager ${id}`);
  const result = await extractPackageFile(await fs.readFile(file, 'utf8'), file, manager);
  assert.ok(result.deps.some(d => d.depName === name && d.currentValue === version), JSON.stringify(result));
}
console.log('PASS native regex extraction: CouchDB, shell Node, CI Python pins');
for (const [id, file, fixture, tag] of [
  ['COUCHDB_TAG', 'build-images.sh', 'COUCHDB_TAG="3.5.3"', '3.5.3'],
  ['NODE_IMAGE', 'build-images.sh', 'NODE_IMAGE="docker.io/library/node:24.22.2"', '24.22.2'],
  ['RUNNER_IMAGE', 'test-module.sh', 'RUNNER_IMAGE="ghcr.io/marketsquare/robotframework-browser/rfbrowser-stable:19.10.1"', '19.10.1'],
]) {
  const manager = managers.find(m => JSON.stringify(m).includes(id));
  for (const digest of [undefined, 'sha256:' + 'a'.repeat(64)]) {
    const content = digest ? fixture.replace(/"$/, `@${digest}"`) : fixture;
    const result = await extractPackageFile(content, file, manager);
    assert.equal(result?.deps.length, 1, id);
    assert.equal(result.deps[0].currentValue, tag, id);
    assert.equal(result.deps[0].currentDigest, digest, id);
    console.log(`PASS native ${id}: ${digest ? 'tag+digest' : 'tag-only'}`);
  }
}
async function runtimeAutomerge(updateType) {
  return (await rule({ manager: 'custom.regex', packageFile: 'build-images.sh', depName: 'couchdb', updateType })).automerge;
}
async function rule(input) {
  return applyPackageRules({ ...config, packageName: input.depName, ...input });
}
const nodes = [
  { manager: 'custom.regex', packageFile: 'build-images.sh', depName: 'node', datasource: 'docker' },
  { manager: 'dockerfile', packageFile: 'ui/Containerfile', depName: 'node', datasource: 'docker' },
  { manager: 'github-actions', packageFile: '.github/workflows/validate.yml', depName: 'node', packageName: 'actions/node-versions', depType: 'uses-with', datasource: 'github-tags' },
];
for (const input of nodes) {
  const r = await rule({ ...input, updateType: 'minor' });
  assert.equal(r.groupName, 'Node.js toolchain');
  assert.equal(r.allowedVersions, '<25');
}
assert.equal((await rule({ manager: 'npm', packageFile: 'ui/package.json', depName: 'vue', updateType: 'major' })).dependencyDashboardApproval, true);
assert.equal((await rule({ manager: 'custom.regex', packageFile: 'build-images.sh', depName: 'couchdb', updateType: 'major' })).dependencyDashboardApproval, true);
console.log('PASS cross-manager Node grouping and major approval');
for (const updateType of ['patch', 'minor', 'major']) {
  const carbon = await rule({ manager: 'npm', packageFile: 'ui/package.json', depName: 'carbon-components', updateType });
  assert.equal(carbon.allowedVersions, '<11', 'Carbon 11 removes the SCSS paths consumed by this UI');
  assert.notEqual(carbon.automerge, true);
}
console.log('PASS Carbon 10 compatibility ceiling; updates remain manual');
assert.equal(await runtimeAutomerge('patch'), true);
assert.notEqual(await runtimeAutomerge('minor'), true);
assert.notEqual(await runtimeAutomerge('major'), true);
assert.equal((await rule({ manager: 'github-actions', packageFile: '.github/workflows/validate.yml', depName: 'actions/checkout', depType: 'action', updateType: 'minor' })).automerge, true);
assert.notEqual((await rule({ manager: 'github-actions', packageFile: '.github/workflows/validate.yml', depName: 'actions/checkout', depType: 'action', updateType: 'major' })).automerge, true);
assert.notEqual((await rule({ manager: 'npm', packageFile: 'ui/package.json', depName: 'vite', updateType: 'patch' })).automerge, true);
console.log('PASS automerge limited to CouchDB patch, CI actions and test tooling');
GlobalConfig.set({ localDir: process.cwd(), platform: 'local' });
// Local SCM reads the actual checkout with git ls-files.
setPlatformScmApi('local');
const oldVersion = (await fs.readFile('CATALOG_VERSION', 'utf8')).trim();
const expected = oldVersion.replace(/(\d+)$/, n => String(Number(n) + 1));
const ui = await rule({ manager: 'npm', packageFile: 'ui/package.json', depName: 'vite', updateType: 'patch' });
// Replay native branch generation and the shared publisher/module-info slash-only mapping.
// The original group name produced renovate/ui-dependencies-(non-major), an invalid OCI tag.
const { generateBranchName } = await import(base + 'workers/repository/updates/branch-name.js');
const { getConfig } = await import(base + 'config/defaults.js');
const branchUpdate = { ...getConfig(), ...ui };
generateBranchName(branchUpdate);
const publishedTag = branchUpdate.branchName.replaceAll('/', '-');
assert.match(publishedTag, /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/, 'shared publisher must receive an OCI-safe branch');
assert.equal(branchUpdate.branchName, 'renovate/ui-dependencies-non-major');
console.log('PASS native UI group branch -> shared publisher/module-info OCI tag');
const runtime = await rule({ manager: 'custom.regex', packageFile: 'build-images.sh', depName: 'couchdb', updateType: 'patch' });
const action = await rule({ manager: 'github-actions', packageFile: '.github/workflows/validate.yml', depName: 'actions/checkout', depType: 'action', updateType: 'minor' });
const lock = await rule({ manager: 'npm', packageFile: 'ui/package.json', depType: 'lockFileMaintenance', updateType: 'lockFileMaintenance' });
let scenarios = 0;
for (const [name, upgrades, packages, artifacts, shouldBump] of [
  ['manifest', [ui], ['ui/package.json'], [], true],
  ['runtime', [runtime], ['build-images.sh'], [], true],
  ['lock-only', [lock], [], ['ui/yarn.lock'], true],
  ['group-action-first', [action, runtime, ui], ['.github/workflows/validate.yml', 'build-images.sh', 'ui/package.json'], [], true],
  ['workflow-only', [action], ['.github/workflows/validate.yml'], [], false],
  ['no-op', [ui], [], [], false],
]) {
  const change = path => ({ type: 'addition', path, contents: 'test update\n' });
  const branch = { ...config, bumpVersions: upgrades[0].bumpVersions, upgrades, updatedPackageFiles: packages.map(change), updatedArtifacts: artifacts.map(change) };
  await bumpVersions(branch);
  assert.ok(!branch.artifactErrors?.length, JSON.stringify(branch.artifactErrors));
  const bumped = [...branch.updatedPackageFiles, ...branch.updatedArtifacts].filter(f => f.path === 'CATALOG_VERSION');
  assert.equal(bumped.length, shouldBump ? 1 : 0, name);
  if (shouldBump) assert.equal(bumped[0].contents.trim(), expected, name);
  scenarios++;
  console.log(`PASS native bumpVersions: ${name}`);
}
console.log(`Renovate policy passed; ${scenarios} release scenarios.`);
