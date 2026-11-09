# Local Vue 3 NS8 bridge

Ported consumed subset of `@nethserver/ns8-ui-lib` (Nethesis S.r.l.,
GPL-3.0-or-later). The original installed2.1.0 and registry2.2.1 are Vue2-only;
retaining their compiled renders or CarbonVue2 inheritance is not compatible
with this application's Vue3 runtime. The inspected related-module port in
ns8-organizr-reworked supplied a starting implementation, not compatibility
proof: LiveSync-specific account modals, four configuration switches, AD group
selection and all task handlers are independently browser tested here.

- `services.js`: consumed Task/QueryParam/Util/PageTitle/Icon methods; same NS8
  task endpoints, loginInfo bearer authentication, event names and event order.
- Task listeners belong to a mounted component; first terminal outcome removes
  all siblings; HTTP failure and unmount clean up too.
- `events.js`: iframe-local event bus; the parent remains its original Vue2
  object, marked raw in Vuex state.
- Consumed `NsButton`, notifications, combobox, modal, empty state, info/service/
  log/backup cards, SVGs and icons preserve Carbon v10 classes and host CSS.
- `NsModal` composes the actual CarbonVue3 modal, including its teleport, focus
  trapping, disabled primary controls, Escape and loading behavior; it does not
  extend a setup component as though it were a Vue2 options component.
- No animation/debounce/date-fns plugins, unused library widgets or Vue2 filters
  are globally registered. Time formatting uses the browser Intl APIs.

See `docs/vue3-ui-migration.md` for old-PR dispositions, fixture limitations,
actual host stylesheet provenance, reproduction and acceptance gates.
