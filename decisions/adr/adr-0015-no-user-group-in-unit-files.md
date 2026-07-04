# ADR-0015 — No `User=`/`Group=` in DDI unit files

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

In portable mode, each app runs as an appctl-allocated `app<uid>` (ADR-0012).
That uid is only known at install time — it cannot be known when the package
is built, because it depends on what else is installed on the target device.
If a unit file inside the DDI contained a `User=`/`Group=` directive, it would
either be wrong (a static guess) or be overridden by appctl's install-time
drop-in.

## Decision

Unit files inside the DDI must **not** contain `User=` or `Group=` directives.
appctl injects these via a drop-in at install time based on the allocated uid
(portable mode). buildctl errors if either directive is present in a unit
file.

## Consequences

- There is a single source of truth for the runtime user: appctl's
  install-time drop-in.
- Authors cannot accidentally ship a stale or wrong `User=`.
- buildctl enforces the constraint at build time.

## Alternatives considered

None considered. Shipping a `User=` that appctl overrides would be misleading
and error-prone; buildctl enforcement makes the constraint structural.

## References

- Related: ADR-0012 (per-app user allocation).
- Original discussion: internal (not published).
