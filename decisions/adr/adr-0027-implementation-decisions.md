# ADR-0027 — Build & signing implementation decisions

| | |
|---|---|
| **Status** | Superseded by ADR-0031 (2026-07-05) — these pure-Go pipeline details died with the implementation; kept for the recorded live-test facts (partition GUIDs, single-block roothash, SHA-256 digest) |
| **Date** | 2026-06-17 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

The pure-Go build/signing pipeline (ADR-0001, ADR-0002, ADR-0024) required a
number of concrete implementation choices — digest algorithms, library
selection, identifier schemes, and GPT details — several of which were
settled (and in some cases bug-fixed) during live testing against systemd on
Fedora 44. This ADR records those resolved implementation decisions in one
place. They are individually small but collectively define exactly how a DDI
is built and identified.

## Decision

The following implementation decisions are adopted:

### PKCS7 digest algorithm: SHA-256 (not SHA-1)

`go.mozilla.org/pkcs7` v0.9.0 defaults to SHA-1 for the digest algorithm.
OpenSSL 3.x (used by systemd for userspace verity verification) rejects SHA-1
with "invalid digest", because SHA-1 is disabled in the default security
provider. buildctl **must** call
`sd.SetDigestAlgorithm(pkcs7.OIDDigestAlgorithmSHA256)` before signing.

### dm-verity root hash for a single data block is the leaf hash

The kernel's dm-verity uses zero hash-tree levels when `num_data_blocks == 1`.
In that case the root hash **is** the leaf hash
(`SHA256(salt + data_block)`), not `SHA256(salt + hash_block)`. The vendored
encoder requires a special case for `dataBlocks <= 1`.

### key_id = SHA-256 of the DER certificate

Key identifiers are **SHA-256 of the DER-encoded certificate**, lowercase hex
— **not** the certificate serial number. This is what appctl uses for
per-key certificate lookup during key rotation.

### GPT verity-sig partition type UUIDs

The verity-sig partition type UUIDs from some online sources are **wrong**.
Verified against `systemd-repart` output on Fedora 44:

- arm64: `6DB69DE6-29F4-4758-A7A5-962190F00CE3`
- amd64: `D4E7CEDE-7F4D-4C7B-9B87-1B7A03A6AB63`

### GPT protective MBR is required

go-diskfs's `Table` must set `ProtectiveMBR: true`, or `systemd-dissect`
cannot identify the image ("Couldn't identify a suitable partition table").

### Pure-Go squashfs: `KarpelesLab/squashfs` v1.2.0

MIT license, zstd compression, supports writing. Pinned to v1.2.0. All
entries are forced to `root:root` via `SetOwner(path, 0, 0)` (per ADR-0014).

### Pure-Go dm-verity: vendored from Monogon OS

Apache-2.0, ~430 lines, vendored. Kernel-tested for byte compatibility
(Monogon's ktest). The single-block root-hash bug above was found and fixed
during live testing on Fedora 44.

### CLI framework: cobra

All commands use `spf13/cobra` for consistent flag parsing, help generation,
and subcommand nesting. No hand-rolled flag parsing.

### Shared module layout: `schemas/`

Shared code lives as the `schemas` module
(`github.com/offline-lab/schemas`). buildctl references it via a `replace`
directive in `go.mod`.

## Consequences

- Signing produces SHA-256 digests that OpenSSL 3.x accepts, so the systemd
  userspace verification path works without modification.
- Correct single-block root-hash handling and correct GPT UUIDs are required
  for systemd to recognize and verify the image at all.
- Key rotation lookups are keyed on the DER-cert SHA-256, not the serial.
- The squashfs and dm-verity dependencies are pinned pure-Go libraries; the
  dm-verity encoder carries a local fix that must be preserved on any
  re-vendor.

## Alternatives considered

For each sub-decision, the obvious alternative (SHA-1 digest; serial-number
key ids; omitting the protective MBR; hand-rolled CLI parsing) was rejected
because it either failed verification or duplicated work the chosen library
already does correctly.

## References

- Related: ADR-0001 (DDI format), ADR-0002 (systemd userspace verification),
  ADR-0007 (key rotation uses the key_id scheme), ADR-0014 (root:root
  ownership), ADR-0024 (pure-Go pipeline).
- Original discussion: internal (not published).
