#
# SPDX-License-Identifier: GPL-3.0-or-later
#

import base64
import http.server
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import unittest.mock
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "imageroot" / "pypkg"))

import livesync_ad  # noqa: E402
import livesync_setup  # noqa: E402


class FakeCouchDB(http.server.ThreadingHTTPServer):
    """Just enough of the CouchDB HTTP API for the provisioning calls."""

    def __init__(self, admin):
        super().__init__(("127.0.0.1", 0), FakeHandler)
        self.admin = admin
        self.users = {}
        self.databases = {}
        self.requests = []

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class FakeHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def handle_any(self):
        server = self.server
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        path = urllib.parse.unquote(self.path)
        server.requests.append((self.command, path, body))

        expected = "Basic " + base64.b64encode(
            f"{server.admin[0]}:{server.admin[1]}".encode()
        ).decode()
        if self.headers.get("Authorization") != expected:
            return self.reply(401, {"error": "unauthorized"})

        if path == "/_up":
            return self.reply(200, {"status": "ok"})
        if path.startswith("/_users/org.couchdb.user:"):
            name = path.split("?")[0].rsplit(":", 1)[1]
            if self.command == "DELETE":
                if name not in server.users:
                    return self.reply(404, {"error": "not_found"})
                if f"rev={server.users[name]['_rev']}" not in path:
                    return self.reply(409, {"error": "conflict"})
                del server.users[name]
                return self.reply(200, {"ok": True})
            if self.command == "GET":
                if name not in server.users:
                    return self.reply(404, {"error": "not_found"})
                return self.reply(200, server.users[name])
            current = server.users.get(name)
            if current and body.get("_rev") != current["_rev"]:
                return self.reply(409, {"error": "conflict"})
            revision = (int(current["_rev"].split("-")[0]) + 1) if current else 1
            server.users[name] = dict(body, _rev=f"{revision}-x")
            return self.reply(201, {"ok": True})
        parts = path.strip("/").split("/")
        database = parts[0]
        if len(parts) == 1 and self.command == "DELETE":
            if server.databases.pop(database, None) is None:
                return self.reply(404, {"error": "not_found"})
            return self.reply(200, {"ok": True})
        if len(parts) == 1 and self.command == "PUT":
            if database in server.databases:
                return self.reply(412, {"error": "file_exists"})
            server.databases[database] = {}
            return self.reply(201, {"ok": True})
        if len(parts) == 2 and parts[1] == "_security":
            if database not in server.databases:
                return self.reply(404, {"error": "not_found"})
            if self.command == "GET":
                return self.reply(200, server.databases[database])
            server.databases[database] = body
            return self.reply(200, {"ok": True})
        return self.reply(400, {"error": "unexpected"})

    do_GET = do_PUT = do_DELETE = handle_any


def account(username, password, database):
    return {"username": username, "password": password, "database": database}


