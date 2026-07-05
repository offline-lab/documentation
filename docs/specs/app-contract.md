# The App Contract

**Status:** draft (2026-07-05), distilled from the
[2026-07-04 design session](https://github.com/offline-lab/documentation/blob/main/decisions/conversation/2026-07-04-design-session.md)
and ADR-0030…0036. This is **contract #1** of the ecosystem: what makes a disk
image an *app*. Contract #2 (the index) is specified separately. Tools —
buildctl, appctl, or anyone else's — are replaceable implementations of these
contracts; conformance is what matters, not the tool.

The container format itself is [UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/)
(see [Package format](package-format.md) for wire-format detail). This page
defines the layer above: the conventions and declarations that make a DDI
runnable, opinionated, and trustable with a single command on any systemd
host (≥ 250 with OpenSSL; ≥ 254 for layered apps).

---

## The five questions

An app is a signed DDI that answers five questions **on its own**, so the
runtime never guesses:

| # | Question | Mandatory |
|---|---|---|
| 1 | **Who am I?** — identity | yes |
| 2 | **Can you trust me?** — authenticity | yes |
| 3 | **How do I run?** — the run intent | yes |
| 4 | **What must survive me?** — persistent state | yes (even if "nothing") |
| 5 | **Do I stand on anything?** — lineage | no (absent = fat app) |

---

## 1. Identity

- **`name`** — lowercase, stable, unique within its index; used for the
  service unit, storage paths, and all lifecycle verbs.
- **`version`** — [UAPI.10](https://uapi-group.org/specifications/specs/version_format_specification/)
  format (`~` pre-release, `^` post-release). Not semver. "Latest" is always
  the UAPI.10 maximum.
- **`arch`** — an open, pattern-validated string (the officially supported
  set is documented separately; anyone who can build for an arch may ship it).
- **Artifact naming:** `<name>_<version>_<arch>.raw` — **one file**
  (ADR-0038); the DDI metadata is the embedded manifest, there is no
  standalone metadata file. `version` is the **DDI version the developer
  assigns** — the version of the software inside is deliberately untracked
  (downgrading the inner software still bumps the DDI version).
- **In-image identity:**
  - *Fat app:* `/etc/os-release` with `ID=<name>`, `VERSION_ID=<version>`.
  - *Layered app:* **no** `/etc/os-release`; identity lives in
    `/usr/lib/extension-release.d/extension-release.<name>` as
    `SYSEXT_ID=<name>`, `SYSEXT_VERSION_ID=<version>` (UAPI.4).
- **Embedded manifest:** the manifest is embedded at
  `/usr/share/<name>/package.yaml` (ADR-0017), so the image carries its own
  identity without the sidecar.

## 2. Trust

- Every app is a **signed** UAPI.3 DDI: root + verity + verity-sig
  partitions. Signing happens inside `build`; **unsigned images do not exist**
  (ADR-0031).
- The build signature travels *inside* the image, forever, independent of
  which index carries it — this is what enables the two-signature model
  (built with the developer's key, published under any index holder's key;
  ADR-0033).
- Verification is systemd's, not the tools': the **up-gate** re-verifies the
  signature at *every start* via the host trust store. Download integrity at
  the **get-gate** comes from the index entry's SHA-256 (projected at
  `index add`, ADR-0038). Trust rides the build signature, never the index
  signature (ADR-0037).

## 3. Run intent

This is the gap systemd leaves: `portablectl attach` only makes units
*available*. The app must declare what "up" means.

- **Activation:** `up` enables + starts `<name>.service` (or
  `<name>.socket` when `socket_activation: true`); `down` stops it.
- **Lifecycle hook stages** (`lifecycle:` block, ADR-0016 as amended;
  session §18): each stage is an **ordered list of unit files** inside the
  image, referenced from `package.yaml` and started by the runtime (they are
  not started by portablectl/nspawn). Stages: `pre_start` / `post_start`
  fire on **every `up`**; `pre_stop` / `post_stop` on every `down`;
  `pre_drop` before teardown; upgrade stages are defined with the upgrade
  design (T103). Use them for provisioning and side work with systemd's
  error handling instead of bash: copy files, run migrations, chown a
  socket, start side software from the same image (a worker beside a
  webservice) — as many jobs per stage as the developer needs.
- **Idempotency is the unit's business:** hooks fire every time their stage
  fires; one-time behavior comes from the unit's own guard
  (`ConditionPathExists=` etc.). `recover` therefore replays hooks like a
  normal `up`, safely. A failing pre-stage hook **aborts the verb loudly**;
  `--force` skips.
- **Systemd-wired oneshots** inside the image (`Before=<name>.service` +
  condition guard) remain available and preferred for pure ordering
  concerns that need no runtime involvement.
- **Runtime mode:** `portable` (default — light, host-integrated) or
  `nspawn` (isolated). **Developer-declared, baked into the app, travels with
  the image**; not an operator toggle (ADR-0030/0011).
- **`command` fallback:** if the image ships no unit and the manifest sets
  `command`, the build tool generates a minimal service unit. A shipped unit
  always wins; if neither exists, the build fails — an app must be runnable.
- **Placement is not the app's business.** Shipped units MUST NOT contain
  `User=`/`Group=` (ADR-0015) and MUST NOT declare host-path mounts
  (`BindPaths=` etc. to host locations). The runtime's generated drop-in owns
  placement: user, storage binds, `PrivateTmp=`, image policy, runtime mode.
  *The image ships intent; the host ships placement* (ADR-0036).

## 4. State

The inside-the-image view is [UAPI.9](https://uapi-group.org/specifications/specs/linux_file_system_hierarchy/);
the host side is ADR-0035 (`<root>/apps/<index-hash>/<name>/{config,data}`,
relocatable root, fixed structure).

| In-image path | Meaning | Backed by (host) |
|---|---|---|
| `/etc/<name>/` | operator-editable config | `…/<name>/config` |
| `/var/lib/<name>/` | private persistent data | `…/<name>/data` |
| `/tmp` | private, ephemeral | `PrivateTmp=` |
| `/var/cache/…` | flushable; never persisted | — |
| logs | stdout/stderr → journald | — |

- The mounts are **per-unit namespace bind mounts** — nothing writes to any
  host or image `/etc`. Because a mount point cannot be created on a
  read-only squashfs at runtime, **the image MUST ship the empty mount-point
  directories** `/etc/<name>/` and `/var/lib/<name>/` (the build tool creates
  them).
- **Factory defaults:** an app ships pristine default config at
  `/usr/share/factory/etc/<name>/` (UAPI.9); the runtime seeds the config
  volume from it on first provision. Apps SHOULD tolerate an empty config dir
  (safe fallbacks) and SHOULD support econf-style drop-in overrides
  (recommended, not required).
- Exactly **two persistent targets** — no freeform volumes (ADR-0013).
- The runtime promises: data survives `down` and `rm`; only the guarded
  `drop` destroys it; the same uid+gid on every start, so the app never needs
  to chown its data (ADR-0032/0036).

## 5. Lineage

- **Fat app** (no declaration): self-contained, carries its own userland.
  Larger, zero dependencies. The explicit opt-out.
- **Layered app:** a [UAPI.4](https://uapi-group.org/specifications/specs/extension_image/)
  sysext that declares the base it stands on **by identity, not by content
  hash**: base `name` + `SYSEXT_LEVEL` (the base publisher's ABI promise).
  Exact-match fields per UAPI.4: `ID=` (the base's — never `_any`),
  `SYSEXT_LEVEL=`, `ARCHITECTURE=`; plus `SYSEXT_SCOPE=portable`. The build
  tool generates the `extension-release.d/` file from the declaration.
- **Max 2 layers:** one distro base + the app (amended 2026-07-05, session
  §20 — the language/runtime layer was removed). Language variety is **flat
  base flavors**: `debian-python` is a complete base (distro *plus*
  interpreter), not a layer. No base-on-base stacking.
- **Additivity gate:** the app layer must be purely additive over its base —
  at build, the app's file list is intersected with the base's; **any
  overlap is a build error** (turns UAPI.4's unenforced "extensions should
  be additive" into a hard conformance rule).
- Level-match is binding — a compatible base update is picked up on the next
  `down`+`up` without rebuilding the app. The exact base built against MAY be
  recorded as **audit metadata**; it never gates the runtime.
- Base images have their own spec (T96); a base vouches for itself with its
  own signature — an app never vouches for base content.

---

## The manifest

`package.yaml` in the project root, embedded into the image at build. The
**floor is four lines** — everything else has defaults or is opt-in:

```yaml
name: hello
version: "1.0.0"
arch: arm64
command: /usr/bin/hello.sh    # or omit, if the image ships its own unit
```

| Field | Required | Default / notes |
|---|---|---|
| `name`, `version`, `arch` | yes | — |
| `command` | if no unit shipped | generates `<name>.service` |
| `runtime` | no | `portable` |
| `socket_activation` | no | `false`; when true, `up` starts `<name>.socket` |
| `lifecycle` | no | hook stages, each an **ordered list** of unit names existing inside the image (ADR-0016 as amended): `pre_start`, `post_start` (every `up`), `pre_stop`, `post_stop` (every `down`), `pre_drop`; upgrade stages per T103; block present only when hooks exist |
| `base` | no | absent = fat app; the base declaration (`name` + `sysext_level`). *(`stack:` is reserved for the future compose feature, T53)* |
| `expose`, `devices`, `resources` | no | **definition pending (T101)** — declared metadata for ports, `/dev` access, and resource estimates |
| `backend` | build-time | or `--backend`; never guessed (ADR-0031) |
| `description`, `publisher`, `publisher_url`, `license`, `homepage`, `source_url`, `maintainer`, `security_contact`, `sbom_url` | no | catalog fields — **enforced at `index add`, not at build** (curation hygiene is the index holder's standard). No `tags`, no `category` (both killed — §21/§24) |

Exact schema (types, patterns, remaining fields such as ports/devices/
resources) is defined by the JSON schemas (T95), which implement this
contract.

---

## Conformance

A conformant builder validates (and a conformant runtime re-checks at `up`):

1. Signed DDI, correct partition roles (UAPI.3).
2. Identity files correct for the mode (os-release **xor** extension-release).
3. All files `root:root` (ADR-0014).
4. No `User=`/`Group=` in any shipped unit (ADR-0015).
5. No host-path mounts in any shipped unit (ADR-0036).
6. `<name>.service` exists in the image; `<name>.socket` exists iff
   `socket_activation`; every unit declared in `lifecycle:` exists.
7. Mount-point dirs `/etc/<name>/` and `/var/lib/<name>/` exist.
8. Embedded manifest present and matching the image identity.
9. Layered mode: exactly one base (2 layers total), extension-release
   fields exact, app layer additive over the base (no file overlap).

## What the runtime promises in return

One command up (`up` = attach + wire + start), one command down. No implicit
network (only `get`). No implicit data loss. Apps cannot read each other's
data; an app cannot mount another app's data; same uid every start; signature
verified at every start; private `/tmp`. (ADR-0032/0035/0036.)

---

## Resolved drafting decisions (2026-07-05)

- **No activation-list field.** Activation is `<name>.service` /
  `<name>.socket`. Additional execution comes from the redesigned lifecycle
  hook stages (ordered unit lists, session §18) and systemd-wired oneshots.
  The lineage field is **`base:`** (`stack:` is reserved for the future
  compose feature, T53). Env-var details and the full stage semantics land
  in the lifecycle-spec rewrite (T98); upgrade stages in T103.
- **`expose`/`devices`/`resources` stay in the contract** — device access
  and port declarations are core to the ecosystem — but their definitions
  (device-class → `/dev` mapping, expose semantics vs the OS-side firewall)
  are scheduled as **T101** (revives Q-A4). The schema (T95) blocks on T101
  for these fields only.
- **YAML only.** `package.json` is dropped: JSON is comment-hostile, and JSON
  is syntactically valid YAML anyway — write JSON *in* `package.yaml` if you
  must.
