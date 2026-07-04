# bootconf

Bootconf is a declarative boot configuration tool for Linux. It reads a single YAML file and applies system settings during early boot, before any other service starts.

It runs on **every boot**, so configuration changes take effect on the next reboot without reinstalling or reimaging the system.

No cloud dependency. No agent. No runtime daemon. Just a binary, a YAML file, and a systemd unit.

## What it manages

| Module | What it does |
|--------|-------------|
| [`system`](modules/system.md) | Sets hostname and timezone via `hostnamectl` / `timedatectl` |
| [`ssh`](modules/ssh.md) | Generates SSH host keys (dropbear or openssh), manages service sentinel |
| [`wifi`](modules/wifi.md) | Writes `wpa_supplicant.conf` from a pre-hashed WPA2 PSK |
| [`services`](modules/services.md) | Creates/removes sentinel files; optionally copies a default config |
| [`users`](modules/users.md) | Provisions user accounts via `systemd-sysusers`, sets up SSH keys and sudo |
| [`files`](modules/files.md) | Copies or writes arbitrary files into the target filesystem |
| [`templates`](modules/templates.md) | Renders Go `text/template` files with config-supplied variables |
| [`shell`](modules/shell.md) | Executes shell commands at boot, capturing output to log files |
| [`unitrun`](modules/unitrun.md) | Writes shell scripts and systemd units, enables them via `systemctl` |

## Where to go next

- [Getting Started](getting-started.md): install, configure, and run bootconf for the first time
- [Configuration](configuration.md): full YAML reference for every field
- [Modules](modules/system.md): per-module documentation with examples
