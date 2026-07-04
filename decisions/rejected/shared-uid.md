# Rejected: Single Shared uid 6000 for All Apps

**Status:** Rejected — replaced by per-app dynamic allocation
**Replaced by:** Per-app uid allocation starting at 6000, monotonically increasing

---

## What was proposed

A single shared user with uid 6000 / gid 6000 used by ALL installed applications.
From the initial brainstorm:

> "a user uid: 6000 gid: 6000"

All app processes would run as this single user, sharing the same uid across all apps.

---

## Why it was rejected

A shared user provides no isolation between apps. If app A and app B both run as
uid 6000, app A can read and write all of app B's data directories. This violates the
security model where each app should only be able to access its own data.

The decision to use per-app dynamic allocation was made early: "Service user: dynamic
allocation per-app, not shared user."

---

## What replaced it

Per-app uid allocation:

- UIDs start at 6000, monotonically increasing, never reused across different apps
- Username: `app<uid>` (e.g. uid 6001 → user `app6001`)
- Reinstalling the same app reuses its original uid (not a new one)
- Reinstalling a DIFFERENT app never reuses a prior uid

The `app6000` format was preserved from the original idea (starting at 6000) but is now
per-app rather than shared.

Each app gets:

- Its own uid and gid (both the same number)
- Its own storage paths: `/var/lib/appctl/apps/<repo-hash>/<name>/{config,data}/`
- Its own sysusers snippet: `/etc/sysusers.d/<repo-hash>-<name>.conf`
- A systemd drop-in that sets `User=app<uid>` and `Group=app<uid>`
