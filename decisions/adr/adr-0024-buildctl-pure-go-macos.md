# ADR-0024 — buildctl: pure Go, macOS required

| | |
|---|---|
| **Status** | Superseded by ADR-0031 (2026-07-05) — image assembly is delegated to systemd-ecosystem tooling (Linux, in a container/VM on macOS); the pure-Go/macOS-native pipeline is abandoned |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

buildctl produces signed DDIs. The core pipeline must run on developer
workstations, including macOS — not only Linux. The security-critical steps
(squashfs creation, dm-verity hash-tree computation, GPT/DDI assembly, PKCS7
signing) have well-known Linux CLI tools (`mksquashfs`, `veritysetup`,
`openssl`), but shelling out to them ties the pipeline to Linux and to
external binary availability.

## Decision

The core buildctl pipeline is **pure Go**. No shelling out to `mksquashfs`,
`veritysetup`, or `openssl`.

Libraries:

- `github.com/diskfs/go-diskfs` — GPT/DDI creation.
- `go.mozilla.org/pkcs7` — PKCS7 signing (build-time only).
- Pure-Go squashfs writer.
- Pure-Go dm-verity hash-tree computation.

**macOS must work.** Any Linux-only tool is forbidden from the core pipeline.

## Consequences

- buildctl runs identically on macOS and Linux for the core pipeline.
- The build depends on the correctness and completeness of the pure-Go
  squashfs/verity implementations rather than system tools.
- Unavoidable shell-outs remain for backend build commands (`docker`,
  `mkosi`, `make`, `bash`) and the publish step (`rsync`, `ssh`) — these are
  outside the core pipeline.

## Alternatives considered

### Shell out to mksquashfs / veritysetup / openssl

Rejected. Breaks macOS support and introduces external-binary dependencies
and version drift in the security-critical path. Pure-Go keeps the pipeline
reproducible and cross-platform.

## References

- Original discussion: internal (not published).
