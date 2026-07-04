# Configuration

Bootconf reads a single YAML file. The default path is `/boot/firmware/bootconf.yaml`. Override it with `--config` / `-c`.

Each top-level key maps to a module. All modules have an `enabled` field. Setting `bootconf.enabled: false` disables the entire tool. Disabling an individual module skips it but does not undo previous runs.

## Full reference

```yaml
# ─── bootconf ────────────────────────────────────────────────────────────────
bootconf:
  enabled: true
  # Status files are written here after each run.
  directory: /var/lib/bootconf
  # Execution order for modules. Modules run sequentially in this order.
  # Omit to use the default order below.
  order:
    - system
    - users
    - wifi
    - ssh
    - services
    - files
    - templates
    - unitrun
    - shell

# ─── system ──────────────────────────────────────────────────────────────────
system:
  enabled: true
  hostname: myhost
  timezone: UTC

# ─── ssh ─────────────────────────────────────────────────────────────────────
ssh:
  enabled: true
  # Directory where host keys are written.
  directory: /etc/bootconf/ssh
  # Key type: ed25519 (default) or rsa
  keytype: ed25519
  # Generate a host key on first boot if one does not exist yet.
  generate_host_keys: true
  # Daemon: dropbear (default) or openssh
  daemon: dropbear

# ─── wifi ────────────────────────────────────────────────────────────────────
wifi:
  enabled: false
  directory: /etc/bootconf/wifi
  ssid: "MyNetwork"
  # Pre-computed WPA2 PSK hash (64 hex chars). Use: wpa_passphrase <ssid>
  # Do NOT use the plaintext password here.
  password_hash: "614b0b8c..."
  # ISO 3166-1 alpha-2 country code
  country: NL

# ─── services ────────────────────────────────────────────────────────────────
services:
  enabled: true
  # Sentinel files are written here.
  directory: /etc/bootconf/services
  services:
    - name: myservice
      # Systemd unit name for systemctl start and health checks.
      # Optional: defaults to name when not set.
      unit: myservice-daemon
      enabled: true
      # Write a sentinel file at <directory>/<name> when enabled.
      sentinel: true
      # Optionally copy a default config on first presence.
      default_config:
        copy: true
        source: /etc/myservice/myservice.conf
        destination: /data/config/myservice/myservice.conf

# ─── users ───────────────────────────────────────────────────────────────────
users:
  enabled: true
  # sysusers .conf files are written here.
  directory: /etc/bootconf/users
  # tmpfiles.d .conf files are written here. Each file contains a C directive
  # that copies /etc/skel into the home directory on first creation.
  tmpfiles_dir: /data/config/tmpfiles
  users:
    - name: admin
      enabled: true
      sudo: true
      # Defaults to /home/<name> if not set.
      home: /home/admin
      authorized_keys:
        - "ssh-ed25519 AAAA... admin@workstation"

# ─── files ───────────────────────────────────────────────────────────────────
files:
  enabled: true
  files:
    # Copy a file from source to destination.
    - source: /boot/firmware/config/app.conf
      destination: /etc/app/app.conf
      chmod: "640"
    # Write inline content to a file.
    - content: |
        [settings]
        key = value
      destination: /etc/app/settings.ini
      chmod: "640"

# ─── templates ───────────────────────────────────────────────────────────────
templates:
  enabled: true
  templates:
    - source: /boot/firmware/templates/app.conf.tpl
      destination: /etc/app/app.conf
      chmod: "640"
      variables:
        listen_address: "127.0.0.1"
        port: "8080"

# ─── shell ───────────────────────────────────────────────────────────────────
shell:
  enabled: true
  # Logs and firstboot sentinels are written here.
  directory: /var/lib/bootconf/shell
  # Prepend a directory to PATH for every command. Inherits environment PATH when empty.
  path: ""
  commands:
    - name: setup-db
      # If false (default), a non-zero exit stops the module.
      allow_fail: false
      # If true, runs only once — a sentinel prevents re-execution on subsequent boots.
      firstboot: true
      command: |
        /usr/local/bin/init-database.sh

# ─── unitrun ─────────────────────────────────────────────────────────────────
unitrun:
  enabled: true
  # If true, injects ConditionFirstBoot=yes into every generated unit.
  firstboot: false
  # Prepend a directory to PATH in every generated unit (e.g. /usr/lib/framework/bin).
  # Omitted when empty — no Environment=PATH line is written.
  path: ""
  # Shell scripts are written here.
  directory: /var/lib/bootconf/scripts
  units:
    - name: setup-overlay
      enabled: true
      # Lines written verbatim into the [Unit] section.
      dependencies:
        - After=local-fs.target
        - Before=network-pre.target
      command: |
        /usr/local/bin/setup-overlay.sh
        exit 0
```

