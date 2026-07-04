# disco

Disco is a name service daemon for offline, airgapped networks. Nodes discover each other automatically via UDP broadcast. Name resolution integrates with glibc via a custom NSS module, so standard tools — `ping`, `ssh`, `curl` — resolve hostnames without DNS or `/etc/hosts` entries.

No internet connection. No central registry. No manual configuration after the initial setup.

## Components

| Component | Binary | What it does |
|-----------|--------|-------------|
| `disco-daemon` | `disco-daemon` | Listens for broadcasts, maintains the host cache, serves NSS queries via Unix socket, optionally runs a DNS server and time sync |
| `disco` | `disco` | CLI for querying and managing the daemon |
| `libnss_disco.so.2` | shared library | NSS module; glibc calls it for name resolution |
| `disco-gps-broadcaster` | `disco-gps-broadcaster` | Broadcasts GPS time over UDP; used with the optional time sync feature |

## Where to go next

- [Getting Started](getting-started.md): install disco on two nodes and watch them discover each other
- [Installation](installation.md): Debian packages, source builds, cross-compilation, systemd setup
- [Configuration](configuration.md): full `config.yaml` reference
- [CLI Reference](cli.md): every `disco` subcommand and flag
- [NSS Module](nss.md): install `libnss_disco.so.2` and configure `nsswitch.conf`
- [Architecture](architecture-overview.md): how discovery and name resolution work
