# users

Provisions system user accounts using the `systemd-sysusers` convention.

## What it does

For each **enabled** user:

1. Writes a `systemd-sysusers` config fragment to `<directory>/<name>.conf`.
2. Writes a `systemd-tmpfiles` config fragment to `<tmpfiles_dir>/<name>.conf` containing a `C` directive that copies `/etc/skel` into the home directory (creating it if it does not yet exist).
3. Runs `systemd-tmpfiles --create <tmpfiles_dir>/<name>.conf` to apply the directive immediately.
4. Creates `<home>/.ssh/` (mode `0700`, owned by the user's UID).
5. Writes `<home>/.ssh/authorized_keys` with the configured public keys (mode `0600`, owned by the user's UID).

The `C` directive is a no-op if the home directory already exists and is non-empty, so re-running bootconf is safe.

For each **disabled** user:

- Removes `<directory>/<name>.conf` and `<tmpfiles_dir>/<name>.conf`.
- Calls `userdel <name>` and removes the user from the `sudo` group.

UIDs are assigned sequentially starting from `2000` based on position in the list.

## Config

```yaml
users:
  enabled: true
  directory: /etc/bootconf/users
  tmpfiles_dir: /data/config/tmpfiles
  users:
    - name: admin
      enabled: true
      sudo: true
      home: /home/admin
      authorized_keys:
        - "ssh-ed25519 AAAA... admin@workstation"
        - "ssh-ed25519 AAAA... admin@laptop"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `directory` | string | | Where sysusers `.conf` files are written |
| `tmpfiles_dir` | string | `/data/config/tmpfiles` | Where tmpfiles.d `.conf` files are written |
| `users[].name` | string | | Username |
| `users[].enabled` | bool | | Provision (`true`) or remove (`false`) the user |
| `users[].sudo` | bool | | Add `m <name> sudo` directive to the sysusers config |
| `users[].home` | string | `/home/<name>` | Home directory. Defaults to `/home/<name>` if not set. |
| `users[].authorized_keys` | list | | SSH public keys to write to `authorized_keys` |

## sysusers config format

Bootconf writes one `.conf` file per user:

```
u admin 2000 "admin" /home/admin /bin/bash
m admin sudo
```

The `m admin sudo` line is only written when `sudo: true`. The `sudo` group must already exist on the system and be configured in `/etc/sudoers` (typically `%sudo ALL=(ALL) ALL`). Bootconf manages membership, not sudoers rules.

These files are picked up by `systemd-sysusers` when it runs. On a system using bootconf, `bootconf-sysusers.service` runs immediately after `bootconf.service` and calls `systemd-sysusers` to create the declared users.

## SSH authorized keys

The `authorized_keys` file is written on every boot, so adding or removing keys from the config takes effect on the next reboot.

## Dry-run

```
INFO [users] would create users dir /etc/bootconf/users (dry-run)
INFO [users] would write sysusers config /etc/bootconf/users/admin.conf (dry-run)
INFO [users] would write tmpfiles config /data/config/tmpfiles/admin.conf (dry-run)
INFO [users] would run systemd-tmpfiles --create /data/config/tmpfiles/admin.conf (dry-run)
INFO [users] would create .ssh dir /home/admin/.ssh (dry-run)
INFO [users] would write 2 authorized key(s) to /home/admin/.ssh/authorized_keys (dry-run)
```
