# ADR-0019 — Backend `Build()` returns `(*BuildResult, error)`

| | |
|---|---|
| **Status** | Deprecated (2026-07-05) — the Backend interface this specified was removed with the buildctl implementation (ADR-0031) |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

buildctl wraps multiple build backends (Docker, shell, GNU Make, mkosi) behind
a common `Backend` interface. Backends need to return structured post-build
data — such as OCI labels and the image digest — to the core pipeline. The
earlier design passed this via a sidecar file written by the backend, which
was opaque and error-prone.

## Decision

The `Backend.Build()` method returns **`(*BuildResult, error)`**, not just
`error`. `BuildResult` carries structured post-build data (OCI labels, image
digest). Backends with nothing to report return `&BuildResult{}, nil`.

This replaces the earlier sidecar-file approach.

## Consequences

- Post-build data is typed and explicit in the interface contract.
- Backends that have no metadata return a clean zero-value result.
- The sidecar-file mechanism is removed; no implicit filesystem contract
  between backend and core.

## Alternatives considered

### Sidecar file written by the backend

Rejected. Opaque, required a fragile filesystem contract, and was easy to get
wrong. A typed return value makes the data exchange explicit.

## References

- Backend interface specification.
- Original discussion: internal (not published).
