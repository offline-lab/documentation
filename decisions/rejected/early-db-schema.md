# Rejected: Early 2-Table Database Schema

**Status:** Historical — both this 2-table schema and the 5-table `packages.sql` that
replaced it are now superseded by file-per-record JSON state (ADR-0026).
**Replaced by:** File-per-record state under `/var/lib/appctl/state/` (ADR-0026).

---

## What was proposed

An early 2-table schema (originally documented in the user-allocation spec):

```sql
CREATE TABLE repos (
    hash     TEXT PRIMARY KEY,
    url      TEXT UNIQUE NOT NULL,
    alias    TEXT UNIQUE NOT NULL,
    key_path TEXT NOT NULL,
    status   TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE packages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo         TEXT NOT NULL REFERENCES repos(hash),
    name         TEXT NOT NULL,
    uid          INTEGER UNIQUE NOT NULL,
    version      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'installed',
    active_uuid  TEXT,
    UNIQUE (repo, name)
);
```

This schema lacked:

- `schema_version` table for migration tracking
- `package_cache` table for cached index entries
- `images` table for tracking multiple retained image versions (needed for rollback)
- WAL mode and foreign-keys pragmas

---

## Why it was replaced

The 2-table schema was designed before rollback support was in scope. When rollback was
added (`appctl rollback <name>`), a separate `images` table was needed to track multiple
versions per app (active, previous, removed) independently from the installed package
row.

The `package_cache` table was added to separate the package index (which is refreshed and
replaced on every `repo refresh`) from the installed-packages state (which only changes
on install/update/remove). Without this separation, a `repo refresh` would need to join
the index against installed packages to avoid losing state — fragile and complex.

`schema_version` was added for migration safety — a standard practice for any SQLite DB
that will evolve over time.

---

## What replaced it

Historically, a 5-table SQLite schema (`packages.sql`: `schema_version`, `repos`,
`package_cache`, `images`, `packages`). **That SQLite design was itself later rejected**
in favour of file-per-record JSON state under `/var/lib/appctl/state/`
([ADR-0026](../adr/adr-0026-appctl-file-per-record-state.md)) — one file per repo,
package, base, image, and lock. The rollback need that drove the separate `images` table
is met by `state/images/<uuid>.json` records; the index/state separation is met by keeping
cached index entries inside the repo record. Build certs are stored at
`/etc/verity.d/<repo-name>-<key-id>.crt` (ADR-0005), not `/data/config/keys/` and not in
any database. See [On-Device State Format](../../docs/schemas/on-device-state.md).

---

## Note

Both schemas are historical. The current state layout is file-per-record JSON —
see [On-Device State Format](../../docs/schemas/on-device-state.md).
