# Hardware

## Supported devices

| Board | Arch | Status |
|---|---|---|
| Raspberry Pi Zero 2W | arm64 | Primary target |
| Raspberry Pi 3 | arm64 | Supported |
| Raspberry Pi 4 | arm64 | Supported |
| QEMU arm64 | arm64 | Development / CI |

The Zero 2W is the primary deployment target: small, low-power, and capable enough for a small group of users. The goal is a setup that fits in a bag with a stack of powerbanks.

## Storage

Each device boots from a micro SD card. Minimum card size is **8 GB**.

See [Boot](boot.md) for the full partition layout and A/B slot logic.

## Power

There are no specific watt-hour targets. The principle is to minimize consumption at every level:

- Disable services that aren't actively needed
- No background tasks, cron jobs, or periodic polling
- Clean logs at boot
- Measure and cut unnecessary CPU and memory usage

The system should run as long as possible on a standard USB powerbank.

## Networking

### Travel router

The recommended setup is a low-power travel router providing WiFi between nodes and, when available, upstream internet for syncing data. No specific model is required. Any device that provides WiFi and DHCP works.

### WiFi

Devices connect to the travel router or any configured network. WiFi credentials are provisioned by `bootconf` from `/data/config/bootconf.yaml`. DHCP is used for IP assignment. See [Boot configuration](bootconf.md) for details.

### USB

The Zero 2W's USB OTG port supports USB networking (gadget mode). This lets a phone or laptop connect directly to the device's services over USB. A `usb0` interface appears on the host with a static link-local address.

### Mesh

Batman-adv mesh networking between nodes is a future goal. This could replace the travel router and reduce power consumption by removing a separate device.
