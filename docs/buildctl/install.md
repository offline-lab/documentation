# Installing buildctl

## From source

### Prerequisites

- [Go](https://go.dev/dl/) 1.22 or later
- Git

### Build

```bash
git clone https://github.com/offline-lab/buildctl.git
cd buildctl
make build
```

The binary is at `build/bin/buildctl`. Copy it to your PATH:

```bash
cp build/bin/buildctl /usr/local/bin/
```

### Cross-compile

```bash
make cross-compile
# Binaries in build/bin/:
#   buildctl-linux-amd64
#   buildctl-linux-arm64
#   buildctl-darwin-amd64
#   buildctl-darwin-arm64
```

## From Homebrew (macOS)

```bash
brew tap offline-lab/tap
brew install buildctl
```

## From package manager (Linux)

### Debian/Ubuntu

```bash
# Download the latest .deb from the GitHub Releases page
sudo dpkg -i buildctl_<version>_linux_amd64.deb
```

### Fedora/RHEL

```bash
# Download the latest .rpm from the GitHub Releases page
sudo rpm -i buildctl-<version>-1.x86_64.rpm
```

## From GitHub Releases

Download the appropriate archive for your platform from
[GitHub Releases](https://github.com/offline-lab/buildctl/releases),
extract it, and add the binary to your PATH.

```bash
# Example: macOS ARM64
curl -L https://github.com/offline-lab/buildctl/releases/latest/download/buildctl_macOS-arm64.tar.gz | tar xz
sudo mv buildctl /usr/local/bin/
```

Verify the download against the published checksums before running.

## Verify installation

```bash
buildctl version
# buildctl <version> (commit: <hash>, built: <date>)
```

## Docker setup

For cross-architecture builds via the Docker backend, run once:

```bash
buildctl init
```

This ensures the `buildctl-builder` buildx builder exists and registers QEMU binfmt handlers for cross-architecture emulation (arm64, armv7, etc.). On macOS, Docker Desktop provides binfmt natively; on Linux, `init` installs the handlers via a privileged container. See [Cross-compile for a different architecture](how-to/cross-compile.md).

## Backend dependencies

buildctl auto-detects the build backend from the project directory. See [Build backends](reference/backends.md) for the contract and per-backend details.

| Backend | Detected from | Install |
|---|---|---|
| Docker | `Dockerfile` | [Docker Desktop](https://docker.com) or `docker-ce` |
| mkosi | `mkosi.conf` | `pipx install mkosi` (Linux only) |
| shell | `build.sh` | `bash` (pre-installed on most systems) |
| make | `Makefile` | `make` (pre-installed on most systems) |

## Next steps

- [Build your first package](tutorials/first-package.md): end-to-end walkthrough.
- [Command reference](reference/commands.md): every command and flag.
