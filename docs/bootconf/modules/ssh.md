# ssh

Manages SSH host key generation and the service sentinel file.

## What it does

When **enabled**:

1. Generates a host key at `<directory>/hostkey` if one does not exist yet.
2. Creates a sentinel file at `<services.directory>/ssh`.

When **disabled**:

- Removes the sentinel file at `<services.directory>/ssh` if it exists.

Bootconf does not start or stop the SSH daemon. It creates or removes the sentinel file and leaves service lifecycle to systemd (via `ConditionPathExists=`).

## Config

```yaml
ssh:
  enabled: true
  directory: /etc/bootconf/ssh
  keytype: ed25519
  generate_host_keys: true
  daemon: dropbear
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable or disable SSH |
| `directory` | string | | Where the host key is written |
| `keytype` | string | `ed25519` | Key algorithm: `ed25519` or `rsa` |
| `generate_host_keys` | bool | | Generate a key on first boot if absent |
| `daemon` | string | `dropbear` | Which daemon to generate keys for: `dropbear` or `openssh` |

## Host key generation

When `generate_host_keys: true` and no key exists at `<directory>/hostkey`:

| Daemon | Command |
|--------|---------|
| `dropbear` | `dropbearkey -t <keytype> -f <directory>/hostkey` |
| `openssh` | `ssh-keygen -t <keytype> -f <directory>/hostkey -N ""` |

Existing host keys are **never** overwritten. The check is a stat on the key file; if it exists, generation is skipped.

The host key is written with mode `0600`. The `<directory>` is created with mode `0700` if it does not exist.

## Sentinel file

The sentinel at `<services.directory>/ssh` is an empty file. Your systemd units use `ConditionPathExists=` to decide whether to start the daemon:

```ini
[Unit]
ConditionPathExists=/etc/bootconf/services/ssh
```

When `enabled: false`, bootconf removes the sentinel. The SSH daemon will not start on the next boot.

## Dry-run

```
INFO [ssh] would generate host key at /etc/bootconf/ssh/hostkey using dropbear (dry-run)
INFO [ssh] would write sentinel /etc/bootconf/services/ssh (dry-run)
```
