# Reboot Proofing

> **⚠ Moved OS-side (2026-07-05).** Per
> [ADR-0036](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0036-foreign-host-baseline.md),
> the tools target the boring persistent systemd host and know nothing about
> overlay wipes; everything on this page is now an **Offline Lab OS conformance
> concern** (duty list: `OS-CONFORMANCE.md` in the umbrella repo). Boot-time
> restore is the generic, idempotent **`appctl recover`** (replaces
> `rehydrate`/`restore-apps.service` as the mechanism); the OS ships one boot
> unit that calls it after `/data` mounts.

This page describes what state survives a reboot, what survives a slot switch
(RAUC A/B OTA), and how each piece is handled.

---

## Storage layout

The disk has three relevant partitions:

| Partition | Mount | Survives reboot | Survives slot switch |
|---|---|---|---|
| rootfs-a / rootfs-b | `/` (read-only) | yes (unchanged) | yes (read-only OS image) |
| overlay.ext4 (p3) | `/mnt/overlay` | **no** (upper wiped on every boot) | **no** (upper wiped on every boot) |
| data.ext4 (p4) | `/data` | yes | yes |

The initramfs sets up an overlayfs combining the read-only rootfs with a per-slot
upper directory from the overlay partition:

```
lowerdir  = rootfs-a (read-only)
upperdir  = /overlay/a/upper     ← wiped on every boot; only explicitly restored files survive
workdir   = /overlay/a/work
merged    = /                    ← what the running system sees
```

The initramfs clears the slot upper directory on **every boot** (`rm -rf /overlay/<slot>/upper`)
before mounting the overlay. Only files explicitly restored from `/data` (currently: `machine-id`)
survive across reboots. Everything else written to `/etc` at runtime is gone on next boot.

---

## What currently survives slot switches

All persistent device state lives on `/data/`, which survives slot switches unchanged:

| State | Location | Populated by |
|---|---|---|
| SSH host key | `/data/config/ssh/hostkey` | `bootconf.service` |
| WiFi credentials | `/data/config/wifi/wpa_supplicant.conf` | `bootconf.service` |
| Admin authorized_keys | `/data/home/admin/.ssh/authorized_keys` | `bootconf.service` |
| App data and config volumes | `/var/lib/appctl/apps/` | appctl at install time |
| App state (file-per-record JSON) | `/var/lib/appctl/state/` | appctl |
| App images | `/var/lib/appctl/images/` | appctl |
| Resource baseline | `/var/lib/appctl/resources.json` | `offlinelab-resources.service` |
| appctl config | `/etc/appctl/appctl.conf` | appctl |

Network configuration (eth0, usb0, wlan0 static files) is in the read-only rootfs
and is identical across both slots. No action needed.

---

## What does not survive slot switches

### machine-id

systemd generates a machine-id on first boot and writes it to `/etc/machine-id` via
the overlayfs (slot upper). A slot switch starts with an empty upper, so systemd
generates a **new** machine-id, which breaks journal continuity and any software
using the machine-id for device identity.

**Fix:** store machine-id in `/data/config/system/machine-id`. The initramfs copies
it to the slot upper at boot before `switch_root`, ensuring consistency across slots.

Flow:
1. First boot: systemd generates machine-id, writes to `/etc/machine-id` (overlay upper).
2. `persist-machine-id.service` runs on shutdown: copies `/etc/machine-id` to `/data/config/system/machine-id` (skipped if destination already exists).
3. Every subsequent boot: initramfs copies `/data/config/system/machine-id` to `/overlay/<slot>/upper/etc/machine-id` before `switch_root`.

The file in `/data/config/system/machine-id` is the authoritative copy. The overlay
entry is always populated from it, never generated fresh after first boot.

### portablectl attachments

`portablectl attach` creates unit symlinks in `/etc/systemd/system/` and drop-ins in
`/etc/systemd/system/<unit>.d/`. These live in the overlay upper and do not survive a
slot switch.

**Fix:** a boot-time service runs `appctl rehydrate` which re-attaches
all apps recorded in `state/packages/`. See T27/T36. This covers both first boot on a new
slot and normal boot after a power cycle.

### Hostname

The default hostname (`offlinelab`) is static in the rootfs and survives slot switches
unchanged. Per-device hostname customization is out of scope until configctl (T46).
If an admin changes the hostname at runtime, it goes into the overlay upper and is lost
on slot switch. This is accepted behaviour for now.

---

## Implementation tasks

| Task | What |
|---|---|
| **T21** | `persist-machine-id.service` + initramfs machine-id copy |
| **T27** | `restore-apps.service` / `appctl rehydrate` boot unit |

---

## What the overlay upper may contain at runtime

For completeness, here is the full list of things that accumulate in the overlay upper
during normal operation. All of these are wiped on every reboot (intentional; the
overlay always starts clean):

| Path | Written by | Needs /data persistence? |
|---|---|---|
| `/etc/machine-id` | systemd PID1 on first boot | **yes** (T21) |
| `/etc/systemd/system/<app>.*` | portablectl attach | **yes** (rehydration T27/T36) |
| `/etc/portables/<app>.conf` | portablectl attach | **yes** (rehydration T27/T36) |
| `/etc/hostname` | hostnamectl (if used) | no; static default is fine for now |
| `/etc/localtime` | timedatectl (if used) | no; default timezone is fine for now |

All other `/etc` files are static in the rootfs and are not written at runtime.
