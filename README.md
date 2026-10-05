# ns8-obsidian-livesync

NethServer 8 module that runs a [CouchDB](https://couchdb.apache.org/) server
prepared for the [Self-hosted LiveSync](https://github.com/vrtmrz/obsidian-livesync)
plugin for Obsidian.

The server settings follow the plugin's own provisioning tool
(`utils/couchdb/provision.ts`, checked at commit
[`66bd811`](https://github.com/vrtmrz/obsidian-livesync/tree/66bd811b0802f988f1329359f79751379876d1cd)):
single-node CouchDB, authentication required for every request, CORS for
`app://obsidian.md`, `capacitor://localhost` and `http://localhost`, 4 GiB
maximum request size and 50 MB maximum document size. They are in
[`imageroot/etc/livesync.ini`](imageroot/etc/livesync.ini).

What the module adds on top of a plain CouchDB container:

- a CouchDB administrator with a generated password;
- sync accounts for the plugin, each with a database of its own: an account
  is administrator of its database only and has no server-wide rights. The
  first account `livesync` with database `obsidiannotes` is created on the
  first configuration; more can be added and deleted on the settings page,
  or created automatically for the members of an AD group;
- a Traefik route with optional Let's Encrypt certificate;
- NS8 backup and restore of the databases, the CouchDB runtime configuration
  and both credentials.

## Install

Install a fixed version, so that the Software Center offers later updates:

```
add-module ghcr.io/platypuschan/obsidian-livesync:0.1.0 1
```

The output of the command returns the instance name, for example
`obsidian-livesync1`.

## Configure

Open the module in cluster-admin and set the host name on the **Settings**
page. Obsidian on iOS and Android only connects to servers with a valid
certificate, so request a Let's Encrypt certificate (or provide another
trusted one for this host).

The same configuration from the command line:

```
api-cli run module/obsidian-livesync1/configure-module --data '{"host": "livesync.example.org", "http2https": true, "lets_encrypt": true}'
```

`database` (optional) only names the database of the first account and is
ignored once the accounts exist.

## Sync accounts

The **Settings** page lists the sync accounts below the server settings,
with the Server URI and, per account, user name, password (shown on click)
and database. Use one database per vault.

- **Add account**: enter a user name and a database name; the password is
  generated. A database name that is not in use by another account is
  created, or taken over if it already exists (for example after an account
  was deleted without its database).
- **Delete**: removes the CouchDB user. Its database is kept and then only
  reachable by the administrator, unless *Also delete the database* is
  checked.

The same from the command line:

```
api-cli run module/obsidian-livesync1/get-configuration
api-cli run module/obsidian-livesync1/add-account --data '{"username": "alice", "database": "alice-notes"}'
api-cli run module/obsidian-livesync1/remove-account --data '{"username": "alice", "delete_database": false}'
```

## Accounts from an AD group

Instead of (or next to) manual accounts, the members of a group of an NS8
Active Directory account domain can get accounts automatically. Enable
*Accounts from an AD group* on the settings page and choose the domain and
the group (optionally including nested groups).

- Every enabled member gets an account named after the AD user name
  (lower case) with the database `notes-<user name>` (`.` becomes `_`) and a
  generated password, shown on the settings page. The AD password is not
  used: Obsidian stores the sync password on every device.
- A user who leaves the group, or whose AD account is disabled, is locked
  out: the CouchDB user is deleted and the account is shown as locked. The
  database is kept. A user who joins again gets the same database and a new
  password.
- Locked accounts can be deleted, with or without their database. Accounts
  of current group members can't be deleted here; remove the user from the
  group instead.
- The sync runs every 5 minutes, after saving the settings, and on *Sync
  with AD now*. If the domain can't be read, nothing changes and the
  settings page shows the error.
- Turning the option off keeps the active accounts working as manual ones.

```
api-cli run module/obsidian-livesync1/configure-module --data '{"host": "livesync.example.org", "http2https": true, "lets_encrypt": true, "ad_enabled": true, "ad_domain": "ad.example.org", "ad_group": "obsidian-users", "ad_nested_groups": false}'
api-cli run module/obsidian-livesync1/sync-accounts
```

## Reset a database

*Reset database* replaces an account's database with an empty one of the
same name; the account and its password stay. Afterwards upload the vault
again from one device: in Self-hosted LiveSync, rebuild the remote database
from that device; the other devices then fetch it again.

```
api-cli run module/obsidian-livesync1/reset-database --data '{"username": "alice"}'
```

## Connect Obsidian

In Obsidian, install *Self-hosted LiveSync*, choose CouchDB as remote type
and enter the Server URI (`https://<host>`) and the user name, password and
database of one account (see the plugin's
[quick setup](https://github.com/vrtmrz/obsidian-livesync/blob/main/docs/quick_setup.md)).
Enable end-to-end encryption in the plugin. Its passphrase is never sent to
this server and cannot be recovered here. After the first device works,
generate a Setup URI in the plugin to add more devices.

## Administration

The CouchDB web interface Fauxton is at `https://<host>/_utils/`. Log in with
the administrator account:

```
runagent -m obsidian-livesync1 cat couchdb.env
```

The administrator password is generated on the first configuration and only
read by CouchDB on its first start; changing `couchdb.env` later has no
effect. Change it in Fauxton instead and update `couchdb.env` to match, so
that the module can still manage the accounts.

Settings changed in Fauxton are written to the `couchdb-etc` volume and take
precedence over `livesync.ini`.

## Backup and restore

The NS8 backup includes the volumes `couchdb-data` (databases) and
`couchdb-etc` (runtime configuration with the hashed administrator password),
plus `couchdb.env` and `accounts.json` (credentials). CouchDB writes its database
files append-only, so the running server can be backed up
([CouchDB documentation](https://docs.couchdb.org/en/stable/maintenance/backups.html)).
A restored instance keeps the same credentials, so the Obsidian clients only
need the new host name if it changed. Release 0.1.0 kept its single account
in `sync.env`; updates and restores move it into `accounts.json`.

## Uninstall

```
remove-module --no-preserve obsidian-livesync1
```

## Testing

The QEMU test suites run on Rocky Linux 9 and Debian 13. `tests/livesync.robot`
covers two scenarios:

- `install`: install the image under test.
- `update`: install the last published release (`.github/scripts/previous-release`)
  and update it to the image under test. Before the first release there is
  nothing to update from, so this scenario is skipped with a notice.

`tests/00__ad_sync.robot` (install scenario, runs first) provisions a Samba AD domain
(`ghcr.io/nethserver/samba`) in the test VM and checks the AD account sync:
accounts for group members, lock-out and kept database after leaving the
group, rejoining, database reset and deletion.

Unit tests (they need `ldap3`, which the NS8 agent environment provides):

```
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Releases

`CATALOG_VERSION` holds the version that a merge to `main` publishes. Every
change to `imageroot/`, `ui/` or `build-images.sh` must raise it; the
*Validate* workflow checks this. After the tests on `main` pass, *Publish
tested catalog version* tags the tested image with that version.
