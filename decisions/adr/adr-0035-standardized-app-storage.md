# ADR-0035 — Standardized, relocatable app storage

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-04 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0005 (contract-defined layout replaces OL-OS FHS wiring) |

## Context

The tools run on any systemd host, so app storage cannot be defined in terms
of one OS's filesystem wiring. Operators need one sanctioned way to relocate
data (another disk) and one sanctioned override surface (config), without
per-app or per-OS variation.

## Decision

Every app gets a predefined layout, identical on every host OS, always mounted
into the runtime:

```
<root>/apps/<index-hash>/<appname>/config   # operator-editable
<root>/apps/<index-hash>/<appname>/data     # app-private persistent data
```

- `<root>` is **relocatable** (default `/var/lib/appctl`); the structure below
  it is **fixed by contract**, not by the host's FHS.
- `<index-hash>` is the **index-key fingerprint** (ADR-0033): apps are
  namespaced by the identity that vouched for them; same-named apps from
  different indexes never collide.
- Exactly two persistent targets (affirms ADR-0013); `config` is the one
  sanctioned override surface for the app's baked-in opinion.
- Each app gets a **private `/tmp`** (`PrivateTmp=`).

Guarantees the runtime provides (mechanisms in ADR-0036):

- Apps cannot read each other's data (per-app uid + `0700` dirs).
- An app cannot mount another app's data (only appctl's drop-in grants
  `BindPaths=`; shipped units declaring host mounts are rejected at build and
  again at `up`).
- An app always starts with the same uid+gid — no chown on start, ever.
- An app starts only if its signature verifies (up-gate, every start).

## Consequences

- On OL OS the persistence of `<root>` is the OS's duty (bind-mount from
  `/data`) — see `OS-CONFORMANCE.md`; the tools don't know about it.
- Data survives `down` and `rm` by construction (it lives outside images);
  only `drop`'s guarded path touches it (ADR-0032).
- The layout is public contract (shared caches/sticks expose it) and must be
  versioned carefully.

## Alternatives considered

### FHS paths per app (`/var/lib/<app>`, `/etc/<app>`) on the host
Rejected: unpredictable across distros, no isolation boundary, no single
relocatable root.

### Freeform volume declarations
Rejected long ago (ADR-0013): a malicious package could target sensitive
paths.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§6).
- ADR-0012/0036 (uid model), ADR-0013, ADR-0033 (index-hash).
