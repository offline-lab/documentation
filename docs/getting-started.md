# Getting Started

Get Offline Lab OS running on a Raspberry Pi Zero 2W: build the image, flash the SD card, and connect over SSH.

## What you need

- A Raspberry Pi Zero 2W
- A micro SD card, at least 8 GB
- A USB powerbank or USB-C power supply
- A computer to build the image and write the SD card (macOS or Linux)
- Docker Desktop or a native arm64 build VM

## Step 1: Build and configure the image

Build the OS image and configure WiFi and SSH credentials. See [Build the OS image](build-image.md) for full instructions covering both Docker and Buildbox paths.

The output is a compressed image file: `artifacts/pi-zero-2w/offlinelab-rpi-pi-zero-2w-arm64-<date>.img.gz`.

## Step 2: Install Offline Lab OS on the SD card

Write the image to your SD card. See [Install Offline Lab OS](burn-image.md) for the full procedure with troubleshooting.

## Step 3: Boot

Insert the SD card into the Pi Zero 2W and connect power. The first boot is slower because the data partition is resized and formatted to fill the card. On large cards (512 GB–1 TB) this can take several minutes on the Zero 2W's single-core IO. The device will reach the login prompt once it finishes.

## Step 4: Connect

Find the device's IP address from your router's DHCP lease table, or use the serial console if you have a USB-to-serial adapter. Then:

    ssh admin@<ip-address>

Once connected, check the system status with [boxctl](https://offline-lab.com/docs/framework):

    boxctl status

## What's next

- [Hardware](hardware.md): power and networking setup
- [Packages](packages.md): how the OS is structured
- [Configuration](configuration.md): WiFi, SSH, and runtime config
- [Contributing](contributing.md): if you want to help build
