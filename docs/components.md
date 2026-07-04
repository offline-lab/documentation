# Service model

## OS packages

The base OS is built from a set of focused Buildroot packages. Each is self-contained with its own scripts and systemd units.

OS-level packages are documented in [Packages](packages.md).

## Service model

Services on Offline Lab are packaged as squashfs images and run as systemd portable services. The base OS provides the foundation. Services provide the functionality.

Each service image contains everything it needs. Images are placed on `/data/apps` and attached using systemd's portable service mechanism.

User data stays on `/data`, separate from the service image. Updating a service means replacing its image without losing data.

## Offline concessions

Packages are designed around a "cutoff" moment, after which no new data can be fetched.

Content databases like Wikipedia and maps are frozen at the last sync. Security updates stop arriving. The network compensates with strict firewall rules and known-client policies. Services must work indefinitely without upstream connectivity.
