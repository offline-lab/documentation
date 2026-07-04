# ADR-0008 — Repository index: per-arch, per-class, latest version only

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0033 (2026-07-05): "index" replaces "repository"; latest-only affirmed, local retention is user-configurable |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

A repository must be indexable by low-power devices (e.g. 512 MB RAM). A
single monolithic index covering every architecture, every artifact class,
and full version history would be large, slow to parse, and wasteful to
download for a device that needs only its own architecture. Version history,
meanwhile, is a client-side concern: rollback uses locally retained images,
not the remote index.

## Decision

Structure the repository as a **discovery manifest plus per-arch, per-class
indexes carrying only the latest version**.

- Root `repository.json` is a discovery manifest only (class URLs + keys); it
  has no package entries. Each artifact class (`bases`, `images`) has its own
  per-arch index.
- Per-class, per-arch: `<class>/<arch>/index.json` — one entry per artifact
  (latest version per name, plus per `sysext_level` for bases).
- Devices download only their architecture and only the classes they need,
  bounding memory usage.
- Each per-arch index carries a `type` discriminator (`"bases"` or `"apps"`)
  and a `key_rotation` counter; an increment triggers re-verification on
  `repo refresh`.
- Index entries reference `raw_url` + `metadata_url` (the DDI and JSON files);
  `zip_url` is optional. Bases additionally carry `oci_url` + `oci_sha256`
  for the build-time Docker image.

Version history is intentionally not in the index — rollback uses locally
retained images.

## Consequences

- Indexes stay small; devices parse only what they need.
- Class separation cleanly supports bases and apps independently.
- Rollback is a local concern, requiring devices to retain previous images.

## Alternatives considered

### Single monolithic index with full version history

Rejected. Too large for 512 MB devices, wastes bandwidth, and conflates
remote catalog with local rollback state.

## References

- Repository spec.
- Original discussion: internal (not published).
