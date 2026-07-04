# Disco CLI reference

## Commands

```bash
disco hosts                     # List all discovered hosts
disco hosts <name>              # Show host details
disco hosts forget <name>       # Remove host from cache
disco hosts mark-lost <name>    # Mark host as lost
disco services                  # List all services
disco services <name>           # Show service details
disco lookup <name>             # Resolve hostname to IP
disco status                    # Daemon status
disco time                      # Time sync status
disco timeset                   # Force time update
disco ping <hostname>           # Ping a discovered host
disco check                     # Check which services are reachable
disco announce                  # Send manual announcement
disco key generate              # Generate security keys
```

## Configuration

Disco is configured via YAML. Minimal config:

```yaml
daemon:
  socket_path: /run/disco.sock
  broadcast_interval: 30s
  record_ttl: 3600s

network:
  broadcast_addr: 255.255.255.255:5354
  max_broadcast_rate: 10

discovery:
  enabled: true
  detect_services: true

security:
  enabled: false
```

Service port mapping is configurable:

```yaml
discovery:
  service_port_mapping:
    www: [80, 443]
    smtp: [25, 587]
    mail: [143, 993]
    ssh: [22]
```

The daemon detects services by attempting a TCP connection to each mapped port on `127.0.0.1`. Open ports are matched to service names and included in announcements.

## Reference implementation

The reference implementation is written in Go and available at [github.com/offline-lab/disco](https://github.com/offline-lab/disco). It includes:

- `disco-daemon` - the core daemon (~6 MB binary)
- `disco` - CLI management tool (~4 MB binary)
- `libnss_disco.so.2` - C NSS module for glibc integration
- `disco-gps-broadcaster` - GPS time source for Raspberry Pi, Arduino, and ESP32

The NSS module requires Linux with glibc. The daemon and CLI work on any platform Go supports, but broadcast discovery requires UDP broadcast support.
