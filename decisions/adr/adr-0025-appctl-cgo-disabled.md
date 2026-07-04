# ADR-0025 — appctl: pure Go, CGO disabled

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

appctl is built for the device and is cross-compiled by Buildroot for the
target architecture. Cross-compiling CGo code requires a full C toolchain for
each target and complicates the build. The natural way to keep the build
simple and portable is to keep appctl pure Go.

## Decision

appctl is built with **`CGO_ENABLED=0`** — pure Go, no cgo. This is a hard
requirement.

It is resolved straightforwardly by the state-storage decision (ADR-0026):
file-per-record state storage avoids any SQLite dependency, which would have
been the main reason to need cgo.

## Consequences

- appctl cross-compiles cleanly via Buildroot with no C toolchain
  dependencies.
- No database library that requires cgo can be pulled into appctl.
- State storage must be pure-stdlib (ADR-0026).

## Alternatives considered

None considered. This is a build-pipeline constraint that follows from the
cross-compilation target and is satisfied by the file-per-record storage
decision.

## References

- Related: ADR-0026 (file-per-record state storage).
- Original discussion: internal (not published).
