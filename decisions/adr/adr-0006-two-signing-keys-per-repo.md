# ADR-0006 — Two independent signing keys per repository

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

A repository serves two distinct kinds of signed artifact: individual
packages (their DDI signature partitions) and the repository index
(`index.json.p7s`). These are signed at different times, from different
machines, and have very different blast radii if compromised. Using a single
key for both means the build machine and the repository host both need the
same high-trust key — widening exposure and coupling two operationally
distinct flows.

## Decision

Each repository uses **two independent signing keys**:

- **Build key** (high trust): lives on the build machine only. Signs each
  package's DDI signature partition.
- **Index key** (lower trust): lives on the repository host. Signs
  `index.json.p7s` after each publish. Compromise blast radius is limited to
  catalog manipulation — it cannot forge package content, because package
  content is signed by the build key.

## Consequences

- Compromise of the index key cannot inject malicious package binaries; it
  can only manipulate the catalog, which is detectable against the
  build-key-signed package signatures.
- The high-trust build key never leaves the build machine.
- Operators must manage two keys per repository rather than one.

## Alternatives considered

### Single signing key for both packages and index

Rejected. Forces the high-trust key onto the repository host (so it can sign
the index), widening the exposure surface and coupling the build and publish
flows under one key.

## References

- Related: ADR-0007 (key rotation), ADR-0009 (index signing).
- Original discussion: internal (not published).
