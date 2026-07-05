# ADR-0040 — One binary; the legs become namespaces

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0039 (binary split → namespace split); reverses `rejected/monolithic-cli.md` |

## Context

ADR-0039 split build/distribute/run into three binaries. Reviewing the
original monolith rejection showed **all three of its technical premises
have dissolved**: the CGO conflict died with the pure-Go pipeline
(ADR-0031 — everything is `CGO_ENABLED=0` orchestration now); macOS vs
arm64 is trivial cross-compilation once CGO is gone; and Docker/portablectl
are runtime deps of individual *verbs*, not of the binary. Meanwhile new
forces push toward bundling: appctl and the distribute tool share on-device
state and a local index (two binaries over one state = version-skew bugs);
the `up --get` composition crossed tool boundaries; T105 ships everything
as one sysext anyway; and the third tool had no name.

## Decision

**One binary, one name (parked — deliberately not chosen yet), with one
namespace per leg.** ADR-0030/0039's separation of concerns survives as
command namespaces and package layout, not binary walls:

- build verbs (`build`, keys) — the build leg
- index verbs (`index init/add/update/trust/list/drop`, `get`, `search`) —
  the distribute leg
- lifecycle verbs (`up/down/rm/drop/recover/doctor`) — the run leg

Until the name lands, "buildctl" and "appctl" in specs and docs are
**working titles for the namespaces**, not shipping binary names.
`boxctl` remains separate (Bash, OS-side, the OL-OS customer's tool).

Consequences of the merge: no state/version skew on devices; `up --get`
composes naturally (open item resolved); one release train; one docs
story; the "indexctl" naming problem dissolves into the single-name
question. Cost, accepted: one static Go binary (~15–25 MB) on the smallest
targets — it replaces three; a device-slim build-tag variant remains
possible if it ever hurts. The three-leg discipline is enforced by
convention and review, since binary walls no longer enforce it.

## Alternatives considered

### Three binaries over a shared module (ADR-0039 as written)
Superseded: pays the skew/boundary costs for a separation that packages
provide equally well. apt/dpkg is the cautionary precedent; git/cargo/nix
are the happy ones.

### Busybox-style multi-call binary (one artifact, argv[0] names)
Viable hedge, rejected as unnecessary: nothing has shipped, so there are no
names to preserve — one clean name beats three symlinks.

## References

- `decisions/conversation/2026-07-04-design-session.md` §23.
- ADR-0031 (CGO premise gone), ADR-0037 (shared local index), ADR-0039,
  `rejected/monolithic-cli.md` (reversal note added), T105.
