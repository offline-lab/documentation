# ADR-0039 — One tool per leg: build, distribute, run

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0040 (2026-07-05): the three legs remain the governing separation, but as **namespaces within one binary**, not three binaries. The verb ownership defined here is unchanged |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0031 (build+index one-codebase preference reversed) |

## Context

buildctl was accumulating index-authoring verbs; appctl was about to grow a
local index author for the import model (ADR-0037). Indexing and searching
are "a different thing than what appctl or buildctl does." The product has
three legs (build / distribute / run, ADR-0030); the tool boundaries should
match them.

## Decision

Three tools, one per leg, no verb sharing:

| Tool | Leg | Owns |
|---|---|---|
| **buildctl** | build | backend → conformant, **signed** DDI. Nothing else — the `index` verbs move out. |
| *(unnamed)* | distribute | **getting DDIs onto the system**: index authoring (`init`/`add`/`update`), subscriptions + refresh, import, extraction (dissect), search. |
| **appctl** | run | lifecycle only: `up`/`down`/`rm`/`drop`/`recover`/`doctor`. |

Shared code (manifest schema, DDI reading/verification) lives in a common
module.

**The third tool's name is parked** — "indexctl" felt opaque; the *index*
noun itself may deserve a better name first.

## Consequences

- buildctl shrinks to its essence; ADR-0031's index sections transfer to
  the new tool unchanged in substance (local-only, no transport,
  flag > config > loud error).
- **Open:** the `up --get` composition now crosses tool boundaries —
  whether appctl shells out to the distribute tool or the composition flags
  die is undecided.
- Three binaries to version and ship; on OL OS all three travel in one
  tools-sysext (T105).

## Alternatives considered

### Keep build+index in one codebase (ADR-0031)
Reversed by the operator: with the device side also authoring indexes
(ADR-0037), distribution is clearly its own concern, not a build appendix.

### Fold distribution into appctl
Rejected: appctl stays purely about running; index state and acquisition are
"a different thing."

## References

- `decisions/conversation/2026-07-04-design-session.md` §22.
- ADR-0030 (three legs), ADR-0031, ADR-0037.
