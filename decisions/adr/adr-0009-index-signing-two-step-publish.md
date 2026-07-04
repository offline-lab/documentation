# ADR-0009 — Index signing: two-step publish on the repository host

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0031/0033 (2026-07-05): the ssh/rsync publish automation is superseded (buildctl does no transport); the two-step concept (files first, index second, index key stays on its host) survives |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

`buildctl publish` must place package files on the repository host and update
the (signed) index. The repository is a static file server — there is no
atomic write API — and multiple publishers may publish concurrently. The
index key (ADR-0006) lives on the repository host and must never be held by a
build machine.

## Decision

Publish is a **two-step operation**: the build machine pushes files, then the
repository host updates and signs the index.

`buildctl publish` does, in order:

1. `rsync` the package files to the repository host.
2. SSH to the repository host.
3. Run `buildctl index update` on the repository host.

The index key lives only on the repository host. The index update (patch +
sign) runs there via SSH, guarded by `flock` to serialize concurrent
publishers. The build machine never holds the index key.

## Consequences

- The index key never leaves the repository host.
- Concurrent publishers are serialized safely via `flock` on the host.
- Publish requires SSH access from the build machine to the repository host.

## Alternatives considered

### Build machine signs the index remotely

Rejected. Would require shipping the index key to every build machine,
violating ADR-0006 and widening the high-value key's exposure. Also offers no
answer for concurrent-publish serialization on a static file repo.

## References

- Related: ADR-0006 (two signing keys per repo), ADR-0008 (repository index).
- Original discussion: internal (not published).
