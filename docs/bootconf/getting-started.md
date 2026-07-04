# Getting Started

Install bootconf, write a config file, register the systemd unit, and run it for the first time.

## Install

### From source

Requires Go 1.24+.

```bash
git clone https://github.com/offline-lab/bootconf
cd bootconf
make
make install           # installs to /usr/local/bin/bootconf
```

Build with version info baked in:

```bash
make VERSION=v0.1.0 all
```

### Cross-compile

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
  -ldflags="-s -w -X github.com/offline-lab/bootconf/cmd/bootconf/commands.Version=v0.1.0" \
  -o bootconf cmd/bootconf/main.go
```

## Configure

Create `/boot/firmware/bootconf.yaml` (override with `--config` / `-c`).

A minimal config that sets hostname and provisions an admin user:

```yaml
bootconf:
  enabled: true
  directory: /var/lib/bootconf

system:
  enabled: true
  hostname: myhost
  timezone: UTC

users:
  enabled: true
  directory: /etc/bootconf/users
  users:
    - name: admin
      enabled: true
      sudo: true
      authorized_keys:
        - "ssh-ed25519 AAAA... admin@workstation"
```

See [Configuration](configuration.md) for every available field.

## Add the systemd unit

```ini
# /etc/systemd/system/bootconf.service
[Unit]
Description=Apply boot configuration
Before=network-pre.target
Wants=network-pre.target
DefaultDependencies=no
After=local-fs.target

[Service]
Type=notify
ExecStart=/usr/local/bin/bootconf run
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
```

```bash
systemctl enable bootconf.service
```

`Type=notify` lets systemd track exact completion. Bootconf sends `READY=1` via `sd_notify` after all modules finish.

## First run

Test your config without touching the system:

```bash
bootconf run --dry-run
```

Dry-run traverses the full code path and catches template syntax errors, missing keys, and validation failures, but skips all file writes and command execution.

Apply the configuration:

```bash
bootconf run
```

Apply and immediately start services (users, ssh, wifi, and each enabled service):

```bash
bootconf run --apply
```

Verify the running system matches the configuration:

```bash
bootconf check
```

Check the last run result:

```bash
bootconf status
```

## What's next

- [Configuration](configuration.md): every config field documented
- [Modules](modules/system.md): per-module reference with examples
- Run `bootconf --help` for the full CLI reference
