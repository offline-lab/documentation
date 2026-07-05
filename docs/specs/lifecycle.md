# App Lifecycle Hooks

**Status:** rewritten 2026-07-05 against the session-§18 hook redesign,
ADR-0016 (as amended) and ADR-0032 (T98). Upgrade stages await the upgrade
design (T103).

Hooks let an app run its own units at defined lifecycle points, started by
the runtime — portablectl/nspawn only make units *available*, so this
mechanism is the runtime's own. Hooks exist so developers get **systemd's
error handling instead of bash glue**: copy files, run migrations, prepare
or chown sockets, start side software that lives in the same image (a worker
beside a webservice). If an app needs fifteen jobs before the main task,
that is the developer's choice — the mechanism supports it.

---

## The model

- **Each stage is an ordered list of unit files** that exist inside the
  image, referenced from `package.yaml`. Units run in list order; the next
  starts only after the previous succeeded.
- **Hooks fire every time their stage fires.** One-time behavior is the
  unit's own business via condition guards (`ConditionPathExists=` etc.) —
  there is no first-run magic in the runtime.
- **`recover` replays hooks like a normal `up`.** The condition guards make
  that safe; this is why storage mounts must be in place before recover
  runs (OS-side ordering).
- **A failing pre-stage hook aborts its verb loudly; `--force` skips.**
  Stricter than the pre-pivot spec (which ignored `pre_remove` failures) —
  consistent with the guarded-force grammar of ADR-0032.

## Stages

| Stage | Fires | Typical use |
|---|---|---|
| `pre_start` | every `up`, before the service starts | copy defaults into the rw config mount, migrations (guarded), socket prep |
| `post_start` | every `up`, after the service is running | start side software from the same image, warmup |
| `pre_stop` | every `down`, before the service stops | flush, stop side pieces, export |
| `post_stop` | every `down`, after the service stopped | cleanup of runtime artifacts |
| `pre_drop` | before the guarded total teardown | final export/backup — the last chance before data is destroyed |
| `pre_upgrade` / `post_upgrade` | around a version switch | **defined by the upgrade design (T103)** |

There are no `rm` hooks (`rm` only removes a cached image — no execution
environment is touched) and no post-drop hook (nothing remains to run in).

## Declaration

```yaml
lifecycle:
  pre_start:
    - myapp-seed-config.service
    - myapp-migrate.service
  post_start:
    - myapp-worker.service
  pre_drop:
    - myapp-export.service
```

Every value is a list, ordered. All stages optional. Per ADR-0016: the
`lifecycle:` block is **present only when hooks exist** — no null/empty
forms. The build tool validates that every referenced unit exists in the
image (conformance rule; T104 validates the units themselves).

## Execution

The runtime starts hook units via `systemctl start`, in list order, after
the image is attached (so hook units are available and run in the app's
namespace: same image, same storage binds, same allocated user — placement
comes from the same generated drop-in as the main service).

**Environment:** each hook receives

| Variable | Value |
|---|---|
| `APP_NAME` | app name |
| `APP_VERSION` | DDI version being operated on |
| `APP_CONFIG_DIR` | in-namespace config path (`/etc/<name>`) |
| `APP_DATA_DIR` | in-namespace data path (`/var/lib/<name>`) |

Dropped from the pre-pivot set: `APP_FIRST_RUN` (condition guards replace
it) and `APP_PREV_VERSION` (belongs to the T103 upgrade stages).

## Sequencing

### `up`

```
1. systemd verifies the image (up-gate: signature + verity, every start)
2. first provision only: allocate uid/gid, create config+data dirs,
   seed config from /usr/share/factory/etc/<name>/ (app contract §4)
3. attach (portablectl / nspawn), write the placement drop-in
pre_start hooks, in order          [failure → abort up, detach; --force skips]
4. enable + start <name>.service (or .socket)
post_start hooks, in order         [failure → service stays up, loud warning]
5. record desired state (recover's source of truth)
```

### `down`

```
pre_stop hooks, in order           [failure → abort down; --force skips]
1. stop the service
post_stop hooks, in order          [failure → loud warning]
2. record desired state
```

### `drop`

```
0. refuse if running ("down it first") and demand the destructive guards
pre_drop hooks, in order           [failure → abort drop; --force skips]
1. teardown: detach, remove environment (uid/gid, config, dirs) and data
```

### `recover`

Replays the recorded desired state as normal `up`s — including hooks, whose
condition guards make the replay idempotent.

## Systemd-wired oneshots (preferred for pure ordering)

Anything that only needs *ordering relative to the service* — no runtime
involvement — should be a unit dependency inside the image, not a hook:

```ini
# myapp-migrate.service (inside the image)
[Unit]
Description=Data migration
Before=myapp.service
ConditionPathExists=!/var/lib/myapp/.migrated-2.0.18

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/lib/myapp/migrate.sh
ExecStartPost=/usr/bin/touch /var/lib/myapp/.migrated-2.0.18
```

Unit files see only in-namespace paths (`/var/lib/myapp` — UAPI.9 view);
host paths must never appear in units. No `User=`/`Group=` (ADR-0015) —
placement is the drop-in's job.

## Image retention and revert

Retention of cached versions is local policy (user-configurable, default
current + previous) and revert is an on-disk operation — see the
[Index contract](index-contract.md) and ADR-0032. How retained versions are
stored on the host (pre-pivot ADR-0020 uuid-keyed dirs vs. the index-layout
`<name>/<version>/` shape of the local collection) is **reconciled in the
upgrade design (T103)**.
