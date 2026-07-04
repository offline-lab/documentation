# Enable DNS

Disco includes an optional DNS server. When enabled, discovered hosts are resolvable as `<hostname>.<domain>` — for example `node1.disco` — using any standard DNS tool.

The DNS server only serves the disco domain; it does not forward other queries.

## Port conflict with systemd-resolved

systemd-resolved binds its stub resolver on `127.0.0.53:53`. If disco binds `0.0.0.0:53`, the kernel rejects the bind with `EADDRINUSE` because the wildcard address overlaps with the existing `127.0.0.53` binding. The daemon continues running (the NSS module still works), but the DNS server silently fails to start.

The fix is to bind disco's DNS server on `127.0.0.1:53` instead of `0.0.0.0:53`. The kernel treats `127.0.0.1` and `127.0.0.53` as distinct local addresses and allows both to hold port 53 simultaneously.

## Configure

In `/etc/disco/config.yaml`:

```yaml
dns:
  enabled: true
  port: 53
  domain: disco
  bind_addresses:
    - "127.0.0.1"    # use 127.0.0.1, not 0.0.0.0 — see port conflict note above
  ttl_healthy: 30
  ttl_stale: 10
```

If you are not running systemd-resolved, `0.0.0.0` works and binds on all interfaces.

## Grant port permission

Port 53 is privileged. The Debian package unit already has `AmbientCapabilities=CAP_NET_BIND_SERVICE`. For source installs:

```bash
sudo setcap 'cap_net_bind_service=+ep' /usr/local/bin/disco-daemon
```

Alternatively, set `dns.port` to a value above 1023 and point resolvers at it explicitly.

## Restart the daemon

```bash
sudo systemctl restart disco-daemon
```

## Verify

Query a discovered host directly against disco's DNS server:

```bash
dig @127.0.0.1 node1.disco
```

The `ANSWER SECTION` should contain an `A` record for `node1`.

## Integrate with systemd-resolved

With disco binding on `127.0.0.1:53`, configure resolved to forward `.disco` queries there. Create `/etc/systemd/resolved.conf.d/disco.conf`:

```ini
[Resolve]
DNS=127.0.0.1
Domains=~disco
```

```bash
sudo systemctl restart systemd-resolved
```

The `~disco` prefix marks this as a routing-only domain: resolved sends queries for names ending in `.disco` to `127.0.0.1:53` (disco), and everything else continues through its normal resolvers. Short names like `node1` still need the NSS module or an explicit `search disco` line to resolve without the `.disco` suffix.

Verify resolved is forwarding correctly:

```bash
resolvectl status
# Look for: DNS Servers: 127.0.0.1
#            DNS Domain: ~disco

dig node1.disco    # resolves via resolved -> disco
```

## Without systemd-resolved

Point `/etc/resolv.conf` directly at disco and set the search domain:

```
nameserver 127.0.0.1
search disco
```

With this, `ping node1` resolves as `node1.disco` through disco's DNS server.
