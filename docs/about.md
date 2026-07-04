# About

## Purpose

Offline Lab is an open-source platform for running applications on low-power devices without internet. We build software for situations where connectivity is unreliable or unavailable: travel, remote areas, temporary setups where existing tools stop working when the network drops.

Offline Lab OS currently targets the Raspberry Pi Zero 2W, Pi 3, Pi 4, and QEMU arm64.

## Use cases

Offline Lab serves people who need computing tools but can't depend on internet access:

- **Travelers** on long trips, cruises, or remote itineraries who want file sharing, media, and communication without roaming or satellite costs.
- **Off-grid communities** in rural or remote areas where internet is slow, expensive, or absent. A few Raspberry Pis provide local services for the whole community.
- **Small groups** that want to share services over a local network without routing anything through the cloud. A travel router and a couple of nodes are enough to get started.

In all cases, the platform works fully offline. When internet is available, it syncs data and pulls updates. When it isn't, nothing breaks.

## Design principles

- **Offline-first, not offline-only.** The system never waits for a network that isn't there. When internet is available, it syncs and updates.
- **Low power above all.** No background polling, no unnecessary logging, no idle services.
- **Simple over clever.** File-per-record state, bind mounts, systemd. Boring technology, no premature abstraction.
- **Portable packages.** Each app ships as a self-contained squashfs image — no package managers, no runtime dependency resolution.

## Project ecosystem

| Project | Docs | Description |
|---|---|---|
| [operating-system](https://github.com/offline-lab/operating-system) | [offline-lab.com/docs](https://offline-lab.com/docs) | OS image builder (Buildroot), packages, and on-device tooling |
| [framework](https://github.com/offline-lab/framework) | [offline-lab.com/docs/framework](https://offline-lab.com/docs/framework) | Bash utility library and boxctl device management CLI |
| [bootconf](https://github.com/offline-lab/bootconf) | [offline-lab.com/docs/bootconf](https://offline-lab.com/docs/bootconf) | Declarative boot-time configuration for Offline Lab OS |
| [disco](https://github.com/offline-lab/disco) | [offline-lab.com/docs/disco](https://offline-lab.com/docs/disco) | Service discovery and name resolution for offline networks |
| [appctl](https://github.com/offline-lab/appctl) | [offline-lab.com/docs/appctl](https://offline-lab.com/docs/appctl) | On-device CLI for installing and managing app packages |
| [buildctl](https://github.com/offline-lab/buildctl) | [offline-lab.com/docs/buildctl](https://offline-lab.com/docs/buildctl) | Developer-side CLI for building, signing, and publishing app packages |
| sync | — | Data synchronization tools (planned) |

## License

Offline Lab is released under [AGPL v3](https://www.gnu.org/licenses/agpl-3.0.en.html).

## Who builds this

Offline Lab is an open-source community project. See the [contributing guide](contributing.md) to get started.
