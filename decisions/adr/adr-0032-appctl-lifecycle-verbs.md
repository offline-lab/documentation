# ADR-0032 — appctl lifecycle: two axes, guarded destruction, no implicit anything

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None (defines the appctl surface; amends ADR-0029 base lifecycle) |

## Context

systemd's `portablectl attach` only makes unit files *available* — nothing
starts. Turning "image present" into "service running, correctly wired" is the
tool's core value. Docker's ergonomics are the benchmark; its implicit network
pulls and casual data destruction are the anti-goals.

## Decision

The lifecycle is **two independent axes plus data orthogonal to both**:

- **Cache axis:** `get <index>/<name>` (fetch into local cache; resolves the
  base closure; the only verb allowed to touch the network) ↔ `rm` (drop the
  cached image; data untouched; re-`get` restores exactly).
- **Run axis:** `up` (attach + wire storage/uid/tmp + start the declared
  units) ↔ `down` (stop; keep everything). Only this axis spends resources.
- **Removal ladder:** `down` → `rm` → `drop` (total, irreversible teardown:
  image + environment + uid/gid **+ data**, behind loud `THIS IS DESTRUCTIVE`
  guards; no keep-data middle state, no split-brain). `drop` refuses on a
  running app. Future: `drop --backup` / `import` (T70/T71).
- **Composition grammar:** a verb moves its own axis; an `--other` flag opts
  into the second: `up --get`, `get --up`, `down --rm`, `rm --down`.

Two product-defining principles:

1. **No implicit network.** Only `get` (or explicit `--get`) may touch the
   network. Bare `up` on an uncached image fails loudly. buildctl-side this is
   absolute (no distribution I/O at all, ADR-0031).
2. **No implicit data loss.** Data survives `down` and `rm`; only `drop`'s
   guarded path destroys it. Base images are never silently deleted: `get`
   pulls the closure, `up` never fetches, `rm` never purges an orphaned base
   (kept for offline reuse; explicit prune only; amends ADR-0029's cleanup
   semantics). Bases are not directly user-deletable while referenced.

Supporting verbs:

- `recover` — idempotent reconcile: re-derives all generated artifacts
  (sysusers, verity.d certs, attachments + drop-ins, enable state) from
  persistent state records, with recorded uid/gids (no chown). Safe every
  boot; how read-only hosts come back (ADR-0036).
- `doctor` — extendable brew-style rule set checking the host contract.
- `index trust <url|path>` / `index list` / `index drop <alias>` — consumer
  side of ADR-0033. `index drop` refuses while apps from that index remain
  provisioned; destructiveness lives at exactly one altitude (the app).

CLI ergonomics is a first-class value: verbs are short and fun to type.

## Consequences

- appctl's surface is fixed by design, not accreted (`install`/`remove`
  vocabulary from earlier specs is gone).
- `up` requires the app's declared activation units (contract question #3).
- `compose` (multi-app groups) confirmed post-v1 (T53).

## Alternatives considered

### Docker-style single axis (`run` fetches implicitly)
Rejected: surprise network pulls are the exact failure mode the offline
product exists to prevent.

### `drop` keeping data (de-provision only)
Rejected by the operator: leftover state after "drop" is split-brain; total
teardown with guards is honest.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§lifecycle, §5–7, §14).
- ADR-0033 (trust/index), ADR-0036 (foreign hosts, recover/doctor).