class ProvisioningTest(unittest.TestCase):
    ADMIN = ("admin", "admin-secret")

    def setUp(self):
        self.server = FakeCouchDB(self.ADMIN)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client = livesync_setup.CouchDB(self.server.url, *self.ADMIN)

    def test_creates_account_database_and_access(self):
        livesync_setup.provision(self.client, [account("livesync", "pw1", "obsidiannotes")])

        user = self.server.users["livesync"]
        self.assertEqual(user["password"], "pw1")
        self.assertEqual(user["type"], "user")
        self.assertEqual(user["roles"], [])
        security = self.server.databases["obsidiannotes"]
        self.assertEqual(security["admins"]["names"], ["livesync"])
        self.assertEqual(security["members"]["names"], ["livesync"])

    def test_repeated_run_keeps_existing_access_and_roles(self):
        livesync_setup.provision(self.client, [account("livesync", "pw1", "obsidiannotes")])
        self.server.users["livesync"]["roles"] = ["extra"]
        self.server.databases["obsidiannotes"]["members"]["names"].append("other")

        livesync_setup.provision(self.client, [account("livesync", "pw2", "obsidiannotes")])

        user = self.server.users["livesync"]
        self.assertEqual(user["password"], "pw2")
        self.assertEqual(user["roles"], ["extra"])
        self.assertEqual(
            self.server.databases["obsidiannotes"]["members"]["names"],
            ["livesync", "other"],
        )
        security_writes = [
            r for r in self.server.requests if r[0] == "PUT" and r[1].endswith("/_security")
        ]
        self.assertEqual(len(security_writes), 1, "unchanged security must not be rewritten")

    def test_accounts_only_reach_their_own_database(self):
        livesync_setup.provision(
            self.client, [account("alice", "a", "alice-db"), account("bob", "b", "bob-db")]
        )
        self.assertEqual(self.server.databases["alice-db"]["admins"]["names"], ["alice"])
        self.assertEqual(self.server.databases["bob-db"]["members"]["names"], ["bob"])

    def test_remove_account_keeps_database_without_access(self):
        alice = account("alice", "a", "alice-db")
        livesync_setup.provision(self.client, [alice])
        self.server.databases["alice-db"]["members"]["names"].append("other")
        livesync_setup.remove_account(self.client, alice, delete_data=False)
        self.assertNotIn("alice", self.server.users)
        security = self.server.databases["alice-db"]
        self.assertEqual(security["admins"]["names"], [])
        self.assertEqual(security["members"]["names"], ["other"])

    def test_remove_account_with_database(self):
        alice = account("alice", "a", "alice-db")
        livesync_setup.provision(self.client, [alice])
        livesync_setup.remove_account(self.client, alice, delete_data=True)
        self.assertNotIn("alice", self.server.users)
        self.assertNotIn("alice-db", self.server.databases)

    def test_remove_is_idempotent(self):
        # A retry after a partly failed removal must not fail
        alice = account("alice", "a", "alice-db")
        livesync_setup.remove_account(self.client, alice, delete_data=True)
        livesync_setup.remove_account(self.client, alice, delete_data=False)

    def test_wrong_admin_password_fails_clearly(self):
        client = livesync_setup.CouchDB(self.server.url, "admin", "wrong")
        with self.assertRaisesRegex(livesync_setup.ProvisioningError, "HTTP 401"):
            livesync_setup.wait_until_up(client, timeout=0, sleep=lambda _: None)

    def test_unreachable_server_times_out(self):
        self.server.shutdown()
        self.server.server_close()
        now = [0]

        def sleep(seconds):
            now[0] += seconds

        with self.assertRaisesRegex(livesync_setup.ProvisioningError, "did not become ready"):
            livesync_setup.wait_until_up(
                self.client, timeout=5, interval=1, clock=lambda: now[0], sleep=sleep
            )


