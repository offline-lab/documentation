# Per-App User Allocation and Storage Layout

**Status:** rewritten 2026-07-05 against ADR-0032/0035/0036/0037 (T98).

Every app running in **portable mode** runs as a dedicated system user. No
two apps ever share a uid or gid. The runtime owns all allocation; no users
are pre-created in any image.

**nspawn mode** allocates no per-app uid — isolation comes from the
namespace, and the user inside the container is root. Everything below
applies to portable mode only.

---

## Identity scheme

| Identifier | Format | Example | Purpose |
|---|---|---|---|
| Index hash | truncated **index-key fingerprint** (ADR-0033/0035) | `a0d7b954` | storage path prefix; ties data to provenance |
| Username | `app<uid>` | `app6000` | Linux account — always valid, short, busybox-safe |
| Display name | `<index-alias>/<name>` | `offline-lab/mosquitto` | human-readable (`list` output, GECOS field) |

The index hash derives from the **identity of the index that provided the
app** — its signing-key fingerprint, not its URL (identity is the key;
URLs are just locations). Apps imported from raw DDIs belong to the
device's **own local index** (ADR-0037), so every app has an index hash.
Exact truncation length is fixed by the schemas (T95).

## Storage layout

```
<root>/apps/<index-hash>/<name>/
  config/    ← operator-editable, writable by the app uid
  data/      ← app-private persistent data, writable by the app uid
```

`<root>` is relocatable (default `/var/lib/appctl`); the structure below it
is fixed contract on every host OS (ADR-0035). Two same-named apps from
different indexes are fully isolated — different hash, different uid,
different storage.

Inside the app's namespace these mount at the fixed UAPI.9 paths —
**config → `/etc/<name>`, data → `/var/lib/<name>`** — via `BindPaths=` in
the generated drop-in. The in-image paths are not author-declared;
software expecting a different path is adapted with symlinks inside the
image. (Whether an override field survives at all is part of T101's
orphaned-fields ruling.)

```ini
# generated drop-in (the keystone: the image ships intent, the host ships placement)
[Service]
User=app6000
Group=app6000
BindPaths=<root>/apps/a0d7b954/mosquitto/config:/etc/mosquitto
BindPaths=<root>/apps/a0d7b954/mosquitto/data:/var/lib/mosquitto
PrivateTmp=yes
```

**Config seeding:** on first provision, the config volume is seeded from
the image's pristine defaults at `/usr/share/factory/etc/<name>/`
(UAPI.9 factory pattern, ADR-0034). Later version switches never overwrite
live config (migration is hook territory — T103).

## File ownership inside the image

The image is read-only (dm-verity enforced); ownership only affects
read/execute, never write. **All files inside the image are `root:root`**
(ADR-0014): binaries `755`, static files `644`. The service user reads and
executes via world permissions, like any user runs `/usr/bin/anything`.
The app uid cannot appear inside the image — it doesn't exist at build
time.

Consequences (enforced as conformance, app contract):

1. No `User=`/`Group=` in shipped units (ADR-0015) — placement comes from
   the drop-in.
2. No internal privilege dropping (`setuid()` to a user from the image's
   own `/etc/passwd`) — the service runs as the single user systemd
   assigns. Upstream daemons that self-drop must have it disabled at build.
3. Everything writable at runtime lives in the two bound volumes — never
   inside the image.

## Allocation rules (ADR-0012 as amended by ADR-0036)

- **When:** at first `up` (provisioning), not at `get` — caching an image
  allocates nothing.
- **Range:** configurable base in the host config, **default 6000+**.
- **Algorithm:** next free = high-water mark + 1. If that uid is occupied
  by a **foreign** (non-appctl) user, the runtime **errors loudly** and
  asks the operator to configure a different range — no silent skipping.
- **Never reused.** The high-water mark survives `drop`: a dropped app's
  uid is permanently retired, so no future app can inherit stray filesystem
  ownership.
- **Same uid every start.** The uid is recorded in state
  (file-per-record, ADR-0026) and reused for the app's whole provisioned
  life — data is never chowned again. `recover` recreates the user from
  the **recorded** uid.

Lifecycle interaction (ADR-0032): `down` and `rm` leave the environment —
uid, config, data — untouched. Only `drop` (total, guarded) removes the
user, storage, and data together; there is no environment-gone-data-kept
state, by design.

## Persistence across reboots

The runtime writes a sysusers snippet at provisioning:

```
# /etc/sysusers.d/<index-hash>-<name>.conf
u app6000 6000 "offline-lab/mosquitto" <root>/apps/a0d7b954/mosquitto /bin/false
g app6000 6000 -
```

…and runs `systemd-sysusers` immediately. On a normal host `/etc`
persists and that's the end of it. On a wiped-`/etc` host, **`appctl
recover`** re-derives the snippet (and everything else) from state records
at boot, with the recorded uid — the mechanism is generic
(ADR-0036); the OS's only duties are mounting `<root>` first and running
recover (see `OS-CONFORMANCE.md`).

## State

State records live file-per-record under `<root>` (ADR-0026;
[On-Device State Format](../schemas/on-device-state.md) — pre-pivot page,
awaiting its own rewrite). The uid high-water mark and per-app uid records
are the `recover` source of truth and outlive `drop` (retired-uid memory).
