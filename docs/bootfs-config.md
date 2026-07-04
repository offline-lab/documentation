# Boot partition configuration

The boot partition (`/boot/firmware`, FAT32, ~32 MB) holds firmware blobs,
U-Boot, the kernel, and a `config/` provisioning directory.

## Boot partition layout

```
/boot/firmware/
├── bootconf.yaml.example       # template — copy to config/bootconf.yaml to activate
├── config/                     # provisioning inbox (consumed by initramfs, see below)
├── overlays/                   # RPi device tree overlays (firmware package)
├── bcm2710-rpi-zero-2-w.dtb    # device tree blob
├── bootcode.bin                # RPi first-stage bootloader
├── boot.scr                    # U-Boot script
├── cmdline.txt                 # kernel command line
├── config.txt                  # RPi firmware config
├── fixup.dat                   # RPi firmware fixup
├── initramfs.cpio.gz           # initramfs
├── start.elf                   # RPi VideoCore firmware
└── u-boot.bin                  # U-Boot
```

## Provisioning via config/

`/boot/firmware/config/` is a **provisioning inbox**. On every boot, the initramfs:

1. Mounts the boot partition read-write.
2. If `config/` exists: copies the entire directory tree into `/data/config/`, overwriting any existing files, then deletes `config/` from the boot partition.
3. Remounts the boot partition read-only.

This means files placed in `config/` are **consumed on first boot** and are gone from the SD card afterwards. The live configuration is always in `/data/config/`. To re-provision after first boot, place the new files in `config/` again.

The directory structure under `config/` mirrors `/data/config/` exactly:

| Place on boot partition | Lands in |
|---|---|
| `config/bootconf.yaml` | `/data/config/bootconf.yaml` |
| `config/wifi/wpa_supplicant.conf` | `/data/config/wifi/wpa_supplicant.conf` |
| `config/ssh/authorized_keys` | `/data/config/ssh/authorized_keys` |

## bootconf.yaml

To configure the device, place a `bootconf.yaml` in `config/` on the boot partition before first boot. After the initramfs moves it to `/data/config/bootconf.yaml`, `bootconf.service` reads it there on every boot.

See [Boot configuration (bootconf)](bootconf.md) for the full YAML reference.

## Getting config onto the boot partition

### Method 1: build-time (via .config)

Set options in your `.config` overlay (copy `config.example` to `.config`):

```ini
# Bake WiFi credentials into bootconf.yaml.example at build time
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_CREATE=y
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_SSID="your-ssid"
# PSK hash from: wpa_passphrase <ssid> <password>
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_PASSWORD_HASH="abc123..."
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_COUNTRY="NL"
```

### Method 2: manual SD card write

After flashing the image, mount the boot partition (first partition, FAT32) and
copy `bootconf.yaml.example` to `config/bootconf.yaml`, then edit it:

```sh
mount /dev/sdX1 /mnt
mkdir -p /mnt/config
cp /mnt/bootconf.yaml.example /mnt/config/bootconf.yaml
# edit /mnt/config/bootconf.yaml — set wifi.ssid, wifi.password_hash, etc.
umount /mnt
```

The boot partition can be mounted and edited from macOS, Windows, or Linux without
any special tools.

### Re-provisioning after first boot

To update credentials on a running device without SSH access (e.g. WiFi changed):

```sh
mount /dev/sdX1 /mnt
mkdir -p /mnt/config
cp new-bootconf.yaml /mnt/config/bootconf.yaml
umount /mnt
# reboot — initramfs overwrites /data/config/bootconf.yaml
```

## Security notes

- The boot partition is mounted read-only at runtime after provisioning completes.
- `bootconf.yaml` is world-readable on the FAT32 partition while it is present. Store
  only the WiFi PSK hash (from `wpa_passphrase`), never the plaintext password.
- After the initramfs consumes `config/`, the boot partition contains no credentials.
- If you used the build-time WiFi option, the hash is stored in your `.config` and
  baked into the boot partition image. Treat both as sensitive.
