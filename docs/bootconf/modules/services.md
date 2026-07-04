# services

Manages service sentinel files and optionally provisions default config files.

## What it does

For each configured service entry:

- If `sentinel: true` and `enabled: true`: creates an empty file at `<directory>/<name>`.
- If `sentinel: true` and `enabled: false`: removes `<directory>/<name>` if it exists.
- If `default_config.copy: true` and `enabled: true`: copies the default config from source to destination on first presence.

Bootconf does not start or stop daemons by default. The sentinel pattern lets your systemd units decide whether to run a service:

```ini
[Unit]
ConditionPathExists=/etc/bootconf/services/myservice
```

Pass `--apply` to `bootconf run` to also start enabled services immediately after writing their sentinel files.

## Config

```yaml
services:
  enabled: true
  directory: /etc/bootconf/services
  services:
    - name: myservice
      unit: myservice-daemon   # optional, defaults to name
      enabled: true
      sentinel: true
      default_config:
        copy: true
        source: /etc/myservice/myservice.conf
        destination: /data/config/myservice/myservice.conf
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable the module |
| `directory` | string | Where sentinel files are written |
| `services[].name` | string | Service name; used as the sentinel filename and display label |
| `services[].unit` | string | Systemd unit name for `systemctl start` and health checks. Defaults to `name` when not set. |
| `services[].enabled` | bool | Create (`true`) or remove (`false`) the sentinel |
| `services[].sentinel` | bool | Whether to manage a sentinel file for this service |
| `services[].default_config.copy` | bool | Copy the default config if set to `true` |
| `services[].default_config.source` | string | Source path for the default config |
| `services[].default_config.destination` | string | Destination path for the default config |

### name vs unit

`name` is always used as the sentinel filename and the display label in `bootconf check` output. `unit` is the systemd unit name passed to `systemctl`. Set `unit` when the two differ:

```yaml
- name: disco          # sentinel file: /data/config/services/disco
  unit: disco-daemon   # systemctl start disco-daemon / systemctl is-active disco-daemon
  enabled: true
  sentinel: true
```

When `unit` is omitted, `name` is used for both.

## Default config copy

When `default_config.copy: true`, bootconf copies the source file to the destination path:

- If the destination already exists, the content is written alongside it as `<destination>.new`; existing config is **never overwritten**.
- The destination directory is created if it does not exist (mode `0750`).
- The copied file is owned by `root:root` with mode `0640`.

This is designed for first-boot provisioning of a writable config from a read-only default. After the first copy, the file is yours; bootconf will not touch it again.

## Apply mode

With `bootconf run --apply`, after each enabled service's sentinel is written, bootconf runs:

```
systemctl start <unit>
```

A failure is logged as a warning but does not fail the module — the sentinel has already been written.

## Health check

`bootconf check` verifies each enabled service is active:

```
systemctl is-active <unit>
```

## Dry-run

```
INFO [services] would write sentinel /etc/bootconf/services/myservice (dry-run)
INFO [services] would copy /etc/myservice/myservice.conf → /data/config/myservice/myservice.conf (dry-run)
```

With `--apply`:

```
INFO [services] would write sentinel /etc/bootconf/services/myservice (dry-run)
INFO [services] would run systemctl start myservice-daemon (dry-run)
```
