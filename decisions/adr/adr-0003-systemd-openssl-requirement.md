# ADR-0003 — Systemd built with OpenSSL requirement

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

ADR-0002 delegates signature verification to systemd's userspace path
(`validate_signature_userspace()`). That function only exists when systemd is
compiled with OpenSSL support (`HAVE_OPENSSL`). Without it, userspace verity
verification is impossible, so signed DDIs cannot be activated — the entire
signing model is inert.

## Decision

Require **systemd >= 250 compiled with OpenSSL support**.

- For Offline Lab OS: verify that the Buildroot systemd package includes
  OpenSSL.
- For external hosts: document the requirement.

The guards that gate this behavior all default to **enabled**, so no extra
configuration is needed at runtime:

- `DISSECT_IMAGE_ALLOW_USERSPACE_VERITY` flag — set unconditionally by callers.
- `$SYSTEMD_ALLOW_USERSPACE_VERITY` environment variable — defaults enabled.
- `systemd.allow_userspace_verity=` kernel command-line argument — defaults
  enabled.

## Consequences

- Signed DDIs activate correctly wherever systemd >= 250 with OpenSSL is
  present.
- Hosts whose systemd lacks OpenSSL cannot run Offline Lab packages at all;
  this must be surfaced clearly as a hard prerequisite.

## Alternatives considered

None considered. This is a hard dependency of the verification model in
ADR-0002.

## References

- Related: ADR-0002 (systemd native userspace verification).
- Original discussion: internal (not published).
