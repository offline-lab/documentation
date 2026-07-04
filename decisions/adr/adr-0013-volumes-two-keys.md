# ADR-0013 — Volumes: exactly two keys (config and data)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

Apps need persistent storage for configuration and data. If package authors
could declare arbitrary filesystem paths as volume targets, a malicious
package could request a bind mount over security-sensitive locations —
signing certificates, another app's data directory, or the appctl state
database — and then read or tamper with them.

## Decision

Package authors may declare **only two volume targets**: `config` and `data`.
No freeform paths. appctl controls the system-side path entirely. A package
cannot reference arbitrary system locations.

## Consequences

- A package cannot mount over signing certs, another app's data, or appctl
  state — those paths are unreachable from the two allowed targets.
- The storage contract is minimal and predictable.
- Authors with more complex layout needs must fit within the two targets.

## Alternatives considered

### Freeform volume paths

Rejected. Enables a malicious package to bind-mount over sensitive system
locations. The two-fixed-key constraint is a deliberate security boundary.

## References

- Original discussion: internal (not published).
