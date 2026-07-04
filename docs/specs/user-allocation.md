# Per-App User Allocation and Storage Layout

> **Amended (2026-07-05).** Per
> [ADR-0035](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0035-standardized-app-storage.md)
> and [ADR-0036](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0036-foreign-host-baseline.md):
> the storage layout is the contract-defined, relocatable
> `<root>/apps/<index-hash>/<app>/{config,data}` (+ private `/tmp`); the uid
> base range is **configurable** (default 6000+) and appctl **errors loudly on
> a clash** with foreign users (no silent skipping); `appctl recover` recreates
> users with recorded uids so data never needs a chown.

Every installed app running in **portable mode** runs as a dedicated system user. No
two apps share a uid or gid. appctl owns all allocation; no users are pre-created in
the base image.

**nspawn mode** does not allocate a per-app uid. Isolation is via PID/mount/network
namespace, and the user inside the container is root. Everything below applies to
portable mode only.

---

## Identity scheme

Three distinct identifiers per app, each serving a different purpose:

| Identifier | Format | Example | Purpose |
|---|---|---|---|
| Repo hash | `sha1(url.lower())[:8]` | `a0d7b954` | Storage path prefix, collision-resistant |
| Username | `app<uid>` | `app6000` | Linux user account, always valid, always short |
| Display name | `<repo-alias>/<name>` | `offline-lab/mosquitto` | Human-readable, `appctl list` output |

**Repo hash** is derived from the canonical repo URL at `appctl repo add` time:
`sha1("https://packages.offline-lab.com".lower())[:8]` yields `a0d7b954`. It is
immutable and cannot be manipulated: `/a/b/repo` and `/ab/repo` hash to different
8-char prefixes. Same approach as Home Assistant Supervisor.

**Username** is `app` followed by the decimal uid. Always starts with a letter,
always alphanumeric, always ≤ 9 chars. Works on busybox and all Linux systems.
The GECOS field carries the human-readable identity (`offline-lab/mosquitto`).

**Display name** uses the user-set repo alias (set at `appctl repo add --name <alias>`)
for readability. The alias is display-only; the repo hash is the canonical identifier.

---

## Storage layout

```
/var/lib/appctl/apps/<repo-hash>/<name>/
  config/    ← app configuration (persistent, writable by app uid)
  data/      ← app runtime data  (persistent, writable by app uid)
```

Example:
```
/var/lib/appctl/apps/a0d7b954/mosquitto/config/
/var/lib/appctl/apps/a0d7b954/mosquitto/data/
```

Two apps named `mosquitto` from different repos are fully isolated:
```
/var/lib/appctl/apps/a0d7b954/mosquitto/   ← offline-lab repo
/var/lib/appctl/apps/f2c91e3a/mosquitto/   ← community repo, separate hash, separate uid
```

---

## File permissions inside the squashfs

The squashfs is read-only (dm-verity enforced). Ownership inside it only affects
whether the service process can read or execute files, not write them.

**Decision: all files inside the squashfs are owned by root (uid 0).**

- Binaries: `root:root 755` (world-executable)
- Static files and config templates: `root:root 644` (world-readable)
- No files inside the squashfs need to be owned by the service user

The service user (`app6000`) can read and execute these files via world permissions,
exactly as any user can execute `/usr/bin/mosquitto` on a normal Linux system.

**Why not use the app uid inside the squashfs:**
The uid is allocated at install time and is not known at build time. There is no
mechanism to specify it in the image. Attempting to use a placeholder uid and remap
at runtime (via `UIDMap=`) adds complexity and requires user namespace kernel support,
with no practical benefit for a read-only filesystem.

**Packaging constraints (must be documented in app-filesystem.md):**

1. Unit files inside the squashfs must not include `User=` or `Group=` directives.
   appctl generates these in a drop-in at install time. If present in the unit file,
   they are overridden by the drop-in, but their presence is misleading and buildctl
   should warn.

