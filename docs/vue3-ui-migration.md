# Coordinated Vue 3 UI migration

This branch is an independently testable **0.4.0 candidate**, not a release or
live deployment. No old dependency PR is merged or closed by this change.
The backend settings, action schemas, CouchDB image choice, AD membership and
credential/recovery storage are unchanged.

## Disposition of every UI major proposal

The package.json patches, exact heads, comments and reviews of all fifteen UI
proposals were inspected. None had comments or reviews at inspection time.
They cannot safely be merged as independent Vue-2-compatible version bumps.

| Existing PR | Disposition in this candidate |
| --- | --- |
| #13 Babel 8 | Remove unused Babel compiler/parser. Vite's Vue3 compiler and ESLint's standard JavaScript parser handle this source; there is no Babel transform configuration or syntax requiring Babel. |
| #14 Carbon Vue 3 | Upgrade to **3.0.32**; register the consumed Vue3 components, port slots/model values/checkboxes/toggles/modals and explicit button types. |
| #15 Vue Prettier config 10 | **10.2.0**, integrated into ESLint's flat configuration. |
| #16 carbon-components 11 | **Hold at 10.59.2**. Carbon Vue 3.0.32 itself depends on Carbon v10 (`^10.58.5`), and the production NS8 host supplies v10 `bx--` CSS. v11 is deprecated too; blindly bumping only this SCSS-token package would not migrate the host or the component CSS. A coordinated host/design-system migration is a separate prerequisite. |
| #17 ESLint 10 | **10.14.0**, flat config and zero-warning lint gate. |
| #18 eslint-plugin-prettier 5 | **5.5.7**, paired with Prettier3 and eslint-config-prettier10.1.8. |
| #19 eslint-plugin-vue 10 | **10.12.0**, vue-eslint-parser10.4.2 and Vue3 rules. |
| #20 lottie-web-vue 3 | Remove unused animation plugin. No animation consumer exists in the application; no unexercised global registration is retained. |
| #21 Prettier 3 | **3.9.10**, source and test formatting updated. |
| #23 Vite 8 | **8.3.7**, Vue3 plugin6.0.10; actual Node24.22.2 production and development bundles tested. |
| #24 Vue 3 | **3.5.45**, createApp/bootstrap/plugin API, one app root, reactive route selection. |
| #25 vue-debounce 6 | Remove unused directive/plugin. No component uses a debounce directive. |
| #26 vue-i18n 11 | **11.4.18**, composition mode with global injection, plural `$t`, EN fallback always loaded, DE and unsupported locales covered. |
| #27 Vue Router 5 | **5.4.0**, hash history, return-style guards (including enter callbacks), lazy About page and host-driven routing. Optional Pinia/Colada peers are not used by this application. |
| #28 Vuex 4 | **4.1.0**, createStore; parent host object marked raw to preserve its Vue2 router/event-bus identity. |

#22 Ubuntu runner and #29 Robot Browser image are **outside the UI stack** and
remain separate integration decisions. This branch does not change either.

Also removed: Vue2-only vue-date-fns, @vitejs/plugin-vue2, obsolete crypto shim,
and vue-axios (axios is explicitly injected without its unnecessary UMD shim).
Yarn is pinned by packageManager, currently4.18.0; all builds use immutable
installation. Node is24.22.2 in production, developer recipe and CI.

## NS8 bridge and host contract

The original installed @nethserver/ns8-ui-lib2.1.0 has a `vue ^2.6.12` peer,
compiled Vue2 render functions and components extending Carbon Vue2. Registry
2.2.1 is also Vue2-only. A root Vue version bump cannot make it compatible.
The consumed bridge/components are locally ported in `ui/src/ns8`, derived
from the GPL-3.0-or-later Nethesis code and an inspected related-module port.
Only code used by this application's complete Settings/Status/About screens is
registered; LiveSync's own forms, action handlers and payloads are retained.

Task transport remains POST `<apiUrl>/module/<instance>/tasks` or
`<apiUrl>/cluster/tasks`, with the loginInfo bearer token and existing
`<action>-<outcome>-<eventId>` parent-core events and argument order. Every
terminal outcome clears sibling subscriptions; HTTP failure and unmount do
likewise. Delayed/duplicate completions cannot refresh an unmounted view.
Host notification, keyboard-shortcut registration and navigation contracts are
retained. The public iframe mobile-toggle event forwards to the local Vue3
bus, with scoped listener cleanup. The stock host stylesheet—not a replacement
Carbon theme—is used.

