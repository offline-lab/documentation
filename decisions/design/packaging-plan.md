# buildctl Packaging Plan

> **Note (2026-07-05):** buildctl was redesigned
> ([ADR-0031](../adr/adr-0031-buildctl-rebuilt-delegated-assembly.md)); the
> tool name and the goal of multi-platform distribution survive, but revisit
> this plan after the rebuild (the new buildctl requires Docker/a Linux
> container for image assembly on macOS, which changes the install story).

## Goal

Create documentation, CI pipelines, and packaging artifacts so buildctl can be
easily installed on multiple platforms.

## Installation targets

| Platform | Format | Tooling | Priority |
|---|---|---|---|
| macOS (arm64, amd64) | Homebrew tap | GoReleaser + homebrew tap repo | P0 |
| Linux (amd64, arm64) | Plain binaries (tar.gz) | GoReleaser + GitHub Releases | P0 |
| Debian/Ubuntu (amd64, arm64) | .deb | GoReleaser + nfpm | P1 |
| Fedora/RHEL (amd64, arm64) | .rpm | GoReleaser + nfpm | P1 |
| Alpine (amd64, arm64) | .apk | nfpm or manual | P2 |
| Arch Linux | AUR PKGBUILD | community or manual | P3 |

## Documentation

### `buildctl/docs/install.md`

Cover:
- Quick install per platform (one-liner per format)
- Build from source (go build, make build)
- Cross-compilation (make cross-compile)
- Verification (checksums, signature)
- Requirements: Go 1.22+, optional Docker for docker backend

## CI Pipeline (GitHub Actions)

### Release workflow: `.github/workflows/release.yml`

Triggers: push tag `v*`.

Steps:
1. Run tests (`go test -tags zstd ./...`)
2. Run linters (`golangci-lint run`)
3. GoReleaser builds for all targets:
   - `linux/amd64`, `linux/arm64`
   - `darwin/amd64`, `darwin/arm64`
4. GoReleaser creates:
   - Binary archives (tar.gz for Linux, zip for macOS)
   - `.deb` packages (via nfpm)
   - `.rpm` packages (via nfpm)
   - Homebrew formula (pushed to `offline-lab/homebrew-tap`)
   - Checksums file
   - SBOM (Syft)
5. Publish all artifacts to GitHub Release

### `.goreleaser.yaml` structure

```yaml
builds:
  - main: ./cmd/buildctl
    tags: [zstd]
    env: [CGO_ENABLED=0]
    goos: [linux, darwin]
    goarch: [amd64, arm64]

nfpms:
  - package_name: buildctl
    formats: [deb, rpm, apk]
    dependencies: [docker] # recommended, not required
    contents:
      - src: build/bin/buildctl
        dst: /usr/bin/buildctl

brews:
  - repository:
      owner: offline-lab
      name: homebrew-tap
    homepage: https://buildctl.offline-lab.com
    description: "Build signed DDI packages for Offline Lab"

archives:
  - format: tar.gz
    name_template: >-
      {{ .ProjectName }}_{{ .Version }}_
      {{- if eq .Os "darwin" }}macOS
      {{- else }}{{ .Os }}{{ end }}-{{ .Arch }}

checksum:
  name_template: 'checksums.txt'

sboms:
  - artifacts: archive
```

## Versioning

- Semantic versioning: `v1.0.0`, `v1.0.1`, etc.
- Pre-release: `v1.0.0-rc1`
- GoReleaser `ldflags` inject version/commit/buildtime (already in Makefile)

## Dependencies to document

| Dependency | Required? | Purpose |
|---|---|---|
| Go 1.22+ | Build only | Compiling buildctl |
| Docker | Optional | Docker backend for `buildctl build` |
| bash | Optional | Shell backend for `buildctl build` |
| make | Optional | Make backend for `buildctl build` |
| mkosi | Optional | mkosi backend for `buildctl build` |
| rsync + ssh | Optional | `buildctl publish` |

## What exists already

- `Makefile` with `build`, `cross-compile`, `test`, `lint`, `fmt`, `vet`, `clean` targets
- `.goreleaser.yaml` skeleton (needs updating for nfpm + brew)
- `.golangci.yml` for linting
- `.gitignore` with proper exclusions

## Tasks

1. Write `docs/install.md`
2. Update `.goreleaser.yaml` with nfpm (deb/rpm/apk) and Homebrew sections
3. Create `.github/workflows/release.yml`
4. Create `offline-lab/homebrew-tap` repo
5. Test GoReleaser locally with `goreleaser release --snapshot`
6. Add Arch Linux AUR PKGBUILD (community contribution or manual)
