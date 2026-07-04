# boxctl

boxctl is the on-device CLI for managing Offline Lab OS. It provides a unified interface to system status, networking, firewall, power, updates, and diagnostics — without requiring raw systemd or nftables commands.

Source: [github.com/offline-lab/framework](https://github.com/offline-lab/framework) · Docs: [framework.offline-lab.com](https://framework.offline-lab.com)

## Usage

Connect to your device via SSH and run:

```bash
boxctl status
```

Run `boxctl help` for an interactive command browser (uses fzf when available).

## Subcommands

| Command | What it does |
|---|---|
| `status` | System overview: hostname, IP addresses, disk, memory, uptime, running services |
| `net` | Network interfaces, IP addresses, WiFi status |
| `firewall` | View and manage nftables rules and per-app fragments |
| `power` | Power profile, CPU governor, sleep states |
| `reboot` | Reboot the device (with A/B slot awareness) |
| `shutdown` | Power off the device |
| `update` | RAUC A/B OTA status and trigger |
| `rollback` | Roll back to the previous A/B slot |
| `logs` | Journal filtering and tail |
| `diagnose` | Health checks: failed units, disk space, memory, network |
| `service` | List and inspect running services |
| `sysext` | Manage systemd system extensions |
| `confext` | Manage systemd configuration extensions |
| `config` | View and edit device configuration |
| `clock` | Hardware clock and time status |
| `screen` | Display and splash screen settings |
| `startup` | Boot target and runlevel management |

boxctl is built on the [framework](https://github.com/offline-lab/framework) Bash library. Each subcommand maps to a framework module (`net.sh`, `fw.sh`, `power.sh`, etc.) and can be called independently from scripts.