2. Services must not perform internal privilege dropping (calling `setuid()` or
   `setgid()` to a named user defined in the squashfs's own `/etc/passwd`). The
   service must run as the single user systemd assigns via `User=`. Upstream daemons
   that drop privileges internally must have this disabled in the Dockerfile/package
   (typically via a `--no-drop-privs` flag or equivalent).

3. Any file that needs to be writable at runtime must be in the bind-mounted
   `/var/lib/appctl/apps/<hash>/<name>/` tree, not inside the squashfs.

---

## Writable storage: volumes

Package authors declare only the namespace target paths for each data category.
Exactly two fixed keys: `config` and `data`. No freeform paths. appctl controls
the system path entirely. A package cannot reference arbitrary system locations.

`package.yaml`:
```yaml
volumes:
  config: /etc/mosquitto     # system: .../config/ → /etc/mosquitto in namespace
  data:   /var/lib/mosquitto # system: .../data/   → /var/lib/mosquitto in namespace
```

The paths on the right are conventional Linux paths, exactly what the upstream daemon
expects. The package author knows these at build time and writes config files referencing
them normally. The system paths (containing the repo hash) are entirely managed by appctl
and invisible to the package author.

appctl-generated drop-in:
```ini
# /etc/systemd/system.attached/mosquitto.service.d/99-appctl.conf
[Service]
User=app6000
Group=app6000
BindPaths=/var/lib/appctl/apps/a0d7b954/mosquitto/config:/etc/mosquitto
BindPaths=/var/lib/appctl/apps/a0d7b954/mosquitto/data:/var/lib/mosquitto
```

**Default config seeding:** on first install, if a volume target path exists inside
the squashfs (e.g., `/etc/mosquitto/mosquitto.conf`), appctl copies its contents to
the writable system directory before the bind mount takes effect. This seeds the writable
config from the image's defaults. Subsequent installs (updates) do not overwrite
the user's live config. That is the `post_update` lifecycle hook's responsibility.

---

## State storage

appctl never deletes app records; they are marked `removed` to preserve uid
assignments permanently and enable reinstall to reuse the original uid.

State is stored as **one JSON file per record** under
`/var/lib/appctl/state/`. See
[On-Device State Format](../schemas/on-device-state.md) for the full file
layout and field reference. Summary:

| Record type | Path | Purpose |
|---|---|---|
| Repo | `state/repos/<hash>.json` | Configured repos (URL, alias, type, certs) |
| Package | `state/packages/<hash>-<name>.json` | Installed app (uid, version, status, stack) |
| Base | `state/bases/<hash>-<name>-<level>.json` | Installed base (ref-counted, layered mode only) |
| Image | `state/images/<uuid>.json` | Staged DDI metadata (path, hash, size, status) |

**Why file-per-record, not SQLite:** corruption on SD-card devices takes out
one record, not the whole state store. Recovery is `cat` or `rm` on a single file.
Same pattern as dpkg, apk, pacman. See
[on-device-state.md § Why not SQLite](../schemas/on-device-state.md#why-not-sqlite).

---

## Allocation algorithm

### Allocate (at install)

1. Check for an existing package record for `(repo_hash, name)` in any status.

   - **Found:** reuse the existing uid. Update `status = 'installed'` and `version`.
   - **Not found:** allocate `max(uid) + 1`, starting at 6000.

2. Write the package record.

3. Write sysusers snippet and call `systemd-sysusers` on it immediately.

4. Create home dirs (`/var/lib/appctl/apps/<hash>/<name>/{config,data}`), `chown app<uid>`.

5. Seed config from squashfs defaults if first install.

6. Generate appctl drop-in with `User=`, `Group=`, `BindPaths=`.

7. Call `portablectl attach`.

Uids are monotonically increasing and never reused across different apps. The `max(uid)`
high-water mark is preserved even after records are marked `removed`, preventing a newly
installed app from inheriting filesystem ownership from a previously purged app.

Reinstalling the same app (same `repo_hash` + `name`) reuses the original uid. Data
dirs remain correctly owned and no `chown` is needed.

---

## Collision handling

`(repo_hash, name)` is the unique key. Two apps with the same name from different repos
are different apps with different uids and fully isolated storage.

Installing an already-`installed` app errors:
```
error: offline-lab/mosquitto is already installed (use --force to reinstall)
```

| Flag | uid | data |
|---|---|---|
| _(none, already installed)_ | error | unchanged |
| `--force` | reused | kept |
| `--force --purge` | reused | deleted and reseeded from image defaults |

---

## Uninstall and cleanup

**`appctl remove <app>`**: detaches service, removes sysusers snippet, marks the record
`removed`. Data in `/var/lib/appctl/apps/<hash>/<name>/` is kept intact. Uid reserved.

**`appctl remove --purge <app>`**: same, plus deletes `/var/lib/appctl/apps/<hash>/<name>/`.
The record stays as `removed`; uid is permanently retired from the high-water mark.

**`appctl cleanup`**: dry-run by default. Removes `removed`-status records
and any orphaned directories on disk. Requires `--yes`. Refuses if a lock file is
present. Uid slots for cleaned-up records remain retired.

---

## Persistence across reboots

The `/etc` overlay resets on every boot. appctl writes a sysusers snippet to
`/etc/sysusers.d/<hash>-<name>.conf` at install:

```
u app6000 6000 "offline-lab/mosquitto" /var/lib/appctl/apps/a0d7b954/mosquitto /bin/false
g app6000 6000 -
```

`offlinelab-sysusers.service` (runs before `sysinit.target`) calls:
```
systemd-sysusers /etc/sysusers.d/*.conf
```

On remove the snippet is deleted; the user is not recreated on next boot.

On OL OS, `/etc/sysusers.d/` is bind-mounted from persistent `/data/` storage at boot,
because `/etc` is ephemeral (overlay upper wiped each boot). On any other systemd host
these paths work natively. Alternatively, appctl may call `systemd-sysusers` directly
during rehydrate — the call is idempotent.

---

## Buildroot implications

- `systemd-sysusers`: part of `BR2_PACKAGE_SYSTEMD`, already required
- `offlinelab-sysusers.service`: ships with `offlinelab-bootconf` package
- No `useradd`/`groupadd` required
