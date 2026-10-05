#
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Credentials and CouchDB provisioning for the Obsidian LiveSync module.

The server settings themselves are static (etc/livesync.ini). This module
creates the administrator credentials once and manages the sync accounts:
each account is a CouchDB user that administers exactly one database of its
own, like utils/couchdb/provision.ts of vrtmrz/obsidian-livesync prepares a
database, but without any server-wide rights.
"""

import base64
import contextlib
import fcntl
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

# Both files live in the module state directory, the working directory of
# actions and of couchdb.service.
ADMIN_ENV = "couchdb.env"
ACCOUNTS = "accounts.json"
# Release 0.1.0 kept its single account here; it is migrated to ACCOUNTS.
LEGACY_SYNC_ENV = "sync.env"
ADMIN_USER = "admin"
DEFAULT_USER = "livesync"
DEFAULT_DATABASE = "obsidiannotes"
# CouchDB database name rules as enforced by the plugin's provisioning tool.
DATABASE_PATTERN = re.compile(r"^[a-z][a-z0-9_$()+-]*$")
DATABASE_MAX_LENGTH = 238
# CouchDB user names must not contain ":" nor start with "_"; keep them simple
# so they can be typed on a phone.
USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
RESERVED_USERNAMES = {ADMIN_USER}
# Accounts are created by hand ("manual") or from the members of an AD
# group ("ad"). An AD account whose user left the group is kept disabled: no
# CouchDB user, no password, its database stays.
SOURCE_MANUAL = "manual"
SOURCE_AD = "ad"
AD_DATABASE_PREFIX = "notes-"


class ProvisioningError(Exception):
    pass


def valid_database(name):
    return (
        isinstance(name, str)
        and len(name) <= DATABASE_MAX_LENGTH
        and DATABASE_PATTERN.fullmatch(name) is not None
    )


def valid_username(name):
    return (
        isinstance(name, str)
        and USERNAME_PATTERN.fullmatch(name) is not None
        and name not in RESERVED_USERNAMES
    )


def read_env(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as stream:
            for line in stream:
                line = line.rstrip("\n")
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key] = value
    except FileNotFoundError:
        pass
    return values


def write_env(path, values):
    """Write a podman/systemd env file readable by the module user only."""
    temporary = path + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def new_password():
    # URL-safe characters only, so the password can be pasted into the plugin
    # and into env files without quoting.
    return secrets.token_urlsafe(24)


def ensure_admin_credentials(state_dir="."):
    """Create the administrator once; keep it (also after a restore).

    Returns (user, password).
    """
    path = os.path.join(state_dir, ADMIN_ENV)
    admin = read_env(path)
    if not admin.get("COUCHDB_USER") or not admin.get("COUCHDB_PASSWORD"):
        admin = {"COUCHDB_USER": ADMIN_USER, "COUCHDB_PASSWORD": new_password()}
        write_env(path, admin)
    else:
        os.chmod(path, 0o600)
    return admin["COUCHDB_USER"], admin["COUCHDB_PASSWORD"]


@contextlib.contextmanager
def accounts_lock(state_dir="."):
    """Serialize changes of the account list between concurrent tasks."""
    path = os.path.join(state_dir, ACCOUNTS + ".lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def read_accounts(state_dir="."):
    """Return the account list, or None if it was never created."""
    try:
        with open(os.path.join(state_dir, ACCOUNTS), "r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError:
        return None


def write_accounts(accounts, state_dir="."):
    path = os.path.join(state_dir, ACCOUNTS)
    temporary = path + ".tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(accounts, stream, indent=2)
        stream.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def migrate_legacy_account(database, state_dir="."):
    """Move the 0.1.0 account from sync.env into accounts.json.

    Returns True if something was migrated.
    """
    legacy_path = os.path.join(state_dir, LEGACY_SYNC_ENV)
    legacy = read_env(legacy_path)
    if not os.path.exists(legacy_path):
        return False
    if read_accounts(state_dir) is None and legacy.get("LIVESYNC_USER") and legacy.get("LIVESYNC_PASSWORD"):
        write_accounts(
            [{
                "username": legacy["LIVESYNC_USER"],
                "password": legacy["LIVESYNC_PASSWORD"],
                "database": database or DEFAULT_DATABASE,
            }],
            state_dir,
        )
    os.remove(legacy_path)
    return True


def ensure_accounts(database=None, state_dir="."):
    """Return the account list; create the default account on first use.

    Once accounts.json exists it is never refilled, so deleting every
    account is respected.
    """
    migrate_legacy_account(database, state_dir)
    accounts = read_accounts(state_dir)
    if accounts is None:
        accounts = [{
            "username": DEFAULT_USER,
            "password": new_password(),
            "database": database or DEFAULT_DATABASE,
            "source": SOURCE_MANUAL,
            "enabled": True,
        }]
        write_accounts(accounts, state_dir)
    else:
        os.chmod(os.path.join(state_dir, ACCOUNTS), 0o600)
    return accounts


def is_ad(account):
    return account.get("source", SOURCE_MANUAL) == SOURCE_AD


def is_enabled(account):
    return account.get("enabled", True)


def ad_database_name(username):
    # "." is valid in user names but not in database names
    return AD_DATABASE_PREFIX + username.replace(".", "_")


def account_errors(accounts, username, database):
    """Validation errors for a new account, in the NS8 validation format."""
    errors = []
    if not valid_username(username):
        errors.append({"field": "username", "parameter": "username", "value": username, "error": "username_invalid"})
    elif any(account["username"] == username for account in accounts):
        errors.append({"field": "username", "parameter": "username", "value": username, "error": "username_exists"})
    if not valid_database(database):
        errors.append({"field": "database", "parameter": "database", "value": database, "error": "database_pattern"})
    elif any(account["database"] == database for account in accounts):
        errors.append({"field": "database", "parameter": "database", "value": database, "error": "database_in_use"})
    return errors


class CouchDB:
    def __init__(self, base_url, user, password, opener=None):
        self.base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.authorization = f"Basic {token}"
        self.opener = opener or urllib.request.urlopen

    def request(self, method, path, body=None):
        """Return (status, decoded JSON body or None). Never raises on HTTP errors."""
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener(request, timeout=30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, raw = error.code, error.read()
        try:
            return status, json.loads(raw) if raw else None
        except ValueError:
            return status, None


def quote(value):
    return urllib.parse.quote(value, safe="")


def wait_until_up(client, timeout=180, interval=2, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    last = "no answer"
    while True:
        try:
            status, body = client.request("GET", "/_up")
            if status == 200:
                return
            last = f"HTTP {status}: {body}"
        except OSError as error:
            last = str(error)
        if clock() >= deadline:
            raise ProvisioningError(f"CouchDB did not become ready: {last}")
        sleep(interval)


def ensure_user(client, user, password):
    path = "/_users/" + quote("org.couchdb.user:" + user)
    status, existing = client.request("GET", path)
    document = {"name": user, "password": password, "roles": [], "type": "user"}
    if status == 200:
        document["_rev"] = existing["_rev"]
        # Keep roles that an administrator added in Fauxton.
        document["roles"] = existing.get("roles", [])
    elif status != 404:
        raise ProvisioningError(f"Reading the {user} account failed with HTTP {status}: {existing}")
    status, body = client.request("PUT", path, document)
    if status not in (201, 202):
        raise ProvisioningError(f"Saving the {user} account failed with HTTP {status}: {body}")


def ensure_database(client, database):
    status, body = client.request("PUT", "/" + quote(database))
    # 412: the database already exists
    if status not in (201, 202, 412):
        raise ProvisioningError(f"Creating database {database} failed with HTTP {status}: {body}")


def ensure_database_access(client, database, user):
    """Make user an administrator of this one database.

    LiveSync writes design and local documents, which needs database admin
    rights. The account stays without any server-wide rights.
    """
    path = "/" + quote(database) + "/_security"
    status, security = client.request("GET", path)
    if status != 200:
        raise ProvisioningError(f"Reading the security of {database} failed with HTTP {status}: {security}")
    security = security or {}
    changed = False
    for section in ("admins", "members"):
        entry = security.setdefault(section, {})
        names = entry.setdefault("names", [])
        entry.setdefault("roles", [])
        if user not in names:
            names.append(user)
            changed = True
    if not changed:
        return
    status, body = client.request("PUT", path, security)
    if status != 200:
        raise ProvisioningError(f"Saving the security of {database} failed with HTTP {status}: {body}")


def provision_account(client, account):
    ensure_user(client, account["username"], account["password"])
    ensure_database(client, account["database"])
    ensure_database_access(client, account["database"], account["username"])


def provision(client, accounts):
    wait_until_up(client)
    for account in accounts:
        if is_enabled(account):
            provision_account(client, account)


def remove_user(client, user):
    path = "/_users/" + quote("org.couchdb.user:" + user)
    status, existing = client.request("GET", path)
    if status == 404:
        return
    if status != 200:
        raise ProvisioningError(f"Reading the {user} account failed with HTTP {status}: {existing}")
    status, body = client.request("DELETE", path + "?rev=" + quote(existing["_rev"]))
    if status not in (200, 202, 404):
        raise ProvisioningError(f"Deleting the {user} account failed with HTTP {status}: {body}")


def revoke_database_access(client, database, user):
    path = "/" + quote(database) + "/_security"
    status, security = client.request("GET", path)
    if status == 404:
        return
    if status != 200:
        raise ProvisioningError(f"Reading the security of {database} failed with HTTP {status}: {security}")
    security = security or {}
    changed = False
    for section in ("admins", "members"):
        names = security.get(section, {}).get("names", [])
        if user in names:
            names.remove(user)
            changed = True
    if not changed:
        return
    status, body = client.request("PUT", path, security)
    if status != 200:
        raise ProvisioningError(f"Saving the security of {database} failed with HTTP {status}: {body}")


def delete_database(client, database):
    status, body = client.request("DELETE", "/" + quote(database))
    if status not in (200, 202, 404):
        raise ProvisioningError(f"Deleting database {database} failed with HTTP {status}: {body}")


def reset_database(client, account):
    """Replace the account's database with an empty one."""
    delete_database(client, account["database"])
    provision_account(client, account)


