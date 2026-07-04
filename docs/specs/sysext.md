# System Extensions

> **Note (2026-07-05).** Scope unchanged: host sysext/confext remain
> **boxctl-managed** (ADR-0023) and are distinct from layered *app* extensions,
> which are now governed by UAPI.4 verbatim
> ([ADR-0034](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0034-uapi-substrate.md)).
> The companion-file signing model further down this page (`.roothash`/`.p7s`/
> `.verity`) still contradicts the in-DDI model and remains **unresolved**
> (Q-C5): this spec needs a proper design pass. This page is also OL-OS
> specific (`/data/…` paths) — per ADR-0036 that wiring is OS-side.

systemd supports two types of runtime extensions that layer additional content on top
of the read-only rootfs without modifying the OS image: **sysext** and **confext**.

| | sysext | confext |
|---|---|---|
| Extends | `/usr/` and `/opt/` | `/etc/` |
| Storage on device | `/data/extensions/sysext/` | `/data/extensions/confext/` |
| Bind-mount target | `/var/lib/extensions/` | `/etc/extensions/` |
| Merged by | `systemd-sysext.service` | `systemd-confext.service` |
| Metadata path | `/usr/lib/extension-release.d/extension-release.<name>` | `/etc/extension-release.d/extension-release.<name>` |
| boxctl command | `boxctl sysext` | `boxctl confext` |

Both use the same squashfs image format, the same dm-verity signing, and the same
naming convention. The difference is purely in what part of the filesystem they extend
and where their metadata file lives inside the image.

---

## When to use sysext

Use a sysext when you need to ship binaries, modules, or libraries into `/usr/` without
a full OTA:

- Extra kernel modules not in the default image
- An alternative build of a library (e.g. ffmpeg with different codec support)
- Debug tooling (strace, gdb, tcpdump) deployed temporarily
- Additional firmware blobs for hardware peripherals

Do **not** use sysext for application services. Use a [portable service](package-format.md)
instead. The distinction: sysext extends the OS layer; portable services add isolated,
managed applications on top of it.

## When to use confext

Use a confext when you need to ship a read-only `/etc` overlay without a full OTA:

- A large set of trusted CA certificates
- A static `nsswitch.conf` or `resolv.conf` override
- Read-only drop-ins for system daemons that don't support `conf.d/` directories

For most configuration on Offline Lab devices, prefer `/data/config/` managed by
`config.sh`. Use confext when a read-only `/etc` overlay is specifically what you need,
or when you want to distribute configuration the same way as sysext images (signed,
versioned, drop-in).

---

## Image format

Both sysext and confext are squashfs images. The only structural difference is the path
of the metadata file inside the image.

**sysext**: metadata at:
```
/usr/lib/extension-release.d/extension-release.<name>
```

**confext**: metadata at:
```
/etc/extension-release.d/extension-release.<name>
```

Minimum required content in both cases:

```ini
ID=offline-lab
SYSEXT_LEVEL=1
```

`ID` must match the OS `ID` field in `/etc/os-release`. systemd will refuse to merge an
extension where this does not match.

The squashfs tree mirrors the paths it extends. To add `/usr/bin/strace` via sysext,
the squashfs must contain `/usr/bin/strace`.

---

## Naming convention

```
<name>_<arch>.raw
```

Examples:
```
debug-tools_arm64.raw
extra-certs_arm64.raw
```

systemd discovers extensions by scanning the extension directories for `*.raw` files.
The `<arch>` suffix is a convention for clarity; it is not parsed by systemd.

---

## Storage and discovery

Extensions are stored on `/data/` and bind-mounted to the paths systemd scans:

```
/data/extensions/sysext/<name>_<arch>.raw   →   /var/lib/extensions/
/data/extensions/confext/<name>_<arch>.raw  →   /etc/extensions/
```

Both `systemd-sysext.service` and `systemd-confext.service` are enabled at boot and
merge all discovered extensions before `multi-user.target`. No manual action is needed
for extensions already present in `/data/extensions/` before reboot.

Extensions are **admin-managed**: drop files into the appropriate directory and
refresh. There is no package manager step.

---

## dm-verity

Both image types support dm-verity companion files, using the same naming convention
as app packages:

```
<name>_<arch>.raw
<name>_<arch>.raw.roothash
<name>_<arch>.raw.roothash.p7s
<name>_<arch>.raw.verity
```

Place them alongside the image. systemd discovers and applies them automatically.
The signing key is the same build key used for app packages from the same repo.

---

## Commands

**sysext:**
```bash
systemd-sysext status    # list extensions and merge state
systemd-sysext merge     # merge all extensions into /usr/
systemd-sysext unmerge   # remove merged extensions
systemd-sysext refresh   # unmerge + merge
```

**confext:**
```bash
systemd-confext status
systemd-confext merge
systemd-confext unmerge
systemd-confext refresh
```

---

## boxctl integration

`boxctl sysext` and `boxctl confext` are thin wrappers for operators who should not
need raw systemd commands:

```bash
boxctl sysext list       # list discovered extensions and merge status
boxctl sysext merge      # merge all extensions
boxctl sysext unmerge    # remove merged extensions
boxctl sysext refresh    # pick up new files in /data/extensions/sysext/
boxctl sysext status     # show merged state
```

`boxctl confext` follows the same command structure. Both use the corresponding
framework modules (`sysext.sh`, `confext.sh`) internally. Neither is exposed via
`appctl`; extensions are a host configuration concern, not an app packaging concern.

---

## What extensions do not provide

- **No lifecycle hooks**: the extension is present or it is not.
- **No port rules or device grants**: extensions only extend the filesystem.
- **No per-app isolation**: content merged by sysext is visible to all processes on
  the system. Do not ship secrets or security-sensitive material in a sysext.
- **No appctl support**: managed manually or via boxctl only.
