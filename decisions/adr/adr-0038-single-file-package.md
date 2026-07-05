# ADR-0038 — Single-file package: the metadata lives inside the DDI

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0001 (two-file format); elevates ADR-0017 |

## Context

Since ADR-0001 a package was two files: the `.raw` DDI and a standalone
metadata `.json` beside it. The metadata file was unprotected by the build
signature, had to be kept consistent with the image, and doubled every
transport operation. ADR-0017 already embeds `package.yaml` inside every
image; `systemd-dissect` can read a DDI without mounting it. A suspected
chicken-and-egg (needing metadata to verify the image that contains the
metadata) was examined and does not exist: verification is metadata-free by
DPS construction.

## Decision

**A package is one file: the `.raw` DDI.** The standalone metadata `.json`
is removed from the package format. The embedded manifest
(`/usr/share/<name>/package.yaml`, ADR-0017) *is* the package metadata —
"DDI metadata", an essential part of the format (the term "sidecar" is
banned).

Extraction happens at **index time**, strictly after verification:

1. Probe the GPT — partitions found by type UUID alone (no content read).
2. Verify the PKCS7 signature over the roothash against the accepted-cert
   store.
3. Verity-verify the root partition.
4. Only then read the embedded manifest (`systemd-dissect --copy-from`,
   image policy enforced during dissection).

The index entry is the **read-optimized projection** of the manifest
(name, version, arch, description, hash, size, `added_at`, …): `search`
and resolution never open DDIs — one extraction at `index add`, then the
index file is the only thing read at scale.

## Consequences

- Metadata is now covered by the build signature — builder-attested,
  tamper-evident with the image (a security upgrade over the loose file).
- Unverified images are never parsed (the userspace-squashfs attack surface
  is closed by ordering); filenames are untrusted — identity comes from the
  verified manifest and files may be renamed to convention at `add`.
- Extraction requires `systemd-dissect` (Linux) — on macOS, index operations
  run in the container, like `build`.
- `package-format.md`, the schemas (the separate metadata schema merges into
  the manifest schema), and both contracts need updating.

## Alternatives considered

### Keep the standalone metadata file
Rejected: unsigned, duplicative, and the single-file goal "solves a lot of
problems" for transport and import.

### A UAPI attach-a-JSON mechanism
Does not exist in UAPI.3 (verified 2026-07-05); the embedded manifest +
dissect achieves the goal with today's tooling.

## References

- `decisions/conversation/2026-07-04-design-session.md` §21–22.
- ADR-0017, ADR-0037; UAPI.3; systemd-dissect(1).
