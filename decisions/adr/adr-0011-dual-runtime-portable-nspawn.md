# ADR-0011 — Dual runtime: portable and nspawn from v1

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0030 (2026-07-04): the runtime mode is developer-declared in the shipped image, not an operator toggle |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

systemd offers two ways to run an image-based service:

- **Portable services** (`portablectl attach`, `RootImage=`, managed via
  `systemctl`) — the service runs as a host-visible unit backed by an
  attached image.
- **nspawn** (`systemd-nspawn --image=`, managed via `machinectl`) — the
  service runs inside a lightweight container/namespace.

Different apps have different isolation requirements, and both code paths in
systemd verify the DDI through the same `verity.d/` mechanism. The question
is whether to ship only one mode initially or support both.

## Decision

Support **both runtime modes from v1**. The packager declares which mode via
`package.yaml`:

```yaml
runtime: portable    # default — portablectl attach, RootImage=, systemctl managed
# or
runtime: nspawn      # systemd-nspawn --image=, machinectl managed
```

Both modes use the same DDI, the same `verity.d/` verification path (confirmed
by live test), and the same certificate store. Only the Runtime
implementation differs.

The operator **cannot override** the runtime mode in v1 — the packager knows
the app's requirements.

## Consequences

- appctl must implement and maintain two Runtime backends from the start.
- Both modes share verification, cert store, and image format, so the
  divergence is contained to the runtime/attach path.
- Operators are locked to the packager's chosen mode per app (v1 limitation).

## Alternatives considered

### Ship only one mode in v1

Rejected. Both modes were verified to share the verity path by live test, and
deferring one would force a later format/verification re-validation. The
shared-core design makes supporting both cheap enough to do now.

## References

- Related: ADR-0002 (systemd native userspace verification).
- Original discussion: internal (not published).
