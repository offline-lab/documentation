# Layered Images — Design

> **⚠ Amended (2026-07-05)** by the
> [2026-07-04 design session](../conversation/2026-07-04-design-session.md)
> and ADR-0031/0032/0034: the 3-layer cap and SYSEXT_LEVEL model are
> **affirmed**; UAPI.4 is now adopted verbatim (ADR-0034). Changed: buildctl's
> build/assembly role (ADR-0031 — no pure-Go pipeline, no `buildctl publish`),
> the appctl verb model (§9's install/update/remove flows → ADR-0032's
> get/up/down/rm/drop; `rehydrate` → `recover`), base lifecycle amendments
> (orphaned bases kept by default, bases not user-deletable while referenced),
> and terminology (repo → index, ADR-0033). **Further amended (2026-07-05,
> session §20): the intermediate language layer (§3.3 layer 1) is removed —
> the cap is 1 base + the app; language flavors (`debian-python`) are flat,
> complete bases.** Read with those on top.

**Status:** Approved design, pending implementation.
**Session:** 2026-06-18.
**Supersedes:** none. Extends [Package Format](../../docs/specs/package-format.md)
and [Security Model](../../docs/specs/security-model.md).

This document is the canonical reference for layered (extension) images.
Implementation tasks are tracked separately.

---

## 1. Goals

Allow apps to be packaged as small **extension** images that layer on top of a
shared **base** image via `portablectl attach --extension`, instead of every app
shipping a self-contained OS tree.

Benefits:

- Apps contain only what they add (binaries, configs, pip packages) — not libc,
  openssl, or the language runtime.
- One base image is stored once on a device, used by every layered app.
- App updates re-download only the small extension, not a full OS tree.
- Centralized security updates to the base propagate to every layered app
  without rebuilding each one.

## 2. Scope decision: opt-in alongside single-image

Both models coexist. `package.yaml` gains an optional `stack:` field. Absent =
today's single-image DDI (contract unchanged). Present = extension image built
against a named base.

Single-image remains the default and is fully supported in v1. Layered is
opt-in for packagers who want smaller images and can declare a base dependency.

## 3. Architecture

### 3.1 Three package types coexist in one repo

| Type | Has `stack:`? | Image contents | systemd attach |
|---|---|---|---|
| **single-image app** | No | os-release + unit + binary + deps | `portablectl attach <app>.raw` |
| **base** | n/a (is a base) | os-release with `SYSEXT_LEVEL=`, runtime libs, **no unit files** | never attached alone |
| **extension app** | Yes | `extension-release.d/` + unit + binary only | `portablectl attach --extension <app>.raw <base>.raw <prefix>` |

A base image is never run on its own — it has no service unit. It exists only
as the lower layer for extensions.

### 3.2 systemd's layering model

