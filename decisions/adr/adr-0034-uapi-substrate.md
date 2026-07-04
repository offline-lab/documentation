# ADR-0034 — UAPI specifications adopted as the format substrate

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0001, ADR-0028 (aligns them to the upstream specs) |

## Context

We build the ecosystem around systemd's image formats, not a rival to them
(ADR-0030). Inventing parallel formats or vocabularies would break the "runs
on any systemd host" promise. The relevant upstream specs: UAPI.3 (DDI),
UAPI.4 (Extension Images), UAPI.10 (Version Format).

## Decision

Adopt the UAPI specs verbatim as the normative substrate; our contracts are
curation, trust, distribution, and lifecycle **on top** of them:

- **UAPI.3 (DDI)** — the package format (affirms ADR-0001): GPT image with
  root + verity + verity-sig partitions, independently signed.
- **UAPI.4 (Extension Images)** — normative for layered apps and bases:
  - An app image is a **sysext**: carries
    `/usr/lib/extension-release.d/extension-release.<name>`, no `os-release`
    (the base owns identity). `SYSEXT_SCOPE=portable`.
  - Matching is UAPI.4 **exact string match**: `ID=` (must equal the base's —
    we do not use `_any`), `SYSEXT_LEVEL=` (our compatibility level;
    `VERSION_ID=` only if level absent), `ARCHITECTURE=`.
  - **Level-match is binding** — it is what allows updating a base without
    rebuilding its apps. The level is the base publisher's ABI promise,
    aligned to how the distro versions (Debian stable point releases share a
    level). An exact build-base identity may be recorded as audit metadata
    only; it never gates the runtime.
  - We are a **stricter subset**: max 3 layers — one distro base + optional
    runtime/language layer + the app (affirms ADR-0028's cap; an artificial
    complexity guard, not a fundamental limit). No base-on-base stacking.
  - confext is **not** used for app config — config is the mutable
    operator-owned bind-mount (ADR-0035). Host sysext/confext remain
    boxctl-managed (ADR-0023, unchanged).
- **UAPI.10 (Version Format)** — the version scheme: `~` pre-release, `^`
  post-release; `systemd-analyze compare-versions` is the reference
  comparator, present on every target host. "Latest" in an index = maximum by
  UAPI.10 ordering. **Supersedes the old "version must be semver" rule.**

Base images are first-class in both contracts: independently signed DDIs
(the base vouches for itself; an app never vouches for base content), a
distinct image class in the index, fetched as part of `get`'s closure.

## Consequences

- Cross-distro compatibility is inherited from upstream, not maintained by us.
- Size strategy is sharing policy, not storage tricks: few curated official
  bases + level-match = one cached base serves many apps; fat-app (no base)
  is the explicit opt-out. Block-level dedup rejected as premature.
- A base-image spec must be written (base = UAPI.4-matchable base DDI:
  `os-release` with `ID` + `SYSEXT_LEVEL`, runtime libs, no unit files).
- Open: cross-layer build-time dependency resolution (installing app-layer
  deps against a lang-layer interpreter) — parked; official base curation
  policy — open.

## Alternatives considered

### Own extension/matching format
Rejected: breaks "any systemd host", duplicates maintained upstream work.

### Exact base pinning (roothash) as the runtime contract
Rejected: every base patch would orphan every app; fights offline patching.

## References

- UAPI.3, UAPI.4, UAPI.10 (uapi-group.org).
- `decisions/conversation/2026-07-04-design-session.md` (§7, §11-versions).
- `decisions/design/layered-images.md` (amended by this ADR).
