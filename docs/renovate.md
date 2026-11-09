# Dependency updates and release gates

Renovate onboarding lives in PR #6. Regular updates start only after a maintainer
merges that configuration into `main` and the installed Renovate app next runs.
This setup does not enable automerge or deploy any installed NS8 module.

## Ownership inventory

Renovate is the single updater for these tracked inputs; there is no competing
custom updater or Dependabot configuration:

| Input | Consumer / ownership |
| --- | --- |
| `COUCHDB_TAG` in `build-images.sh` | Docker regex manager; shipped CouchDB image label |
| `NODE_IMAGE` in `build-images.sh` | Docker regex manager; production UI builder |
| `ui/Containerfile` | Dockerfile manager; development UI environment |
| setup-node `node-version` in `validate.yml` | GitHub Actions manager; coordinated with both Node images |
| `ui/package.json`, `ui/yarn.lock` | npm manager; UI dependencies, dev tools, Yarn; weekly lock maintenance |
| `.github/workflows/*.yml` | Actions/workflow/runner updates; includes pinned Renovate validation image |
| `PyYAML`, `ldap3` in `validate.yml` | PyPI regex manager; unit-test environment only |
| `RUNNER_IMAGE` in `test-module.sh` | Docker regex manager; Robot Framework browser environment |
| `robotframework-sshlibrary` in `test-module.sh` | PyPI regex manager; acceptance test dependency |

CouchDB is an upstream runtime, not the Obsidian plugin: upgrading the server does
not install or upgrade clients. NS8 core/min-core and module release metadata
are compatibility contracts, not upstream dependency pins. Agent-provided Python
runtime libraries are maintained by NS8, not vendored here. `ubuntu-latest` floats
with GitHub; only explicit runner versions can be upgraded by Renovate. Upstream
image-internal OS packages require an upstream rebuild, not an invented local
package-refresh mechanism.

## Policy

- All merges remain manual; normal PR concurrency and hourly creation limit: 2.
- Major updates require Dependency Dashboard approval. Security proposals can
  bypass normal creation limits; they still must not automerge.
- Node stays below 25 until a separately reviewed migration proves the exact
  production `corepack enable && yarn install --immutable && yarn build` path.
  CI, production builder and development image updates share one Node group.
- GitHub Actions grouping excludes setup-node's `uses-with` dependency.
- Non-major UI changes are grouped. Image-affecting updates under `ui/**` or in
  `build-images.sh` use Renovate's native `bumpVersions` to increment
  `CATALOG_VERSION` once, including lockfile-only maintenance. Workflow/test-only
  changes do not bump the module version. This configuration PR does not bump it.
- `rebaseWhen: behind-base-branch` regenerates stale proposals. The existing
  catalog-version check remains necessary to reject version collisions.

## Review, test, publish, deploy

Run strict validation and regression tests with the same pinned official image
as `.github/workflows/renovate-policy.yml`:

```sh
image=ghcr.io/renovatebot/renovate:44.222.5
podman run --rm --user=0 --entrypoint renovate-config-validator -v "$PWD:/work:ro" -w /work "$image" --strict renovate.json
podman run --rm --user=0 --entrypoint node -v "$PWD:/work:ro" -w /work "$image" tests/renovate-policy.mjs
podman run --rm --user=0 --entrypoint renovate -v "$PWD:/work:ro" -w /work "$image" --platform=local --dry-run=extract --require-config=required --onboarding=false
```

The credential-free extraction test does not perform authenticated GitHub release
lookups; its token warning is expected, not proof of a bot permission failure.
The policy tests resolve recommended presets, use native RE2 extraction, real
package-rule matching and real release bumping for manifest/runtime, lock-only,
grouped action-first, workflow-only and no-op proposals. They do not publish.

Before merging dependency PRs, inspect the generated diff/version bump and wait
for Static checks, UI lint/build, Renovate policy and the existing Publish images
suite, including install/update on Rocky 9 and Debian 13. Check intentional skips
separately; a skipped scan is not a successful security scan. Branch pushes already
produce testing images via existing automation, not a stable release. Only the
successful main-branch publish suite can trigger `publish-catalog-version.yml` to
promote the tested image and create its GitHub release. This PR does not change
that release automation. NS8 instance upgrades remain a separate operator action.

The repository currently has no protected main branch. Maintainers must enforce
these manual merge gates; protection/required checks should be configured before
considering any future automerge policy.
