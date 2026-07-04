# Architecture

## Overview

Disco is built around two ideas: nodes announce themselves, and the daemon caches what it hears. Nothing is centralized. Every node is self-contained.

The daemon has no knowledge of the network topology at startup. It broadcasts its presence on a UDP socket, receives announcements from other nodes, and builds an in-memory cache of what it has seen. The cache drives both the NSS module (via Unix socket) and the optional DNS server.

## Discovery protocol

Each node broadcasts a JSON `ANNOUNCE` message on UDP port 5354 at a configurable interval (default 30 seconds). The message contains the node's hostname, IP addresses, machine ID, and detected services.

```json
{
  "type": "ANNOUNCE",
  "message_id": "announce-1234567890",
  "timestamp": 1708123456,
  "hostname": "node1",
  "machine_id": "a1b2c3d4...",
  "addresses": ["192.168.1.10"],
  "services": [
    {"name": "www", "port": 80},
    {"name": "ssh", "port": 22}
  ],
  "ttl": 3600
}
```

Any node that receives this message updates its cache. There is no handshake, no acknowledgement, no central coordinator. A node that goes silent has its cache entry transition from `healthy` to `stale` to `lost` as time passes; eventually the record is removed.

Message deduplication uses the `message_id` field with a 5-minute TTL, which also serves as replay protection when security is enabled.

## Service detection

When `discovery.detect_services: true`, the daemon periodically scans local ports. It compares open ports against `discovery.service_port_mapping` to produce human-readable service names (`www`, `smtp`, `ssh`, etc.) and includes these in each announcement.

Services can also be registered dynamically via `disco service add`, which tells the running daemon to advertise a new service immediately without a config change.

## Name resolution

Applications call `getaddrinfo()` or `gethostbyname()`, which glibc routes through the Name Service Switch based on `/etc/nsswitch.conf`. With `disco` in the `hosts` line, glibc loads `libnss_disco.so.2` and calls into it.

The NSS module connects to the daemon's Unix socket at `/run/disco.sock` and sends a JSON query:

```json
{"type": "QUERY_BY_NAME", "request_id": "query-001", "name": "node1"}
```

The daemon responds with the cached record:

```json
{
  "type": "SUCCESS",
  "request_id": "query-001",
  "hosts": [{
    "hostname": "node1",
    "addresses": ["192.168.1.10"],
    "status": "healthy",
    "services": {"www": "80/tcp"},
    "last_seen_ago": "12s"
  }]
}
```

If the daemon is not running, the socket does not exist and the NSS module returns `UNAVAIL` immediately. glibc falls through to the next source in `nsswitch.conf` (usually `resolve` or `dns`), so resolution continues to work.

## Security model

Without security enabled, any node on the broadcast domain can inject arbitrary records. With security enabled, each node signs its `ANNOUNCE` messages using HMAC-SHA256. The daemon verifies signatures against a list of trusted public keys and drops messages that fail verification or carry an unknown key.

Signed messages include a timestamp. The daemon rejects messages with a timestamp more than 5 minutes old, preventing replays of captured announcements.

The `TIME_ANNOUNCE` messages used for GPS time sync follow the same signing mechanism.

## Time synchronization

When `time_sync.enabled: true`, the daemon listens for `TIME_ANNOUNCE` messages on the same UDP port. These messages carry GPS-derived timestamps from broadcaster nodes (Raspberry Pi, Arduino, ESP32).

The daemon does not accept a single source. It waits for `min_sources` independent broadcasters to agree within `max_source_spread` of each other. Once the threshold is met, it adjusts the system clock: stepping for large offsets, slewing for small ones.

This design tolerates a single malfunctioning GPS source.

## Failure modes

**Daemon not running**: The NSS socket does not exist. glibc returns `UNAVAIL` and falls through to `resolve` or `dns`. Discovery stops but name resolution continues.

**Network partition**: Announcements stop arriving. Affected nodes transition from `healthy` to `stale` to `lost` over time. When the partition heals and announcements resume, records return to `healthy`.

**Broadcast storm**: The token bucket rate limiter caps outbound broadcasts at `network.max_broadcast_rate` messages per second (default 10). Incoming duplicates within the 5-minute deduplication window are discarded.

**Cache expiry**: If all records expire (e.g. daemon restarted with no peers online), `getent hosts` returns nothing from disco. glibc falls through to the next NSS source. Records repopulate on the next broadcast cycle (default 30 seconds).

## Code structure

```
cmd/
  daemon/              Entry point for disco-daemon
  disco/               Entry point for disco CLI
    commands/          One file per subcommand
    internal/cli/      Shared CLI utilities, table output, validation
  gps-broadcaster/     Entry point for disco-gps-broadcaster

internal/
  client/              HTTP-over-Unix-socket client for daemon queries
  config/              Configuration parsing and validation
  daemon/              Core daemon: cache management, socket server
  discovery/           Broadcast protocol, rate limiting, deduplication
  dns/                 Optional DNS server
  logging/             Structured logging (text and JSON)
  nss/                 NSS query/response types and protocol constants
  security/            Message signing and verification (HMAC-SHA256)
  service/             Local port scanning and service detection
  timesync/            GPS time synchronization

libnss/                C source for libnss_disco.so.2
gps-broadcaster/       Arduino and ESPHome implementations
```
