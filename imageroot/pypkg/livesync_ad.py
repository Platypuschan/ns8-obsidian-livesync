#
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Read the members of an Active Directory group of an NS8 account domain."""

import ipaddress

LDAP_MATCHING_RULE_IN_CHAIN = "1.2.840.113556.1.4.1941"
LDAP_BITWISE_AND = "1.2.840.113556.1.4.803"
ACCOUNTDISABLE = 2


class ADError(Exception):
    """A safe-to-show error; never contains the bind password."""


def members_filter(group_dn, nested, hidden_users_clause=""):
    from ldap3.utils.conv import escape_filter_chars

    dn = escape_filter_chars(group_dn)
    membership = f"(memberOf:{LDAP_MATCHING_RULE_IN_CHAIN}:={dn})" if nested else f"(memberOf={dn})"
    return "".join([
        "(&",
        "(objectCategory=person)",
        "(objectClass=user)",
        membership,
        # Disabled AD users count as not being members
        f"(!(userAccountControl:{LDAP_BITWISE_AND}:={ACCOUNTDISABLE}))",
        hidden_users_clause,
        ")",
    ])


def member_names(results):
    """Lower-case sAMAccountNames from a paged search result.

    Without schema information (get_info=NONE) ldap3 returns every attribute
    as a list, with schema as a plain value; accept both.
    """
    names = set()
    for entry in results:
        if entry.get("type") != "searchResEntry":
            continue
        value = entry.get("attributes", {}).get("sAMAccountName")
        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else None
        if value:
            names.add(str(value).lower())
    return names


def domain_settings(domain_name):
    from agent.ldapproxy import Ldapproxy

    proxy = Ldapproxy()
    domain = proxy.get_domain(domain_name)
    if domain is None:
        raise ADError(f"The account domain {domain_name!r} is not available.")
    if domain.get("schema") != "ad":
        raise ADError(f"The account domain {domain_name!r} is not an Active Directory.")
    host = str(domain.get("host", ""))
    # The NS8 LDAP proxy listens on the node itself; never send the bind
    # credentials anywhere else.
    if host != "localhost":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ADError("NS8 returned a non-loopback LDAP proxy endpoint.")
    return {
        "host": host,
        "port": int(domain["port"]),
        "base_dn": str(domain["base_dn"]),
        "bind_dn": str(domain["bind_dn"]),
        "bind_password": str(domain["bind_password"]),
        "hidden_users_clause": proxy.get_ldap_users_search_filter_clause(domain_name),
    }


def group_members(domain_name, group, nested):
    """Return the lower-case sAMAccountNames of the enabled group members.

    Raises ADError if the domain or the group cannot be read, so a failed
    lookup is never mistaken for an empty group.
    """
    from ldap3 import NONE, SUBTREE, Connection, Server
    from ldap3.utils.conv import escape_filter_chars

    settings = domain_settings(domain_name)
    try:
        server = Server(settings["host"], port=settings["port"], connect_timeout=10, get_info=NONE)
        connection = Connection(
            server,
            user=settings["bind_dn"],
            password=settings["bind_password"],
            auto_bind=True,
            receive_timeout=30,
            raise_exceptions=True,
        )
    except Exception as error:
        raise ADError(f"Cannot connect to the account domain {domain_name!r}: {type(error).__name__}") from None
    try:
        connection.search(
            search_base=settings["base_dn"],
            search_filter=f"(&(objectCategory=group)(sAMAccountName={escape_filter_chars(group)}))",
            search_scope=SUBTREE,
            attributes=["distinguishedName"],
            size_limit=2,
        )
        if len(connection.entries) != 1:
            raise ADError(f"The AD group {group!r} was not found exactly once.")
        group_dn = str(connection.entries[0].entry_dn)
        results = connection.extend.standard.paged_search(
            search_base=settings["base_dn"],
            search_filter=members_filter(group_dn, nested, settings["hidden_users_clause"]),
            search_scope=SUBTREE,
            attributes=["sAMAccountName"],
            paged_size=500,
            generator=False,
        )
        return member_names(results)
    except ADError:
        raise
    except Exception as error:
        raise ADError(f"Reading the AD group {group!r} failed: {type(error).__name__}") from None
    finally:
        connection.unbind()


STATUS_FILE = "ad-sync.json"


def configured():
    """Return (domain, group, nested) or None when AD sync is off."""
    import os

    domain = os.environ.get("LIVESYNC_AD_DOMAIN", "")
    group = os.environ.get("LIVESYNC_AD_GROUP", "")
    if not domain or not group:
        return None
    return domain, group, os.environ.get("LIVESYNC_AD_NESTED", "False") == "True"


def write_status(status, state_dir="."):
    import json
    import os

    path = os.path.join(state_dir, STATUS_FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        json.dump(status, stream)
    os.replace(path + ".tmp", path)


def read_status(state_dir="."):
    import json
    import os

    try:
        with open(os.path.join(state_dir, STATUS_FILE), encoding="utf-8") as stream:
            return json.load(stream)
    except (FileNotFoundError, ValueError):
        return None


def run_sync(state_dir=".", members_lookup=None):
    """Synchronize the AD accounts once. Returns the report, or None if AD
    sync is off. The outcome is also stored for the settings page."""
    import os
    import time

    import livesync_setup

    settings = configured()
    if settings is None:
        return None
    lookup = members_lookup or group_members
    started = time.time()
    try:
        members = lookup(*settings)
        client = livesync_setup.CouchDB(
            "http://127.0.0.1:" + os.environ["TCP_PORT"],
            *livesync_setup.ensure_admin_credentials(state_dir),
        )
        with livesync_setup.accounts_lock(state_dir):
            accounts = livesync_setup.ensure_accounts(os.environ.get("LIVESYNC_DATABASE"), state_dir)
            livesync_setup.wait_until_up(client)
            report = livesync_setup.sync_ad_accounts(
                client, accounts, members,
                lambda changed: livesync_setup.write_accounts(changed, state_dir),
            )
    except (ADError, livesync_setup.ProvisioningError) as error:
        write_status({"time": int(started), "ok": False, "error": str(error)}, state_dir)
        raise
    write_status({"time": int(started), "ok": True, "members": len(members), "report": report}, state_dir)
    return report
