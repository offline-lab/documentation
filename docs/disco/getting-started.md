# Getting Started

By the end of this tutorial, two nodes will be running disco and resolving each other's hostnames without DNS.

## Prerequisites

- Two Linux hosts on the same broadcast domain (LAN, VLAN, or Wi-Fi network)
- Go 1.24+ and GCC on the build machine
- Root or sudo access on both nodes

## Build

On a machine with Go and GCC installed:

```bash
git clone https://github.com/offline-lab/disco
cd disco
make
```

This produces three binaries in `build/bin/` and the NSS module in `build/lib/`:

```
build/bin/disco
build/bin/disco-daemon
build/bin/disco-gps-broadcaster
build/lib/libnss_disco.so.2
```

## Install on each node

Copy the files to each node, then run the installer:

```bash
sudo ./install.sh
```

The installer:

- Creates a `disco` system user
- Installs binaries to `/usr/local/bin/`
- Installs `libnss_disco.so.2` to `/lib/` and runs `ldconfig`
- Adds `disco` to the `hosts` line in `/etc/nsswitch.conf`
- Writes a default config to `/etc/disco/config.yaml`
- Installs and enables the systemd unit

If you prefer to install manually, see [Installation](installation.md).

## Start the daemon

On each node:

```bash
sudo systemctl start disco-daemon
sudo systemctl status disco-daemon
```

The daemon begins broadcasting immediately. Each node announces its hostname, IP addresses, and any detected services every 30 seconds.

## Verify discovery

Wait up to 30 seconds, then check what each node has discovered:

```bash
disco hosts
```

```
ID        HOSTNAME   ADDRESSES       STATUS   SERVICES   LAST SEEN
a1b2c3d4  node1      192.168.1.10    healthy  ssh        12s ago
e5f6a7b8  node2      192.168.1.11    healthy  ssh        8s ago
```

If no hosts appear after a minute, check the troubleshooting section at the bottom of this page.

## Resolve hostnames

With the NSS module installed, standard tools resolve disco hostnames:

```bash
ping node2
ssh node2
getent hosts node2
```

`getent hosts node2` should return the IP without hitting DNS.

## Check a specific host

```bash
disco hosts show node2
```

```
Hostname:    node2
Machine ID:  e5f6a7b8...
Addresses:   192.168.1.11
Status:      healthy
Last Seen:   8s ago
Static:      false

Services:
  - ssh (22/tcp)
```

## What's next

- Run a web server on one node and watch `disco services` pick it up within a scan interval (default 60 seconds)
- See [Configuration](configuration.md) to tune broadcast intervals, enable security, or configure DNS
- See [How-to: Enable Security](how-to/security.md) if you need signed messages between nodes

## Troubleshooting

**No hosts appear after 60 seconds**

Check that UDP port 5354 is open on both nodes:

```bash
sudo iptables -L -n | grep 5354
sudo tcpdump -i any -n udp port 5354
```

If `tcpdump` shows no traffic, the daemon may not be running or your network blocks broadcast. Check the logs:

```bash
journalctl -u disco-daemon -n 50
```

**Name resolution fails but `disco hosts` works**

The NSS module is likely not installed or not registered. See [NSS Module](nss.md).