def disable_account(client, account):
    """Lock an AD account out but keep its database (admin access only)."""
    remove_user(client, account["username"])
    revoke_database_access(client, account["database"], account["username"])
    account["enabled"] = False
    account["password"] = ""


def sync_ad_accounts(client, accounts, members, save):
    """Make the AD accounts match the AD group members.

    accounts is changed in place and passed to save() after every change,
    so a failure halfway keeps what was already done. Returns a report.
    """
    report = {"created": [], "enabled": [], "disabled": [], "skipped": []}
    by_name = {account["username"]: account for account in accounts}
    databases = {account["database"] for account in accounts}

    for name in sorted(members):
        account = by_name.get(name)
        if account is None:
            database = ad_database_name(name)
            if not valid_username(name) or not valid_database(database):
                report["skipped"].append({"username": name, "reason": "invalid_name"})
                continue
            if database in databases:
                report["skipped"].append({"username": name, "reason": "database_in_use"})
                continue
            account = {
                "username": name,
                "password": new_password(),
                "database": database,
                "source": SOURCE_AD,
                "enabled": True,
            }
            provision_account(client, account)
            accounts.append(account)
            by_name[name] = account
            databases.add(database)
            report["created"].append(name)
            save(accounts)
        elif not is_ad(account):
            report["skipped"].append({"username": name, "reason": "manual_account_exists"})
        elif not is_enabled(account):
            # Back in the group: same database, but a new password, so devices
            # that kept the old one do not silently regain access.
            account["password"] = new_password()
            account["enabled"] = True
            provision_account(client, account)
            report["enabled"].append(name)
            save(accounts)

    for account in accounts:
        if is_ad(account) and is_enabled(account) and account["username"] not in members:
            disable_account(client, account)
            report["disabled"].append(account["username"])
            save(accounts)
    return report


def release_ad_accounts(accounts):
    """AD sync turned off: active AD accounts become manual ones and keep
    working; disabled ones stay disabled until they are deleted."""
    changed = False
    for account in accounts:
        if is_ad(account) and is_enabled(account):
            account["source"] = SOURCE_MANUAL
            changed = True
    return changed


def remove_account(client, account, delete_data):
    """Delete the CouchDB user; drop or keep (without access) its database."""
    remove_user(client, account["username"])
    if delete_data:
        delete_database(client, account["database"])
    else:
        revoke_database_access(client, account["database"], account["username"])
