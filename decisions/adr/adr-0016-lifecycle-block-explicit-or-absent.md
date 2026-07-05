# ADR-0016 — Lifecycle block: explicit or absent

| | |
|---|---|
| **Status** | Accepted — amended 2026-07-05 (design session §18): hook stages become **ordered lists** of units; stage set redefined (`pre_start`/`post_start`/`pre_stop`/`post_stop`/`pre_drop`; upgrade stages in T103); explicit-or-absent principle unchanged |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

A package may declare lifecycle hooks (e.g. pre/post install units). The
`lifecycle:` block in `package.yaml` needs an unambiguous representation: an
empty, null, or tilde-valued block could be interpreted differently by
different parsers and consumers, and clutters the generated metadata.

## Decision

The `lifecycle:` block is **present only when hooks are actually defined**.
If the app has no hooks, the block is omitted entirely. No null, tilde, or
empty forms are accepted — if the key exists, its values must be real unit
names.

- `package.yaml`: omit `lifecycle:` entirely when there are no hooks.
- Generated metadata JSON: the `lifecycle` key is omitted when no hooks are
  declared.
- buildctl validates this at build time.

## Consequences

- The presence of `lifecycle` is a reliable signal that real hooks exist.
- Consumers never have to handle null/empty edge cases.
- buildctl is the enforcement point.

## Alternatives considered

### Allow null/empty `lifecycle:` for explicit "no hooks"

Rejected. Introduces parser ambiguity and redundant representation for no
benefit; absence is already a clear signal.

## References

- Original discussion: internal (not published).