Verified from `portablectl.xml`, `systemd.exec.xml`, and the systemd
[Portable Services](https://systemd.io/PORTABLE_SERVICES/) doc:

- `portablectl attach --extension <ext> <base> <prefix>` (since v249)
- Extensions are matched against the **RootImage's** `os-release`, not against
  each other. Every extension's `extension-release.d/extension-release.<name>`
  must carry `ID=` + `SYSEXT_LEVEL=` matching the base.
- systemd mounts all extensions as overlayfs layers on top of `/usr/`, `/opt/`
  (sysext) and `/etc/` (confext). Order is bottom-to-top as listed.
- All images in the stack are independently signed DDIs with their own
  verity + signature partitions. systemd verifies each one.

systemd sees **one base + N extensions**. The conceptual chain
(`myservice` → needs `python` → needs `debian`) is our metadata concern,
resolved by appctl at install time, then flattened to a list of `--extension`
flags at attach time.

### 3.3 Layer cap: 3 total

Hard cap: a maximum of **3 images** per attach (1 base + up to 2 extensions,
where the app is the topmost extension). Enforced at `buildctl validate` and
`appctl install`.

| Layer | Role | Example |
|---|---|---|
| 0 (base) | distro runtime | `ol-base-debian` |
| 1 (extension) | language/runtime | `ol-base-debian-python` |
| 2 (extension) | the app | `myservice` |

Configurable upward later if a real use case appears. v1 ships with the cap to
set the cultural expectation and prevent abuse.

### 3.4 Version compatibility: SYSEXT_LEVEL matching

systemd enforces exact string match on `ID=` + `SYSEXT_LEVEL=` between the
base's `os-release` and each extension's `extension-release.d/extension-release.<name>`.
No semver ranges, no floating channels.

We use `SYSEXT_LEVEL` as a **compatibility version** (like a SONAME), not a
package version:

- `ol-base-debian_1.0.0`, `1.0.1`, `1.0.2` all declare `SYSEXT_LEVEL=1.0` —
  mutually compatible at the ABI level.
- `ol-base-debian_1.1.0` declares `SYSEXT_LEVEL=1.1` — breaking change;
  extensions must rebuild.

Extensions target a `SYSEXT_LEVEL`, not a specific base version. At install,
appctl finds any installed base matching `name` + `sysext_level`; if none, it
fetches the latest matching from the repo.

## 4. Schema changes

### 4.1 `package.yaml` gains `stack:`

Single ordered list, position = layer position, bottom-to-top. The package
itself is implicit at the top of the stack. Single-image apps omit the field.

```yaml
# Single-image app (today's model — unchanged)
spec_version: "1"
name: myservice
version: 1.0.0
arch: arm64
# ... no stack: field ...

# Extension app
spec_version: "1"
name: myservice
version: 1.0.0
arch: arm64
stack:
  - name: ol-base-debian          # required (root base)
    sysext_level: "1.0"
  - name: ol-base-debian-python   # optional (intermediate layer)
    sysext_level: "1.0"
# ... myservice is implicit at layer 3 ...
```

Validation rules (in `schemas/validate.go`):

- If `stack:` is absent → single-image mode. Tree must contain `/etc/os-release`.
- If `stack:` is present → extension mode. Tree must contain
  `/usr/lib/extension-release.d/extension-release.<name>` (generated by
  buildctl). Tree must NOT contain `/etc/os-release` for the app's identity
  (systemd reads `extension-release.d/` for extensions).
- `stack[0]` is the root base. Its `name` + `sysext_level` get baked into the
  extension's `extension-release.d/extension-release.<name>`.
- `len(stack) + 1 <= 3` (layer cap: the package itself counts as the top).
- Each entry requires `name` + `sysext_level`. Optional `version` field pins an
  exact base version (default: latest matching the sysext_level).

### 4.2 Metadata JSON gains `stack`

Mirrors `package.yaml`. Absent for single-image apps. Present (possibly empty
list for direct-on-base extensions) for extension apps.

```json
{
  "name": "myservice",
  "version": "1.0.0",
  "stack": [
    {"name": "ol-base-debian", "sysext_level": "1.0"},
    {"name": "ol-base-debian-python", "sysext_level": "1.0"}
  ]
}
```

### 4.3 Separate subtrees for bases and apps, unified discovery

Bases and apps live under separate subtrees (`bases/` and `images/`) within
a single repo, or as separate repos, or as a meta-repo that points at both
via absolute URLs. Each subtree has its own per-arch index. The repo's root
`repository.json` declares which artifact classes are served and where each
one lives.

**Repository structure** (see [Repository spec](../../docs/specs/repository.md)
for the full reference):

```
<repo-root>/
  repository.json                  ← manifest: declares bases/images URLs + keys[]
  repository.json.p7s              ← signature over manifest
  keys/
    signing-<key-id>.crt
    signing-<index-key-id>.crt
  bases/                           ← optional (omit if repo doesn't serve bases)
    <arch>/
      index.json                   ← type: "bases"
      index.json.p7s
      <name>/<version>/<files>
  images/                          ← optional (omit if repo doesn't serve apps)
    <arch>/
      index.json                   ← type: "apps"
      index.json.p7s
      <name>/<version>/<files>
```

Each per-arch index carries a top-level `type` field (`"bases"` or `"apps"`)
so appctl can detect class mismatches. Old appctl that doesn't read `type`
ignores it cleanly — on a bases-only repo it sees no `packages` array and
fails cleanly with "no packages found."

**`repository.json` example (full repo):**

```json
{
  "spec_version": "1",
  "name": "Offline Lab Packages",
  "bases":  "bases/",
  "images": "images/",
  "key_rotation": 0,
  "keys": [
    {"key_id": "...", "type": "build", "cert_url": "keys/signing-<id>.crt", "active": true},
    {"key_id": "...", "type": "index", "cert_url": "keys/signing-<id>.crt", "active": true}
  ]
}
```

**`bases` and `images` URLs** may be:

- Relative paths resolved against the repo root (default — same host).
- Absolute URLs pointing at different hosts (meta-repo pattern).

Either may be omitted/null if the repo hosts only one artifact class.

**appctl handling:**

- `appctl repo add <url>` fetches `<url>/repository.json`, reads the class URLs
  and `keys[]`, verifies the manifest signature, and stores everything in the
  repo's state record at `state/repos/<hash>.json`.
- Apps repos: behave exactly as today.
- Bases repos: not searchable via `appctl search`; bases aren't shown in
  `appctl list`; only consulted when an installed layered app needs a base
  that isn't present locally.
- `appctl repo list` shows which classes each configured repo serves.

## 5. Image policy

Already pinned in
[Security Model: Image policy](../../docs/specs/security-model.md#image-policy).
The canonical string `root=signed:=absent` applies to **every** image appctl
attaches — single-image, base, or extension. No fallback to unsigned verity.

For layered mode, appctl writes the policy in two directives in the drop-in:

```ini
RootImagePolicy=root=signed:=absent
ExtensionImagePolicy=root=signed:=absent
```

`RootImagePolicy=` applies to `RootImage=` (the base); `ExtensionImagePolicy=`
applies to every entry in `ExtensionImages=`. Both have the same string because
every DDI in our format is the same shape (root + root-verity + root-verity-sig
partitions).

**systemd version requirement:** layered mode requires systemd ≥ 254 for the
split policy directives. Single-image mode continues to work on systemd ≥ 250
with the older unified `ImagePolicy=` directive.

## 6. Build flows

### 6.1 buildctl's role is unchanged

buildctl takes whatever filesystem tree a backend produces and wraps it as a
signed DDI. For layered apps, the backend produces a **delta tree** (just the
files the extension adds on top of its declared base). buildctl's pipeline is
identical for single-image and extension apps:

1. Merge `rootfs/` skeleton.
2. Generate missing required files (single-image: os-release; extension:
   `extension-release.d/extension-release.<name>`).
3. Validate (mode-aware: os-release vs extension-release.d/).
4. chown 0:0.
5. Embed `package.yaml` at `/usr/share/<name>/package.yaml`.
6. squashfs → verity → sign → GPT.

buildctl does NOT resolve bases at build time, download bases, or convert
formats. The backend handles all of that. buildctl's only layered-specific work
is generating the `extension-release.d/` file from `stack[0]`.

### 6.2 Docker backend (cross-platform, including macOS)

Standard Docker multistage pattern. The user's Dockerfile references the
**OCI-published form** of the base image:

```dockerfile
FROM ghcr.io/offline-lab/ol-base-debian-python:1.0 AS build
COPY requirements.txt /tmp/
RUN pip install --target=/install -r /tmp/requirements.txt

FROM scratch
COPY --from=build /install/ /usr/lib/python3.11/site-packages/
COPY myservice.py /app/myservice.py
COPY myservice.service /usr/lib/systemd/system/
```

The final stage produces a filesystem tree containing only the delta. Docker
buildx exports it; buildctl wraps it as a DDI.

Works on macOS via Docker Desktop. The Linux VM inside Docker runs the actual
`pip install` against the base's Python interpreter, which is guaranteed to
match the runtime because the OCI image was derived from the same source tree
as the runtime DDI (see §7.3).

### 6.3 mkosi backend (Linux native + macOS via container)

On Linux, mkosi runs directly. The user's `mkosi.conf` uses mkosi's native
layering:

```ini
[Output]
Format=portable
Overlay=yes

[Content]
BaseTrees=/path/to/ol-base-debian_1.0_arm64
Packages=python3,python3-pip
```

mkosi mounts the base as overlayfs lower layer, runs the build scripts, and
emits a structurally-guaranteed delta. Output is a signed portable DDI directly.

On macOS, the mkosi backend runs mkosi inside a Docker container
(see §8). Same `mkosi.conf`, different execution shell.

### 6.4 shell and make backends

User's responsibility. buildctl wraps whatever tree the script produces. The
script must produce a delta tree if the package declares a `stack:`.

## 7. Base-images repository

### 7.1 Separate repo, multiple flavors

A new git repository `github.com/offline-lab/base-images` (NOT in the
offline-lab monorepo). Houses multiple mkosi-built base flavors:

```
base-images/
  mkosi.conf                     ← shared config (output dir, cache, keys)
  mkosi.images/
    debian-base/mkosi.conf       ← Format=directory, debootstrap+libc+openssl+...
    debian-python/mkosi.conf     ← Format=sysext, Overlay=yes, BaseTrees=%O/debian-base, +python3
    debian-ruby/mkosi.conf       ← Format=sysext, Overlay=yes, BaseTrees=%O/debian-base, +ruby
    debian-golang/mkosi.conf     ← Format=sysext, Overlay=yes, BaseTrees=%O/debian-base, +golang
    debian-perl/mkosi.conf       ← Format=sysext, Overlay=yes, BaseTrees=%O/debian-base, +perl
    centos-base/mkosi.conf
    centos-python/mkosi.conf
    alpine-base/mkosi.conf
    alpine-python/mkosi.conf
  keys/                          ← gitignored; build key + index key
  README.md
```

One `mkosi -f` builds the whole tree. Each sysext output is guaranteed to be a
delta of its declared base (mkosi's `Overlay=yes` produces only the diff via
overlayfs).

### 7.2 v1 flavor set

Proof-of-concept level. Each base flavor is a minimal debootstrap/dnf/apk +
libc + openssl + ca-certificates + libseccomp + libcap + bash. Per-language
extensions add the language runtime on top.

Distros: **debian, centos, alpine**.
Languages: **python, perl, ruby, golang** per distro (where the language is
packaged for that distro).

Grow as apps demand. Adding a flavor = adding a subdirectory.

### 7.3 Single source of truth (no drift)

Each base flavor publishes three artifacts from one source tree:

| Artifact | Purpose | mkosi output |
|---|---|---|
| `<name>_<ver>_<arch>.raw` | Runtime DDI for `portablectl attach --extension` | `Format=portable` (with verity+sig) |
| `<name>:<ver>` Docker image | Build-time use in app Dockerfiles | `Format=oci` + `docker load` |
| `<name>_<ver>_<arch>.json` | appctl metadata | generated by post-build script |

Both runtime and build-time artifacts derive from the same mkosi build tree —
**structurally impossible to drift**. The OCI image is just the squashfs
contents in a different wrapper. This is the answer to the dual-artifact
concern: there's no "second build" that could diverge; both formats are
emitted from one build.

### 7.4 Signing model

Identical to app packages (per
[Security Model](../../docs/specs/security-model.md)). The
base-images repo has its own build key + index key pair, just like any
publisher's repo. One cert in `/etc/verity.d/` covers every base and base
extension the repo publishes. No per-image keys.

This is the same model the project already uses; layering introduces no new
key management complexity.

### 7.5 Repo layout for published artifacts

Bases live in their own repo, separate from any apps repo. Two repos, two
indexes, two `repo add` calls on the device. See §4.3 for the index format.

The base-images git repo (T-LAYER-04) publishes artifacts via rsync to a
static-file repo URL, same as apps do today. The on-server layout:

```
<bases-repo-root>/
  index.json                    ← root index (keys + arch listing + type: "bases")
  keys/
    signing-<key-id>.crt        ← public build cert
    index-<key-id>.crt          ← public index cert
  packages/
    arm64/
      index.json                ← per-arch bases index (type: "bases")
      index.json.p7s
      ol-base-debian/
        1.0.2/
          ol-base-debian_1.0.2_arm64.raw
          ol-base-debian_1.0.2_arm64.json
          ol-base-debian_1.0.2_arm64.oci.tar
        1.0.1/
          ...
      ol-base-debian-python/
        1.0/
          ...
```

Mirrors the apps repo layout exactly. Same `buildctl publish` and
`buildctl index update` flow, just with `--repo-type=bases` (or detected from
the repo's existing root index).

**Hosting flexibility:** the two repos may be on the same static file server
under different paths (e.g. `https://packages.offline-lab.com/bases/` and
`https://packages.offline-lab.com/apps/`), on different subdomains
(`bases.offline-lab.com` vs `packages.offline-lab.com`), or on entirely
different services. appctl doesn't care; each is configured separately via
`appctl repo add`.

## 8. mkosi-in-Docker for macOS

The mkosi backend in buildctl must work on macOS as well as Linux. On macOS,
mkosi runs inside a Docker container that buildctl manages.

### 8.1 Container image

A new `Dockerfile.mkosi` lives in buildctl's repo at
`buildctl/docker/mkosi/Dockerfile`. Modern mkosi install (no `setup.py`):

- Base: `fedora:latest` (version-pinned in production).
- Install mkosi via `pipx install git+https://github.com/systemd/mkosi.git`.
- Install all distro bootstraps: `debootstrap`, `dnf`, `pacman`, `zypper`.
- Pre-bake distro keyrings (`debian-keyring`, `archlinux-keyring`, etc.) so
  users don't need network at build time.
- Include `systemd-repart`, `systemd-dissect`, `squashfs-tools`.

Published to `ghcr.io/offline-lab/mkosi:latest` plus version tags matching the
bundled mkosi release. A GitHub Actions workflow rebuilds on upstream mkosi
release.

### 8.2 Platform detection in the mkosi backend

```
runtime.GOOS == "linux"  →  invoke mkosi directly (current behavior)
runtime.GOOS != "linux"  →  invoke via: docker run --rm \
                                                 -v <source>:/work \
                                                 -v <output>:/out \
                                                 -v <cache>:/cache \
                                                 -v <keys>:/keys:ro \
                                                 ghcr.io/offline-lab/mkosi:<tag> \
                                                 mkosi ...
```

Path translation: buildctl rewrites `mkosi.conf` paths to the container's view
before invoking. Output is written to the mounted `/out` directory; buildctl
reads from the host-side equivalent.

### 8.3 Privileges

Modern mkosi (v16+) runs unprivileged inside containers via subuid/subgid
mapping, per the mkosi documentation. buildctl tries `--userns=keep-id` first;
if the requested output format requires loop devices (some `disk` modes), it
falls back to `--privileged`. The `portable` and `sysext` output formats we
care about do not require loop devices.

### 8.4 Auto-pull

buildctl checks for the mkosi image locally before invoking. If missing, it
runs `docker pull ghcr.io/offline-lab/mkosi:<tag>`. The tag is pinned in
buildctl's source for reproducibility; bumping the tag is a buildctl release.

## 9. Base lifecycle on device (appctl)

This section covers everything appctl does differently when an app declares a
`stack:`. Single-image appctl behavior (today's design) is unchanged.

### 9.1 Layered install flow

The canonical sequence for `appctl install <layered-app>`:

**Phase 1 — Resolve:**

1. Fetch metadata JSON for the app from the apps repo.
2. Read `stack` field. For each entry (root first, intermediates after):
   - Check `state/bases/<repo-hash>-<name>-<sysext-level>.json` for an installed
     base matching `name` + `sysext_level`.
   - If found: record its `image_uuid` for later drop-in generation.
   - If not found: this base must be downloaded (Phase 2).
3. Verify the resolved stack is within the layer cap: `len(stack) + 1 <= 3`.
4. Verify runtime compatibility: layered mode requires `runtime: portable` until
   T-LAYER-07 confirms nspawn support.
5. Verify systemd version ≥ 254. Reject on older versions with a clear error.

**Phase 2 — Download missing bases (skipped if `--no-download`):**

For each missing base, in stack order (root first):

6. Query every configured repo whose `repository.json` declares a `bases` class
   for entries matching `name` + `sysext_level`. See §9.2 for the disambiguation
   rule.
7. Download the base DDI + metadata JSON.
8. Verify the base's PKCS7 signature against the source repo's build cert
   (in `/etc/verity.d/`). Reject on failure.
9. Stage to `/var/lib/appctl/bases/<new-uuid>/`.
10. Write `state/images/<uuid>.json` (kind=base) and
    `state/bases/<repo-hash>-<name>-<level>.json`.

**Phase 3 — Download the app:**

11. Download the app's DDI + metadata JSON from the apps repo.
12. Verify signature against the apps repo's build cert.
13. Stage to `/var/lib/appctl/images/<new-uuid>/`.
14. Write `state/images/<uuid>.json` (kind=app).

**Phase 4 — Allocate identity:**

15. Allocate uid (reuse existing if reinstalling; otherwise `MAX(uid)+1` from
    6000).
16. Write sysusers snippet; call `systemd-sysusers`.
17. Create `/var/lib/appctl/apps/<hash>/<name>/{config,data}/`; chown to uid.
18. Seed config defaults from app's squashfs if first install.

**Phase 5 — Update base ref counts:**

For each base in the resolved stack:

19. Read `state/bases/<repo-hash>-<name>-<level>.json`. Append this package's ID
    (`<app-repo-hash>-<name>`) to `referenced_by`. Atomic write.

**Phase 6 — Attach:**

20. Generate the drop-in at
    `/etc/systemd/system.attached/<name>.service.d/99-appctl.conf` (see §10 for
    the layered drop-in shape).
21. Invoke:

    ```
    portablectl attach --extension <python-uuid>/<python.raw> \
                       --extension <app-uuid>/<app.raw> \
                       <base-uuid>/<base.raw> \
                       <prefix>
    ```

    systemd verifies each image's signature independently via `verity.d/`, then
    mounts the overlay.
22. Run `pre_start` hook if declared.
23. `systemctl enable --now <name>.service`.
24. Run `post_start` hook if declared.

**Phase 7 — Record state:**

25. Write `state/packages/<app-hash>-<name>.json` with the full record including
    the `stack` array referencing the resolved base UUIDs.

**Phase 8 — Lock file cleanup:**

26. Remove `state/locks/<operation-id>.json`.

### 9.2 Base source discovery

**Decision A (locked):** when a layered app needs a base not installed locally,
appctl searches **every configured repo whose `repository.json` declares a
`bases` class**. The operator does not configure "bases repos" separately — they
just add repos, and appctl uses whatever classes each repo serves.

**Disambiguation rule** (multiple repos carry the same base):

| Situation | Behavior |
|---|---|
| One repo carries the base | Use it. |
| Multiple repos carry it, different versions | Pick the highest semver. Tie-break by repo alias alphabetical. Log which was chosen. |
| Multiple repos carry it, same version | Pick alphabetically first repo alias. Log. |
| Operator wants a specific source | Run `appctl install-base --repo <alias> <name>` first to pre-stage from that source. |

**Failure mode** (no configured repo serves the needed base): exit code **1**
with:

```
error: myservice requires base 'ol-base-debian' (sysext_level=1.0), which is not installed.
       No configured repo serves this base. Add a repo that carries it:
         appctl repo add <url>
       Then re-run: appctl install myservice
```

### 9.3 Failure modes and pre-staging

**Decision B (locked):** `appctl install --no-download <layered-app>` resolves
the stack, checks what's locally staged, and reports missing artifacts without
downloading. Exit code **2** (distinct from "no source repo configured" which is
exit 1). Example output:

```
--no-download: 3 artifacts required, 2 missing locally.

  ✓ ol-base-debian 1.0.2 (installed)
  ✗ ol-base-debian-python 1.0 — available from repo 'offline-lab'
    pre-stage with: appctl install-base --repo offline-lab ol-base-debian-python
  ✗ myservice 1.0 — available from repo 'offline-lab'
    pre-stage with: appctl install --download-only --repo offline-lab myservice

Re-run after pre-staging: appctl install --no-download myservice
```

`appctl install --download-only <layered-app>` resolves + downloads the full
stack but does not attach. Used for pre-staging offline deployments.

### 9.4 Updates

**Decision C (locked):** `appctl update <app>` does NOT auto-update bases the app
depends on, even if newer base versions exist in any configured repo. Bases are
high-trust — an untested base bump can break every layered app on the device.

**Explicit base update:** `appctl update-base <name> [--version <ver>]` updates
a single base. Affects every app layered on it. Warns before proceeding:

```
$ appctl update-base ol-base-debian
This will update ol-base-debian from 1.0.2 to 1.0.3 (sysext_level=1.0).
3 apps depend on this base: myservice, anotherservice, thirdservice.
All three will be re-attached atomically with the new base.
Continue? [y/N]
```

**Atomic swap:** `portablectl reattach` (since v248) detaches and reattaches in
one operation; running services are not stopped during the swap. It takes the
same `--extension` flags as `attach`. appctl uses this for all layered updates
(not detach+attach):

```
portablectl reattach --extension <new-python.raw> --extension <new-app.raw> \
                     <new-base.raw> <prefix>
```

The whole stack swaps atomically. If `portablectl reattach` fails mid-operation,
systemd leaves the previous stack attached — no half-state.

**Three update scenarios:**

| What changed | What appctl does |
|---|---|
| Only the app (common case) | `portablectl reattach --extension <new-app> <base> <prefix>`. Bases untouched, no base re-download. App record's `active_image_uuid` updated; old moves to `previous_image_uuids`. |
| An intermediate layer (e.g. python) | `portablectl reattach --extension <new-python> --extension <app> <base> <prefix>`. Intermediate's base record updated. App record unchanged except the python `base_uuid` reference. |
| The base itself (rare; explicit) | `appctl update-base <name>`. For each app referencing this base: `portablectl reattach` with new base + same extensions. Atomic per app. Old base is not retained (bases don't support rollback). |

### 9.5 Rollback

**Decision D (locked):** `appctl rollback <name>` for a layered app rolls back
**only the app image**, not the bases. Bases stay at whatever version is currently
installed.

Reasoning:

- The base may have been updated since the previous app version was installed.
  Rolling back the base too would break other apps depending on the newer base.
- Bases are shared; apps are isolated. App-only rollback keeps the blast radius
  contained to the one app.

**Bases do not support rollback at all.** There is no `appctl rollback-base`
command. If a base update broke things, the operator must explicitly downgrade
via `appctl update-base --version <old> <name>`.

### 9.6 Explicit base management

**Decision E (locked):** the layered-mode CLI surface:

| Command | Purpose |
|---|---|
| `appctl install <layered-app>` | Resolves stack, auto-downloads missing bases, attaches |
| `appctl install --no-download <layered-app>` | Resolves, reports missing, downloads nothing (exit 2 if missing) |
| `appctl install --download-only <layered-app>` | Resolves + downloads, doesn't attach |
| `appctl install-base <name> [--version \| --sysext-level \| --repo]` | Explicit base pre-staging |
| `appctl remove-base <name> [--force]` | Ref-counted removal (errors unless `--force` if referenced) |
| `appctl update-base <name> [--version <ver>]` | Explicit base update (affects all layered apps; interactive confirm) |
| `appctl list-bases` | Show installed bases with version, sysext_level, ref count |
| `appctl deps <name>` (alias: `appctl tree <name>`) | Print resolved stack without installing |

`appctl install-base` semantics:

- Searches configured repos with a `bases` class.
- Errors if no configured repo carries the named base.
- Errors on ambiguity (multiple repos have it, no `--repo` given) — operator must
  disambiguate.
- The installed base has `referenced_by: []` until an app uses it.
- Does NOT attach the base to anything — bases are never attached alone.

`appctl remove-base` semantics:

- Errors if `referenced_by` is non-empty (base is in use).
- `--force`: also removes every app in `referenced_by` (cascading remove).
- Otherwise: removes the base record + image file.

### 9.7 Reference counting

Bases are stored at `/var/lib/appctl/bases/<uuid>/` (parallel to
`/var/lib/appctl/images/<uuid>/` for apps). A base's `state/bases/<...>.json`
record carries a `referenced_by` array — the source of truth for the ref count.

Rules:

- **On package install/update:** each `stack` entry's `base_uuid` must point to
  an existing base record. The package's ID is appended to that base's
  `referenced_by`.
- **On package remove:** the package's ID is removed from `referenced_by` on
  each base in its stack. Bases whose `referenced_by` becomes empty are kept
  cached (for fast reinstall) until explicit `appctl cleanup --bases` or
  `appctl remove-base <name>`.
- **On explicit `appctl remove-base <name>`:** errors if `referenced_by` is
  non-empty. Otherwise removes the base record and its image.

### 9.8 Multi-SYSEXT_LEVEL coexistence

Multiple base versions of the same flavor (e.g. `ol-base-debian` 1.0.x and
1.1.x) coexist on a device. Each gets its own `state/bases/<...>.json` record
(distinct `<sysext-level>` in the filename) and its own image UUID. appctl
attaches the base matching each app's declared `sysext_level`.

No global "current base" — each app gets the base its `stack:` declares.

### 9.9 Layered rehydrate

`restore-apps.service` runs `appctl rehydrate` at boot. For each package record
in `state/packages/`:

1. Read the record. If `stack` is null → single-image rehydrate (today's flow,
   unchanged).
2. If `stack` is non-null:
   - Verify each referenced base still exists at its recorded `image_uuid` path.
     If any base file is missing, fail loudly (corruption event requiring
     operator intervention — not silently fixed).
   - Regenerate the drop-in (paths in `/etc/systemd/system.attached/` were
     wiped by the overlay reset on OL OS).
   - Invoke `portablectl attach --extension ... <base> <prefix>` with the
     recorded UUIDs.

No base re-download at boot — bases are persistent on `/data`. If a base is
missing at boot, that's a corruption event, not something rehydrate silently
fixes.

## 10. Example drop-in (layered mode)

```ini
# /etc/systemd/system.attached/myservice.service.d/99-appctl.conf
[Service]
User=app6000
Group=app6000
RootImage=/var/lib/appctl/bases/<base-uuid>/ol-base-debian_1.0.2_arm64.raw
ExtensionImages=/var/lib/appctl/images/<python-uuid>/ol-base-debian-python_1.0_arm64.raw
ExtensionImages=/var/lib/appctl/images/<app-uuid>/myservice_1.0_arm64.raw
RootImagePolicy=root=signed:=absent
ExtensionImagePolicy=root=signed:=absent
BindPaths=/var/lib/appctl/apps/<hash>/myservice/config:/etc/myservice
BindPaths=/var/lib/appctl/apps/<hash>/myservice/data:/var/lib/myservice
```

Multiple `ExtensionImages=` lines = multiple `--extension` flags. Order is
bottom-to-top as listed.

## 11. systemd version requirements

| Mode | Minimum systemd | Why |
|---|---|---|
| Single-image app | ≥ 250 | userspace verity verification (current floor) |
| Layered app | **≥ 254** | `RootImagePolicy=` + `ExtensionImagePolicy=` directives |
| Atomic layered update | ≥ 248 (already met) | `portablectl reattach` (no policy split needed) |

appctl detects systemd version at install time and refuses layered install on
< 254 with a clear error. Single-image install continues to work on ≥ 250.

## 12. Migration phases

| Phase | What | Owner | Tasks |
|---|---|---|---|
| **A** | Specs + schema changes (docs only, no code) | plans/ | (this doc + decisions) |
| **B** | Base-images repo scaffold; first signed DDIs | new repo | T-LAYER-04 |
| **C** | mkosi-in-Docker container image | buildctl repo | T-LAYER-05 |
| **D** | schemas `stack:` field + validation | `schemas/` | T-LAYER-01, T-LAYER-03 |
| **E** | buildctl extension mode + mkosi macOS backend | buildctl | T-LAYER-02, T-LAYER-06 |
| **F** | Spike: end-to-end layered attach on test host | cross-team | T-LAYER-07 |
| **G** | Spec updates informed by spike | `docs/specs/` | T-LAYER-08 |
| **H** | appctl base lifecycle (auto-install, ref counting, reattach) | appctl | T-LAYER-09 (deferred) |
| **I** | First real layered app (mosquitto on ol-base-debian) | packages/ | T-LAYER-10 |

B, C, D are parallel and independent. E depends on D (and optionally C for the
mkosi macOS path). F depends on B + E. G depends on F. H is deferred until F
validates the design. I depends on H.

## 13. Open items (to resolve in the spike or subsequent sessions)

1. **OCI image publication path.** Confirm mkosi's `Format=oci` output loads
   cleanly into Docker via `docker load`, and that the resulting image is
   usable as a `FROM` target. Verify in T-LAYER-04 / T-LAYER-07.

2. **mkosi-in-Docker privileges on macOS Docker Desktop.** Verify that
   unprivileged mode (`--userns=keep-id`) works for `Format=portable` and
   `Format=sysext` outputs. If not, document the `--privileged` requirement
   explicitly. Verify in T-LAYER-05 / T-LAYER-06.

3. **nspawn path for layered apps.** The design assumes `portablectl
   --extension` works; it has not been verified whether `systemd-nspawn
   --image=<base> --extension=<app>` works the same way. Must be confirmed
   in T-LAYER-07 before deferring nspawn support.

4. **Path translation edge cases.** When mkosi runs in the container with
   mounted volumes, `BaseTrees=` paths in the user's `mkosi.conf` need to
   resolve inside the container. Decide whether buildctl rewrites the config
   or requires container-relative paths.

5. **Signing key for `Format=oci` vs `Format=portable`.** mkosi emits verity
   signatures for `portable` but Docker signatures for `oci`. Decide whether
   we care about Docker content trust for the OCI artifacts, or whether the
   runtime DDI's verity signature is sufficient (it is — Docker is just a
   build-time convenience).

6. **Index versioning.** ~~The repo index gains a `type` field; this is a
   schema change. Decide whether old appctl versions reject the new field or
   ignore it gracefully.~~ **RESOLVED 2026-06-18:** bases and apps live in
   separate repos with separate indexes (see §4.3). Each index carries a
   top-level `type` field defaulting to `"apps"`. Old appctl ignores the
   field; on a bases repo it sees no `packages` array and fails cleanly with
   "no packages found." No forward-compat problem.

7. **Layer cap enforcement point.** Enforced at `buildctl validate` (build
   time) and `appctl install` (install time). Decide whether to also enforce
   at the repo index level (`buildctl index` rejects stacks deeper than 3).

## 14. What does NOT change

- The DDI format itself (GPT + root/verity/verity-sig partitions).
- The signing model (PKCS7 over roothash, systemd userspace verification).
- The pure-Go pipeline constraint in buildctl.
- The dual portable/nspawn runtime modes.
- The FHS path conventions.
- The repo publish flow (rsync + SSH + index update).
- The per-app user allocation model.
- The 2-key signing model per repo (build key + index key).

Layering extends the model; it does not replace any existing decisions.

## 15. References

- [Portable Services — systemd docs](https://systemd.io/PORTABLE_SERVICES/) —
  authoritative description of `portablectl --extension` and the layering model.
- `man/portablectl.xml` (systemd source) — `--extension=PATH` flag, v249.
- `man/systemd.exec.xml` (systemd source) — `ExtensionImages=`, `RootImagePolicy=`,
  `ExtensionImagePolicy=` directives.
- `man/systemd.image-policy.xml` (systemd source) — policy string syntax.
- [Security Model: Image policy](../../docs/specs/security-model.md#image-policy) —
  canonical `root=signed:=absent` policy.
- [Decisions: Image policy enforcement](decisions.md#image-policy-enforcement) —
  decision record.
- [`man/mkosi.1.md`](https://github.com/systemd/mkosi/blob/main/mkosi/resources/man/mkosi.1.md) —
  `Format=portable`, `Format=sysext`, `Overlay=`, `BaseTrees=`.
- [A re-introduction to mkosi](https://0pointer.net/blog/a-re-introduction-to-mkosi-a-tool-for-generating-os-images.html) —
  multi-image sysext build walkthrough.

Implementation tasks are tracked separately.
