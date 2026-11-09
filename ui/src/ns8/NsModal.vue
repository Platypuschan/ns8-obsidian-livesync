<!-- Copyright (C) 2023 Nethesis S.r.l.; SPDX-License-Identifier: GPL-3.0-or-later -->
<template>
  <CvModal
    :visible="visible"
    :kind="kind"
    :size="size === 'default' ? '' : size"
    :primary-button-disabled="primaryButtonDisabled || isLoading"
    :auto-hide-off="true"
    @modal-hidden="$emit('modal-hidden')"
    @modal-hide-request="hideRequested"
    @primary-click="$emit('primary-click')"
    @secondary-click="$emit('secondary-click')"
  >
    <template #title><slot name="title" /></template>
    <template #content><slot name="content" /></template>
    <template #primary-button>
      <span v-if="isLoading" role="status" aria-label="Loading">… </span>
      <slot name="primary-button" />
    </template>
    <template #secondary-button><slot name="secondary-button" /></template>
  </CvModal>
</template>
<script>
import { CvModal } from "@carbon/vue";
export default {
  name: "NsModal",
  components: { CvModal },
  props: {
    visible: Boolean,
    isLoading: Boolean,
    primaryButtonDisabled: Boolean,
    autoHideOff: Boolean,
    hideOnClickOutside: Boolean,
    kind: { type: String, default: "" },
    size: { type: String, default: "default" },
  },
  emits: ["modal-hidden", "primary-click", "secondary-click"],
  methods: {
    hideRequested(event) {
      if (this.autoHideOff || this.isLoading) return;
      if (event["cv:reason"] !== "external-click" || this.hideOnClickOutside)
        this.$emit("modal-hidden");
    },
  },
};
</script>
