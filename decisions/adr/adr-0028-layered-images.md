# ADR-0028 — Layered images: extensions on shared bases

| | |
|---|---|
| **Status** | Accepted — amended by ADR-0034 (2026-07-05): UAPI.4 adopted verbatim (SYSEXT_SCOPE=portable, no `_any`); build-side flows affected by ADR-0031. Further amended (session §20, 2026-07-05): the intermediate language layer is **removed** — cap is **base + app**; language flavors are flat bases |
| **Date** | 2026-06-18 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

In the single-image model (ADR-0001), every app bundles a full OS tree inside
its DDI. That is wasteful when many apps share a common base (a distro plus a
language runtime). systemd's `portablectl attach --extension` can mount
extension images as overlayfs layers on top of a base `RootImage=`, allowing
an app to ship as a small delta on top of a shared base. The design must be
opt-in (single-image remains valid), must preserve the mandatory-signing
model, and must handle base production, version compatibility, repository
structure, and cross-platform building.

## Decision

Layering is an **opt-in extension** to the package format, coexisting with
single-image apps. The decisions below define the mechanism, constraints, and
supporting infrastructure.

### Layering is opt-in alongside single-image

Both models coexist. `package.yaml` gains an optional `stack:` field.
Absent = today's single-image DDI (current contract unchanged). Present =
extension image layered on the declared base(s). Single-image remains the
default.

### Mechanism: `portablectl attach --extension` (not sysext)

Layering uses `portablectl attach --extension` (systemd v249+), which mounts
extension images as overlayfs layers on top of a base `RootImage=`. This is a
portable-services feature, **distinct** from `systemd-sysext` (host-level
extensions). The existing decision that sysext/confext is boxctl-only
(ADR-0023) remains valid for host-level extensions and is unaffected.

### Layer cap: 3 total

Hard cap of 3 images per attach: 1 base + up to 2 extensions (where the app
is the topmost extension). Allows base + language layer + app. Prevents
deep-stack abuse. Enforced at `buildctl validate` and `appctl install`. The
cap is configurable upward later if a real use case appears.

### `stack:` schema in package.yaml

A single ordered list. Position = layer position bottom-to-top; the package
itself is implicit at the top. Each entry is `{ name, sysext_level, version? }`.
The `name` + `sysext_level` of `stack[0]` (the root base) are baked into the
extension's `extension-release.d/extension-release.<name>` by buildctl.

### Version compatibility: SYSEXT_LEVEL matching

systemd enforces an exact string match on `ID=` + `SYSEXT_LEVEL=` between the
base's `os-release` and each extension's `extension-release.d/`. SYSEXT_LEVEL
is used as a **compatibility version** (like a SONAME), not a package version.
Bases sharing a `sysext_level` are mutually compatible at the ABI level;
bumping `sysext_level` signals a breaking change that requires extensions to
rebuild.

### All images must be signed

Already pinned by ADR-0004. Canonical policy: `root=signed:=absent`. For
layered mode, appctl writes the policy in two directives —
`RootImagePolicy=root=signed:=absent` and
`ExtensionImagePolicy=root=signed:=absent`. No fallback to unsigned verity on
any image class.

### systemd >= 254 for layered mode; >= 250 still works for single-image

Layered apps require systemd >= 254 for the split `RootImagePolicy=` and
`ExtensionImagePolicy=` directives. Single-image apps continue to work on
systemd >= 250 (current floor) via the older unified `ImagePolicy=` directive.
appctl detects the systemd version at install time and refuses a layered
install on < 254 with a clear error.

### Base images are built in a separate repository

A dedicated `offline-lab/base-images` repository (outside the monorepo)
houses the mkosi configurations for each base flavor. The pipeline is plain
mkosi — buildctl is not involved in base production. Initial flavors:
**debian, centos, alpine** as distro bases; **python, perl, ruby, golang** as
per-language extensions on each distro base. Grows as apps demand.

### Single source of truth — no drift between DDI and Docker image

Each base flavor is built **once** as a directory tree; mkosi then emits
multiple output formats from that same tree: `Format=portable` (runtime DDI),
`Format=oci` (build-time Docker image), and a metadata JSON. Both runtime and
build-time artifacts derive from one source, so drift is structurally
impossible.

