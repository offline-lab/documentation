# ADR-0029 — Layered appctl lifecycle

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0032 (2026-07-05): verb model replaces install/remove vocabulary; orphaned bases are kept by default (explicit prune only); bases not user-deletable while referenced |
| **Date** | 2026-06-18 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

Once layered images exist (ADR-0028), appctl must manage the *runtime*
lifecycle of layered apps: discovering and provisioning bases, installing and
updating the full stack atomically, handling rollback, and rehydrating layered
apps at boot. Bases are high-trust, multi-app shared dependencies — a bad
base bump can break every layered app on the device — so the lifecycle rules
treat base changes more conservatively than app changes.

## Decision

The following decisions define how appctl handles layered apps at runtime.

### Base source discovery: search all configured repos

When a layered app needs a base not installed locally, appctl searches every
configured repo whose `repository.json` declares a `bases` class. Operators do
not configure "bases repos" separately — they add repos, and appctl uses
whatever classes each repo serves.

Disambiguation when multiple repos carry the same base:

- Different versions → pick highest semver, tie-break alphabetically by repo
  alias, log the choice.
- Same version → pick alphabetically first repo alias.
- Operator override → `appctl install-base --repo <alias> <name>` pre-stages
  from a specific source.

If no configured repo serves the needed base, appctl exits 1 with a clear
error pointing the operator at `appctl repo add <url>`.

### `--no-download` failure mode: actionable report, exit 2

`appctl install --no-download` resolves the stack, checks local state, prints
what is missing with the exact pre-stage commands, and exits **2** (distinct
from "no source repo", which is exit 1). Nothing is attached.

Companion: `appctl install --download-only` resolves and downloads but does
not attach (for offline pre-staging).

### No auto base updates; explicit `update-base` only

`appctl update <app>` does **not** auto-update bases the app depends on, even
if newer base versions exist. Bases are high-trust; an untested base bump can
break every layered app on the device.

Base updates happen only via explicit `appctl update-base <name>
[--version <ver>]`, which warns before proceeding (listing every dependent
app) and re-attaches each one atomically via `portablectl reattach`.

### Rollback is app-only; bases do not roll back

`appctl rollback <name>` for a layered app reverts **only the app image**.
Bases stay at whatever version is currently installed. The base may have been
updated since the previous app version was installed; rolling back the base
would break other apps depending on the newer version.

There is no `appctl rollback-base` command. If a base update broke things, the
operator must explicitly downgrade via `appctl update-base --version <old>
<name>`.

### Explicit base management commands

| Command | Purpose |
|---|---|
| `appctl install-base <name> [--version \| --sysext-level \| --repo]` | Explicit pre-staging |
| `appctl remove-base <name> [--force]` | Ref-counted removal (`--force` cascades to dependent apps) |
| `appctl update-base <name> [--version <ver>]` | Explicit base update (interactive confirm) |
| `appctl list-bases` | Show installed bases with version, sysext_level, ref count |
| `appctl deps <name>` (alias: `appctl tree <name>`) | Print resolved stack without installing |

`install-base` errors on ambiguity (multiple source repos, no `--repo` flag).
An installed base has `referenced_by: []` until an app uses it. Bases are
never attached alone — they are only attached as part of an app's stack via
`RootImage=`.

### Atomic updates via `portablectl reattach`

`portablectl reattach` (v248+) detaches and reattaches in one operation;
running services are not stopped during the swap. It takes the same
`--extension` flags as `attach`. appctl uses this for `appctl update` on
layered apps, not detach+attach.

### Layered rehydrate at boot

`restore-apps.service` runs `appctl rehydrate` at boot. For each installed
package with a non-null `stack`:

1. Verify each referenced base still exists at its recorded path (corruption
   check; a missing base is a loud failure, not a silent re-download).
2. Regenerate the drop-in (paths under `/etc/systemd/system.attached/` were
   wiped by the overlay reset on Offline Lab OS — see ADR-0021).
3. Attach via `portablectl attach --extension ... <base> <prefix>`.

There is no base re-download at boot — bases are persistent on `/data`.

## Consequences

- Layered installs are self-provisioning: appctl resolves and fetches missing
  bases from configured repos, with deterministic disambiguation.
- Base changes are conservative and always operator-initiated; app updates
  never silently pull a new base.
- Rollback is scoped to the app only, protecting co-tenant apps from a base
  downgrade.
- Reboot rehydration treats a missing base as a hard failure rather than
  silently re-downloading.
- The lifecycle adds a distinct set of base-management commands and exit-code
  semantics (exit 1 vs 2) that operators must learn.

## Alternatives considered

### Auto-update bases on app update

Rejected. An untested base bump can break every layered app on the device.
Bases are high-trust shared dependencies and must be advanced explicitly.

### `appctl rollback-base`

Rejected. Rolling back a base would break other apps depending on a newer
base version. Explicit downgrade via `update-base --version <old>` covers the
recovery case without an implicit multi-app rollback hazard.

### Silent base re-download at boot

Rejected during the rehydrate design. A missing base at boot is treated as a
loud failure (possible corruption or tampering) rather than silently repaired
by re-download.

## References

- Related: ADR-0021 (overlay wipe — why drop-ins must be regenerated),
  ADR-0028 (layered images), ADR-0005 (persistent state on `/data`).
- Original discussion: internal (not published).
