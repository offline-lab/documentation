# unitrun

Writes shell scripts and systemd unit files, then enables them via `systemctl enable`.

## What it does

For each **enabled** unit:

1. Creates `<directory>/` if it does not exist.
2. Writes `<directory>/<name>.sh` with a `#!/bin/bash` shebang followed by the configured command body.
3. Writes `/etc/systemd/system/bootconf-<name>.service` with `[Unit]`, `[Service]`, and `[Install]` sections.
4. Calls `systemctl enable bootconf-<name>.service`.

For each **disabled** unit:

- Calls `systemctl disable bootconf-<name>.service`.
- Removes `/etc/systemd/system/bootconf-<name>.service`.
- Removes `<directory>/<name>.sh`.

After all units are processed, a single `systemctl daemon-reload` applies all changes.

## Config

```yaml
unitrun:
  enabled: true
  firstboot: false
  directory: /var/lib/bootconf/scripts
  units:
    - name: setup-overlay
      enabled: true
      dependencies:
        - After=local-fs.target
        - Before=network-pre.target
        - Conflicts=shutdown.target
      command: |
        /usr/local/bin/setup-overlay.sh
        exit 0
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `firstboot` | bool | `false` | Inject `ConditionFirstBoot=yes` into every generated unit |
| `directory` | string | | Where shell scripts are written |
| `path` | string | | Prepend a directory to `PATH` in every generated unit (e.g. `/usr/lib/framework/bin`). Omitted when empty. |
| `units[].name` | string | | Unit name. Used for script and service file names. |
| `units[].enabled` | bool | | Provision (`true`) or remove (`false`) the unit |
| `units[].dependencies` | list | | Lines written verbatim into the `[Unit]` section |
| `units[].command` | string | | Script body, written after `#!/bin/bash\n` |

## Generated files

### Script

`<directory>/setup-overlay.sh`:

```bash
#!/bin/bash
/usr/local/bin/setup-overlay.sh
exit 0
```

Mode: `0750`.

### Unit file

`/etc/systemd/system/bootconf-setup-overlay.service`:

```ini
[Unit]
Description=Bootconf Unit Task setup-overlay
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target
Conflicts=shutdown.target

[Service]
Type=oneshot
RemainAfterExit=no
Environment=PATH=/usr/lib/framework/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/var/lib/bootconf/scripts/setup-overlay.sh

[Install]
WantedBy=multi-user.target
```

## Dependencies

Lines in `dependencies` are written verbatim into the `[Unit]` section. Standard systemd directives apply:

```yaml
dependencies:
  - After=network-online.target
  - Before=myservice.service
  - Wants=network-online.target
  - Conflicts=shutdown.target
```

There is no separate DSL. Use standard systemd unit keywords directly.

## First-boot units

When `firstboot: true` at the section level, `ConditionFirstBoot=yes` is added to the `[Unit]` section of **every** generated unit:

```ini
[Unit]
Description=Bootconf Unit Task setup-overlay
DefaultDependencies=no
ConditionFirstBoot=yes
After=local-fs.target
```

Systemd evaluates this condition using the machine-id state. On the first boot (before `machine-id` is written), `ConditionFirstBoot=yes` passes and the unit runs. On subsequent boots, systemd skips the unit automatically.

No custom sentinel file is used. This is a native systemd condition.

## Dry-run

```
INFO [unitrun] would create directory /var/lib/bootconf/scripts (dry-run)
INFO [unitrun] would write script /var/lib/bootconf/scripts/setup-overlay.sh (dry-run)
INFO [unitrun] would write unit file /etc/systemd/system/bootconf-setup-overlay.service (dry-run)
INFO [unitrun] would add ConditionFirstBoot=yes to bootconf-setup-overlay.service (dry-run)
INFO [unitrun] would systemctl enable bootconf-setup-overlay.service (dry-run)
```

## vs. shell

| | `shell` | `unitrun` |
|---|---|---|
| Execution | Runs during `bootconf run` | Runs when systemd starts the unit |
| Ordering control | Sequential, stops on failure | Full systemd dependency graph |
| Per-command firstboot | Sentinel file per command | `ConditionFirstBoot=yes` in unit |
| Output | Log file | systemd journal |

Use `shell` for commands that must complete before boot continues and where sequential ordering is sufficient. Use `unitrun` when you need systemd dependency ordering, parallel execution with other units, or journal integration.
