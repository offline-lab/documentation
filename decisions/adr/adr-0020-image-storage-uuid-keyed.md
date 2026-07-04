# ADR-0020 — Image storage: UUID-keyed directories

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

appctl stages installed images on disk and must track, per app, which image
versions are present and which is active/previous/removed. The storage layout
needs stable, collision-free keys and a retention policy that bounds disk
usage on small devices.

## Decision

Each staged image lives at **`/var/lib/appctl/images/<uuid>/`**.

A per-image state record at `state/images/<uuid>.json` maps the UUID to its
app, version, and status (`active` | `previous` | `removed`).

**Default retention: 3 images per app.**

## Consequences

- UUID keys avoid name/version collisions and support multiple versions
  coexisting per app.
- Status tracking enables rollback to a `previous` image.
- Retention is bounded; older images beyond the limit are pruned.

## Alternatives considered

### Name+version-keyed paths

Rejected. Names and versions can collide or be renamed; UUIDs give stable
storage keys independent of package identity. Status tracking still maps UUIDs
back to app/version.

## References

- On-device state schema.
- Related: ADR-0026 (file-per-record state storage).
- Original discussion: internal (not published).