LiveSync has **no credential-copy controls**. The account password visibility
control, readonly credentials, add/remove/reset confirmations and cancellation
are exercised without unintended configuration submission. No clipboard
functionality has been invented or claimed.

## Reproduction and evidence

```sh
# Same shared bootstrap as production build-images.sh
cd ui && ./build-ui.sh
# In repository root: extract files only; never execute the core image
NS8_CORE_IMAGE=ghcr.io/nethserver/core:latest@sha256:91f910e7e247d5806ce63abc54914edd59558b0bd7669a2337b678c295f3b5c6 \
  .github/scripts/extract-core-css "$TMPDIR/ns8-core.css"
cd ui
NS8_CORE_CSS="$TMPDIR/ns8-core.css" yarn test:e2e
NS8_CORE_CSS="$TMPDIR/ns8-core.css" yarn test:e2e:dev
```

The browser harness explicitly simulates the NS8 host API/event bus around the
**real generated application bundles**; it does not claim a deployed NS8
browser login. Missing real core CSS fails closed. All browser warning messages
and page exceptions are rejected, including Router5 diagnostics that no longer
use the old VueRouter warning prefix. Deliberately generated API errors are
separate expected console.error diagnostics.

TDD evidence: original delayed repository completion after navigation produced
an unwanted fifth request (expected four). The Vue3 stack test failed against
Vue2. New build/bootstrap/CI contracts failed against Corepack-dependent
recipes. After migration the credential regression caught Vue3's empty
readonly fields until `model-value` replaced Vue2 `value`. Broad development
console checking caught return-guard deprecations and unsupported-locale
warnings; both were repaired rather than suppressed.

CI runs the shared immutable bootstrap, stack contracts, real-host-CSS
production/development Chromium regressions, exact production Node container,
and actual developer image build/watch/nonroot interactive serve. Checkout and
setup-node actions are SHA pinned; Playwright1.65.0 pins its browser revision.
Existing Python, native Renovate and Debian13/Rocky9 install/update QEMU gates
remain enabled. Hosted acceptance/review status belongs to the draft PR's
exact head, not to an earlier successful local run.

Two remaining Yarn peer diagnostics are upstream declaration omissions:
@vueuse/core4.11.2 and @vueuse/shared4.11.2 do not declare Vue for vue-demi.
There are no incompatible root application peers; these warnings are recorded,
not globally suppressed. Production build's external `/cluster-admin/css/core.css`
notice is expected because the actual host supplies that URL at runtime.

## Resumed verification and remaining acceptance gates

Fresh verification on 2026-11-09 preserved and tested the full staged migration,
not the original main HEAD. Results: 54 Python tests, one stack contract,
47 production Chromium tests and 47 development Chromium tests passed. The
browser commands ran on local Node26.12.1 with pinned Playwright1.65.0;
the independent immutable install, zero-warning ESLint and production build ran
inside the exact `node:24.22.2` production container. The developer image was
rebuilt without cache and its actual nonroot `build`, `watch` and `serve`
entrypoints all passed. The extracted host CSS SHA256 is
`eca2f8c9d36bbd4baf7e0d37e4a2b998b40615427fdddd86a2f9ee6d89c12d7e`.
The only resume edit to application/test code corrects a stale fixture comment;
no behavior changes were justified by the passing checks.

This remains **draft**, with these gates explicitly open:

1. Review this final migration diff, including local NS8 component/bridge parity,
   independently; local tests are not independent review approval.
2. Obtain exact-head hosted Validate, Renovate-policy and publisher results;
   verify all four Debian13/Rocky9 install/update QEMU legs and candidate image
   revision. Prior GitHub internal errors before job allocation are not passes.
3. Exercise Settings, Status and About in an authorized disposable actual NS8
   cluster. The browser harness uses real bundles/CSS but a simulated host/API,
   not a live cluster or login. No installed user instance has been changed.
4. Parent must reconcile PR31 before merging: this branch deliberately keeps
   its original main base and does not integrate the compatible branch. Preserve
   PR31's CouchDB3.5.3, OCI-safe Renovate groupSlug, policy/runtime updates and
   reviewed lock/toolchain intent when resolving overlapping files; keep the
   coordinated migration version **0.4.0**, not PR31's **0.3.2**. Re-run all
   gates after that integration. Yarn on this candidate is4.18.0, not PR31's4.18.1.
5. Carbon11 is deliberately deferred pending host/design-system compatibility;
   #22 runner and #29 Robot Browser remain separate. No original PR is merged
   or closed, no automerge or branch-protection bypass is enabled.
