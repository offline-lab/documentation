# Time Sync

Disco can synchronize the system clock from GPS time broadcasters on the network. This is useful in airgapped environments where NTP is unavailable. The daemon listens for `TIME_ANNOUNCE` messages on the same UDP port as discovery (5354).

## Prerequisites

At least one node on the network must run `disco-gps-broadcaster` or an equivalent (Arduino, ESP32). See [GPS Broadcaster](gps-broadcaster.md).

## Configure

In `/etc/disco/config.yaml`:

```yaml
time_sync:
  enabled: true
  min_sources: 2
  max_source_spread: 100ms
  max_stale_age: 30s
  max_dispersion: 1.0
  step_threshold: 128ms
  slew_threshold: 500us
  poll_interval: 60s
  require_signed: true
  allow_step_backward: false
```

Key tuning parameters:

- `min_sources`: how many independent GPS broadcasters must agree before the daemon adjusts the clock. Set to `1` if you only have one GPS source.
- `step_threshold`: offsets above this value cause an immediate clock step; offsets below it are slewed gradually.
- `allow_step_backward`: keep `false` unless your environment has a reason to allow it. Stepping the clock backward can break log timestamps and certificate validity checks.

## Restart the daemon

```bash
sudo systemctl restart disco-daemon
```

## Check sync status

```bash
disco time
```

```
Synced: YES
Sources: 2
Offset: +0.000023 seconds
Last sync: 2026-06-13T10:30:00Z
```

If `Synced: NO`, the daemon has not received enough agreeing TIME_ANNOUNCE messages yet. Check that GPS broadcasters are running and reachable on the same broadcast domain.

## Force a sync

```bash
disco timeset
```

The daemon applies an adjustment immediately using current sources, rather than waiting for the next `poll_interval`.

## Signed time messages

Set `require_signed: true` to reject unsigned TIME_ANNOUNCE messages. This requires that the GPS broadcaster is configured to sign its messages with a key that is in the daemon's trusted peers list. See [Enable Security](security.md) for key setup.
