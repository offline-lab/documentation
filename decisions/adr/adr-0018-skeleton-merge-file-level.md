# ADR-0018 — Skeleton merge: file-level override (buildctl)

| | |
|---|---|
| **Status** | Deprecated (2026-07-05) — the buildctl implementation this specified was removed (ADR-0031); authoring conveniences will be re-decided in the new design if needed |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

A project may want to add or override files on top of whatever a build
backend produces (e.g. inject config, patch a vendored file). buildctl needs a
defined merge semantics so authors can predict exactly how their overlay
interacts with backend output, including how to remove files the backend
produced.

## Decision

An optional `rootfs/` directory in the project is **merged into the backend
output after the backend runs**.

- Skeleton files override backend output **file-for-file**.
- Directories are recursively merged.
- Deletion is handled by `.buildignore`, applied post-merge.

## Consequences

- Authors have a predictable override mechanism: same path wins, recursively.
- Deletion requires `.buildignore` rather than an empty override file.
- Merge runs once, after the backend, so backend output is the base layer.

## Alternatives considered

### Let skeleton override at directory granularity

Rejected. File-level granularity is more predictable and less destructive;
directory-level replacement would discard legitimate backend files the author
did not intend to remove.

## References

- Original discussion: internal (not published).
