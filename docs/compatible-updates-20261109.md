# Compatible dependency integration (2026-11-09)

Base: `3a2798b17faed6d5ca0758ea10a19aa7250514bd`. One native module bump: 0.3.1 → 0.3.2.

| Original PR | Reviewed head | Disposition |
|---|---|---|
| #7 | `7ad7073c629fcbc8747731b58b485836395f5611` | CouchDB 3.5.3 runtime integrated |
| #8 | `43fce6b724ec4152509cdc8abfbd59dc87b093ae` | Full UI manifest/lock update integrated; Vue 2 stack retained |
| #10 | `7da3d3d0301b25eac9969b45a08df77d8b863179` | Robot Browser 19.15.1 integrated |
| #11 | `a2728b5c41e3a3830004d681f08ec6030157dc75` | Official Renovate validation image 44.224.1 integrated |
| #12 | `5dc2e4e51d0d0eb8d8a7428f8dc59eb9d8b03dc8` | Node 24.22.2 across all three consumers integrated |
| #30 | `9c69704a55263f8fc2224b68726b34c464a289cc` | Separate later lock-maintenance batch; not implicitly covered by #8 |

No existing PR is merged or closed by this integration. Major UI updates are coordinated separately. Browser 21 (#29) is not included.

## OCI tag root cause and regression

Failed run 42605717605 built the UI successfully, then failed publication with `invalid reference format`. `publish-branch.yml@v1` passes its input to IMAGETAG, replaces only `/` with `-`, writes GITHUB_ENV, then uses that value in its own later buildah push. Changing a variable only in the child build-images.sh cannot repair the parent publisher. `module-info.yml@v1` independently applies the same slash-only mapping to the branch.

The native Renovate group-name slug retained parentheses: `renovate/ui-dependencies-(non-major)`. Set an explicit OCI-safe `groupSlug: ui-dependencies-non-major` at the source. Both shared consumers now derive `renovate-ui-dependencies-non-major`; shared upstream remains unchanged. This prevents future invalid UI group branch names; it does not retroactively rename #8. Its changes are carried on this safe integration branch instead.

Strict TDD: native generateBranchName regression first failed on exactly `renovate-ui-dependencies-(non-major)` against OCI tag grammar; only then added groupSlug and observed GREEN. Regression runs inside the official pinned Renovate image, along with native extraction, package-rule and six release-version scenarios. The real integration pipeline uses the same unmodified shared publisher and module-info workflow.

## Local execution

- Exact production `docker.io/library/node:24.22.2`: Corepack, Yarn 4.18.1 immutable install, lint and build passed.
- All 50 Python unit tests passed without skips.
- Official Renovate 44.224.1 strict configuration validator, native extraction/rules/release regressions and local repository extraction passed.
- Existing Vue 2/ESLint 6 peer warnings and build warnings (runtime host CSS, upstream lottie eval) remain visible; these are not evidence that major UI upgrades are compatible.

Hosted final-head publication and Debian13/Rocky9 install/update results must be checked before accepting the candidate. No automerge, release-age policy override, branch-protection change or live deployment is authorized here.
