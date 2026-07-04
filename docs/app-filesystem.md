# App Filesystem Layout

For the full package format spec (naming, metadata schema, signing), see
[Package Format Spec](specs/package-format.md).

---

## Required files

Every squashfs image must contain at minimum:

```
/etc/os-release          ← required by portablectl for image identification
/usr/lib/systemd/system/<name>.service   ← main service unit
```

`/etc/os-release` must include at least:
```
ID=<name>
VERSION_ID=<version>
```

where `<name>` matches the `name` field in the package JSON metadata exactly.

A `.socket` unit is required alongside the service unit if `socket_activation: true`
is set in the package metadata.

---

## File ownership and permissions

**All files inside the squashfs must be owned by root (uid 0, gid 0).**

The squashfs is read-only (dm-verity enforced at runtime). The service process can
read and execute root-owned files via world permissions (`755` for binaries, `644`
for static files), the same way any process reads `/usr/bin/*` on a normal system.

The service user is allocated at install time and is not known at build time. There is
no mechanism to embed the runtime uid in the image, and no reason to: write access
to the squashfs is impossible regardless of ownership.

**Required permissions:**
- Binaries and scripts: `root:root 755`
- Config templates and static files: `root:root 644`
- Directories: `root:root 755`

---

## Packaging constraints

These constraints are enforced or warned on by `buildctl validate`.

### 1. Use `RuntimeDirectory=` for runtime files

If the service needs PID files, Unix sockets, or lock files, declare
`RuntimeDirectory=<name>` in the unit file. systemd creates `/run/<name>/` on the
system and bind-mounts it into the service namespace automatically (verified: systemd 257 +
`RootImage=`). The app name is always known at build time.

Do not create ad-hoc directories in `/run/` via `ExecStartPre=` or similar.

### 2. No `User=` or `Group=` in unit files


Unit files inside the squashfs must not include `User=` or `Group=` directives.
appctl generates these in a drop-in at install time based on the allocated uid.
Including them in the unit file is misleading (they are overridden at install) and
buildctl will warn.

**Why:** the runtime username (`app<uid>`) is not known until appctl allocates a uid
at install time. It cannot be embedded in the image at build time.

### 3. No internal privilege dropping

Services must not call `setuid()`, `setgid()`, or `initgroups()` to switch to a named
user defined in the image's own `/etc/passwd` after startup. The service must run as
the single user systemd assigns via `User=` throughout its lifetime.

Many upstream daemons start as root and drop to an internal user (e.g., mosquitto drops
to a `mosquitto` user, nginx to `nginx`). That internal user (e.g. uid 100 inside the
squashfs) will not match the runtime user (`app6000`), causing the process to run with
the wrong uid or fail.

**This is a squashfs content requirement.** The image must ship with internal privilege
dropping disabled. Concretely, the config file or startup flags inside the squashfs must
tell the daemon not to switch users. Common approaches:

- Remove the `user <name>` directive from the daemon's config file inside the squashfs
  (e.g., `/etc/mosquitto/mosquitto.conf`, `/etc/nginx/nginx.conf`)
- Pass a `--no-drop-privs`, `--foreground`, or equivalent flag in the `ExecStart=` line
  of the unit file

Note: buildctl uses Docker as its build backend to produce squashfs images. These
config changes are applied during that build step, but they are requirements on the
squashfs content, not on Docker itself. buildctl should warn on common daemons known to
drop privileges if the mitigation is not detected in the resulting image.

### 4. No writable paths inside the squashfs

All paths that the service writes to at runtime must be declared as volumes in
`package.yaml`. Writing to paths inside the squashfs root is not possible; dm-verity
will block the write and the service will fail.

---

## Writable storage: volumes

Only two sources may be mounted into a service namespace:

1. Paths already inside the squashfs (read-only, dm-verity protected)
2. Paths managed by appctl: the app's own data dirs and its runtime dir

No other system paths are permitted. appctl controls the left side of every `BindPaths=`
entirely. A package cannot declare mounts to arbitrary system locations. This prevents a
malicious or compromised package from accessing other apps' data, signing keys, or
system configuration.

### Persistent volumes (declared in package.yaml)

Package authors declare the namespace target paths for persistent data:

```yaml
volumes:
  config: /etc/mosquitto     # where config lives inside the namespace
  data:   /var/lib/mosquitto # where runtime data lives inside the namespace
```

Two keys: `config` and `data`. No freeform keys accepted.
System path: `/data/apps/<hash>/<name>/{config,data}/` (persistent across reboots).

Apps must not write logs to files. Log output goes to stderr/stdout, captured by the
systemd journal. This reduces SD card write wear and provides a unified log interface
via `journalctl -u <name>`.

### Runtime directory (declared in the unit file, not in package.yaml)