### mkosi-in-Docker for macOS

The mkosi backend must work on macOS. A container image bundles mkosi plus
all distro bootstraps. buildctl detects the platform: on Linux it invokes
mkosi directly; on macOS it runs mkosi inside the container. Same backend,
two execution strategies. This removes the Linux-only constraint from the
mkosi backend without changing the user's `mkosi.conf`.

### Docker backend for layered apps (cross-platform)

The Docker backend handles layered builds via standard Docker multistage
Dockerfiles (`FROM <base-oci-image> AS build`, `FROM scratch` final stage
containing only the delta). Works on macOS via Docker Desktop. buildctl's
pipeline is unchanged for either mode — it wraps whatever filesystem tree the
backend produces.

### Two signing keys per repo (unchanged)

Bases use the same 2-key model as apps (ADR-0006): build key on the build
machine, index key on the repository host. One certificate in `verity.d/` per
repository covers every image the repo publishes (bases and apps). No
per-image or per-flavor keys. The base-images repository has its own keys,
just like any other publisher's repository.

### Separate subtrees/repos for bases and apps

Bases and apps are served from separate subtrees within a single repo, from
separate repos entirely, or from a meta-repo that points at both via absolute
URLs in `repository.json`. Each artifact class has its own per-arch index
(ADR-0008). The repo's root `repository.json` declares which classes are
served and where each lives.

Repository structure:

- Root: `repository.json` (discovery manifest) + `repository.json.p7s` + `keys/`.
- Per class: `<bases-url>/<arch>/index.json` and `<images-url>/<arch>/index.json`.
- URLs may be relative (default, same host) or absolute (meta-repo pattern,
  different hosts).

Each per-arch index carries a top-level `type` field (`"bases"` or `"apps"`)
so appctl can detect mismatches (e.g. an apps URL returning a bases index).
Old appctl that does not read `type` ignores it cleanly — on a bases-only
repo it sees no `packages` array and fails cleanly with "no packages found".

appctl stores the resolved per-class URLs at `repo add` time. Apps repos
behave exactly as today. Bases repos are not searchable via `appctl search`,
not listed via `appctl list`, and are only consulted when an installed layered
app needs a base that is not present locally.

**No credentials in URLs.** Auth is not supported in v1; if added later it
will be via environment variables or a transport wrapper, never via embedded
credentials.

### buildctl's role is unchanged

buildctl takes whatever filesystem tree a backend produces and wraps it as a
signed DDI. For layered apps, the backend produces a delta tree (the
extension's contents only). buildctl's only layered-specific work is
generating `extension-release.d/extension-release.<name>` from `stack[0]`
instead of `/etc/os-release`. buildctl does **not** resolve bases at build
time, download bases, or convert artifact formats — those are the backend's
job (Docker multistage or mkosi `BaseTrees=`+`Overlay=yes`) and appctl's job
(runtime resolution).

## Consequences

- Apps can ship as small deltas, sharing common bases across many apps.
- Single-image apps are completely unaffected; layered mode is purely opt-in.
- The mandatory-signing model applies uniformly to bases and extensions.
- Bases require their own production pipeline (mkosi, separate repo) and their
  own repository class/index.
- Layered mode raises the systemd floor to 254 on devices that use it.
- Cross-platform base building depends on a bundled mkosi container image.

## Alternatives considered

### Always-bundled single image (no layering)

Rejected as the only model. Wasteful for shared-base scenarios; layering is
kept opt-in precisely so this remains the default where it fits.

### `systemd-sysext` as the layering mechanism

Rejected. sysext extends `/usr/` at the host level and is admin-managed via
boxctl (ADR-0023); it is not the portable-services extension path.
`portablectl attach --extension` is the correct mechanism for layering app
images.

## References

- Related: ADR-0001 (DDI format), ADR-0004 (image policy), ADR-0006 (two
  signing keys), ADR-0008 (repository index), ADR-0023 (sysext is boxctl-only).
- Repository spec.
- Original discussion: internal (not published).
