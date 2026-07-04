# Boot

## Boot chain

```
RPi firmware (bootcode.bin → start.elf)
  └─ loads U-Boot (u-boot.bin from boot partition)
       └─ runs boot.scr
            └─ reads bootstate (p9), selects slot A or B
                 └─ loads kernel from kernel-a or kernel-b (squashfs)
                      └─ loads initramfs from boot partition
                           └─ mounts rootfs read-only
                                └─ mounts data partition (/data)
                                     └─ mounts boot partition (/boot/firmware)
                                          └─ provisions /data/config from /boot/firmware/config/
                                               └─ mounts overlayfs (upper on overlay partition)
                                                    └─ restores machine-id into overlay upper
                                                         └─ switch_root → systemd
```

No U-Boot shell, no GRUB, no splash screen at this stage. The terminal shows U-Boot output followed by kernel boot messages until systemd takes over.

## Partition layout

```
Primary:
  p1  boot       FAT32   32MB    firmware, U-Boot, initramfs, boot.scr, config files
  p2  (extended)                 container for logical partitions
  p3  overlay    ext4    96MB    per-slot overlayfs upper/work directories
  p4  data       ext4   64MB+   persistent user data (expanded on first boot)

Logical (inside p2):
  p5  kernel-a   sqfs   24MB    kernel Image, DTBs (slot A)
  p6  rootfs-a   ext4  512MB    root filesystem (slot A)
  p7  kernel-b   sqfs   24MB    kernel Image, DTBs (slot B)
  p8  rootfs-b   ext4  512MB    root filesystem (slot B)
  p9  bootstate  raw     8MB    U-Boot environment: BOOT_ORDER, boot counters
```

## U-Boot boot logic

U-Boot runs `boot.scr` (compiled from `boot.cmd`). The script implements an A/B bootchooser:

1. Read `BOOT_ORDER` from the bootstate env (e.g. `A B` or `B A`).
2. For each slot in order, check its boot counter. If the counter is zero, skip the slot (exhausted).
3. Decrement the counter for the selected slot and save it back to bootstate.
4. Load the kernel from the selected slot's squashfs partition.
5. Pass `rauc.slot=A` or `rauc.slot=B` on the kernel command line.

If both slots are exhausted (counters at zero), U-Boot resets both counters and retries, preferring whichever slot is first in `BOOT_ORDER`.

## Boot success signaling

The initramfs passes `rauc.slot=A|B` through to userspace via the kernel command line. After reaching multi-user.target, a systemd service (`rauc-mark-good.service`) reads this value and marks the active slot as good by resetting its boot counter to the configured maximum.

If the system crashes or panics before reaching multi-user.target, the counter stays decremented. After enough failures, U-Boot switches to the other slot.

## Initramfs

The initramfs is a small static busybox environment. The `init` script:

