# ADR-0001 — DDI as the package format

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0034 (2026-07-05): UAPI.3 adopted verbatim as substrate |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None (replaces a prior 5-file format, not another ADR) |

## Context

App packages need a single, self-contained, verifiable artifact that any
systemd host can consume natively — without custom companion-file discovery,
custom verity setup, or runtime PKCS7 code in the client tool. The package
must carry its own integrity metadata so that authenticity can be checked at
attach time by the platform, not by bespoke tooling.

The earlier package format was an ad-hoc collection of five files: a squashfs
root image plus separate companion files for the verity hash tree, root hash,
signature, and metadata. This required custom logic at every stage (discovery,
verity setup, signature verification) and was not a recognized standard.

## Decision

Adopt the **Discoverable Disk Image (DDI, UAPI.3)** as the package format,
paired with a metadata JSON sidecar.

A package is two files, shipped together in a zip:

- `<name>_<version>_<arch>.raw` — the DDI: a GPT partition table containing
  root, verity, and verity-sig partitions.
- `<name>_<version>_<arch>.json` — appctl metadata (ports, volumes,
  resources, etc.).

On install the archive is extracted to `/var/lib/appctl/images/<uuid>/`.

Partition layout inside the DDI:

- **Partition 1 — Root** (arch-specific type UUID): squashfs or erofs filesystem.
- **Partition 2 — Verity** (arch-specific type UUID): dm-verity superblock + hash tree.
- **Partition 3 — Signature** (arch-specific type UUID): JSON `{rootHash, signature}`.

Per the Discoverable Partitions Specification (UAPI.2), partition UUIDs encode
the root hash: the root partition UUID is the first 128 bits of the root hash,
the verity partition UUID is the last 128 bits.

## Consequences

- The DDI is a UAPI standard that systemd handles natively: no custom
  companion-file discovery, no custom verity setup, no custom PKCS7
  verification at runtime.
- A single artifact is distributable, verifiable, and attachable by any
  compliant systemd host — not only Offline Lab OS.
- Tooling must produce well-formed GPT images with correct partition type
  UUIDs and DPS-compliant root-hash-encoded partition UUIDs.

## Alternatives considered

### 5-file format — squashfs + companion files

Rejected. Required bespoke discovery, verity setup, and PKCS7 verification
code in the client; not a recognized standard; more moving parts to get wrong.
The DDI moves all of that into systemd and the kernel.

## References

- UAPI.3 (Discoverable Disk Image) and UAPI.2 (Discoverable Partitions
  Specification) — partition type UUIDs and root-hash encoding.
- Original discussion: internal (not published).
