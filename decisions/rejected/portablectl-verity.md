# Rejected: Belief that portablectl Handles dm-verity Natively

**Status:** Incorrect assumption — portablectl does NOT verify plain squashfs images
**Replaced by:** shipping DDIs so systemd verifies natively (ADR-0001/0002); no PKCS7
verification code in appctl

---

## What was assumed

In an early dm-verity design session, when asked about the attach flow for a
dm-verity-protected squashfs, the initial response was:

> "I think you are overdoing it: Afaik we can just use dm-verity during the attach and
> let portablectl handle the signing verification — please verify this."

The assumption was that portablectl, when given a squashfs with companion verity files,
would automatically set up dm-verity and verify the signature.

---

## What was discovered

Research showed that `systemd-dissect` supports dm-verity + PKCS7 signatures, but
**only for DDI format images** (images with a GPT partition table following the
Discoverable Partitions Specification). For plain squashfs files used as portable
services, portablectl does NO verification of its own.

---

## What the correct model is (post-DDI)

This finding is exactly **why the project adopted the DDI package format**
([ADR-0001](../adr/adr-0001-package-format-ddi.md)): systemd verifies dm-verity + PKCS7
natively, but **only for DDI-format images**. Rather than ship a plain squashfs and verify
in appctl, packages ship as DDIs so the platform does the verification:

1. Download the zip → extract the `.raw` DDI + `.json` metadata.
2. `portablectl attach <name>.raw` (or `systemd-nspawn --image=`) — systemd discovers the
   signature partition, tries the kernel keyring, falls back to userspace PKCS7 verification
   against `/etc/verity.d/*.crt`, then activates dm-verity from the verified root hash.
3. The kernel's dm-verity target enforces block-level integrity at runtime — every block
   read is checked against the hash tree in the verity partition.

**There is no PKCS7 verification code in appctl** at install or at rehydrate
([ADR-0002](../adr/adr-0002-signing-model-systemd-userspace.md)); systemd performs it.
appctl may *optionally* pre-check the signature for an early failure, but the authoritative
verification is systemd's. See [Security Model](../../docs/specs/security-model.md).
