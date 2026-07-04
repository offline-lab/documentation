# Burn image to SD card

This page assumes you already have a built image in `artifacts/`. If you don't have one yet, see [Build the image](build-image.md) first.

## Prerequisites

- A micro SD card, at least 8 GB
- The compressed image file: `artifacts/pi-zero-2w/offlinelab-rpi-pi-zero-2w-arm64-<date>.img.gz`
- `dd` (built into macOS and Linux)
- `gunzip` (built into macOS and Linux)

## Find your SD card device

**macOS:**

```bash
diskutil list
```

Look for a disk matching your SD card's size. The device name will be something like `/dev/disk4`. Note it down; you'll need it in the `dd` command.

Unmount the disk before writing:

```bash
diskutil unmountDisk /dev/disk4
```

**Linux:**

```bash
lsblk
```

The SD card will appear as `/dev/sdX` or `/dev/mmcblkX`. Unmount any auto-mounted partitions before proceeding.

## Write the image

Decompress the image first (this keeps the `.gz` file):

```bash
gunzip -k artifacts/pi-zero-2w/offlinelab-rpi-pi-zero-2w-arm64*.img.gz
```

Then write it to the SD card. Replace `/dev/diskN` with the device from the previous step:

```bash
sudo dd if=artifacts/pi-zero-2w/offlinelab-rpi-pi-zero-2w-arm64*.img of=/dev/diskN bs=4M status=progress
```

On macOS, using the raw device (`/dev/rdiskN` instead of `/dev/diskN`) is faster:

```bash
sudo dd if=artifacts/pi-zero-2w/offlinelab-rpi-pi-zero-2w-arm64*.img of=/dev/rdisk4 bs=4M status=progress
```

Wait for `dd` to finish and the prompt to return. On a Class 10 / UHS-I card, writing ~250MB takes around 30–60 seconds.

## After writing

Eject the SD card before removing it:

```bash
# macOS
diskutil eject /dev/disk4

# Linux
sync && udisksctl power-off -b /dev/sdX
```

Insert the SD card into the Pi Zero 2W and connect power. The first boot takes slightly longer than subsequent boots because the data partition is expanded to fill the remaining card space.

## Troubleshooting

**`dd: /dev/diskN: Resource busy`**: the disk has mounted partitions. Run `diskutil unmountDisk /dev/diskN` (macOS) or unmount each partition manually (Linux).

**Write speed is very slow**: write speed depends on the SD card. Cheap cards can be significantly slower than rated speeds. Use a name-brand A1- or A2-rated card.

**Device doesn't boot**: verify the image was written to the correct device and wasn't corrupted during the gunzip step. Compare the uncompressed image size against the SD card capacity.
