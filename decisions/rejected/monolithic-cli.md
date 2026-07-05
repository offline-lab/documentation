# Rejected: Monolithic offline-lab CLI

**Status:** Rejected — split into three separate tools.
**REVERSED 2026-07-05** for the Go tools by
[ADR-0040](../adr/adr-0040-one-binary-legs-as-namespaces.md): all three
technical premises below dissolved (the CGO conflict died with the pure-Go
pipeline, ADR-0031; cross-compilation is trivial at `CGO_ENABLED=0`;
Docker/portablectl are per-verb runtime deps, not binary deps). The Go
tooling is now one binary with one namespace per leg. `boxctl` remains
separate — that part of this rejection stands.
**Replaced by:** `boxctl` (Bash), `appctl` (Go), `buildctl` (Go) *(the Go
names are working titles for namespaces since ADR-0040)*

---

## What was proposed

A single, monolithic "docker-like CLI" combining all operations: build, publish,
and app management. From the initial brainstorm:

> "Over time I want to build several tools, perhaps combined into a single docker like cli"

Early command-line tooling notes described `buildctl` and `appctl` as separate, but the
vision was a single docker-like interface.

---

## Why it was rejected

The tools have fundamentally different deployment contexts:

1. `buildctl` — runs on developer workstations and CI servers. Requires macOS support.
   Pure Go. Needs Docker for builds. Never installed on the device.
2. `appctl` — runs on-device only. Cross-compiled by Buildroot. `CGO_ENABLED=0` required.
   No macOS needed. Never installed on dev workstations.
3. `boxctl` — OS management on-device. Bash. Uses the framework library.

A monolithic binary would need to be both `CGO_ENABLED=0` (for appctl) and
`CGO_ENABLED=1` (for buildctl), run on macOS (for buildctl) and arm64 only (for appctl),
and require both Docker and portablectl. These constraints are fundamentally incompatible.

The early decision was explicit: "CLI naming: `appctl`/`buildctl` separate binaries (not
monolith `offline-lab`)."

---

## What replaced it

Three tools, each with a clear scope:

| Tool | Language | Runs on | CGO | Purpose |
|---|---|---|---|---|
| `boxctl` | Bash | Device | N/A | OS management (WiFi, firewall, updates, diagnostics) |
| `appctl` | Go | Device | 0 | App package lifecycle (install, update, remove, rehydrate) |
| `buildctl` | Go | Dev workstation/CI | 1 | Package building and repo management |
