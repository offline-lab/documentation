# ADR-0014 — File ownership inside the DDI root: root:root

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

The DDI root partition is mounted read-only and dm-verity-protected. In
portable mode the service runs as a dedicated `app<uid>` user. The question
is what uid/gid should own the files inside the read-only root partition.

## Decision

All files inside the root partition are owned **`root:root`** (uid 0). The
service user (`app<uid>`) reads and executes via world permissions. The
partition is read-only, so write access is impossible regardless of
ownership.

## Consequences

- Image authors cannot rely on file ownership for access control; permissions
  must be expressed via standard read/execute bits.
- No per-app uid needs to be baked into the image at build time — the image is
  uid-agnostic and portable across allocations.
- Write semantics are enforced by the read-only mount, not by ownership.

## Alternatives considered

### Bake the app uid into image ownership

Rejected. Couples the image to a specific uid allocation, breaking
portability and reuse. Read-only mounting already removes any write benefit
from non-root ownership.

## References

- Related: ADR-0012 (per-app user allocation).
- Original discussion: internal (not published).
