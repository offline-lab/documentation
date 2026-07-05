# On-Device State Format

> **Amended (2026-07-05).** File-per-record is **affirmed** (ADR-0026 — and now
> also the source of truth for `appctl recover`, ADR-0036). Stale below:
> "repo" → **index** (ADR-0033), storage namespacing → `<index-hash>` (the
> index-key fingerprint, ADR-0035), `<root>` is relocatable (default
> `/var/lib/appctl`), and install/remove flows → the ADR-0032 verb model
> (`get`/`up`/`down`/`rm`/`drop`). Record shapes await the contract-spec
> rewrite.

appctl's persistent state lives under `/var/lib/appctl/state/` as one JSON file
per record. File-per-record storage (dpkg-style) — not a single database file.

**Rationale:** on devices with frequent power loss and SD-card storage, a
single corrupt SQLite file takes out the whole appctl state. File-per-record
limits corruption blast radius to one record; each file is atomically written
via temp-file + `rename(2)`; recovery is `cat` or `rm` on a single file. Same
pattern used by dpkg, apk, pacman, and brew.

See:
- [User Allocation](../specs/user-allocation.md) for how package records drive
  uid allocation, drop-in generation, and storage paths.
- [Lifecycle](../specs/lifecycle.md) for how records are written/updated
  during install/update/remove.
- [Reboot Proofing](../specs/reboot-proofing.md) for what survives reboots
  and slot switches.

---

## Layout

```
/var/lib/appctl/state/
  repos/
    <repo-hash>.json                            # one file per configured repo
  packages/
    <repo-hash>-<name>.json                     # one file per installed package
  bases/
    <repo-hash>-<name>-<sysext-level>.json      # one file per installed base (layered mode)
  images/
    <uuid>.json                                 # one file per staged image DDI
  locks/
    <operation-id>.json                         # transient; marks in-progress operations
```

Each file is small (<1 KB), atomically written (temp file in same dir +
`rename(2)`), human-readable, and individually recoverable. Records are created
and updated only by appctl (single writer); no concurrent writers, no locking
beyond the per-file atomic rename.

---

## Common conventions

- All timestamps are ISO 8601 UTC (`2026-06-18T10:30:00Z`).
- All UUIDs are lowercase canonical form.
- Optional fields are omitted (not `null`) when unset, unless documented
  otherwise.
- All paths inside records are absolute (system-side). Package authors never
  see these paths; they only see namespace paths via `BindPaths=` in the
  drop-in.
- File ownership on disk: `root:root` mode `0644`. appctl is the only writer.

---

## Repo record: `state/repos/<repo-hash>.json`

```json
{
  "hash": "a0d7b954",
  "url": "https://packages.offline-lab.com",
  "alias": "offline-lab",
  "arch": "arm64",
  "status": "active",
  "bases_url": "https://packages.offline-lab.com/bases/",
  "images_url": "https://packages.offline-lab.com/images/",
  "index_cert_path": "/etc/verity.d/offline-lab-index.crt",
  "build_certs": [
    {"key_id": "a1b2c3d4e5f6", "path": "/etc/verity.d/offline-lab-a1b2c3d4e5f6.crt"}
  ],
  "key_rotation": 0,
  "last_fetched_at": "2026-06-18T12:00:00Z",
  "added_at": "2026-06-18T10:00:00Z"
}
```

| Field | Format | Notes |
|---|---|---|
| `hash` | string | `sha1(url.lower())[:8]`. Canonical identifier; used in filenames and storage paths. |
| `url` | string | Repo base URL (the URL passed to `repo add`). Immutable. |
| `alias` | string | Human-readable name set by operator. Display-only. |
| `arch` | string | Device arch; which per-arch index to fetch. |
| `status` | enum | `"active"` \| `"paused"` \| `"blocked"`. *(Pre-pivot design; whether pause/block survives the ADR-0037 subscribe/import model is a rewrite question for this page.)* |
| `bases_url` | URL \| null | Resolved bases URL from `repository.json`. `null` if repo doesn't serve bases. |
| `images_url` | URL \| null | Resolved apps URL from `repository.json`. `null` if repo doesn't serve apps. |
| `index_cert_path` | path | Public cert used to verify `repository.json.p7s` and per-arch `index.json.p7s` files. |
| `build_certs` | array | One entry per active build cert; each has `key_id` + `path` under `/etc/verity.d/`. systemd reads these at attach time. |
| `key_rotation` | integer | Last seen `key_rotation` value from `repository.json`. Detects Option B rotations. |
| `last_fetched_at` | timestamp | Last successful `repo refresh`. Omitted if never refreshed. |
| `added_at` | timestamp | When `repo add` was called. |

