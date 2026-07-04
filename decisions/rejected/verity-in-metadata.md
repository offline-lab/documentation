# Rejected: Verity Root Hash / Checksum in Metadata JSON

**Status:** Superseded by DDI — the root hash and its signature now live inside the
DDI signature partition (ADR-0001), not in a companion file and not in metadata JSON.

---

## What was proposed (verity hash tree as companion file — ACCEPTED)

The verity hash tree data should be a separate companion file:

`<name>-<version>-<arch>.squashfs.verity`

This was accepted: the `.verity` file contains the full Merkle hash tree.

## What was proposed (root hash placement — PARTIALLY ACCEPTED, PARTIALLY DROPPED)

From a follow-up design answer:

> "If we have a separate file, we might not need it in the metadata file. If we don't
> need it, let's remove it."

> "I'd like to prevent hash offset as it comes with complexity that is easy avoided by
> shipping a second file."

> "Let's store the shasum in the metadata file so that we can verify whether we did a
> full or partial download."

Two things were being discussed:

1. Whether to put the root hash in the metadata JSON → DROPPED (use `.roothash` file
   instead)
2. Whether to put a download SHA checksum in the metadata JSON → ACCEPTED (but may not
   be implemented)

---

## Superseded by the DDI format (ADR-0001)

Both the "root hash in metadata JSON" proposal **and** the companion-file model that
briefly replaced it are now obsolete. Under the DDI package format
([ADR-0001](../adr/adr-0001-package-format-ddi.md)) there are **no companion files**:

- The dm-verity **root hash** and its **PKCS7 signature** live together inside the DDI's
  signature partition as JSON `{rootHash, signature, certificateFingerprint}`, discovered
  by GPT partition type UUID — not by filename convention.
- The dm-verity **hash tree** lives in the DDI's verity partition, not a `.verity` sidecar.
- **Download integrity** is covered by `ddi_sha256` (a SHA-256 over the `.raw` file) in the
  metadata JSON and the per-arch index — this is the whole-file checksum that was mentioned
  here.

The original decision to keep the root hash *out* of the metadata JSON was correct; only
the mechanism changed — from a signed `.roothash` companion file to the in-DDI signature
partition. See [Package Format](../../docs/specs/package-format.md).
