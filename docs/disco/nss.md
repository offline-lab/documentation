# NSS Module

`libnss_disco.so.2` integrates disco with glibc's Name Service Switch. Once installed and registered, standard name resolution functions (`getaddrinfo`, `gethostbyname`, etc.) query the disco daemon automatically. Tools like `ping`, `ssh`, and `curl` resolve disco hostnames without any changes to `/etc/hosts` or DNS.

The module connects to the daemon's Unix socket at `/run/disco.sock` (or the path set in `daemon.socket_path`). If the daemon is not running, glibc falls through to the next source in `nsswitch.conf`.

## Install the library

Find the correct library directory for your system:

```bash
ldconfig -p | grep libnss | head -1
# Example output: /lib/x86_64-linux-gnu/libc.so.6
```

The NSS library directory is typically:

- Debian/Ubuntu x86_64: `/lib/x86_64-linux-gnu/`
- Debian/Ubuntu arm64: `/lib/aarch64-linux-gnu/`
- Alpine and minimal distros: `/lib/`

Install the module and update the linker cache:

```bash
sudo install -m 644 build/lib/libnss_disco.so.2 /lib/x86_64-linux-gnu/
sudo ln -sf /lib/x86_64-linux-gnu/libnss_disco.so.2 /lib/x86_64-linux-gnu/libnss_disco.so
sudo ldconfig
```

Confirm it loaded:

```bash
ldconfig -p | grep libnss_disco
```

Expected output:

```
libnss_disco.so.2 (libc6,x86-64) => /lib/x86_64-linux-gnu/libnss_disco.so.2
libnss_disco.so (libc6,x86-64) => /lib/x86_64-linux-gnu/libnss_disco.so
```

## Configure nsswitch.conf

Edit `/etc/nsswitch.conf` and insert `disco` in the `hosts` line immediately after `files`:

```
hosts: files disco dns
```

**Do not replace the entire line.** Only insert `disco` after `files` and leave everything else in place.

### With systemd-resolved

On systems running systemd-resolved, the hosts line typically looks like:

```
hosts: files resolve [!UNAVAIL=return] dns myhostname
```

The `[!UNAVAIL=return]` action means: if `resolve` returns anything other than `UNAVAIL` — including `NOTFOUND` — stop the chain immediately. Any entry placed after it is never consulted. `disco` must therefore appear **before** `resolve [!UNAVAIL=return]`:

```
hosts: files disco resolve [!UNAVAIL=return] dns myhostname
```

`myhostname` at the end is a last-resort fallback: it is only reached when resolved itself is down (`UNAVAIL`), at which point it ensures the machine can still resolve its own hostname.

The correct way to insert it is to add `disco` immediately after `files`, leaving the rest of the line unchanged. Do not replace the whole line; doing so removes `myhostname` and `resolve`, which breaks hostname and systemd-resolved lookups.

```bash
# Safe insert — leaves resolve, myhostname, and everything else in place
sudo sed -i '/^hosts:/ s/files/files disco/' /etc/nsswitch.conf
```

## Verify

Start the daemon, then test resolution:

```bash
getent hosts node1
```

`getent hosts node1` should return the host's IP without a DNS query. To confirm the module is called:

```bash
NSS_DEBUG=yes getent hosts node1
```

## Uninstall

Remove the library and restore `nsswitch.conf`:

```bash
sudo rm /lib/x86_64-linux-gnu/libnss_disco.so.2
sudo rm /lib/x86_64-linux-gnu/libnss_disco.so
sudo ldconfig
```

Edit `/etc/nsswitch.conf` and remove `disco` from the `hosts` line.

## Troubleshooting

**`getent hosts` returns nothing but `disco hosts` shows the host**

The NSS module is not registered, or `disco` appears after `resolve [!UNAVAIL=return]` in `nsswitch.conf`. Check both:

```bash
ldconfig -p | grep libnss_disco
grep ^hosts /etc/nsswitch.conf
```

**`getent hosts` hangs**

The daemon socket exists but the daemon is not responding. Remove the stale socket and restart:

```bash
sudo systemctl status disco-daemon
sudo rm /run/disco.sock
sudo systemctl restart disco-daemon
```

**`NSS_DEBUG` output shows `disco: failed to connect`**

The daemon is not running or the socket path does not match the hardcoded path in the library (`/run/disco.sock`). Check that `daemon.socket_path` in the config matches:

```bash
stat /run/disco.sock
grep socket_path /etc/disco/config.yaml
```
