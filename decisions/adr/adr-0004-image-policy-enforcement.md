# ADR-0004 — Image policy: signed images only, no fallback

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

systemd's default image policy accepts all protection levels
(`verity+signed+encrypted+unprotected+unused+absent`). With the default, a
DDI whose signature check fails can still be activated as unsigned verity —
there is a silent fallback path. A live test confirmed this: removing the
cert from `/etc/verity.d/` did **not** prevent the image from mounting under
the default policy.

For Offline Lab the security intent is strict: every image must be
cryptographically signed end-to-end.

## Decision

Every image appctl attaches — single-image app, base image, or extension
image — **must** be cryptographically signed. Unsigned images are never
distributed, never accepted at install, and never activated at runtime. There
is no fallback path.

appctl writes a pinned, non-configurable image policy string verbatim:

```
root=signed:=absent
```

- `root=signed` — the root partition must exist with dm-verity and a valid
  PKCS7 signature.
- `=absent` — every other partition type is forbidden (a DDI contains only
  root, root-verity, and root-verity-sig).

appctl writes `ImagePolicy=root=signed:=absent`:

- In portable mode: the drop-in at
  `/etc/systemd/system.attached/<name>.service.d/99-appctl.conf`.
- In nspawn mode: the `.nspawn` file.

> **Layered refinement (ADR-0028):** the directive above is the single-image
> form (systemd ≥250). For layered images, appctl writes the split
> `RootImagePolicy=root=signed:=absent` and
> `ExtensionImagePolicy=root=signed:=absent` directives (systemd ≥254). The
> mandatory-signing intent is identical.

## Consequences

- A failed signature check is fatal; there is no downgrade to unsigned verity.
- The policy is pinned in code, not configurable at runtime — operators
  cannot weaken it.
- The image-policy string must be kept in lockstep with the DDI partition
  layout (root + verity + verity-sig only).

## Alternatives considered

### systemd default image policy

Rejected. Accepts unsigned verity as a fallback, which defeats the
mandatory-signing security model. Confirmed dangerous by live test.

## References

- Security Model spec (image policy; partition-policy syntax).
- Related: ADR-0002 (systemd native userspace verification).
- Original discussion: internal (not published).