---

## Package record: `state/packages/<repo-hash>-<name>.json`

**Single-image app example:**

```json
{
  "repo_hash": "a0d7b954",
  "name": "mosquitto",
  "version": "2.0.18",
  "arch": "arm64",
  "status": "installed",
  "runtime": "portable",
  "uid": 6000,
  "username": "app6000",
  "active_image_uuid": "f3e2a1b8-c4d5-6789-0123-456789abcdef",
  "previous_image_uuids": ["11111111-2222-3333-4444-555555555555"],
  "stack": null,
  "installed_at": "2026-06-18T10:30:00Z",
  "updated_at": "2026-06-18T11:00:00Z",
  "metadata": {
    /* full snapshot of the package metadata JSON from install time */
  }
}
```

**Layered app example:**

```json
{
  "repo_hash": "a0d7b954",
  "name": "myservice",
  "version": "1.0",
  "arch": "arm64",
  "status": "installed",
  "runtime": "portable",
  "uid": 6001,
  "username": "app6001",
  "active_image_uuid": "...",
  "previous_image_uuids": [],
  "stack": [
    {"name": "ol-base-debian",        "sysext_level": "1.0", "base_uuid": "..."},
    {"name": "ol-base-debian-python", "sysext_level": "1.0", "base_uuid": "..."}
  ],
  "installed_at": "...",
  "updated_at": "...",
  "metadata": { /* ... */ }
}
```

| Field | Format | Notes |
|---|---|---|
| `repo_hash` | string | Foreign reference to a repo record. Omitted for manual installs (no repo). |
| `name` | string | Package name (matches metadata). |
| `version` | string | Currently installed version. |
| `arch` | string | Device arch. |
| `status` | enum | `"installed"` \| `"removed"`. Removed rows preserved for uid reservation and reinstall reuse. |
| `runtime` | enum | `"portable"` \| `"nspawn"`. Determines drop-in shape and isolation model. |
| `uid` / `username` | int / string | Allocated at install time. Portable mode only — nspawn omits these. Never reused across different apps. |
| `active_image_uuid` | UUID | References an image record. |
| `previous_image_uuids` | UUID[] | Retained for rollback. Subject to image retention limit (default 3). |
| `stack` | array \| null | Layered mode only. `null` (or omitted) = single-image app. Each entry references a base record by `base_uuid`. |
| `installed_at` / `updated_at` | timestamp | Lifecycle tracking. |
| `metadata` | object | Full snapshot of the package metadata JSON at install time. Source of truth for drop-in generation; not re-read from the repo after install. |

---

## Base record: `state/bases/<repo-hash>-<name>-<sysext-level>.json`

Layered mode only. Bases are ref-counted: a base is only removed when no
installed package references it.

```json
{
  "repo_hash": "b1c2d3e4",
  "name": "ol-base-debian",
  "version": "1.0.2",
  "arch": "arm64",
  "sysext_level": "1.0",
  "image_uuid": "...",
  "referenced_by": [
    "a0d7b954-myservice",
    "a0d7b954-anotherservice",
    "a0d7b954-thirdservice"
  ],
  "installed_at": "..."
}
```

| Field | Format | Notes |
|---|---|---|
| `repo_hash` | string | Which bases repo this came from. |
| `name` / `version` / `arch` | strings | Image identity. |
| `sysext_level` | string | Compatibility version (SONAME-like). Multiple base versions of the same flavor with different `sysext_level` may coexist on device. |
| `image_uuid` | UUID | References an image record. Bases do not use rollback; only one version per `(name, sysext_level)` is retained at a time. |
| `referenced_by` | string[] | Package record IDs (`<repo-hash>-<name>`). Source of truth for the reference count; `ref_count` is computed as `len(referenced_by)`. |
| `installed_at` | timestamp | When the base was first installed. |

