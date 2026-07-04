# Installation

## Debian packages

Disco ships four packages. `disco-common` installs the NSS module and is a dependency of both `disco-daemon` and `disco-cli`.

| Package | Contents |
|---------|---------|
| `disco` | Metapackage; pulls in all components |
| `disco-daemon` | Main daemon binary |
| `disco-cli` | `disco` CLI binary |
| `disco-common` | NSS module, default config, shared files |
| `disco-gps-broadcaster` | GPS time broadcaster binary |

Install the full suite:

```bash
sudo apt install ./disco_*.deb
```

Or install components individually:

```bash
sudo apt install ./disco-daemon_*.deb ./disco-cli_*.deb ./disco-common_*.deb
```

After installation, enable and start the daemon:

```bash
sudo systemctl enable --now disco-daemon
```

## From source

Requires Go 1.24+ and GCC.

```bash
git clone https://github.com/offline-lab/disco
cd disco
make
sudo make install
```

`make install` installs binaries to `/usr/local/bin/`, the NSS module to `/lib/x86_64-linux-gnu/`, and man pages to `/usr/local/share/man/man1/`.

To build only specific components:

```bash
make disco          # CLI binary only
make disco-daemon   # Daemon binary only
make libnss         # NSS shared library only (Linux, requires GCC)
```

### Cross-compile

The Go binaries cross-compile without CGO. The NSS module is C and must be compiled natively or with a cross-compiler targeting the same architecture.

Cross-compile the binaries for ARM64:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
  -ldflags="-s -w" \
  -o build/bin/disco-daemon cmd/daemon/main.go

CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
  -ldflags="-s -w" \
  -o build/bin/disco cmd/disco/main.go
```

Build the NSS module for ARM64 using a cross-compiler:

```bash
aarch64-linux-gnu-gcc -fPIC -shared \
  -o build/lib/libnss_disco.so.2 \
  -Wl,-soname,libnss_disco.so.2 \
  libnss/nss_disco.c
```

## NSS module

The NSS module requires manual installation on the target system. See [NSS Module](nss.md) for the full procedure, including `nsswitch.conf` configuration.

## systemd service

The daemon ships a systemd unit. If you installed from source using `make install`, the unit file is not installed automatically. Create `/etc/systemd/system/disco-daemon.service`:

```ini
[Unit]
Description=Disco name service daemon
After=network.target

[Service]
Type=notify
ExecStart=/usr/local/bin/disco-daemon -config /etc/disco/config.yaml
Restart=on-failure
RestartSec=5
RuntimeDirectory=disco
RuntimeDirectoryMode=0755
User=disco
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

`Type=notify` lets systemd track when the daemon is ready. The daemon sends `READY=1` via `sd_notify` once the socket and any enabled servers (DNS, time sync) are accepting connections.

`RuntimeDirectory=disco` creates `/run/disco/` before the process starts. If you change `daemon.socket_path` in config, make sure the directory exists and the `disco` user can write to it.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now disco-daemon
```

## Embedded systems (Buildroot)

Create `package/disco/disco.mk`:

```makefile
DISCO_VERSION = $(call qstrip,$(BR2_PACKAGE_DISCO_VERSION))
DISCO_SITE = $(call github,offline-lab,disco,$(DISCO_VERSION))
DISCO_LICENSE = MIT
DISCO_DEPENDENCIES = host-go host-gcc

define DISCO_BUILD_CMDS
    cd $(@D) && \
    CGO_ENABLED=0 GOOS=linux GOARCH=$(BR2_ARCH) \
    $(HOST_GO_ENV) go build -o build/bin/disco-daemon cmd/daemon/main.go && \
    CGO_ENABLED=0 GOOS=linux GOARCH=$(BR2_ARCH) \
    $(HOST_GO_ENV) go build -o build/bin/disco cmd/disco/main.go && \
    $(TARGET_CC) -fPIC -shared -o build/lib/libnss_disco.so.2 \
        -Wl,-soname,libnss_disco.so.2 libnss/nss_disco.c
endef

define DISCO_INSTALL_TARGET_CMDS
    $(INSTALL) -D -m 755 $(@D)/build/bin/disco-daemon $(TARGET_DIR)/usr/bin/disco-daemon
    $(INSTALL) -D -m 755 $(@D)/build/bin/disco $(TARGET_DIR)/usr/bin/disco
    $(INSTALL) -D -m 644 $(@D)/build/lib/libnss_disco.so.2 $(TARGET_DIR)/lib/libnss_disco.so.2
    ln -sf libnss_disco.so.2 $(TARGET_DIR)/lib/libnss_disco.so
endef

$(eval $(generic-package))
```

## Uninstall

```bash
sudo systemctl stop disco-daemon
sudo systemctl disable disco-daemon
sudo rm /etc/systemd/system/disco-daemon.service
sudo systemctl daemon-reload

sudo rm /usr/local/bin/disco /usr/local/bin/disco-daemon /usr/local/bin/disco-gps-broadcaster
sudo rm /lib/x86_64-linux-gnu/libnss_disco.so.2 /lib/x86_64-linux-gnu/libnss_disco.so
sudo ldconfig

# Restore nsswitch.conf: remove "disco" from the hosts line
sudo sed -i 's/ disco//' /etc/nsswitch.conf
```
