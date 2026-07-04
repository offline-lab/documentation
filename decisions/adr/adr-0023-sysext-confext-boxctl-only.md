# ADR-0023 — sysext/confext: boxctl-managed, not appctl

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

systemd offers two host-level extension mechanisms: **sysext** (extends
`/usr/`) and **confext** (extends `/etc/`), managed via `systemd-sysext` and
related tooling. These are host-configuration concerns — they alter the
running OS image — distinct from app packaging. The question is which tool in
this project owns them.

## Decision

Extensions (sysext and confext) are **admin-managed via `boxctl`**.

There is **no appctl support** for extensions. They are a host configuration
concern, not an app packaging concern.

## Consequences

- appctl's scope stays focused on app packages; it does not grow a host-OS
  extension surface.
- Operators manage OS extensions through `boxctl` alongside other host
  administration.
- The app-layer extension mechanism (layered apps via
  `portablectl attach --extension`) is a separate feature and is unaffected
  (see ADR-0028).

## Alternatives considered

### Let appctl manage sysext/confext

Rejected. Conflates app packaging with host-OS configuration and would
enlarge appctl's trusted surface into OS mutation. `boxctl` is the natural
owner of host administration.

## References

- Related: ADR-0028 (layered images use `portablectl attach --extension`,
  which is distinct from host-level sysext).
- Original discussion: internal (not published).