Services that need a runtime directory for PID files, Unix sockets, or lock files
declare it in their unit file with `RuntimeDirectory=<name>`:

```ini
[Service]
RuntimeDirectory=mosquitto
```

`RuntimeDirectory=` with `RootImage=` is handled entirely by systemd (verified on
systemd 257, man systemd.exec(5)): systemd creates `/run/<name>/` on the **system**,
owned by the service user, and automatically bind-mounts it into the service namespace.
No manual `BindPaths=` needed. The directory is removed when the service stops.

The socket or PID file at `/run/mosquitto/mosquitto.sock` is accessible from the
system at that same path, with no hash prefix or namespace entry required.

`RuntimeDirectory=<name>` belongs in the squashfs unit file, not in appctl's drop-in:
the app name is known at build time and this is a legitimate service definition concern.

On the system, appctl maps these to `/data/apps/<repo-hash>/<name>/{config,data}/`.
The package author never references or knows the system path.

**Why not freeform mounts:** allowing packages to declare arbitrary system paths would
let a malicious package mount `/data/config/keys/` (signing keys), another app's data
dir, or the appctl database. Restricting to the app's own subdirs eliminates this
attack surface entirely.

**Common cases that might seem to need system mounts (and why they don't):**

| Case | Solution |
|---|---|
| SSL CA certificates | Bake a cert bundle into the squashfs; refresh at image update |
| Timezone | Bake `/etc/localtime` into squashfs, or use UTC |
| Large user-provided content (e.g. media files) | User places files in the app's `data/` dir |
| Cross-app Unix socket | Managed by appctl at `/run/apps/<hash>/<name>/`; not a package concern |
| Device access | Declared via `devices` metadata field, handled separately |

**Default config seeding:** if a declared volume target path contains files inside
the squashfs (e.g., `/etc/mosquitto/mosquitto.conf`), appctl copies those files to
the writable system directory on first install, before the bind mount takes effect. This seeds
writable config from the image's bundled defaults. Updates do not overwrite live config —
that is the `post_install` lifecycle hook's responsibility.

Place default config files at their normal paths inside the squashfs. They will be
copied to the writable volume on first install and shadowed by the bind mount thereafter.

---

## Example: mosquitto

```
squashfs/
  etc/
    os-release                     ← ID=mosquitto VERSION_ID=2.0.18
    mosquitto/
      mosquitto.conf               ← default config (seeded to writable volume on install)
  usr/
    sbin/
      mosquitto                    ← root:root 755
    lib/systemd/system/
      mosquitto.service            ← no User=, no Group=
```

`mosquitto.service` (inside squashfs):
```ini
[Unit]
Description=Mosquitto MQTT broker
After=network.target

[Service]
ExecStart=/usr/sbin/mosquitto -c /etc/mosquitto/mosquitto.conf
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`package.yaml`:
```yaml
name: mosquitto
version: 2.0.18
arch: arm64
volumes:
  config: /etc/mosquitto
  data:   /var/lib/mosquitto
```

appctl generates at install:
```ini
# /etc/systemd/system.attached/mosquitto.service.d/99-appctl.conf
[Service]
User=app6000
Group=app6000
BindPaths=/data/apps/a0d7b954/mosquitto/config:/etc/mosquitto
BindPaths=/data/apps/a0d7b954/mosquitto/data:/var/lib/mosquitto
```

The `RuntimeDirectory=mosquitto` in the unit file is handled by systemd: it creates
`/run/mosquitto/` on the system and bind-mounts it into the service namespace automatically.
After attach, the Unix socket is reachable system-wide at `/run/mosquitto/mosquitto.sock`.

---

## One service per image

Each squashfs image should contain exactly one primary service. This is not technically
enforced; portablectl will attach all units found in the image. Multiple services
in a single image are strongly discouraged.

**Why:**

- **Lifecycle coupling.** appctl installs, updates, and removes an image as a unit. Two services in the same image cannot be updated, rolled back, or removed independently.
- **Resource accounting.** appctl tracks resource usage per image. Bundled services produce misleading estimates and cannot be individually constrained.
- **User isolation.** Each image runs as a single `app<uid>`. Multiple services sharing one uid share a filesystem identity with no separation between them.

This mirrors the Docker convention: one process per container, compose for multi-service stacks.

**For multi-service applications:** use `appctl compose` (see T53). Compose lets you
declare multiple apps as a group with ordered install and coordinated lifecycle, while
keeping each service in its own image with independent versioning and rollback.

Until `appctl compose` is available, install services independently and wire them
together via their declared ports and Unix sockets.

---

## References

- [systemd portable services](https://systemd.io/PORTABLE_SERVICES/)
- [systemd.exec(5): RootImage=](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#RootImage=)
- [systemd.exec(5): BindPaths=](https://www.freedesktop.org/software/systemd/man/systemd.exec.html#BindPaths=)
