# wifi

Writes a `wpa_supplicant.conf` file and manages the wifi service sentinel.

## What it does

When **enabled**:

1. Creates `<directory>/` with mode `0700`.
2. Writes `<directory>/wpa_supplicant.conf` from the configured SSID and PSK hash.
3. Creates a sentinel file at `<services.directory>/wifi`.

When **disabled**:

- Removes the sentinel file at `<services.directory>/wifi` if it exists.

Bootconf does not start `wpa_supplicant`. It writes the config and creates the sentinel. Your init scripts pick up the sentinel and start the daemon.

## Config

```yaml
wifi:
  enabled: true
  directory: /etc/bootconf/wifi
  ssid: "MyNetwork"
  password_hash: "614b0b8c3b6c5e8a7d9f2a1c4e3f5d7b9a8c6e4f2d1b3a5c7e9f0d2b4a6c8e0"
  country: NL
```

| Field | Type | Description |
|-------|------|-------------|
| `enabled` | bool | Enable or disable wifi |
| `directory` | string | Directory where `wpa_supplicant.conf` is written |
| `ssid` | string | Network SSID (max 32 bytes, printable characters only) |
| `password_hash` | string | WPA2 PSK hash: 64 hex characters |
| `country` | string | ISO 3166-1 alpha-2 country code (e.g. `NL`, `US`, `DE`) |

## PSK hash

The `password_hash` field expects the 64-character hex PSK computed by `wpa_passphrase`, **not** the plaintext password. The hash is safe to store in the config file on the boot partition.

Generate it:

```bash
wpa_passphrase MyNetwork
# type your password and press Enter
# copy the psk= line (64 hex characters)
```

## Generated config

The module writes a standard `wpa_supplicant.conf`:

```
country=NL
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="MyNetwork"
    psk=614b0b8c...
}
```

The wifi config **is always overwritten** on each boot. This makes it the authoritative source; changing the config file takes effect on the next reboot.

## Sentinel file

Works the same as the SSH sentinel. An empty file at `<services.directory>/wifi` signals your init system to start `wpa_supplicant`. When `enabled: false`, bootconf removes it.

## Dry-run

```
INFO [wifi] would create directory /etc/bootconf/wifi (dry-run)
INFO [wifi] would write wpa_supplicant.conf to /etc/bootconf/wifi/wpa_supplicant.conf (dry-run)
INFO [wifi] would create services directory /etc/bootconf/services and write sentinel /etc/bootconf/services/wifi (dry-run)
```
