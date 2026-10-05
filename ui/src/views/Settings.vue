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
            <cv-toggle
              value="adEnabled"
              :label="$t('settings.ad_enabled')"
              v-model="adEnabled"
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
            <template v-if="adEnabled">
              <p class="mg-bottom helper">
                {{ $t("settings.ad_description") }}
              </p>
              <NsInlineNotification
                v-if="error.listUserDomains"
                kind="error"
                :title="$t('action.list-user-domains')"
                :description="error.listUserDomains"
                :showCloseButton="false"
              />
              <NsComboBox
                v-model="adDomain"
                :options="adDomains"
                auto-highlight
                :title="$t('settings.ad_domain')"
                :label="$t('settings.ad_domain_placeholder')"
                :invalid-message="$t(error.ad_domain)"
                :disabled="
                  loading.getConfiguration ||
                  loading.configureModule ||
                  loading.listUserDomains
                "
                class="mg-bottom"
                ref="ad_domain"
              />
              <cv-text-input
                id="ad-group"
                :label="$t('settings.ad_group')"
                placeholder="obsidian-users"
                v-model.trim="adGroup"
                :invalid-message="$t(error.ad_group)"
                :disabled="loading.getConfiguration || loading.configureModule"
                class="mg-bottom"
                ref="ad_group"
              />
              <cv-toggle
                value="adNestedGroups"
                :label="$t('settings.ad_nested_groups')"
                v-model="adNestedGroups"
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
            </template>
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
          <div v-if="adConfigured" class="mg-bottom">
            <NsInlineNotification
              v-if="adLastSync && !adLastSync.ok"
              kind="error"
              :title="$t('settings.ad_sync_failed')"
              :description="adLastSync.error"
              :showCloseButton="false"
            />
            <p v-else-if="adLastSync" class="mg-bottom" id="ad-sync-status">
              {{
                $t("settings.ad_sync_status", {
                  time: new Date(adLastSync.time * 1000).toLocaleString(),
                  members: adLastSync.members,
                })
              }}
            </p>
            <NsInlineNotification
              v-if="error.syncAccounts"
              kind="error"
              :title="$t('action.sync-accounts')"
              :description="error.syncAccounts"
              :showCloseButton="false"
            />
            <NsButton
              kind="secondary"
              :icon="Restart20"
              :loading="loading.syncAccounts"
              :disabled="loading.getConfiguration || loading.syncAccounts"
              @click="syncAccounts"
              >{{ $t("settings.ad_sync_now") }}</NsButton
            >
          </div>
          <NsInlineNotification
            v-if="error.resetDatabase"
            kind="error"
            :title="$t('action.reset-database')"
            :description="error.resetDatabase"
            :showCloseButton="false"
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
              v-if="account.enabled"
              :id="'account-password-' + account.username"
              :label="$t('settings.password')"
              :value="account.password"
              type="password"
              readonly
            />
            <cv-text-input
              v-else
              :id="'account-password-' + account.username"
              :label="$t('settings.password')"
              :value="$t('settings.account_locked')"
              readonly
            />
            <cv-text-input
              :id="'account-database-' + account.username"
              :label="$t('settings.database_name')"
              :value="account.database"
              readonly
            />
            <div class="account-meta">
              <cv-tag
                :id="'account-source-' + account.username"
                :kind="account.source === 'ad' ? 'blue' : 'gray'"
                :label="
                  account.source === 'ad'
                    ? $t('settings.source_ad')
                    : $t('settings.source_manual')
                "
              />
              <cv-tag
                v-if="!account.enabled"
                kind="red"
                :label="$t('settings.account_locked_tag')"
              />
            </div>
            <div class="account-actions">
              <NsButton
                v-if="account.enabled"
                kind="ghost"
                size="small"
                :icon="Reset20"
                :disabled="loading.getConfiguration"
                @click="showResetModal(account)"
                >{{ $t("settings.reset_database") }}</NsButton
              >
              <NsButton
                v-if="account.source !== 'ad' || !account.enabled"
                kind="danger--ghost"
                size="small"
                :icon="TrashCan20"
                :disabled="loading.getConfiguration"
                @click="showRemoveModal(account)"
                >{{ $t("settings.remove_account") }}</NsButton
              >
            </div>
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
    <!-- reset database -->
    <NsModal
      kind="danger"
      size="default"
      :visible="isResetModalShown"
      :isLoading="loading.resetDatabase"
      :primary-button-disabled="loading.resetDatabase"
      :autoHideOff="loading.resetDatabase"
      @modal-hidden="isResetModalShown = false"
      @secondary-click="isResetModalShown = false"
      @primary-click="resetDatabase"
    >
      <template slot="title">{{
        $t("settings.reset_database_title", {
          database: accountToReset.database,
        })
      }}</template>
      <template slot="content">
        <NsInlineNotification
          kind="warning"
          :title="$t('settings.remove_account_database_warning')"
          :showCloseButton="false"
        />
        <p>{{ $t("settings.reset_database_description") }}</p>
      </template>
      <template slot="secondary-button">{{ $t("settings.cancel") }}</template>
      <template slot="primary-button">{{
        $t("settings.reset_database")
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
      isResetModalShown: false,
      accountToReset: {
        username: "",
        database: "",
      },
      adEnabled: false,
      adConfigured: false,
      adDomain: "",
      adDomains: [],
      adGroup: "",
      adNestedGroups: false,
      adLastSync: null,
      loading: {
        getConfiguration: false,
        configureModule: false,
        addAccount: false,
        removeAccount: false,
        resetDatabase: false,
        syncAccounts: false,
        listUserDomains: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        addAccount: "",
        removeAccount: "",
        resetDatabase: "",
        syncAccounts: "",
        listUserDomains: "",
        ad_domain: "",
        ad_group: "",
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
    this.listUserDomains();
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
      this.adEnabled = config.ad_enabled;
      this.adConfigured = config.ad_enabled;
      this.adDomain = config.ad_domain;
      this.adGroup = config.ad_group;
      this.adNestedGroups = config.ad_nested_groups;
      this.adLastSync = config.ad_last_sync;

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
      if (this.adEnabled && !this.adDomain) {
        this.error.ad_domain = "settings.ad_domain_required";
        if (isValidationOk) {
          this.focusElement("ad_domain");
        }
        isValidationOk = false;
      }
      if (this.adEnabled && !this.adGroup) {
        this.error.ad_group = "settings.ad_group_required";
        if (isValidationOk) {
          this.focusElement("ad_group");
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
          ad_enabled: this.adEnabled,
          ad_domain: this.adDomain,
          ad_group: this.adGroup,
          ad_nested_groups: this.adNestedGroups,
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
    showResetModal(account) {
      this.accountToReset = account;
      this.error.resetDatabase = "";
      this.isResetModalShown = true;
    },
    async resetDatabase() {
      this.loading.resetDatabase = true;
      this.error.resetDatabase = "";
      const err = await this.runTask(
        "reset-database",
        { username: this.accountToReset.username },
        {
          aborted: this.resetDatabaseAborted,
          completed: this.resetDatabaseCompleted,
        }
      );
      if (err) {
        console.error("error creating task reset-database", err);
        this.error.resetDatabase = this.getErrorMessage(err);
        this.loading.resetDatabase = false;
        this.isResetModalShown = false;
      }
    },
    resetDatabaseAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.error.resetDatabase = this.$t("error.generic_error");
      this.loading.resetDatabase = false;
      this.isResetModalShown = false;
    },
    resetDatabaseCompleted() {
      this.loading.resetDatabase = false;
      this.isResetModalShown = false;
    },
    async syncAccounts() {
      this.loading.syncAccounts = true;
      this.error.syncAccounts = "";
      const err = await this.runTask("sync-accounts", undefined, {
        aborted: this.syncAccountsAborted,
        completed: this.syncAccountsCompleted,
      });
      if (err) {
        console.error("error creating task sync-accounts", err);
        this.error.syncAccounts = this.getErrorMessage(err);
        this.loading.syncAccounts = false;
      }
    },
    syncAccountsAborted(taskResult, taskContext) {
      console.error(`${taskContext.action} aborted`, taskResult);
      this.loading.syncAccounts = false;
      // The task stores its error; show it with the account list
      this.getConfiguration();
    },
    syncAccountsCompleted() {
      this.loading.syncAccounts = false;
      this.getConfiguration();
    },
    async listUserDomains() {
      this.loading.listUserDomains = true;
      this.error.listUserDomains = "";
      const action = "list-user-domains";
      const eventId = this.getUuid();
      this.core.$root.$once(`${action}-aborted-${eventId}`, () => {
        this.error.listUserDomains = this.$t("error.generic_error");
        this.loading.listUserDomains = false;
      });
      this.core.$root.$once(
        `${action}-completed-${eventId}`,
        (taskContext, taskResult) => {
          this.adDomains = taskResult.output.domains
            .filter((domain) => domain.schema === "ad")
            .map((domain) => ({
              name: domain.name,
              label: domain.name,
              value: domain.name,
            }));
          this.loading.listUserDomains = false;
        }
      );
      const res = await to(
        this.createClusterTaskForApp({
          action,
          extra: {
            title: this.$t("action." + action),
            isNotificationHidden: true,
            eventId,
          },
        })
      );
      if (res[0]) {
        console.error(`error creating task ${action}`, res[0]);
        this.error.listUserDomains = this.getErrorMessage(res[0]);
        this.loading.listUserDomains = false;
      }
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

.account-meta,
.account-actions {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-03;
  align-items: center;
}

.helper {
  max-width: 38rem;
}
</style>
