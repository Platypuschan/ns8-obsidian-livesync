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
- a separate `livesync` account for the plugin. It is administrator of the
  vault database only and has no server-wide rights;
- the vault database (default `obsidiannotes`), created on configuration;
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
api-cli run module/obsidian-livesync1/configure-module --data '{"host": "livesync.example.org", "http2https": true, "lets_encrypt": true, "database": "obsidiannotes"}'
```

Changing `database` later creates a new, empty database and gives the
`livesync` account access to it. Existing databases are never deleted.

## Connect Obsidian

After saving, the **Settings** page shows a *Connection for Self-hosted
LiveSync* panel with the values for the plugin:

| Plugin field | Value |
| --- | --- |
| Server URI | `https://<host>` |
| Username | `livesync` |
| Password | shown in the panel |
| Database name | the configured database |

In Obsidian, install *Self-hosted LiveSync*, choose CouchDB as remote type
and enter these values (see the plugin's
[quick setup](https://github.com/vrtmrz/obsidian-livesync/blob/main/docs/quick_setup.md)).
Enable end-to-end encryption in the plugin. Its passphrase is never sent to
this server and cannot be recovered here. After the first device works,
generate a Setup URI in the plugin to add more devices.

The same values from the command line:

```
api-cli run module/obsidian-livesync1/get-configuration
```

Each vault needs its own database. To sync another vault with the same
account, configure that database name in the module (the account keeps
access to the earlier ones), or create the database in Fauxton and add
`livesync` to its admins.

## Administration

The CouchDB web interface Fauxton is at `https://<host>/_utils/`. Log in with
the administrator account:

```
runagent -m obsidian-livesync1 cat couchdb.env
```

The administrator password is generated on the first configuration and only
read by CouchDB on its first start; changing `couchdb.env` later has no
effect. Change it in Fauxton instead and update `couchdb.env` to match, so
that `configure-module` can still provision the database.

Settings changed in Fauxton are written to the `couchdb-etc` volume and take
precedence over `livesync.ini`.

## Backup and restore

The NS8 backup includes the volumes `couchdb-data` (databases) and
`couchdb-etc` (runtime configuration with the hashed administrator password),
plus `couchdb.env` and `sync.env` (credentials). CouchDB writes its database
files append-only, so the running server can be backed up
([CouchDB documentation](https://docs.couchdb.org/en/stable/maintenance/backups.html)).
A restored instance keeps the same credentials, so the Obsidian clients only
need the new host name if it changed.

## Uninstall

```
remove-module --no-preserve obsidian-livesync1
```

## Testing

The QEMU test suite (`tests/livesync.robot`) runs on Rocky Linux 9 and
Debian 13 for two scenarios:

- `install`: install the image under test.
- `update`: install the last published release (`.github/scripts/previous-release`)
  and update it to the image under test. Before the first release there is
  nothing to update from, so this scenario is skipped with a notice.

Unit tests:

```
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Releases

`CATALOG_VERSION` holds the version that a merge to `main` publishes. Every
change to `imageroot/`, `ui/` or `build-images.sh` must raise it; the
*Validate* workflow checks this. After the tests on `main` pass, *Publish
tested catalog version* tags the tested image with that version.
