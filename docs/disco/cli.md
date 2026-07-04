# CLI Reference

The `disco` binary is the management interface for the running daemon. It communicates over the Unix socket at `/run/disco.sock`.

## Global flags

These flags apply to all subcommands that connect to the daemon.

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--socket` | `-s` | `/run/disco.sock` | Path to daemon socket |
| `--config` | `-c` | | Config file to read socket path from |
| `--json` | `-j` | | Output in JSON format |

The socket path is resolved in this order: `--socket` flag, `DISCO_SOCKET` environment variable, `daemon.socket_path` from `--config`, default `/run/disco.sock`.

---

## disco hosts

List all hosts in the daemon's cache.

```bash
disco hosts
disco hosts --json
```

**Output columns**: ID (first 8 chars of machine ID), HOSTNAME, ADDRESSES, STATUS, SERVICES, LAST SEEN

**Host status values**:

| Status | Meaning |
|--------|---------|
| `healthy` | Seen within the grace period |
| `stale` | Not seen recently but not yet expired |
| `lost` | Expired; will be removed on next cleanup |
| `static` | Defined in config; never expires |

### disco hosts show

Show detailed information for one host. Accepts a hostname, a full machine ID (32 hex chars), or a unique machine ID prefix.

```bash
disco hosts show node1
disco hosts show a1b2c3d4
disco hosts show a1b2          # prefix match; fails if ambiguous
```

### disco hosts forget

Remove a host from the cache immediately. The host will reappear if it broadcasts again.

```bash
disco hosts forget node1
```

### disco hosts mark-lost

Mark a host as lost. It will be removed on the next cleanup cycle.

```bash
disco hosts mark-lost node1
```

---

## disco services

List all services discovered across all hosts.

```bash
disco services
disco services --json
```

Pass a service name to show which hosts advertise it:

```bash
disco services www
```

---

## disco service add

Tell the running daemon to advertise a new service on this host. The daemon updates its store, broadcasts immediately, and includes the service in all future announcements. Useful in `ExecStartPost=` of a systemd unit.

```bash
disco service add <name> <port> [--alias <alias>]
```

```bash
disco service add myapp 8080
disco service add myapp 8080 --alias myapp.local --alias app
```

| Flag | Short | Description |
|------|-------|-------------|
| `--alias` | `-a` | Additional alias name(s) to advertise |

---

## disco lookup

Resolve a hostname to its IP addresses.

```bash
disco lookup node1
```

Returns one IP per line. Exits non-zero if the host is not found.

---

## disco status

Show a summary of the daemon's current state.

```bash
disco status
```

```
Disco Daemon Status
------------------------------
Socket:      /run/disco.sock
Total hosts: 4
  Healthy:   3
  Stale:     1
  Lost:      0
  Static:    0
```

---

## disco ping

Send UDP ping requests to check daemon connectivity on a remote node. The target is resolved via the daemon as a hostname, machine ID, or service name before sending.

```bash
disco ping <target> [flags]
```

```bash
disco ping node1
disco ping node1 --count 10 --verbose
disco ping 192.168.1.10 --port 5354
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--port` | `-p` | `5354` | Target UDP port |
| `--count` | `-n` | `4` | Number of pings (1–10) |
| `--interval` | `-i` | `1s` | Time between pings (minimum `100ms`) |
| `--verbose` | `-v` | | Print each ping result |

---

## disco listen

Listen for raw broadcast messages on the network. Binds directly to the UDP port; no daemon connection required.

```bash
disco listen [flags]
```

```bash
disco listen
disco listen --json
disco listen --broadcast 192.168.1.255:5354
disco listen --key-file /etc/disco/keys.json --require-signed
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--broadcast` | `-b` | config or `255.255.255.255:5354` | Broadcast address to listen on |
| `--key-file` | `-k` | | Key file for signature verification; unsigned messages are shown but flagged |
| `--require-signed` | | `false` | Drop unsigned or unverifiable messages (requires `--key-file`) |

---

## disco check

Attempt TCP connections to all discovered services and report which are reachable.

```bash
disco check [flags]
```

```bash
disco check
disco check --timeout 2s --verbose
disco check --json
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--timeout` | `-t` | `2s` | Connection timeout per service |
| `--verbose` | `-v` | | Show error detail for unreachable services |

---

## disco location

List GPS location broadcasts received by the daemon. The daemon stores the latest fix per source — each source corresponds to one GPS device on the network.

```bash
disco location
disco location --json
```

**Output columns**: SOURCE, LATITUDE, LONGITUDE, ALTITUDE, SATS, LAST SEEN

### disco location show

Show full detail for one GPS source.

```bash
disco location show gps-timeserver
disco location show gps-pi-01 --json
```

---

## disco announce

Send manual broadcast announcements. Does not require a running daemon.

```bash
disco announce --hostname <name> [flags]
```

```bash
disco announce --hostname web1
disco announce --hostname web1 --service www --port 80
disco announce --hostname web1 --count 3 --interval 2s
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--hostname` | `-n` | (required) | Hostname to announce |
| `--addr` | `-a` | `255.255.255.255:5354` | Broadcast address |
| `--interval` | `-i` | `5s` | Time between announcements |
| `--count` | | `0` (unlimited) | Number of announcements |
| `--service` | `-S` | | Service name to include (requires `--port`) |
| `--port` | `-p` | | Service port (requires `--service`) |
| `--alias` | `-A` | | Alias name(s) for the service |

---

## disco key

Manage cryptographic keys for message signing.

### disco key generate

Generate a new public/private key pair and save it to a file.

```bash
disco key generate [key-file]   # default: /etc/disco/keys.json
```

Output includes the public key, which you distribute to trusted peers.

### disco key show

Display the current keys and list of trusted peers from a key file.

```bash
disco key show [key-file]
```

### disco key add-trusted

Add a peer's public key to the trusted list.

```bash
disco key add-trusted <public-key> [key-file]
```

The public key must be 64 hex characters. See [How-to: Enable Security](how-to/security.md).

---

## disco time

Show the current time synchronization status.

```bash
disco time
```

```
Synced: YES
Sources: 2
Offset: +0.000023 seconds
Last sync: 2026-06-13T10:30:00Z
```

---

## disco timeset

Force the daemon to apply a time update immediately from available GPS sources.

```bash
disco timeset [flags]
```

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--backward` | `-b` | `false` | Allow stepping the clock backward |
| `--verbose` | `-v` | | Print adjustment details |
| `--timeout` | `-t` | `30s` | Operation timeout |

---

## disco start

Start the `disco-daemon` binary with validated flags. The daemon binary is searched in the same directory as `disco`, then in `PATH`.

```bash
disco start [daemon-flags]
```

Only these daemon flags are allowed:

| Flag | Description |
|------|-------------|
| `-config <path>` | Path to configuration file |
| `-v`, `-verbose` | Enable verbose logging |
| `-help` | Show daemon help |

---

## disco config validate

Validate a configuration file and print a summary.

```bash
disco config validate /etc/disco/config.yaml
```

Exits non-zero if validation fails. Prints warnings for non-fatal issues.