class ADSyncTest(unittest.TestCase):
    ADMIN = ("admin", "admin-secret")

    def setUp(self):
        self.server = FakeCouchDB(self.ADMIN)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.client = livesync_setup.CouchDB(self.server.url, *self.ADMIN)
        self.saved = []
        self.accounts = [dict(account("livesync", "pw", "obsidiannotes"), source="manual", enabled=True)]
        livesync_setup.provision(self.client, self.accounts)

    def sync(self, members):
        return livesync_setup.sync_ad_accounts(
            self.client, self.accounts, set(members), lambda a: self.saved.append(json.dumps(a))
        )

    def by_name(self, name):
        return next(a for a in self.accounts if a["username"] == name)

    def test_members_get_accounts_with_own_database(self):
        report = self.sync({"anna", "bert.b"})
        self.assertEqual(report["created"], ["anna", "bert.b"])
        anna = self.by_name("anna")
        self.assertEqual((anna["database"], anna["source"], anna["enabled"]), ("notes-anna", "ad", True))
        self.assertEqual(self.by_name("bert.b")["database"], "notes-bert_b")
        self.assertEqual(self.server.users["anna"]["password"], anna["password"])
        self.assertEqual(self.server.databases["notes-anna"]["admins"]["names"], ["anna"])
        self.assertEqual(len(self.saved), 2, "saved after every change")

    def test_repeated_sync_changes_nothing(self):
        self.sync({"anna"})
        requests = len(self.server.requests)
        report = self.sync({"anna"})
        self.assertEqual(report, {"created": [], "enabled": [], "disabled": [], "skipped": []})
        self.assertEqual(len(self.server.requests), requests, "no CouchDB calls without changes")

    def test_leaving_the_group_locks_out_but_keeps_the_database(self):
        self.sync({"anna"})
        report = self.sync(set())
        self.assertEqual(report["disabled"], ["anna"])
        anna = self.by_name("anna")
        self.assertEqual((anna["enabled"], anna["password"]), (False, ""))
        self.assertNotIn("anna", self.server.users)
        self.assertIn("notes-anna", self.server.databases)
        self.assertEqual(self.server.databases["notes-anna"]["admins"]["names"], [])
        # manual accounts are never touched by the sync
        self.assertTrue(self.by_name("livesync")["enabled"])
        self.assertIn("livesync", self.server.users)

    def test_rejoining_gets_the_old_database_and_a_new_password(self):
        self.sync({"anna"})
        old_password = self.by_name("anna")["password"]
        self.sync(set())
        report = self.sync({"anna"})
        self.assertEqual(report["enabled"], ["anna"])
        anna = self.by_name("anna")
        self.assertEqual(anna["database"], "notes-anna")
        self.assertNotEqual(anna["password"], old_password)
        self.assertEqual(self.server.users["anna"]["password"], anna["password"])
        self.assertEqual(self.server.databases["notes-anna"]["admins"]["names"], ["anna"])

    def test_conflicts_are_skipped(self):
        self.accounts.append(dict(account("other", "x", "notes-carl"), source="manual", enabled=True))
        report = self.sync({"livesync", "carl", "admin", "_bad"})
        reasons = {item["username"]: item["reason"] for item in report["skipped"]}
        self.assertEqual(reasons, {
            "livesync": "manual_account_exists",
            "carl": "database_in_use",
            "admin": "invalid_name",
            "_bad": "invalid_name",
        })
        self.assertEqual(report["created"], [])

    def test_provision_skips_disabled_accounts(self):
        self.sync({"anna"})
        self.sync(set())
        livesync_setup.provision(self.client, self.accounts)
        self.assertNotIn("anna", self.server.users)

    def test_reset_database_gives_an_empty_database(self):
        self.sync({"anna"})
        self.server.databases["notes-anna"]["members"]["names"].append("x")
        livesync_setup.reset_database(self.client, self.by_name("anna"))
        self.assertEqual(self.server.databases["notes-anna"]["admins"]["names"], ["anna"])
        self.assertEqual(self.server.databases["notes-anna"]["members"]["names"], ["anna"])
        deletes = [r for r in self.server.requests if r[0] == "DELETE" and r[1] == "/notes-anna"]
        self.assertEqual(len(deletes), 1)

    def test_turning_ad_off_keeps_active_accounts_working(self):
        self.sync({"anna", "bert"})
        self.sync({"anna"})
        self.assertTrue(livesync_setup.release_ad_accounts(self.accounts))
        self.assertEqual(self.by_name("anna")["source"], "manual")
        self.assertEqual((self.by_name("bert")["source"], self.by_name("bert")["enabled"]), ("ad", False))
        self.assertFalse(livesync_setup.release_ad_accounts(self.accounts))


