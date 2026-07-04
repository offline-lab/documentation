# ADR-0005 — FHS standard paths

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0035 (2026-07-05): contract-defined relocatable layout `<root>/apps/<index-hash>/…`; OL-OS `/data` wiring moves OS-side |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

appctl must store its state, images, app data, and signing certificates
somewhere on the host. Offline Lab OS has a constrained filesystem: a
read-only rootfs and an ephemeral `/etc` (overlayfs upper wiped on boot), with
a persistent `/data` partition. The question is whether appctl should target
Offline Lab OS-specific paths directly or standard Linux paths and adapt at
the OS layer.

## Decision

Use **standard Linux FHS conventions** everywhere in appctl. Offline Lab OS
adapts its constrained filesystem to those paths via bind mounts.

| Concern | Standard path | Offline Lab OS backing |
|---|---|---|
| appctl state | `/var/lib/appctl/` | bind from `/data/` |
| appctl images | `/var/lib/appctl/images/<uuid>/` | bind from `/data/` |
| app data | `/var/lib/appctl/apps/<hash>/<name>/` | bind from `/data/` |
| signing certs | `/etc/verity.d/` | bind from `/data/` |
| metadata | `/var/lib/appctl/` | bind from `/data/` |

On any other systemd host, these paths work natively. The complexity of
Offline Lab OS's read-only rootfs and ephemeral `/etc` stays in the OS layer,
not in appctl.

## Consequences

- appctl is portable to any systemd host without path configuration.
- OS-specific constraints (read-only root, ephemeral `/etc`) are isolated in
  the OS image, keeping appctl simpler.
- Offline Lab OS must provision the bind mounts before appctl runs.

## Alternatives considered

### Offline Lab OS-specific paths (e.g. write directly to `/data`)

Rejected. Couples appctl to Offline Lab OS internals and breaks portability
to generic systemd hosts. The bind-mount approach gets both standard paths
and OS-level persistence.

## References

- Original discussion: internal (not published).
