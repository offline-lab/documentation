# Rejected: systemd-homed for Per-App Home Directories

**Status:** Evaluated and rejected
**Replaced by:** systemd-sysusers + mkdir + chown

---

## What was proposed

Using `systemd-homed` as the mechanism for per-app persistent home directories.
Each installed app would have a homed-managed home directory on `/data/`.

From the gap analysis:

> "Why we prefer it over systemd-tmpfiles for app data:
> - `/data/apps/<name>/config` and `/data/apps/<name>/data` are persistent, durable state
>   — not temporary files. systemd-tmpfiles creates dirs at boot and can silently clean
>   them up. That is dangerous for app data.
> - systemd-homed gives us a managed, durable home per app user, stored under /data/.
>   Deleting it requires an explicit `homectl remove` — no accidental loss.
> - Aligns with the per-app user model (T07): each app has a user, each user has a home.
> - appctl uses `homectl create` at install and `homectl remove` only on `--purge`."

An open question at the time was whether systemd-homed supported a plain (non-LUKS)
directory backend suitable for embedded use without cryptsetup overhead.

---

## Why it was rejected

User statement: "homed is more for mounting encrypted filesystems for users: did not
match our goal, so we chose sysusers. At the same time, if it solves a problem we're
having we can add it."

systemd-homed is designed for encrypted, portable user home directories. The use case
is user sessions with optional encryption at rest. The per-app storage concern in Offline
Lab is different: we need namespace-level isolation via bind mounts, not encrypted home
dirs. The extra complexity (PAM dependency, cryptsetup, homectl tooling) is unnecessary.

The concern about tmpfiles "silently cleaning up" directories is valid but addressed
differently: appctl creates directories with explicit `mkdir` + `chown`, not via
tmpfiles. These directories persist because they are on `/data` (persistent ext4), not
because tmpfiles protects them.

---

## What replaced it

At install time, appctl:

1. Allocates a uid (per-app dynamic allocation starting at 6000)
2. Writes a sysusers snippet to `/etc/sysusers.d/<repo-hash>-<name>.conf`
3. Calls `systemd-sysusers` on the snippet to create the `app<uid>` user
4. Creates `/var/lib/appctl/apps/<repo-hash>/<name>/{config,data}/` directories
5. `chown app<uid>` the directories

The directories persist because they live under `/var/lib/appctl/` — on Offline Lab OS
bind-mounted from the persistent `/data` ext4 partition (ADR-0005). They are not managed
by any systemd mechanism — just regular directories with correct ownership.

At remove time: directories are deleted only on `--purge`. Without purge, the
directories (and uid) are retained in case the app is reinstalled.

---

## When to revisit

If per-app data-at-rest encryption becomes a requirement (e.g. a multi-user device where
different apps belong to different physical users). The sysusers + mkdir approach does
not provide encryption. systemd-homed's non-LUKS backend (if it exists and works without
TPM) could provide managed directories without the encryption overhead.