class ADRunSyncTest(unittest.TestCase):
    """run_sync with a fake member lookup: settings, status file, errors."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = directory.name
        self.server = FakeCouchDB(("admin", "secret"))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        with open(os.path.join(self.state, "couchdb.env"), "w", encoding="utf-8") as stream:
            stream.write("COUCHDB_USER=admin\nCOUCHDB_PASSWORD=secret\n")
        environment = {
            "TCP_PORT": str(self.server.server_address[1]),
            "LIVESYNC_AD_DOMAIN": "ad.test",
            "LIVESYNC_AD_GROUP": "obsidian",
            "LIVESYNC_AD_NESTED": "True",
        }
        patcher = unittest.mock.patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_sync_uses_the_settings_and_records_the_outcome(self):
        calls = []

        def lookup(domain, group, nested):
            calls.append((domain, group, nested))
            return {"anna"}

        report = livesync_ad.run_sync(self.state, lookup)
        self.assertEqual(calls, [("ad.test", "obsidian", True)])
        self.assertEqual(report["created"], ["anna"])
        names = [a["username"] for a in livesync_setup.read_accounts(self.state)]
        self.assertEqual(names, ["livesync", "anna"])
        status = livesync_ad.read_status(self.state)
        self.assertTrue(status["ok"])
        self.assertEqual(status["members"], 1)

    def test_failed_lookup_changes_nothing_and_is_recorded(self):
        livesync_ad.run_sync(self.state, lambda *args: {"anna"})

        def broken(*args):
            raise livesync_ad.ADError("The AD group 'obsidian' was not found exactly once.")

        with self.assertRaises(livesync_ad.ADError):
            livesync_ad.run_sync(self.state, broken)
        anna = next(a for a in livesync_setup.read_accounts(self.state) if a["username"] == "anna")
        self.assertTrue(anna["enabled"], "a failed lookup must not lock anybody out")
        status = livesync_ad.read_status(self.state)
        self.assertFalse(status["ok"])
        self.assertIn("not found", status["error"])

    def test_off_when_not_configured(self):
        with unittest.mock.patch.dict(os.environ, {"LIVESYNC_AD_DOMAIN": ""}):
            self.assertIsNone(livesync_ad.run_sync(self.state, lambda *args: {"anna"}))
        self.assertIsNone(livesync_ad.read_status(self.state))


class ADFilterTest(unittest.TestCase):
    def test_member_names_accepts_list_and_plain_values(self):
        results = [
            {"type": "searchResEntry", "attributes": {"sAMAccountName": ["Anna"]}},
            {"type": "searchResEntry", "attributes": {"sAMAccountName": "bert.b"}},
            {"type": "searchResEntry", "attributes": {"sAMAccountName": []}},
            {"type": "searchResRef", "uri": ["ldap://elsewhere"]},
        ]
        self.assertEqual(livesync_ad.member_names(results), {"anna", "bert.b"})

    def test_filter_escapes_the_group_and_excludes_disabled_users(self):
        dn = "CN=Obsidian (Sync),CN=Users,DC=ad,DC=test"
        direct = livesync_ad.members_filter(dn, nested=False, hidden_users_clause="(!(|(sAMAccountName=krbtgt)))")
        self.assertIn(r"(memberOf=CN=Obsidian \28Sync\29,CN=Users,DC=ad,DC=test)", direct)
        self.assertIn("(!(userAccountControl:1.2.840.113556.1.4.803:=2))", direct)
        self.assertTrue(direct.endswith("(!(|(sAMAccountName=krbtgt))))"))
        nested = livesync_ad.members_filter(dn, nested=True)
        self.assertIn("memberOf:1.2.840.113556.1.4.1941:=", nested)


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = directory.name

    def path(self, name):
        return os.path.join(self.state, name)

    def mode(self, name):
        return stat.S_IMODE(os.stat(self.path(name)).st_mode)

    def test_generates_private_admin_once(self):
        admin = livesync_setup.ensure_admin_credentials(self.state)
        self.assertEqual(admin[0], "admin")
        self.assertGreaterEqual(len(admin[1]), 32)
        self.assertEqual(self.mode("couchdb.env"), 0o600)
        self.assertEqual(livesync_setup.ensure_admin_credentials(self.state), admin)

    def test_keeps_restored_admin(self):
        with open(self.path("couchdb.env"), "w", encoding="utf-8") as stream:
            stream.write("COUCHDB_USER=admin\nCOUCHDB_PASSWORD=restored=value\n")
        os.chmod(self.path("couchdb.env"), 0o644)
        self.assertEqual(livesync_setup.ensure_admin_credentials(self.state), ("admin", "restored=value"))
        self.assertEqual(self.mode("couchdb.env"), 0o600)

    def test_env_file_has_no_quoting(self):
        livesync_setup.ensure_admin_credentials(self.state)
        with open(self.path("couchdb.env"), encoding="utf-8") as stream:
            content = stream.read()
        # podman --env-file takes values literally
        self.assertRegex(content, r"\ACOUCHDB_USER=admin\nCOUCHDB_PASSWORD=[A-Za-z0-9_-]+\n\Z")

    def test_default_account_is_created_once(self):
        accounts = livesync_setup.ensure_accounts("vault", self.state)
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["username"], "livesync")
        self.assertEqual(accounts[0]["database"], "vault")
        self.assertGreaterEqual(len(accounts[0]["password"]), 32)
        self.assertEqual(self.mode("accounts.json"), 0o600)
        self.assertEqual(livesync_setup.ensure_accounts("other", self.state), accounts)

    def test_deleting_all_accounts_is_respected(self):
        livesync_setup.ensure_accounts(None, self.state)
        livesync_setup.write_accounts([], self.state)
        self.assertEqual(livesync_setup.ensure_accounts(None, self.state), [])

    def test_migrates_the_0_1_0_account(self):
        with open(self.path("sync.env"), "w", encoding="utf-8") as stream:
            stream.write("LIVESYNC_USER=livesync\nLIVESYNC_PASSWORD=old-secret\n")
        accounts = livesync_setup.ensure_accounts("mynotes", self.state)
        self.assertEqual(accounts, [account("livesync", "old-secret", "mynotes")])
        self.assertFalse(os.path.exists(self.path("sync.env")))
        self.assertFalse(livesync_setup.migrate_legacy_account("mynotes", self.state))

    def test_migration_does_not_overwrite_existing_accounts(self):
        livesync_setup.write_accounts([account("alice", "a", "alice-db")], self.state)
        with open(self.path("sync.env"), "w", encoding="utf-8") as stream:
            stream.write("LIVESYNC_USER=livesync\nLIVESYNC_PASSWORD=old\n")
        self.assertTrue(livesync_setup.migrate_legacy_account(None, self.state))
        self.assertEqual(livesync_setup.read_accounts(self.state), [account("alice", "a", "alice-db")])

    def test_lock_is_reentrant_across_calls(self):
        with livesync_setup.accounts_lock(self.state):
            pass
        with livesync_setup.accounts_lock(self.state):
            livesync_setup.ensure_accounts(None, self.state)


class AccountValidationTest(unittest.TestCase):
    EXISTING = [account("livesync", "x", "obsidiannotes")]

    def errors(self, username, database):
        return [
            (error["parameter"], error["error"])
            for error in livesync_setup.account_errors(self.EXISTING, username, database)
        ]

    def test_valid_new_account(self):
        self.assertEqual(self.errors("alice", "alice-notes"), [])

    def test_duplicates_and_reserved_names(self):
        self.assertEqual(self.errors("livesync", "other"), [("username", "username_exists")])
        self.assertEqual(self.errors("alice", "obsidiannotes"), [("database", "database_in_use")])
        self.assertEqual(self.errors("admin", "x"), [("username", "username_invalid")])

    def test_invalid_names(self):
        for name in ("", "Alice", "_alice", "a:b", "1a", "a" * 65):
            self.assertIn(("username", "username_invalid"), self.errors(name, "db"), name)
        self.assertEqual(self.errors("alice", "Bad"), [("database", "database_pattern")])

    def test_schema_uses_the_same_username_pattern(self):
        schema = json.loads(
            (ROOT / "imageroot/actions/add-account/validate-input.json").read_text()
        )
        self.assertEqual(
            schema["properties"]["username"]["pattern"], livesync_setup.USERNAME_PATTERN.pattern
        )
        self.assertEqual(
            schema["properties"]["database"]["pattern"], livesync_setup.DATABASE_PATTERN.pattern
        )


class DatabaseNameTest(unittest.TestCase):
    def test_names(self):
        for name in ("obsidiannotes", "vault_2", "a(b)+c-$"):
            self.assertTrue(livesync_setup.valid_database(name), name)
        for name in ("", "Notes", "_users", "1vault", "a/b", "a" * 239):
            self.assertFalse(livesync_setup.valid_database(name), name)

    def test_schema_uses_the_same_pattern(self):
        schema = json.loads(
            (ROOT / "imageroot/actions/configure-module/validate-input.json").read_text()
        )
        database = schema["properties"]["database"]
        self.assertEqual(database["pattern"], livesync_setup.DATABASE_PATTERN.pattern)
        self.assertEqual(database["maxLength"], livesync_setup.DATABASE_MAX_LENGTH)


class ServerSettingsTest(unittest.TestCase):
    """The static ini must carry every setting of the plugin's provision.ts."""

    def test_livesync_settings(self):
        import configparser

        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ROOT / "imageroot/etc/livesync.ini")
        expected = {
            ("chttpd", "require_valid_user"): "true",
            ("chttpd_auth", "require_valid_user"): "true",
            ("httpd", "WWW-Authenticate"): 'Basic realm="couchdb"',
            ("httpd", "enable_cors"): "true",
            ("chttpd", "enable_cors"): "true",
            ("chttpd", "max_http_request_size"): "4294967296",
            ("couchdb", "max_document_size"): "50000000",
            ("cors", "credentials"): "true",
            ("cors", "origins"): "app://obsidian.md,capacitor://localhost,http://localhost",
            ("couchdb", "single_node"): "true",
        }
        for (section, key), value in expected.items():
            self.assertEqual(parser.get(section, key), value, f"[{section}] {key}")


if __name__ == "__main__":
    unittest.main()
