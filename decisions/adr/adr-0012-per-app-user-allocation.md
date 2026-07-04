# ADR-0012 — Per-app user allocation (portable mode)

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0036 (2026-07-05): base range configurable (default 6000+), loud error on clash with foreign users, no silent skipping; `recover` recreates users with recorded uids |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

In portable mode, an app runs as a host-visible systemd service backed by an
attached DDI. For isolation, each app should run under a dedicated system
user rather than a shared one, so that filesystem permissions provide a
second layer of separation on top of the read-only image. The allocation
mechanism must survive reboots (Offline Lab OS wipes `/etc` on boot) and must
not require pre-baking users into the base image.

## Decision

Allocate a dedicated system user **per installed app** in portable mode:

- Each app gets `app<uid>`, where the uid is `MAX(existing uid) + 1` starting
  at 6000.
- Allocation is owned entirely by appctl; no pre-created users in the base
  image.
- `systemd-sysusers` creates the user from a snippet written by appctl.
- The snippet persists to survive reboots (on Offline Lab OS it is
  bind-mounted from `/data/`).
- UIDs are monotonically increasing and **never reused** across different
  apps.
- Reinstalling the same app reuses its original UID.

**nspawn mode does not allocate uids** — isolation comes from the namespace.

## Consequences

- Each portable app has a distinct uid, giving filesystem-permission-level
  isolation between apps.
- UID allocation state must be persistent (survives reboot / overlay wipe).
- The uid namespace from 6000 upward is owned by appctl and must not collide
  with other system users.

## Alternatives considered

### systemd-homed

Rejected. `systemd-homed` is designed for encrypted-filesystem mounting per
user, which does not match the isolation goal here (namespace/bind-mount
level separation). Plain `systemd-sysusers` + `mkdir` + `chown` is the right
tool.

## References

- Related: ADR-0011 (dual runtime — nspawn does not allocate uids).
- Original discussion: internal (not published).
