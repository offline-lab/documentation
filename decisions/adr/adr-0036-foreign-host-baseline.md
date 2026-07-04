# ADR-0036 — Foreign-host baseline; OL-OS specifics move to the OS

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0012 (uid allocation), ADR-0021 (reboot-proofing becomes OS-side) |

## Context

appctl must deliver its guarantees on any systemd host. Offline Lab OS is the
*weird* host (read-only rootfs, `/etc` overlay wiped each boot); a normal
Debian/Fedora box with persistent `/etc` is the easy case. Building OL-OS
accommodations into the tools would couple them to one customer.

## Decision

**appctl targets the boring persistent systemd host.** OL OS uses its own
machinery to look like one; the tools carry no reservations for it. The
OS-side duty list lives at `offline-lab/OS-CONFORMANCE.md`.

**The host contract** (all appctl requires): systemd ≥ 250 built with OpenSSL
(≥ 254 for layered), `portablectl`/`systemd-nspawn`, root (or polkit) for
state-changing verbs, a writable persistent `<root>`.

**Mechanisms** (all stock systemd/Unix): per-app uid + `0700` dirs;
`sysusers.d` snippets; certs in `/etc/verity.d/` installed at `index trust`;
pinned `RootImagePolicy=signed:=absent` re-verified by systemd at **every
start**; `PrivateTmp=yes`; `systemctl enable` for power-cut resume. **The
generated drop-in is the keystone**: the image ships intent (the unit); the
host ships placement (the drop-in: `User=`, `BindPaths=` to exactly
config/data, `PrivateTmp=`, image policy, runtime mode). Developer owns the
unit; appctl owns the drop-in (restates ADR-0015 as the run leg's seam).

**Rulings:**

- **uid allocation: error on clash.** Configurable base range in the config
  (default 6000+), monotonic, never reused; if the next uid is occupied by a
  foreign user, appctl errors loudly and asks the operator to configure a
  different range. No silent skipping (amends ADR-0012).
- **Privilege model: bounded by systemd.** State changes go through
  D-Bus/polkit → effectively root; read verbs run unprivileged. Non-root
  operation is a *documented* pattern (an `appctl` group + sudoers/polkit
  snippet, like the `docker` group), not built machinery.
- **`doctor`:** an extendable rule set (brew-doctor style) checking the host
  contract; grows over time; cheap subset re-checked on `up`.
- **`recover`:** idempotent reconcile that re-derives every generated artifact
  (sysusers, verity.d certs, attachments + drop-ins, enable state) from
  persistent state records, using recorded uid/gids. A read-only OS ships one
  trivial boot unit running `appctl recover`. State is truth; `/etc` is
  derived cache.

## Consequences

- ADR-0021 and `specs/reboot-proofing.md` become OS-side conformance material.
- OL OS integration shrinks to: bind-mount `<root>` from `/data` + run
  `appctl recover` at boot.
- appctl state records (file-per-record, ADR-0026) are the recovery source of
  truth and live on the persistent volume beside the data.

## Alternatives considered

### OS-side file replay (persist/restore `/etc` artifacts via bind-mounts)
Rejected as the primary mechanism: `recover` is generic (any RO/wiped host,
disaster repair), simpler to reason about, and keeps the artifact set
appctl-internal.

### Building privilege management into appctl
Rejected: systemd/polkit already defines the boundary; documentation beats
machinery.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§14).
- `offline-lab/OS-CONFORMANCE.md` (OS-side duties).
- ADR-0032 (verb definitions), ADR-0035 (storage guarantees).
