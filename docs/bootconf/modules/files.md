# files

Copies or writes arbitrary files into the target filesystem.

## What it does

For each configured entry, bootconf either copies a file from a source path or writes inline content to a destination path.

Existing files are **never overwritten**. If the destination already exists, the content is placed at `<destination>.new` instead.

## Config

```yaml
files:
  enabled: true
  files:
    # Copy from a source file
    - source: /boot/firmware/config/app.conf
      destination: /etc/app/app.conf
      chmod: "640"

    # Write inline content
    - content: |
        [settings]
        key = value
      destination: /etc/app/settings.ini
      chmod: "640"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `files[].source` | string | | Source file path. Mutually exclusive with `content`. |
| `files[].content` | string | | Inline file content. Mutually exclusive with `source`. |
| `files[].destination` | string | | Destination path (required) |
| `files[].chmod` | string | `640` | Octal permission string (e.g. `640`, `600`, `755`) |

Exactly one of `source` or `content` must be set per entry. Setting both or neither is a validation error.

## Behaviour

- The destination directory is created if it does not exist (mode `0750`).
- Files are written as `root:root`. If `chown` fails (e.g. on a filesystem that does not support it), a warning is logged and the run continues.
- `chmod` values above `0777` are rejected. Setuid, setgid, and sticky bits cannot be set via bootconf.

## `.new` suffix

If `/etc/app/app.conf` already exists, bootconf writes to `/etc/app/app.conf.new` instead. No existing file is modified. This prevents overwriting user-edited configs on every boot.

To force a re-write, delete the destination file before rebooting.

## Dry-run

```
INFO [files] would copy /boot/firmware/config/app.conf → /etc/app/app.conf (chmod 640) (dry-run)
INFO [files] would write content → /etc/app/settings.ini (chmod 640) (dry-run)
```
