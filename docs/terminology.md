# Terminology

Quick reference for terms used across the documentation.

| Term | Meaning |
|---|---|
| **Offline Lab OS** | The offline-first operating system built with Buildroot |
| **Package** | A set of five files per app: `.squashfs`, `.squashfs.roothash`, `.squashfs.roothash.p7s`, `.squashfs.verity`, `.json`. Distributed as a `.zip` archive. The distributable unit |
| **Service** | A running instance of an installed package on a device |
| **Framework** | The Bash utility library and `boxctl` CLI bundled with Offline Lab OS |
| **Node** | A single device (e.g. Raspberry Pi Zero 2W) running Offline Lab OS |
| **Disco** | The service discovery and name resolution daemon |
| **Slot** | One of two root filesystem partitions (A/B) used for atomic updates |
| **Boot partition** | The FAT32 partition holding firmware, U-Boot, kernel, initramfs, and `bootconf.yaml` |
| **Overlay partition** | Holds per-slot overlayfs upper/work directories |
| **/data** | The persistent read-write partition for user data and package state |
| **bootconf** | Boot-time configuration tool: reads `/data/config/bootconf.yaml` at every boot and provisions SSH keys, WiFi, hostname, and user config |
| **boxctl** | On-device CLI for managing Offline Lab OS (status, updates, network, diagnostics) |
| **appctl** | On-device CLI for installing and managing app packages |
| **buildctl** | Developer-side CLI for building, signing, and publishing app packages |
| **sysext** | systemd system extension: a squashfs image that extends `/usr/` or `/opt/` at runtime without modifying the read-only rootfs |
| **confext** | systemd configuration extension: a squashfs image that layers additional config under `/etc/` at runtime |
