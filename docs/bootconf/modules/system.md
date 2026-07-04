# system

Sets the system hostname and timezone during early boot.

## What it does

- Calls `hostnamectl set-hostname <hostname>` if `hostname` is set.
- Calls `timedatectl set-timezone <timezone>` if `timezone` is set.

Both fields are optional. If neither is set, the module is a no-op.

Before applying changes, the module checks that the status directory is writable. If it is not, the module fails immediately without calling either tool.

## Config

```yaml
system:
  enabled: true
  hostname: myhost
  timezone: UTC
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable the module |
| `hostname` | string | Hostname to set. Leave empty to skip. |
| `timezone` | string | Timezone to set (e.g. `UTC`, `Europe/Amsterdam`). Leave empty to skip. |

## Behaviour

`hostnamectl` and `timedatectl` are idempotent; applying the same value twice has no visible effect. Bootconf calls them unconditionally on every boot when the module is enabled.

## Dry-run

In dry-run mode, the module logs the commands it would run but does not execute them:

```
INFO [system] would run: hostnamectl set-hostname "myhost" (dry-run)
INFO [system] would run: timedatectl set-timezone "UTC" (dry-run)
```
