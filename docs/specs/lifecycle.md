# App Lifecycle Hooks

> **Amended (2026-07-05).** The appctl verb model was redesigned in
> [ADR-0032](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0032-appctl-lifecycle-verbs.md):
> the install/update/remove vocabulary below maps onto the two-axis model
> (`get`/`rm` cache, `up`/`down` run, `drop` guarded teardown). The *hook
> concept* (units run at defined lifecycle points) survives; the flow names and
> semantics they attach to await the rewrite. appctl remains unwritten.

Apps can declare systemd units that appctl starts at defined points in the install,
update, and remove flow. Hooks are the correct place for one-time operations that
cannot be expressed as regular service dependencies: database init, config migration,
pre-removal export.

For recurring setup on every start (first-run guards, dependency checks), the preferred
pattern is a `oneshot` unit wired as a systemd dependency inside the squashfs, using
`ConditionPathExists=` to skip subsequent runs. See the example below.

---

## Hook types

| Hook | When it runs |
|---|---|
| `pre_start` | After portablectl attach, before the service is enabled and started |
| `post_start` | After the service is running for the first time |
| `pre_update` | After the new image is attached, before the service is restarted |
| `post_update` | After the service is running on the new image |
| `pre_remove` | Before the service is stopped and the image is detached |

There is no `post_remove`. By the time removal is complete, the image is detached
and no hook execution environment exists.

---

## Declaration

Hooks are declared in `package.yaml` as unit names that must exist inside the squashfs:

```yaml
lifecycle:
  pre_start:  mosquitto-pre-start.service
  post_start: mosquitto-post-start.service
  pre_update: mosquitto-pre-update.service
  post_update: mosquitto-post-update.service
  pre_remove: mosquitto-pre-remove.service
```

All hooks are optional. Omit any hook the app does not need.

Units must exist at the declared name inside the squashfs. buildctl validates this
at package build time.

---

## Execution

appctl invokes hooks via `systemctl start <unit>`. The unit file lives inside the
squashfs; portablectl has already attached it to the system before any hook runs.

Hooks run as the app's allocated user (`app<uid>`) with the app's data volumes
bind-mounted, with the same context as the main service, except they are started directly
by appctl rather than being part of the service's normal lifecycle.

appctl provides environment variables to each hook via a transient drop-in written
to `/run/systemd/system.control/` before starting the unit, and removed after.

---

## Environment variables

| Variable | Value | Available in |
|---|---|---|
| `APP_NAME` | App name (e.g. `mosquitto`) | all hooks |
| `APP_VERSION` | Version being installed, updated, or removed | all hooks |
| `APP_PREV_VERSION` | Previous installed version | `pre_update`, `post_update` |
| `APP_FIRST_RUN` | `1` on first install, unset on reinstall/update | `pre_start`, `post_start` |
| `APP_DATA_DIR` | Namespace path of the data volume | all hooks |
| `APP_CONFIG_DIR` | Namespace path of the config volume | all hooks |

`APP_FIRST_RUN=1` is set when there is no prior install record for this app in
`state/packages/`. Use it to distinguish first-install init from reinstall in `pre_start`.

---

## Sequencing

### Install

```
1. Stage DDI to /var/lib/appctl/images/<uuid>/
2. Allocate uid, write sysusers snippet, call systemd-sysusers
3. Create /var/lib/appctl/apps/<repo-hash>/<name>/{config,data}/
4. Seed config from DDI defaults (first install only)
5. Generate appctl drop-in (User=, Group=, BindPaths=)
6. portablectl attach (systemd verifies signature via /etc/verity.d/)
pre_start                              [APP_FIRST_RUN=1 on first install]
7. portablectl enable + systemctl start <name>.service
post_start                             [APP_FIRST_RUN=1 on first install]
8. Write package record to state/packages/<hash>-<name>.json
```

### Update

```
1. Stage new DDI to /var/lib/appctl/images/<uuid-new>/
2. systemctl stop <name>.service
3. portablectl detach <old>
4. portablectl attach <new> (systemd verifies signature via /etc/verity.d/)
5. Regenerate appctl drop-in from new metadata
pre_update                             [APP_PREV_VERSION=<old>]
6. systemctl start <name>.service
post_update
7. Update package record (new uuid active, old uuid retained per retention policy)
8. Prune images beyond retention limit
```

### Remove

```
pre_remove                             [service still running]
1. systemctl stop <name>.service
2. portablectl detach
3. Delete sysusers snippet
4. Mark package record as removed in state/packages/<hash>-<name>.json
[--purge: delete /var/lib/appctl/apps/<repo-hash>/<name>/]
```

---

## Image storage and rollback

Each staged image lives in its own UUID-named directory under `/var/lib/appctl/images/`:

```
/var/lib/appctl/images/<uuid>/
  mosquitto_2.0.18_arm64.raw
  mosquitto_2.0.18_arm64.json
```

The per-image record at `state/images/<uuid>.json` maps each UUID to its app,
version, and status (`active` | `previous` | `removed`). The DDI is a single
`.raw` file with partitions discovered by GPT type UUID, not by filename
convention.

**Retention:** after each successful install or update, appctl prunes images for that
app beyond the configured limit (default: 3). The active image is always retained.
Retained previous images enable rollback via `appctl rollback <name>`.

The retention limit is configurable in `/etc/appctl/appctl.conf`:
```
image_retention = 3
```

---

## Failure behaviour

| Hook | Failure behaviour |
|---|---|
| `pre_start` | Abort install; portablectl detach; no service started |
| `post_start` | Service left running; operator must intervene |
| `pre_update` | Abort update; re-attach old image; restart old version |
| `post_update` | New version running; operator must intervene |
| `pre_remove` | Remove proceeds anyway; hook failure is logged but not blocking |

`pre_remove` failure is non-blocking because a hook that always fails would make
the app impossible to remove.

All hook failures are logged to the journal under the appctl unit.

---

## Systemd-wired lifecycle (preferred for migrations)

For database migrations and first-run guards, the preferred pattern is a `oneshot`
unit wired as a systemd dependency inside the squashfs:

```ini
# mosquitto-migrate.service (inside squashfs)
[Unit]
Description=Mosquitto data migration
Before=mosquitto.service
ConditionPathExists=!/var/lib/mosquitto/.migrated-2.0.18

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/lib/mosquitto/migrate.sh
ExecStartPost=/usr/bin/touch /var/lib/mosquitto/.migrated-2.0.18
```

The `ConditionPathExists` guard prevents re-running on every start. Unit files inside
the squashfs only see namespace paths (e.g. `/var/lib/mosquitto`). System paths
containing the repo hash are invisible to the service and must not appear in unit files
or scripts. This pattern requires no appctl involvement; systemd handles ordering and
execution.

`User=` and `Group=` are not declared in the unit file; appctl provides them via
the same drop-in it generates for the main service.
