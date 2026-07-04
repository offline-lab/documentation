# Command line tools

Offline Lab provides three CLIs, each scoped to a different context:

| Tool | Runs on | Purpose |
|---|---|---|
| [boxctl](boxctl.md) | The device | System management: status, network, firewall, power, updates, diagnostics |
| [appctl](appctl.md) | The device | App lifecycle: install, remove, update, start, stop, search |
| [buildctl](buildctl.md) | Developer workstation | Build, sign, and publish app packages |

boxctl and appctl are installed on the device at build time. buildctl runs on your workstation or CI machine and does not touch the device directly.
