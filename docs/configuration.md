# Configuration

There are three ways to configure the OS:

1. **Build time**: options in `.config` baked into the image
2. **Boot partition provisioning**: files placed in `/boot/firmware/config/` are consumed by the initramfs on next boot and land in `/data/config/`
3. **Runtime**: editing files directly on `/data` (requires SSH or console access)

## Build-time configuration

Copy `config.example` to `.config` in the repo root. Options in `.config` override the Buildroot defconfig at build time.

### Development users and SSH keys

The `offlinelab-testing` package (dev/test only, never in production) creates an `admin` user (uid 1000) and a `testuser` (uid 1001). Set their SSH public keys:

```ini
BR2_PACKAGE_OFFLINELAB_TESTING=y
BR2_PACKAGE_OFFLINELAB_TESTING_ADMIN_PUBKEY="ssh-ed25519 AAAA... you@host"
BR2_PACKAGE_OFFLINELAB_TESTING_TESTUSER_PUBKEY="ssh-ed25519 AAAA... builder@host"
```

See the [Development guide](development.md) for SSH key setup details.

### Baking WiFi credentials into the boot partition example config

```ini
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_CREATE=y
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_SSID="your-network"
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_PASSWORD_HASH="<hash from wpa_passphrase>"
BR2_PACKAGE_OFFLINELAB_BOOTCONF_WIFI_COUNTRY="NL"
```

Writes WiFi credentials into `bootconf.yaml.example` on the boot partition at build time. This is a dev/lab convenience: copy `bootconf.yaml.example` to `bootconf.yaml` before first boot. Use the hash from `wpa_passphrase <ssid> <password>`, not the plaintext password.

**Security note:** Build-time credentials are baked into every image flashed from that build. For per-card configuration, use `bootconf.yaml` on the boot partition instead.

## Boot-partition provisioning

Place files under `/boot/firmware/config/` on the FAT32 boot partition. On the next boot, the initramfs copies the `config/` tree into `/data/config/` and removes it from the boot partition. See [Boot partition configuration](bootfs-config.md) for the full layout and [`bootconf.yaml` reference](bootconf.md).

## Runtime configuration

After first boot, live config lives under `/data`. Changes here are persistent across reboots.

### WiFi

```bash
# Edit credentials
sudo nano /data/config/wifi/wpa_supplicant.conf

# Apply without rebooting
wpa_cli -i wlan0 reconfigure
```

### SSH authorized keys

```bash
# Edit or replace authorized keys
sudo nano /data/home/admin/.ssh/authorized_keys
```

Changes take effect immediately; dropbear re-reads the file on each connection.

## /data layout

```
/data/
├── config/
│   ├── wifi/
│   │   └── wpa_supplicant.conf     # live WiFi credentials
│   ├── ssh/
│   │   └── dropbear/               # dropbear host keys (persist across reboots)
│   ├── firewall/
│   │   └── rules.d/                # per-app nftables rule fragments
│   ├── system/
│   │   └── machine-id              # stable machine-id across A/B slot switches
│   ├── keys/                       # appctl repo verification certs
│   ├── sysusers.d/                 # appctl user allocation snippets
│   ├── disco/
│   │   └── config.yaml             # disco daemon configuration
│   └── resources.json              # resource baseline (written at boot)
├── home/
│   └── admin/
│       ├── .bashrc
│       └── .ssh/
│           └── authorized_keys     # live SSH public keys
├── apps/                           # systemd portable service images (.raw)
├── offline-lab/
│   ├── images/                     # staged app package images
│   ├── state/                      # appctl state (repos, packages, bases, images — one JSON file per record)
│   └── apps/                       # per-app persistent storage (config, data)
└── extensions/
    ├── sysext/                     # sysext images (bind-mounted to /var/lib/extensions)
    └── confext/                    # confext images (bind-mounted to /etc/extensions)
```

The overlay partition (separate from `/data`) holds the overlayfs upper/work directories and is managed automatically. User data should not be placed there.
