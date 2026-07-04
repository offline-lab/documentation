# ADR-0002 — Systemd native userspace signature verification

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

DDI packages are cryptographically signed, and signature verification must
happen before a package can be activated. Two verification surfaces exist:

1. The kernel's `.secondary_trusted_keys` keyring, which requires every cert
   to be cross-signed by a CA baked into the kernel at build time.
2. Systemd's built-in userspace PKCS7 verification via `verity.d/` certificate
   directories.

Offline Lab supports an open, multi-publisher repository model: any publisher
creates their own signing key without involving the project. The kernel
keyring requirement — a baked-in cross-signing CA — is incompatible with that
model.

## Decision

Use **systemd's built-in userspace PKCS7 verification** via `verity.d/`
directories. This is implemented in systemd's `src/shared/dissect-image.c`
(`validate_signature_userspace()`) and is the default behavior for all
callers (`portablectl`, `systemd-nspawn`, `systemd-dissect`).

Verification flow:

1. `systemd-dissect` discovers the DDI's signature partition by GPT type UUID.
2. Reads JSON `{rootHash, signature}` from the partition.
3. Attempts kernel keyring verification → fails (cert not in keyring) →
   this is expected.
4. Falls back to userspace: scans `/etc/verity.d/*.crt`.
5. Calls `PKCS7_verify(signature, certs, roothash, PKCS7_NOINTERN|PKCS7_NOVERIFY)`.
6. On success, activates dm-verity using the root hash.

Build-time signing remains in buildctl (pure Go, `go.mozilla.org/pkcs7`).
Runtime verification is systemd-native — **there is no PKCS7 verification
code in appctl**.

This path was verified by a live test on Fedora 44 with systemd 259: the full
kernel-fail → userspace-succeed → dm-verity-activate sequence works as
designed.

## Consequences

- The open multi-publisher model works without per-publisher kernel changes.
- Certificates are managed as files in `/etc/verity.d/`, imported at
  `appctl repo add` time.
- The kernel still enforces block-level integrity at runtime via dm-verity;
  only the signature decision is delegated to systemd userspace.
- Verification correctness now depends on systemd being built with OpenSSL
  support (see ADR-0003).

## Alternatives considered

### Kernel `.secondary_trusted_keys` keyring

Rejected. Requires every signing cert to be cross-signed by a CA baked into
the kernel image. Incompatible with an open, multi-publisher repository model
where publishers generate their own keys independently.

### PKCS7 verification code in appctl

Rejected. Duplicates work systemd already does natively, adding a
security-critical code path for no benefit.

## References

- Related: ADR-0003 (systemd OpenSSL requirement), ADR-0004 (image policy
  enforcement).
- Original discussion: internal (not published).