1. Mounts `proc`, `sys`, `dev`.
2. Reads `rauc.slot` from `/proc/cmdline` to determine which slot to boot (default: A).
3. Waits for the block device to appear (MMC or virtio, up to 10 s at 1 s intervals).
4. Waits for the selected rootfs partition to appear (up to 5 s at 0.1 s intervals).
5. Mounts the selected rootfs read-only at `/mnt`.
6. Mounts the data partition (`p4`) at `/data`.
7. Mounts the boot partition (`p1`, FAT32) at `/boot/firmware` read-write.
8. If `/boot/firmware/config/` exists: copies its contents into `/data/config/`, then deletes the directory. This is the provisioning step — see [Provisioning](#provisioning) below.
9. Remounts `/boot/firmware` read-only.
10. Mounts the overlay partition (`p3`) at `/overlay`.
11. Wipes and recreates the per-slot upper/work directories for a clean `/etc` on every boot.
12. Restores `machine-id` from `/data/config/system/machine-id` into the overlay upper (if present).
13. Sets up overlayfs with lower=`/mnt`, upper and work from the overlay partition, merged at `/newroot`.
14. Moves `/overlay` to `/newroot/mnt/overlay` (keeps the overlay partition accessible after switch_root).
15. Bind-mounts `/data` at `/newroot/data`.
16. Moves `proc`, `sys`, `dev`, and `/boot/firmware` into `/newroot`.
17. Runs `switch_root /newroot /sbin/init` to hand off to systemd.

The static busybox binary is embedded in the initramfs. There are no external dependencies.

## Provisioning

Any file placed under `/boot/firmware/config/` is treated as a provisioning intent. On every boot, the initramfs copies the entire `config/` directory tree into `/data/config/` (overwriting existing files) and then deletes `config/` from the boot partition.

This means:

- **First boot:** place `config/bootconf.yaml` on the SD card; it is moved to `/data/config/bootconf.yaml` and consumed.
- **Re-provisioning** (e.g. WiFi credentials changed): plug the SD card into any computer, create `config/` with the new file(s), reboot. The device picks up the change and the boot partition is clean again.
- **Normal boots** (no `config/` directory): the step is skipped; `/data/config/` is untouched.

The `config/` directory path mirrors `/data/config/` exactly. For example, to replace the WiFi config, place `config/wifi/wpa_supplicant.conf` on the boot partition.

## Overlayfs design

The overlay partition (`p3`) exists separately from `/data` for two reasons:

- **Slot isolation.** Each A/B slot gets its own upper/work directory. Switching slots doesn't carry stale OS-level write state from the previous slot.
- **Data separation.** User data on `/data` is independent of the OS overlay. An OS update doesn't touch user data, and user data doesn't bleed into the OS layer.

The upper is **not** tmpfs. On a 512MB device, using RAM for the overlay upper would be wasteful. The overlay partition is on SD card, same as everything else.

After a successful A/B slot switch, the old slot's overlay directory is left as-is. It can be cleared manually or will be reinitialised on the next write.

## First boot

On first boot the data partition is grown by `systemd-repart` using the configuration at `/usr/lib/repart.d/10-data.conf`. Systemd boot order is:

```
clock-load.service      ← loads fake hardware clock from /data
  └─ systemd-repart       ← grows /data partition to fill remaining card (first boot only)
       └─ bootconf.service  ← applies /data/config/bootconf.yaml
            └─ network, wifi, ssh, and all other services
```

`systemd-repart` grows the data partition to fill the remaining SD card space. It is a no-op on subsequent boots if `/data` is already at the expected size.

**First boot duration scales with card size.** `resize2fs` must initialise the entire partition. On an 8 GB card this takes a few seconds; on large cards (512 GB–1 TB) it can take several minutes on the Zero 2W. The device will reach the login prompt once it finishes; no intervention needed.

Boot-time provisioning (WiFi credentials, SSH keys) is applied by `bootconf` after the data partition is ready. See [Boot configuration](bootconf.md) and [Configuration](configuration.md).

## Boot partition contents

```
/boot/firmware/
├── bootconf.yaml.example       # template — copy to config/bootconf.yaml to activate
├── config/                     # provisioning inbox (consumed by initramfs on boot)
│   └── bootconf.yaml           # present only before first boot or when re-provisioning
├── overlays/                   # RPi device tree overlays
├── bcm2710-rpi-zero-2-w.dtb    # device tree blob
├── bootcode.bin                # RPi first-stage bootloader
├── boot.scr                    # U-Boot script (compiled from boot.cmd)
├── cmdline.txt                 # kernel command line
├── config.txt                  # RPi firmware config
├── fixup.dat                   # RPi firmware fixup
├── initramfs.cpio.gz           # initramfs
├── start.elf                   # RPi VideoCore firmware
└── u-boot.bin                  # U-Boot
```

The boot partition is mounted by the initramfs read-write (for provisioning), then remounted read-only before `switch_root`. Systemd adopts the existing mount via `boot-firmware.mount`; no remount occurs. The partition is not written to after `switch_root`.

## Trade-offs

**Shared bootloader.** U-Boot lives on the boot partition and is shared between slots. A bad U-Boot update affects both slots. This is a known limitation; per-slot bootloaders would require a more complex partition layout.

**Kernel per slot.** Each slot has its own kernel squashfs, so a kernel update is contained to the inactive slot and follows the same A/B rollback path as a rootfs update.

**Overlay persistence.** After a rootfs update, the old slot's overlay directory is not automatically cleared. If the slot is later activated again, it may see stale overlay state. Manual cleanup is required.

**Boot splash.** psplash is enabled. It runs during early boot and is dismissed once systemd's `psplash-quit.service` fires.
