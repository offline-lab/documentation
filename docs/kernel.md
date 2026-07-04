# Kernel Strategy

## Current state

The current build uses `bcm2711_defconfig` from the RPi kernel fork (`rpi-6.12.y`) with a
small fragment overlay adding overlayfs, initramfs, and USB gadget support.

This defconfig is designed for all Raspberry Pi models (Pi 3, 3+, 4, 400, Zero 2W, CM3, CM4)
and includes support for a huge range of peripherals. The resulting kernel has:

- **3814 enabled options** (1916 built-in, 1898 modules)
- **85 network vendor drivers** (Intel, Mellanox, Broadcom enterprise, Amazon, etc.)
- **307 media/video drivers** (V4L2 capture, DVB tuners, webcam drivers)
- **157 sound drivers** (HiFiBerry, JustBoom, IQAudio, USB audio, dozens of I2C codecs)
- **73 input drivers** (touchscreens, joysticks, keyboards, mice)
- **126 crypto algorithms** (most unused)
- **Pi 4/5 specific hardware** (PCIe, BCM2711 thermal, BCM2712 IOMMU, V3D, GENET)
- **Unused buses** (CAN, ATA/SATA, NFC, SCSI, Gameport)
- **All wireless vendors** (Atheros, Intel, MediaTek, Realtek, Marvell; only Broadcom is needed)
- **Enterprise storage** (NFS, CIFS, CEPH, GFS2, OCFS2, Btrfs, ReiserFS, JFS, XFS)

On a Pi Zero 2W with 512MB RAM, every unnecessary module wastes build time, image space,
and kernel memory for metadata. The full module tree is ~100MB+ uncompressed.

## What we actually need

### SoC & boot essentials (built-in, =y)
- BCM2835 mailbox, power, thermal, watchdog
- MMC: `BCM2835`, `SDHCI_IPROC` (must be built-in for initramfs to find /dev/mmcblk0)
- Serial: `SERIAL_8250` + `BCM2835AUX` (mini UART/ttyS0), `SERIAL_AMBA_PL011` (BT/ttyAMA0)
- GPIO, pinctrl, clocks (pulled in by SoC selection)

### Overlayfs & initramfs (built-in)
- `OVERLAY_FS`, `BLK_DEV_INITRD`, `RD_GZIP`

### USB gadget (built-in)
- `USB_DWC2`, `USB_GADGET`, `USB_CONFIGFS`, `USB_LIBCOMPOSITE`
- Functions: `USB_F_ACM`, `USB_F_ECM`, `USB_F_SERIAL`, `USB_U_SERIAL`, `USB_U_ETHER`
- Keep `USB_CONFIGFS_MASS_STORAGE` (useful for exposing SD card partitions to host)

### WiFi (module)
- `CFG80211`, `MAC80211` (wireless stack)
- `BRCMUTIL`, `BRCMFMAC`, `BRCMFMAC_SDIO` (only driver we need)

### Bluetooth (module)
- `BT`, `BT_BREDR`, `BT_LE`, `BT_RFCOMM`, `BT_HIDP`, `BT_BNEP`
- `BT_HCIUART` + `BT_HCIUART_BCM` + `BT_HCIUART_H4` + `BT_HCIUART_SERDEV`
- `BT_BCM` (BCM43xx firmware loading)

### Audio (module)
- `SND_BCM2835` (HDMI + headphone jack audio via VCHIQ)
- `SND_SOC` + `SND_BCM2835_SOC_I2S` (if I2S DAC hats needed later)
- `SND_USB_AUDIO` (USB speakers/DACs; keep for portable service use cases)
- Drop all 30+ HiFiBerry/IQAudio/JustBoom board-specific codec drivers

### GPU/Display (module)
- `DRM_VC4` + `DRM_VC4_HDMI_CEC` (vc4 is the Pi Zero 2W GPU)
- `DRM_FBDEV_EMULATION` (console on HDMI)
- Drop `DRM_V3D` (Pi 4/5 only), all panel drivers, `DRM_UDL`, `DRM_GUD`

### Filesystems
- `EXT4_FS` (rootfs, data partition)
- `VFAT_FS`, `FAT_FS`, `MSDOS_FS` (boot partition)
- `OVERLAY_FS` (core feature)
- `SQUASHFS` + `SQUASHFS_ZSTD` (portable services)
- `CONFIGFS_FS` (USB gadget)
- `PROC_FS`, `SYSFS`, `TMPFS`, `DEVTMPFS`
- Drop: ReiserFS, JFS, XFS, GFS2, OCFS2, Btrfs, Bcachefs, NILFS2, F2FS, NTFS3, exFAT,
  HFS, HFSPLUS, JFFS2, UBIFS, EROFS, NFS, CEPH, 9P, ISO9660, UDF, eCryptFS

### Networking
- `INET`, `IPV6` (basic stack)
- `NETFILTER` basics (for future firewall rules)
- `BRIDGE` only if needed for container networking (can defer)
- Drop: all 85 NET_VENDOR_* drivers, CAN, NFC, SCSI, ATA, InfiniBand

