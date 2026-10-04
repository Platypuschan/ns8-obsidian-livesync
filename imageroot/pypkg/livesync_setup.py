#
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Credentials and CouchDB provisioning for the Obsidian LiveSync module.

The server settings themselves are static (etc/livesync.ini). This module
creates the credentials once and prepares the LiveSync database and account,
like utils/couchdb/provision.ts of vrtmrz/obsidian-livesync, but with a
separate account that is not a CouchDB server administrator.
"""

import base64
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
SYNC_ENV = "sync.env"
ADMIN_USER = "admin"
SYNC_USER = "livesync"
DEFAULT_DATABASE = "obsidiannotes"
# CouchDB database name rules as enforced by the plugin's provisioning tool.
DATABASE_PATTERN = re.compile(r"^[a-z][a-z0-9_$()+-]*$")
DATABASE_MAX_LENGTH = 238


class ProvisioningError(Exception):
    pass


def valid_database(name):
    return (
        isinstance(name, str)
        and len(name) <= DATABASE_MAX_LENGTH
        and DATABASE_PATTERN.fullmatch(name) is not None
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


def ensure_credentials(state_dir="."):
    """Create missing credentials; keep existing ones (also after a restore).

    Returns (admin, sync), each a (user, password) tuple.
    """
    admin_path = os.path.join(state_dir, ADMIN_ENV)
    admin = read_env(admin_path)
    if not admin.get("COUCHDB_USER") or not admin.get("COUCHDB_PASSWORD"):
        admin = {"COUCHDB_USER": ADMIN_USER, "COUCHDB_PASSWORD": new_password()}
        write_env(admin_path, admin)
    else:
        os.chmod(admin_path, 0o600)

    sync_path = os.path.join(state_dir, SYNC_ENV)
    sync = read_env(sync_path)
    if not sync.get("LIVESYNC_USER") or not sync.get("LIVESYNC_PASSWORD"):
        sync = {"LIVESYNC_USER": SYNC_USER, "LIVESYNC_PASSWORD": new_password()}
        write_env(sync_path, sync)
    else:
        os.chmod(sync_path, 0o600)

    return (
        (admin["COUCHDB_USER"], admin["COUCHDB_PASSWORD"]),
        (sync["LIVESYNC_USER"], sync["LIVESYNC_PASSWORD"]),
    )


def read_sync_credentials(state_dir="."):
    sync = read_env(os.path.join(state_dir, SYNC_ENV))
    return sync.get("LIVESYNC_USER", ""), sync.get("LIVESYNC_PASSWORD", "")


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


def provision(client, database, user, password):
    wait_until_up(client)
    ensure_user(client, user, password)
    ensure_database(client, database)
    ensure_database_access(client, database, user)
