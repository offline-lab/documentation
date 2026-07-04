# Discovery

Automatic service discovery and name resolution for offline networks.

## What it does

Each node runs a daemon that broadcasts its identity (hostname, IP addresses, running services) over UDP. Other nodes receive these broadcasts and build a local cache. A custom NSS module wires name resolution into the OS, so standard tools like `ssh`, `curl`, and `ping` resolve discovered hosts without extra configuration.

## Why it exists

Offline Lab nodes run on a local WiFi network with no internet and no external DNS. Hardcoding IPs doesn't scale and breaks when nodes change. Disco fills this gap with zero-configuration discovery designed for resource-constrained devices.

Design priorities:

- **Minimal footprint**: under 10 MB RAM, designed for Raspberry Pi Zero 2W
- **Zero configuration**: nodes discover each other on first broadcast
- **Native integration**: NSS module means standard tools work without extra setup
- **Offline-first**: no dependencies on external services

## How it works

Each node runs `disco-daemon`, which does three things:

1. **Broadcast** - periodically sends a UDP packet (port 5354) with its hostname, IP addresses, and detected services
2. **Listen** - receives broadcasts from other nodes and maintains an in-memory cache
3. **Resolve** - answers name queries from the local NSS module over a Unix domain socket

Service detection is automatic. The daemon scans local TCP ports and maps them to service names (port 80 becomes `www`, port 25 becomes `smtp`, and so on). Discovered services are included in broadcasts so other nodes know what's running where.

```
Node A                          Node B
  |                               |
  |-- UDP broadcast (announce) -->|
  |   hostname: web1              |
  |   addresses: [10.0.0.1]       |
  |   services: {www: 80}         |
  |                               |
  |<-- UDP broadcast (announce) --|
  |        from Node B            |
  |                               |
  Both nodes update their caches
```

### Components

| Component | Description |
|---|---|
| disco-daemon | Go daemon. Handles broadcast, listening, service detection, name resolution. ~6 MB binary. |
| disco | CLI tool for querying and managing the daemon. Separate binary to avoid memory overhead in scripts. |
| libnss_disco.so.2 | C NSS module. Integrates with glibc so `gethostbyname()` and friends resolve discovered hosts. |
| disco-gps-broadcaster | Optional. Broadcasts GPS time for clock synchronization on airgapped networks. |

### Optional features

**DNS server.** Disco can serve DNS for the `.disco` domain, allowing standard DNS clients to resolve discovered hosts without the NSS module.

**Time synchronization.** On airgapped networks, NTP is unavailable. Disco can receive time from GPS broadcaster devices and synchronize the local clock. Requires at least two agreeing GPS sources before adjusting.

**Location sharing.** GPS broadcasters also share location data (coordinates, estimated country and timezone) via `LOCATION_ANNOUNCE` messages. All nodes maintain a location store with a 2-minute stale timeout. Location is always enabled when the daemon is running.

**Message signing.** Broadcasts can be signed with HMAC-SHA256 to prevent spoofing and replay attacks. Nodes verify signatures against a shared key before accepting announcements.

## In this section

- [Protocol reference](protocol.md) - wire protocol, message types, NSS queries, signing, rate limiting
- [CLI reference](cli.md) - commands and configuration
