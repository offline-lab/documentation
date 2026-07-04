# Rejected: Kernel Keyring for Signing Verification

**Status:** Rejected — permanent design decision to use userspace instead
**Replaced by:** systemd-native userspace PKCS7 verification via `/etc/verity.d/` (ADR-0002)

---

## What was proposed

Using the Linux kernel's `.secondary_trusted_keys` keyring + `CONFIG_SYSTEM_TRUSTED_KEYS`
to enforce PKCS7 signature verification at mount time. The kernel would verify the
signature on the verity root hash (`.roothash.p7s`) whenever portablectl (or dm-verity
setup) attaches a squashfs image.

This was the initial answer in an early design Q&A: "option A: sign the root hash (PKCS7)
— kernel enforces at mount time."

For trusted public keys, the original answer was flexible: keys could be added at build
time, copied to `/data/config`, or both. The intent was that keys be updatable — new
keys importable for new repos without rebaking the kernel.

---

## Why it was rejected

The kernel's `.secondary_trusted_keys` keyring requires all repo signing certs to be
cross-signed by a CA that was baked into the kernel image at build time.

This creates a **walled garden**: every repo operator needs the Offline Lab project's CA
to cross-sign their keys before the kernel will accept their packages. That is
incompatible with an open, multi-publisher model where any developer can publish packages
without involving Offline Lab.

Additionally, the kernel keyring cannot be updated at runtime without a full OS update —
making key rotation for per-repo certs impossible.

---

## What replaced it

**Systemd-native** userspace verification
([ADR-0002](../adr/adr-0002-signing-model-systemd-userspace.md)):

1. The build cert is imported at `appctl repo add` time and written to
   `/etc/verity.d/<repo-name>-<key-id>.crt`.
2. At attach time, systemd (`validate_signature_userspace()` in
   `src/shared/dissect-image.c`) verifies the DDI signature partition against the certs in
   `/etc/verity.d/` — the kernel keyring is tried first and falls back cleanly.
   **appctl runs no PKCS7 verification itself** (an optional pre-check aside), and there is
   no per-boot re-verification in appctl.
3. The kernel's dm-verity enforces block-level integrity at runtime, separately from the
   signature check.

This is a permanent design decision, not a compromise. (The earlier plan had appctl perform
the PKCS7 check with `go.mozilla.org/pkcs7`; that library is now used **build-time only**,
inside buildctl, to *produce* the signature.)

---

## When to revisit

Potentially relevant if targeting x86_64 hardware with UEFI Secure Boot and a TPM,
where the device owner controls the full boot chain and can bake a CA into the kernel
image. Not applicable to Pi hardware today (no UEFI firmware, no TPM).