Reference counting rules:

- On package install/update: each `stack` entry's `base_uuid` must point to an
  existing base record. If the base isn't installed, appctl auto-downloads and
  installs it first. The package's ID is then appended to `referenced_by`.
- On package remove: the package's ID is removed from `referenced_by` on each
  base in its stack. Bases whose `referenced_by` becomes empty are kept cached
  (for fast reinstall) until explicit `appctl cleanup --bases` or
  `appctl remove-base <name>`.
- On explicit `appctl remove-base <name>`: errors if `referenced_by` is
  non-empty. Otherwise removes the base record and its image.

---

## Image record: `state/images/<uuid>.json`

Every staged DDI (app or base) has an image record. The image file lives at
`/var/lib/appctl/images/<uuid>/` (apps) or `/var/lib/appctl/bases/<uuid>/`
(bases); the image record is just metadata about it.

```json
{
  "uuid": "f3e2a1b8-c4d5-6789-0123-456789abcdef",
  "name": "mosquitto",
  "version": "2.0.18",
  "arch": "arm64",
  "kind": "app",
  "status": "active",
  "raw_path": "/var/lib/appctl/images/f3e2a1b8-c4d5-6789-0123-456789abcdef/mosquitto_2.0.18_arm64.raw",
  "raw_sha256": "abc123...",
  "ddi_size": 4194304,
  "staged_at": "2026-06-18T10:25:00Z"
}
```

| Field | Format | Notes |
|---|---|---|
| `uuid` | UUID | Primary key; storage dir name. |
| `name` / `version` / `arch` | strings | Image identity. |
| `kind` | enum | `"app"` \| `"base"`. Determines storage path prefix and lifecycle rules. |
| `status` | enum | `"active"` \| `"previous"` \| `"removed"`. Apps use all three for rollback. Bases use only `"active"` (no rollback). |
| `raw_path` | path | Absolute path to the `.raw` file on disk. |
| `raw_sha256` | hex | SHA-256 of the `.raw` file. Verified after download and on integrity checks. |
| `ddi_size` | int | Size of the `.raw` in bytes. Used for retention/cleanup decisions. |
| `staged_at` | timestamp | When the image was first written to disk. |

---

## Lock files: `state/locks/<operation-id>.json`

Transient. Written before multi-step operations (install, update, remove);
removed after success. On startup, any remaining lock file indicates an
interrupted operation that needs recovery or rollback.

```json
{
  "operation_id": "install-a0d7b954-myservice-20260618T103000Z",
  "operation": "install",
  "package": "a0d7b954-myservice",
  "started_at": "2026-06-18T10:30:00Z",
  "steps_total": 8,
  "steps_completed": 4,
  "current_step": "verify_signature"
}
```

Lock files are advisory — appctl is the only writer. They exist purely for
crash recovery: on startup, `appctl` scans `state/locks/` and either resumes
or rolls back each interrupted operation.

---

## Why not SQLite

Considered and rejected. Reasons:

1. **Corruption blast radius.** A single bad sector or fsync failure on the SD
   card takes out the whole SQLite file. File-per-record limits damage to one
   record.
2. **Recovery.** Operators on a Pi can `cat`, edit, or `rm` a single JSON file
   with standard tools. SQLite recovery requires the `sqlite3` CLI (not always
   installed) and may be incomplete.
3. **Binary size.** `modernc.org/sqlite` adds ~20 MB to the appctl binary.
   File-per-record uses only `encoding/json` from the stdlib.
4. **Sufficient performance.** At 10-50 records per device, every query is a
   directory listing + N small file reads. Sub-millisecond. No indexes needed.
5. **Precedent.** dpkg, apk, pacman, brew, and most package managers use
   file-per-record storage. There's a reason none of them use SQLite.

What we lose: indexes, SQL queries, ACID transactions. None of these matter at
single-device scale with a single writer.