### Crypto
- Keep only what the kernel, WiFi (WPA), and Bluetooth need
- `CRYPTO_AES`, `CRYPTO_SHA256`, `CRYPTO_HMAC`, `CRYPTO_CCM`, `CRYPTO_GCM`
- `CRYPTO_ECB`, `CRYPTO_CBC` (needed by various subsystems)
- Drop the other ~100 algorithms

## Implementation plan

### Phase 0.5: Kernel trimming (after first successful boot)

**Approach**: expanded kernel fragment that disables categories of drivers.

1. Boot the current image, run `lsmod` to see what's actually loaded
2. Save the running config via `/proc/config.gz`
3. Build expanded fragment file that disables unused categories:
   - All `NET_VENDOR_*` except Broadcom
   - All `WLAN_VENDOR_*` except Broadcom
   - All `SND_BCM2708_SOC_*` hat drivers
   - All `DRM_PANEL_*` except `RASPBERRYPI_TOUCHSCREEN` (maybe)
   - All non-Broadcom Bluetooth drivers (`BT_ATH3K`, `BT_INTEL`, `BT_MTK`, `BT_MRVL`, `BT_RTL`)
   - All USB audio except `SND_USB_AUDIO`
   - `DRM_V3D`, `DRM_GUD`, `DRM_UDL`, `DRM_SSD130X`
   - `BCM2711_THERMAL`, `BCM2712_*`, `PCIE_BRCMSTB` (Pi 4/5 only)
   - `CAN`, `NFC`, `ATA`, `GAMEPORT`, `SCSI` (as module)
   - Unused filesystems
   - Unused crypto

**Expected result**: ~1500-2000 enabled options (down from 3814), faster builds,
smaller module directory (~20-30MB vs 100MB+), lower RAM overhead.

### Phase 1: Custom defconfig

**Approach**: replace `bcm2711_defconfig` + fragment with a full custom defconfig.

1. Take the trimmed `.config` from Phase 0.5
2. Run `make savedefconfig` to produce a minimal defconfig
3. Store as `br2-external/configs/offlinelab_pi_zero_2w_defconfig` (replace current)
4. Remove the kernel fragment file (everything is in the defconfig now)
5. Test boot, WiFi, BT, USB gadget, audio, HDMI

**Benefits**: single source of truth, no fragment merge surprises, easier to review.

### Phase 1+: Power-saving patches

**Approach**: patch series on top of RPi fork.

Candidates for power-saving:
- CPU frequency governor tuning (schedutil with aggressive downscaling)
- `CONFIG_CPU_IDLE` + `CONFIG_ARM_CPUIDLE` (C-states for Cortex-A53)
- `CONFIG_SUSPEND` + `CONFIG_PM` for system suspend-to-RAM
- USB autosuspend for when gadget is not connected
- WiFi power save (`CONFIG_CFG80211_DEFAULT_PS=y`, already enabled)
- Runtime PM for unused peripherals (HDMI, I2C buses, SPI)
- Disable kernel features that consume power: `CONFIG_NO_HZ_FULL`, tickless idle

Patch location: `br2-external/boards/rpi/pi-zero-2w/patches/linux/`

### Why not mainline kernel

- BCM2710 (Pi Zero 2W SoC) has quirks handled by RPi fork:
  - Mini UART clock tied to GPU core clock (RPi-specific clock driver)
  - Firmware-based WiFi/BT initialization sequence
  - DWC2 OTG errata workarounds
  - VCHIQ kernel module for GPU communication (audio, camera, video decode)
  - vc4 driver patches not yet upstream
- Mainline support works but requires more debugging effort for less hardware coverage
- RPi fork tracks mainline closely (rebased regularly), so we get upstream fixes anyway
- If we ever need a mainline feature, cherry-pick into the fork

## Sizing estimates

| Config              | Options | Modules dir | Build time | RAM savings |
|---------------------|---------|-------------|------------|-------------|
| bcm2711 (current)   | ~3800   | ~100MB      | baseline   | —           |
| Trimmed fragment    | ~2000   | ~30MB       | -30-40%    | ~10-15MB    |
| Full custom defconf | ~1200   | ~15MB       | -50-60%    | ~15-20MB    |
| Tiny + addback      | ~800    | ~8MB        | -70%       | ~20-25MB    |

On 512MB RAM, 15–25MB saved by the kernel is significant. That is 3–5% of total RAM freed for portable services.

## Decision log

- **RPi fork over mainline**: hardware support maturity, less debugging, no blocker
- **Fragment-first over immediate custom defconfig**: need a working boot before trimming
- **Keep modules over built-in for WiFi/BT/audio/GPU**: allows unloading when unused,
  smaller kernel image for faster boot, runtime PM can suspend module hardware
- **Squashfs as module**: only loaded when portable services are attached
