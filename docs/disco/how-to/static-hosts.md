# Static Hosts

Static hosts are defined in the config file and never expire. They appear in host lists with status `static`, are served by the NSS module, and are included in DNS responses if the DNS server is enabled.

Use static hosts for devices that do not run disco (printers, routers, fixed-IP appliances) but that you want to resolve by name on the network.

## Configure

In `/etc/disco/config.yaml`:

```yaml
static_hosts:
  printer:
    addresses:
      - "192.168.1.50"
    services:
      - name: ipp
        port: 631
        protocol: tcp

  router:
    addresses:
      - "192.168.1.1"
    services: []

  fileserver:
    addresses:
      - "192.168.1.20"
      - "10.0.0.20"          # multiple addresses are supported
    services:
      - name: smb
        port: 445
        protocol: tcp
      - name: nfs
        port: 2049
        protocol: tcp
```

The map key (`printer`, `router`, `fileserver`) is the hostname. Restart the daemon to apply changes.

## Verify

```bash
disco hosts
```

Static hosts appear with `static` in the STATUS column.

```bash
disco hosts show printer
```

```
Hostname:    printer
Addresses:   192.168.1.50
Status:      static
Last Seen:   static
Static:      true

Services:
  - ipp (631/tcp)
```

Name resolution works the same as for discovered hosts:

```bash
getent hosts printer
ping router
```
