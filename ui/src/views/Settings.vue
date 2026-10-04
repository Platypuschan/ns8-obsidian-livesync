<!--
  Copyright (C) 2022 Nethesis S.r.l.
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("settings.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error.getConfiguration">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('action.get-configuration')"
          :description="error.getConfiguration"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <cv-form @submit.prevent="configureModule">
            <cv-text-input
              :label="$t('settings.livesync_fqdn')"
              placeholder="livesync.example.org"
              v-model.trim="host"
              class="mg-bottom"
              :invalid-message="$t(error.host)"
              :disabled="loading.getConfiguration || loading.configureModule"
              ref="host"
            >
            </cv-text-input>
            <cv-toggle
              value="letsEncrypt"
              :label="$t('settings.lets_encrypt')"
              v-model="isLetsEncryptEnabled"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
            >
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </cv-toggle>
            <cv-toggle
              value="httpToHttps"
              :label="$t('settings.http_to_https')"
              v-model="isHttpToHttpsEnabled"
              :disabled="loading.getConfiguration || loading.configureModule"
              class="mg-bottom"
            >
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </cv-toggle>
            <cv-row v-if="error.configureModule">
              <cv-column>
                <NsInlineNotification
                  kind="error"
                  :title="$t('action.configure-module')"
                  :description="error.configureModule"
                  :showCloseButton="false"
                />
              </cv-column>
            </cv-row>
            <NsButton
              kind="primary"
              :icon="Save20"
              :loading="loading.configureModule"
              :disabled="loading.getConfiguration || loading.configureModule"
              >{{ $t("settings.save") }}</NsButton
            >
          </cv-form>
        </cv-tile>
      </cv-column>
    </cv-row>
    <!-- sync accounts -->
    <cv-row v-if="url">
      <cv-column>
        <cv-tile light>
          <h4 class="mg-bottom">{{ $t("settings.accounts_title") }}</h4>
          <p class="mg-bottom">{{ $t("settings.accounts_description") }}</p>
          <NsInlineNotification
            v-if="!isLetsEncryptEnabled"
            kind="warning"
            :title="$t('settings.https_warning_title')"
            :description="$t('settings.https_warning_description')"
            :showCloseButton="false"
          />
          <cv-text-input
            id="livesync-uri"
            :label="$t('settings.server_uri')"
            :value="url"
            readonly
            class="mg-bottom"
          />
          <NsInlineNotification
            v-if="error.removeAccount"
            kind="error"
            :title="$t('action.remove-account')"
            :description="error.removeAccount"
            :showCloseButton="false"
          />
          <NsEmptyState
            v-if="!accounts.length"
            :title="$t('settings.no_accounts')"
            class="mg-bottom"
          />
          <div
            v-for="account in accounts"
            :key="account.username"
            class="account mg-bottom"
          >
            <cv-text-input
              :id="'account-username-' + account.username"
              :label="$t('settings.username')"
              :value="account.username"
              readonly
            />
            <cv-text-input
              :id="'account-password-' + account.username"
              :label="$t('settings.password')"
              :value="account.password"
              type="password"
              readonly
            />
            <cv-text-input
              :id="'account-database-' + account.username"
              :label="$t('settings.database_name')"
              :value="account.database"
              readonly
            />
            <NsButton
              kind="danger--ghost"
              :icon="TrashCan20"
              :disabled="loading.getConfiguration"
              @click="showRemoveModal(account)"
              >{{ $t("settings.remove_account") }}</NsButton
            >
          </div>
          <NsButton
            kind="secondary"
            :icon="Add20"
            :disabled="loading.getConfiguration"
            class="mg-bottom"
            @click="showAddModal"
            >{{ $t("settings.add_account") }}</NsButton
          >
          <p>{{ $t("settings.passphrase_hint") }}</p>
        </cv-tile>
      </cv-column>
    </cv-row>
    <!-- add account -->
    <NsModal
      size="default"
      :visible="isAddModalShown"
      :isLoading="loading.addAccount"
      :primary-button-disabled="loading.addAccount"
      :autoHideOff="loading.addAccount"
      @modal-hidden="isAddModalShown = false"
      @secondary-click="isAddModalShown = false"
      @primary-click="addAccount"
    >
      <template slot="title">{{ $t("settings.add_account") }}</template>
      <template slot="content">
        <cv-form @submit.prevent="addAccount">
          <cv-text-input
            id="new-account-username"
            :label="$t('settings.username')"
            :helper-text="$t('settings.username_helper')"
            v-model.trim="newAccount.username"
            :invalid-message="$t(error.username)"
            :disabled="loading.addAccount"
            class="mg-bottom"
            ref="username"
          />
          <cv-text-input
            id="new-account-database"
            :label="$t('settings.database_name')"
            :helper-text="$t('settings.database_helper')"
            v-model.trim="newAccount.database"
            :invalid-message="$t(error.database)"
            :disabled="loading.addAccount"
            class="mg-bottom"
            ref="database"
          />
        </cv-form>
        <NsInlineNotification
          v-if="error.addAccount"
          kind="error"
          :title="$t('action.add-account')"
          :description="error.addAccount"
          :showCloseButton="false"
        />
      </template>
      <template slot="secondary-button">{{ $t("settings.cancel") }}</template>
      <template slot="primary-button">{{ $t("settings.create") }}</template>
    </NsModal>
    <!-- remove account -->
    <NsModal
      kind="danger"
      size="default"
      :visible="isRemoveModalShown"
      :isLoading="loading.removeAccount"
      :primary-button-disabled="loading.removeAccount"
      :autoHideOff="loading.removeAccount"
      @modal-hidden="isRemoveModalShown = false"
      @secondary-click="isRemoveModalShown = false"
      @primary-click="removeAccount"
    >
      <template slot="title">{{
        $t("settings.remove_account_title", {
          username: accountToRemove.username,
        })
      }}</template>
      <template slot="content">
        <p class="mg-bottom">
          {{ $t("settings.remove_account_description") }}
        </p>
        <cv-checkbox
          id="remove-account-database"
          value="deleteDatabase"
          v-model="deleteDatabase"
          :label="
            $t('settings.remove_account_database', {
              database: accountToRemove.database,
            })
          "
          :disabled="loading.removeAccount"
        />
        <NsInlineNotification
          v-if="deleteDatabase"
          kind="warning"
          :title="$t('settings.remove_account_database_warning')"
          :showCloseButton="false"
        />
      </template>
      <template slot="secondary-button">{{ $t("settings.cancel") }}</template>
      <template slot="primary-button">{{
        $t("settings.remove_account")
      }}</template>
    </NsModal>
  </cv-grid>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import {
  QueryParamService,
  UtilService,
  TaskService,
  IconService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

export default {
  name: "Settings",
  mixins: [
    TaskService,
    IconService,
    UtilService,
    QueryParamService,
    PageTitleService,
  ],
  pageTitle() {
    return this.$t("settings.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "settings",
      },
      urlCheckInterval: null,
      host: "",
      isLetsEncryptEnabled: false,
      isHttpToHttpsEnabled: true,
      url: "",
      accounts: [],
      isAddModalShown: false,
      newAccount: {
        username: "",
        database: "",
      },
      isRemoveModalShown: false,
      accountToRemove: {
        username: "",
        database: "",
      },
      deleteDatabase: false,
      loading: {
        getConfiguration: false,
        configureModule: false,
        addAccount: false,
        removeAccount: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        addAccount: "",
        removeAccount: "",
        host: "",
        lets_encrypt: "",
        http2https: "",
        username: "",
        database: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
  },
  created() {
    this.getConfiguration();
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  methods: {
    // Start a module task and route its events to the given handlers
    async runTask(action, data, handlers, extra) {
      const eventId = this.getUuid();
      this.core.$root.$once(`${action}-aborted-${eventId}`, handlers.aborted);
      this.core.$root.$once(
        `${action}-completed-${eventId}`,
        handlers.completed
      );
      if (handlers.validationFailed) {
        this.core.$root.$once(
          `${action}-validation-failed-${eventId}`,
          handlers.validationFailed
        );
      }
      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: {
            title: this.$t("action." + action),
            isNotificationHidden: true,
            ...extra,
            eventId,
          },
        })
      );
      return res[0];
    },
    async getConfiguration() {
      this.loading.getConfiguration = true;
      this.error.getConfiguration = "";
      const err = await this.runTask("get-configuration", undefined, {
        aborted: this.getConfigurationAborted,
        completed: this.getConfigurationCompleted,
      });
      if (err) {
        console.error("error creating task get-configuration", err);
        this.error.getConfiguration = this.getErrorMessage(err);
        this.loading.getConfiguration = false;
      }
    },
    getConfigurationAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.getConfiguration = this.$t("error.generic_error");
      this.loading.getConfiguration = false;
    },
    getConfigurationCompleted(taskContext, taskResult) {
      const config = taskResult.output;
      this.host = config.host;
      this.isLetsEncryptEnabled = config.lets_encrypt;
      this.isHttpToHttpsEnabled = config.http2https;
      this.url = config.url;
      this.accounts = config.accounts;

      this.loading.getConfiguration = false;
      this.focusElement("host");
    },
    validateConfigureModule() {
      this.clearErrors(this);

      let isValidationOk = true;
      if (!this.host) {
        this.error.host = "common.required";

        if (isValidationOk) {
          this.focusElement("host");
        }
        isValidationOk = false;
      }
      return isValidationOk;
    },
    // Show task validation errors next to their fields
    showValidationErrors(validationErrors) {
      let focusAlreadySet = false;
      for (const validationError of validationErrors) {
        const param = validationError.parameter;
        this.error[param] = "settings." + validationError.error;

        if (!focusAlreadySet) {
          this.$nextTick(() => this.focusElement(param));
          focusAlreadySet = true;
        }
      }
    },
    async configureModule() {
      if (!this.validateConfigureModule()) {
        return;
      }
      this.loading.configureModule = true;
      const err = await this.runTask(
        "configure-module",
        {
          host: this.host,
          lets_encrypt: this.isLetsEncryptEnabled,
          http2https: this.isHttpToHttpsEnabled,
        },
        {
          aborted: this.configureModuleAborted,
          completed: this.configureModuleCompleted,
          validationFailed: this.configureModuleValidationFailed,
        },
        {
          title: this.$t("settings.instance_configuration", {
            instance: this.instanceName,
          }),
          description: this.$t("settings.configuring"),
          isNotificationHidden: false,
        }
      );
      if (err) {
        console.error("error creating task configure-module", err);
        this.error.configureModule = this.getErrorMessage(err);
        this.loading.configureModule = false;
      }
    },
    configureModuleValidationFailed(validationErrors) {
      this.loading.configureModule = false;
      this.showValidationErrors(validationErrors);
    },
    configureModuleAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.configureModule = this.$t("error.generic_error");
      this.loading.configureModule = false;
    },
    configureModuleCompleted() {
      this.loading.configureModule = false;
      this.getConfiguration();
    },
    showAddModal() {
      this.newAccount = { username: "", database: "" };
      this.error.addAccount = "";
      this.error.username = "";
      this.error.database = "";
      this.isAddModalShown = true;
      this.$nextTick(() => this.focusElement("username"));
    },
    validateAddAccount() {
      this.error.username = "";
      this.error.database = "";
      let isValidationOk = true;
      if (!/^[a-z][a-z0-9._-]{0,63}$/.test(this.newAccount.username)) {
        this.error.username = "settings.username_invalid";
        this.focusElement("username");
        isValidationOk = false;
      }
      if (!/^[a-z][a-z0-9_$()+-]*$/.test(this.newAccount.database)) {
        this.error.database = "settings.database_pattern";
        if (isValidationOk) {
          this.focusElement("database");
        }
        isValidationOk = false;
      }
      return isValidationOk;
    },
    async addAccount() {
      if (!this.validateAddAccount()) {
        return;
      }
      this.loading.addAccount = true;
      this.error.addAccount = "";
      const err = await this.runTask(
        "add-account",
        {
          username: this.newAccount.username,
          database: this.newAccount.database,
        },
        {
          aborted: this.addAccountAborted,
          completed: this.addAccountCompleted,
          validationFailed: this.addAccountValidationFailed,
        }
      );
      if (err) {
        console.error("error creating task add-account", err);
        this.error.addAccount = this.getErrorMessage(err);
        this.loading.addAccount = false;
      }
    },
    addAccountValidationFailed(validationErrors) {
      this.loading.addAccount = false;
      this.showValidationErrors(validationErrors);
    },
    addAccountAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.addAccount = this.$t("error.generic_error");
      this.loading.addAccount = false;
    },
    addAccountCompleted() {
      this.loading.addAccount = false;
      this.isAddModalShown = false;
      this.getConfiguration();
    },
    showRemoveModal(account) {
      this.accountToRemove = account;
      this.deleteDatabase = false;
      this.error.removeAccount = "";
      this.isRemoveModalShown = true;
    },
    async removeAccount() {
      this.loading.removeAccount = true;
      this.error.removeAccount = "";
      const err = await this.runTask(
        "remove-account",
        {
          username: this.accountToRemove.username,
          delete_database: this.deleteDatabase,
        },
        {
          aborted: this.removeAccountAborted,
          completed: this.removeAccountCompleted,
        }
      );
      if (err) {
        console.error("error creating task remove-account", err);
        this.error.removeAccount = this.getErrorMessage(err);
        this.loading.removeAccount = false;
        this.isRemoveModalShown = false;
      }
    },
    removeAccountAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.removeAccount = this.$t("error.generic_error");
      this.loading.removeAccount = false;
      this.isRemoveModalShown = false;
    },
    removeAccountCompleted() {
      this.loading.removeAccount = false;
      this.isRemoveModalShown = false;
      this.getConfiguration();
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";
.mg-bottom {
  margin-bottom: $spacing-06;
}

.account {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: $spacing-05;
  align-items: end;
  padding-bottom: $spacing-05;
  border-bottom: 1px solid $ui-03;
}
</style>
