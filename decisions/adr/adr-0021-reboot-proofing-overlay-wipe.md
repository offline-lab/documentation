# ADR-0021 — Reboot proofing: initramfs wipes the overlay upper

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0036 (2026-07-05): reboot-proofing is now an OS-side conformance concern (`OS-CONFORMANCE.md`); the tools know nothing about overlay wipes, and boot-time restore is `appctl recover` |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

Offline Lab OS is immutable: the rootfs is read-only and `/etc` is an
overlayfs. For immutability to mean anything, operator-level runtime changes
to `/etc` must not silently persist across reboots — otherwise the system
drifts from its built image. At the same time, certain machine identity and
installed-app state *must* survive reboot, so there must be an explicit, narrow
restore path rather than wholesale persistence.

## Decision

The **initramfs clears `/overlay/<slot>/upper` on every boot**. Only files
explicitly restored from `/data` survive the reboot.

Concretely:

- `/etc` overlay upper is wiped → runtime `/etc` changes do not persist.
- `machine-id` is restored from `/data/config/system/machine-id`.
- `portablectl` attachments are rehydrated by `restore-apps.service` at boot
  (via an `appctl rehydrate` command), since the drop-ins under
  `/etc/systemd/system.attached/` were wiped by the overlay reset.

This is intentional: the OS is immutable; operator runtime changes don't
persist by default.

## Consequences

- The system returns to a known-good `/etc` state every boot.
- Anything that must persist (machine-id, app attachments) requires an
  explicit restore step from `/data`.
- appctl must rehydrate all installed portable services at boot — install
  state alone (on `/data`) is not enough; the `/etc` drop-ins must be
  regenerated.

## Alternatives considered

### Persist `/etc` overlay across reboots

Rejected. Would let runtime changes accumulate, breaking immutability and
making the running state non-reproducible from the image. The explicit-restore
model keeps persistence deliberate and auditable.

## References

- Related: ADR-0005 (FHS paths — persistent state lives under `/data`).
- Original discussion: internal (not published).
