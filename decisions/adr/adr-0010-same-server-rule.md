# ADR-0010 — Same-origin rule for artifact URLs

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0033 (2026-07-05): refined to relative-URLs-only so indexes are location-independent (mirrors, sticks, caches) |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

A repository index is itself signed (ADR-0009), but individual package
download URLs (`raw_url`, `metadata_url`) inside the index could, in
principle, point anywhere. An attacker who can influence the index — even
without forging package signatures — could try to redirect downloads to a
host they control, enabling traffic analysis, targeted denial of service, or
attempts to exploit client-side download handling.

## Decision

appctl **rejects any `raw_url` or `metadata_url` that resolves to a different
origin** than the `base_url` set at `appctl repo add` time. An attacker cannot
use a legitimate index to redirect downloads to a different host.

## Consequences

- All artifact downloads for a repository are confined to the origin the
  operator explicitly trusted at `repo add` time.
- Index entries with cross-origin URLs fail at install, not silently.

## Alternatives considered

None considered. This is a defensive baseline; allowing arbitrary redirect
would undermine the per-repo trust model.

## References

- Related: ADR-0008 (repository index), ADR-0009 (index signing).
- Original discussion: internal (not published).
