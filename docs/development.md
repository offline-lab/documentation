# Development guide

A guide for contributors working on the OS image, framework, and packages.

## Quick start

For build environment setup (Docker or Buildbox), see [Build the OS image](build-image.md).

This page covers the development workflow after your build environment is working: making changes and common pitfalls. See the [Style guide](styleguide.md) for coding conventions.

## Making changes

### Rebuilding after edits

Buildroot caches package output. After editing files under `br2-external/`, force a clean rebuild:

```bash
make offlinelab-<package>-dirclean
```

Then rebuild. Without this, your changes won't appear in the image. This is the most common source of "my change isn't in the image" confusion.

### Framework development

The framework lives in its own repository at [github.com/offline-lab/framework](https://github.com/offline-lab/framework). Edit it there, then update the pinned commit in `BR2_PACKAGE_OFFLINELAB_FRAMEWORK_VERSION` (in the package Config.in or your `.config`) to pick up the changes.

After editing framework source, rebuild:

```bash
make offlinelab-framework-dirclean && make offlinelab-framework
```

See the [framework API reference](https://offline-lab.com/docs/framework/) for the full library and boxctl CLI reference.

## Critical gotchas

### Config provisioning is idempotent

Boot-time configuration is applied by `bootconf` reading `/data/config/bootconf.yaml` at every boot. If the target file already exists in `/data`, `bootconf` leaves it unchanged.

To re-provision a setting: delete the live file from `/data` and reboot.

To re-provision a flashed card: delete the file from `/data` (requires booting the device first), or reflash.

### USB OTG: keyboard or gadget, not both

The Zero 2W has one USB port in OTG mode. It can act as a USB host (keyboard, USB drives) or as a USB gadget (serial + ethernet), but not both simultaneously.

The `usb-gadget.sh` script detects whether a USB host device is already connected and skips gadget setup if so. This means: if you plug a keyboard in before boot, the USB gadget interfaces (ttyGS0, usb0) will not come up.

### Overlayfs upper is on the overlay partition

The overlayfs upper directory is `/overlay/a/upper` or `/overlay/b/upper` on the dedicated overlay partition (`p3`), not on `/data`. Changes to rootfs-managed paths (anything not under `/data`) land on the overlay partition.

If you see unexpected state persisting across rootfs updates, check the overlay partition, not `/data`.

### machine-id persists via /data

On every boot the initramfs clears the overlay upper directory and restores `/etc/machine-id` from `/data/config/system/machine-id`. On first boot, `persist-machine-id.service` writes the machine-id to `/data` so it survives subsequent slot switches and overlay resets. The framework function `machine_id::persist` (in `system.sh`) handles the persistence logic.

## Verification

### Static checks

`bin/verify.sh` runs 200+ checks against the build artifacts without requiring hardware:

```bash
bin/verify.sh artifacts/
```

Checks include:

- Partition layout and types
- Boot partition contents (U-Boot, boot.scr, kernel sqfs, initramfs)
- Initramfs structure (static busybox, init script, overlayfs logic)
- Rootfs contents (all systemd units enabled, scripts installed, users present)
- Kernel config (built-in options: overlayfs, DWC2, zram, MMC)
- Module dependencies (modules.dep populated, XZ decompression available)
- A/B boot logic assertions

Add new checks to `bin/verify.sh` when adding new packages or changing the image structure.

### End-to-end tests (QEMU)

`bin/test-qemu` boots the QEMU arm64 image and runs the full pytest-testinfra test suite against it over SSH. This catches runtime issues that static checks cannot: service failures, user creation, firewall rules, filesystem mounts, and package-level integration.

#### Prerequisites

```bash
brew install qemu          # QEMU for macOS
cd tests && uv sync        # install Python test dependencies
```

#### SSH key setup

The test runner connects to the image as `testuser` using `.ssh/builder`. You must generate a dedicated key pair and bake the public half into the image at build time:

```bash
# Generate a dedicated ed25519 key pair (do this once)
mkdir -p .ssh
ssh-keygen -t ed25519 -f .ssh/builder -N "" -C "builder"
```

Then set the public key in `.config` so it gets installed in `testuser`'s `authorized_keys` at build time:

```
BR2_PACKAGE_OFFLINELAB_TESTING_TESTUSER_PUBKEY="ssh-ed25519 AAAA... builder"
```

Also set the `admin` user's authorized key (for interactive SSH access during development):

```
BR2_PACKAGE_OFFLINELAB_TESTING_ADMIN_PUBKEY="ssh-ed25519 AAAA... you@host"
```

**Key rules:**
- Always use **ed25519** keys. The image's Dropbear may be compiled without ECDSA support.
- `.ssh/builder` is the test runner key (used by `bin/test-qemu` and `bin/buildbox.sh`). It does **not** have to be your personal key.
- Your personal key goes in `BR2_PACKAGE_OFFLINELAB_TESTING_ADMIN_PUBKEY` so you can SSH as `admin` interactively.
- Both keys are gitignored. **Never commit keys or their values to the defconfig** — production builds must not contain developer keys.

#### Running the tests

```bash
bin/test-qemu                  # run full suite against existing artifacts
bin/test-qemu --build          # build and fetch artifacts first, then test
bin/test-qemu -k firewall      # run only tests matching 'firewall'
bin/test-qemu -x               # stop on first failure
```

Reports are written to `tests/reports/report.html` and `tests/reports/junit.xml`.

#### Against a real device or manually-started QEMU

```bash
cd tests
bin/run-tests --host ssh://testuser@<device-ip>
bin/run-tests --host ssh://testuser@localhost:2222   # bin/run-qemu uses port 2222
```

#### Test structure

Tests live in `tests/tests/` and are grouped by package:

| File | Covers |
|---|---|
| `test_boot.py` | Systemd target, failed units, mounts, kernel |
| `test_base.py` | Users, groups, services, sudoers, framework |
| `test_system.py` | Rootfs overlay, skeleton files, system config |
| `test_firewall.py` | nftables rules, service state |
| `test_bootconf.py` | bootconf binary, service, sysusers, provisioned users |
| `test_resources.py` | offlinelab-resources oneshot service |
| `test_portable.py` | portablectl, sysext, AppArmor, /var/lib/portables symlink |
| `test_disco.py` | disco-daemon binary, service, NSS, capabilities |
| `test_ssh.py` | Dropbear service, key-only auth, host key persistence |
| `test_wifi.py` | wpa_supplicant, wlan0 network config, WiFi fix |
| `test_rauc.py` | RAUC slots, rauc-mark-good, fw_env config, USB update |
| `test_usb_gadget.py` | USB gadget service, ttyGS0, usb0 network |
| `test_zram.py` | zram swap device, LZ4 compression, module loading |
| `test_testing.py` | admin/testuser accounts (offlinelab-testing package only) |

The `offlinelab-testing` package (enabled via `BR2_PACKAGE_OFFLINELAB_TESTING=y`) is required for the test suite to run. It creates `testuser` (uid 1001) with NOPASSWD sudo and installs the test SSH key. It must never be included in production builds.

## Adding a package

1. Create `br2-external/package/offlinelab-<name>/`:
   - `Config.in`: Buildroot Kconfig options
   - `offlinelab-<name>.mk`: install rules
   - `src/`: source files (scripts, systemd units, config)

2. Register in `br2-external/Config.in`:
   ```
   source "package/offlinelab-<name>/Config.in"
   ```

3. Enable in the defconfig:
   ```
   BR2_PACKAGE_OFFLINELAB_<NAME>=y
   ```

4. Add verification checks to `bin/verify.sh`.

Follow the pattern of an existing package. Keep each package focused on one concern. Use the provisioning pattern for any config that users might need to change (boot partition to `/data`).