## Field summary

### bootconf

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | If false, the tool exits immediately without running any module |
| `directory` | string | `/data/config/bootconf` | Directory for status files |
| `order` | list | see below | Module execution order. Modules run sequentially in the listed order. Each entry must be a known module name; duplicates are rejected. Default: `system`, `users`, `wifi`, `ssh`, `services`, `files`, `templates`, `unitrun`, `shell`. |

### system

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable the module |
| `hostname` | string | Set via `hostnamectl set-hostname` |
| `timezone` | string | Set via `timedatectl set-timezone` |

### ssh

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `directory` | string | | Where host keys are written |
| `keytype` | string | `ed25519` | Key algorithm (`ed25519` or `rsa`) |
| `generate_host_keys` | bool | | Generate a key if none exists |
| `daemon` | string | `dropbear` | `dropbear` or `openssh` |

### wifi

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable the module |
| `directory` | string | Where `wpa_supplicant.conf` is written |
| `ssid` | string | Network SSID (max 32 bytes, printable characters) |
| `password_hash` | string | WPA2 PSK hash (64 hex characters) |
| `country` | string | ISO 3166-1 alpha-2 country code |

### services

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable the module |
| `directory` | string | Where sentinel files are written |
| `services[].name` | string | Service name; used as the sentinel filename and display label |
| `services[].unit` | string | Systemd unit name for `systemctl start` and health checks. Defaults to `name`. |
| `services[].enabled` | bool | Create or remove the sentinel |
| `services[].sentinel` | bool | Whether to manage a sentinel file |
| `services[].default_config.copy` | bool | Copy a default config if set |
| `services[].default_config.source` | string | Source path |
| `services[].default_config.destination` | string | Destination path |

### users

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `directory` | string | | Where sysusers `.conf` files are written |
| `tmpfiles_dir` | string | `/data/config/tmpfiles` | Where tmpfiles.d `.conf` files are written; used to copy `/etc/skel` into each home directory |
| `users[].name` | string | | Username |
| `users[].enabled` | bool | | Provision or remove the user |
| `users[].sudo` | bool | | Add to the `sudo` group |
| `users[].home` | string | `/home/<name>` | Home directory path |
| `users[].authorized_keys` | list | | SSH public keys written to `~/.ssh/authorized_keys` |

### files

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `files[].source` | string | | Source file path. Mutually exclusive with `content`. |
| `files[].content` | string | | Inline file content. Mutually exclusive with `source`. |
| `files[].destination` | string | | Destination path (required) |
| `files[].chmod` | string | `640` | Octal permission string. Setuid bits are rejected. |

Exactly one of `source` or `content` must be set per entry.

### templates

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `templates[].source` | string | | Source template path |
| `templates[].destination` | string | | Destination path |
| `templates[].chmod` | string | `640` | Octal permission string |
| `templates[].variables` | map | | Key/value pairs available in the template as `{{ .key }}` |

### shell

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `directory` | string | | Where logs and firstboot sentinels are written |
| `path` | string | | Prepend a directory to `PATH` for every command. Inherits environment `PATH` when empty. |
| `commands[].name` | string | | Command name (used for log and sentinel filenames) |
| `commands[].command` | string | | Shell command passed to `bash -c` |
| `commands[].allow_fail` | bool | `false` | If false, a non-zero exit stops the module |
| `commands[].firstboot` | bool | `false` | Run only once; subsequent boots skip it |

### unitrun

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `firstboot` | bool | `false` | Inject `ConditionFirstBoot=yes` into every generated unit |
| `directory` | string | | Where shell scripts are written |
| `path` | string | | Prepend a directory to `PATH` in every generated unit. Omitted when empty. |
| `units[].name` | string | | Unit name (used for script and service filenames) |
| `units[].enabled` | bool | | Provision or remove the unit |
| `units[].dependencies` | list | | Lines written verbatim into the `[Unit]` section |
| `units[].command` | string | | Script body (written after `#!/bin/bash\n`) |
