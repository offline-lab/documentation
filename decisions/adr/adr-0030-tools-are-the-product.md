# ADR-0030 — Tools are the product; the OS is a customer

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-04 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None (reframes the whole corpus) |

## Context

The decision corpus grew up treating buildctl/appctl as support tooling for
Offline Lab OS. That inverted the real priorities: OL OS is a personal side
project; the tools are the thing being built for a general audience. Docker
solves this space with a daemon, heavy images, and implicit network use;
Flatpak solves delivery but not services; systemd already ships the entire
runtime engine (DDI, dm-verity, PKCS7 verification, portablectl, nspawn,
extension images) unused by either.

## Decision

**The tools are the product; the OS is a customer.** Mission:

> Package any Linux service — Debian, RHEL, Alpine, whatever it was built
> from — into a small, immutable, signed image; carry and share those images
> offline; run them on any systemd host with a single command, no daemon, no
> layer pulls, near-zero overhead. Start it, stop it — the data stays.

Structural rules:

- **The engine is free; the envelope is ours.** systemd owns the runtime
  (DDI/verity/signing/portablectl/nspawn/extensions). We never rebuild it.
  Our value: a pleasing build experience, offline-first distribution with
  trust, and a dead-simple run lifecycle.
- **The product is two contracts, not a set of tools:** (1) what a DDI-app
  *is*; (2) what an *index* (distribution) is. CLIs are replaceable reference
  implementations of the contracts.
- **Core runtime is the light portable service** ("nicer portable services",
  as Docker was "nicer chroots"). Isolation (nspawn) is optional and
  **developer-declared in the image**, not an operator toggle (amends
  ADR-0011's framing).
- An app is defined by five questions it must answer: identity, trust,
  run-intent (which units activate on `up` — systemd only *attaches*; we
  provide *up*), persistent state, lineage (base).

## Consequences

- The existing buildctl implementation is removed and redesigned (ADR-0031).
- The tools carry **no reservations for Offline Lab OS**; OL-OS adaptations
  live in the OS itself (ADR-0036, `OS-CONFORMANCE.md`).
- The spec corpus is re-anchored on the two contracts; OS-centric specs
  become OS-side conformance docs.

## Alternatives considered

### Keep the OS-centric framing

Rejected. It produced a tool that reimplemented solved problems (ADR-0031's
context) and coupled general-purpose tools to one host's quirks.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§1–§5).
- ADR-0031…0036 (the decisions this pivot produced).
