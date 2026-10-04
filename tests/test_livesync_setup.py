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
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "imageroot" / "pypkg"))

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
            name = path.rsplit(":", 1)[1]
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

    do_GET = do_PUT = handle_any


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
        livesync_setup.provision(self.client, "obsidiannotes", "livesync", "pw1")

        user = self.server.users["livesync"]
        self.assertEqual(user["password"], "pw1")
        self.assertEqual(user["type"], "user")
        self.assertEqual(user["roles"], [])
        security = self.server.databases["obsidiannotes"]
        self.assertEqual(security["admins"]["names"], ["livesync"])
        self.assertEqual(security["members"]["names"], ["livesync"])

    def test_repeated_run_keeps_existing_access_and_roles(self):
        livesync_setup.provision(self.client, "obsidiannotes", "livesync", "pw1")
        self.server.users["livesync"]["roles"] = ["extra"]
        self.server.databases["obsidiannotes"]["members"]["names"].append("other")

        livesync_setup.provision(self.client, "obsidiannotes", "livesync", "pw2")

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

    def test_new_database_keeps_the_old_one(self):
        livesync_setup.provision(self.client, "first", "livesync", "pw")
        livesync_setup.provision(self.client, "second", "livesync", "pw")
        self.assertEqual(set(self.server.databases), {"first", "second"})

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


class CredentialsTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = directory.name

    def mode(self, name):
        return stat.S_IMODE(os.stat(os.path.join(self.state, name)).st_mode)

    def test_generates_private_credentials_once(self):
        admin, sync = livesync_setup.ensure_credentials(self.state)
        self.assertEqual(admin[0], "admin")
        self.assertEqual(sync[0], "livesync")
        self.assertGreaterEqual(len(admin[1]), 32)
        self.assertNotEqual(admin[1], sync[1])
        self.assertEqual(self.mode("couchdb.env"), 0o600)
        self.assertEqual(self.mode("sync.env"), 0o600)

        self.assertEqual(livesync_setup.ensure_credentials(self.state), (admin, sync))
        self.assertEqual(livesync_setup.read_sync_credentials(self.state), sync)

    def test_keeps_restored_credentials(self):
        path = os.path.join(self.state, "couchdb.env")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("COUCHDB_USER=admin\nCOUCHDB_PASSWORD=restored=value\n")
        os.chmod(path, 0o644)
        admin, _ = livesync_setup.ensure_credentials(self.state)
        self.assertEqual(admin, ("admin", "restored=value"))
        self.assertEqual(self.mode("couchdb.env"), 0o600)

    def test_env_file_has_no_quoting(self):
        livesync_setup.ensure_credentials(self.state)
        with open(os.path.join(self.state, "couchdb.env"), encoding="utf-8") as stream:
            content = stream.read()
        # podman --env-file takes values literally
        self.assertRegex(content, r"\ACOUCHDB_USER=admin\nCOUCHDB_PASSWORD=[A-Za-z0-9_-]+\n\Z")


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
