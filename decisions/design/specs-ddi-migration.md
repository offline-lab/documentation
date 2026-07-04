# Spec Migration Guide: 5-File Format to UAPI DDI

> **Historical (2026-07-05):** this migration was executed. A second sweep
> (repo→index terminology, verb model, UAPI.4/.10 adoption) followed the
> [2026-07-04 design session](../conversation/2026-07-04-design-session.md) —
> see ADR-0030…0036.

This document specifies the exact changes required to migrate the Offline Lab
specification and schema corpus from the custom 5-file package format to the
UAPI DDI (Discoverable Disk Image) standard. It is a **migration guide**, not a
rewrite of the specs. Each section tells an editor exactly what to remove, add,
and modify in a given file.

**Source of truth for the new design:**
[design session 2026-06-15](../conversation/2026-06-15-design-session.md) (authoritative
record of the design session that produced this migration).

**Scope:** All files under
`../../docs/specs/` and `../../docs/schemas/`, plus
cross-referenced files that need path/format updates for consistency.

**Ordering convention used below:**
- **REMOVE** — content to delete outright
- **ADD** — content to insert (new sections, fields, paths)
- **MODIFY** — content that stays but needs rewriting in place

---

## 1. Overview of What Changed

### 1.1 The seven decision areas

| # | Decision | Old state | New state |
|---|---|---|---|
| 1 | Package format | 5 custom files (squashfs + `.roothash` + `.roothash.p7s` + `.verity` + `.json`) | DDI (single `.raw` with GPT: root + verity + signature partitions) + separate `.json` metadata |
| 2 | Naming separator | Hyphen: `name-version-arch.ext` | Underscore: `name_version_arch.ext` (per UAPI spec) |
| 3 | Runtime verification | Custom PKCS7 verify in appctl; certs in `/data/config/keys/` | systemd native userspace verify via `/etc/verity.d/*.crt` |
| 4 | dm-verity setup | Custom (`losetup` + `veritysetup`) | Native (`systemd-dissect` handles internally) |
| 5 | Storage paths | All under `/data/...` (OL OS-specific) | Standard FHS paths; OL OS bind-mounts `/data/` underneath |
| 6 | Runtime modes | Portable services only | Dual mode: `portable` (default) or `nspawn`; declared in `package.yaml` |
| 7 | Build backends | Docker primary, others deferred | Auto-detect Docker / mkosi / shell / make; mkosi first-class from start |

### 1.2 Path migration table

Apply this table globally to every file in scope. Every occurrence of a
left-hand path must be replaced with the right-hand path, regardless of file.

| Old path | New path | Notes |
|---|---|---|
| `/data/offline-lab/packages.db` | `/var/lib/appctl/packages.db` | appctl state DB |
| `/data/offline-lab/images/<uuid>/` | `/var/lib/appctl/images/<uuid>/` | staged DDI images |
| `/data/apps/<hash>/<name>/` | `/var/lib/appctl/apps/<hash>/<name>/` | per-app storage |
| `/data/config/keys/` | `/etc/verity.d/` | signing cert store (systemd native) |
| `/data/config/keys/<repo-hash>-<key-id>.crt` | `/etc/verity.d/<repo-name>-<key-id>.crt` | individual build cert |
| `/data/config/sysusers.d/` | `/etc/sysusers.d/` (or direct `systemd-sysusers` call) | per-app user snippets |
| `/data/config/resources.json` | `/var/lib/appctl/resources.json` | resource budget state |
| `/data/config/appctl.conf` | `/etc/appctl/appctl.conf` | appctl configuration |
| `/data/config/system/machine-id` | `/etc/machine-id` (bind-mounted from `/data/` on OL OS) | machine identity |

**OL OS binding note (add wherever the old `/data/config/keys/` discussion
lived):** On Offline Lab OS the standard FHS paths are bind-mounted from
persistent `/data/` storage at boot, because `/etc` is ephemeral (overlay upper
wiped each boot). On any other systemd host these paths work natively. The
complexity lives in the OS layer, not in appctl.

### 1.3 Component fate table

This is the master reference for what the migration eliminates, simplifies, and
keeps. Every spec change below traces back to one of these rows.

**Eliminated**

| Component | Reason |
|---|---|
| 5-file package format | Replaced by DDI (UAPI.3) |
| Custom PKCS7 verification code path in appctl | systemd does it natively via `verity.d/` |
| Custom dm-verity setup (`losetup` + `veritysetup`) | `systemd-dissect` handles loop + verity internally |
| Companion file naming convention (`.roothash`, `.roothash.p7s`, `.verity`) | Everything lives inside the DDI |
| `/data/config/keys/` cert storage | Replaced by standard `/etc/verity.d/` |
| All `/data/` hardcoded paths in tool-facing specs | Replaced by FHS paths |

**Simplified**

| Component | Before | After |
|---|---|---|
| `appctl install` step count | 16 steps incl. manual verity setup | ~9 steps; verity collapses to one `portablectl attach` |
| PKCS7 usage in appctl | Sign and verify across both tools | Verify removed; only buildctl signs (build-time) |
| Custom verity library in appctl | Required at runtime | Not required; systemd handles verity |

**Kept (unchanged in concept)**

| Component | Notes |
|---|---|
| Pure-Go squashfs in buildctl | Creates the root partition filesystem |
| Pure-Go dm-verity computation in buildctl | Creates the verity partition |
| Pure-Go PKCS7 signing in buildctl | Creates the signature partition content |
| Per-app uid allocation | appctl-owned; portable mode only (nspawn uses namespace isolation) |
| Storage namespacing under `/var/lib/appctl/apps/<hash>/<name>/` | Path changed, concept unchanged |
| Lifecycle hooks (pre/post start/update/remove) | Unchanged |
| Resource checks | Path to budget file changed; logic unchanged |
| Drop-in generation for portable mode | `User=`, `Group=`, `BindPaths=`, `RootImage=` |
| Repo model (signed index, per-arch, offline-capable) | Full model from start |
| 2-key signing model (build key + index key) | Build key signs DDI signature partition; index key signs `index.json.p7s` |

---

## 2. Spec File Changes

### 2.1 `package-format.md`

Currently defines the 5-file package set, companion-file naming convention, and
zip transport. This file is the most heavily rewritten.

**REMOVE:**

| Content | Reason |
|---|---|
| The 5-file inventory block (squashfs, `.roothash`, `.roothash.p7s`, `.verity`, `.json`) | Replaced by DDI |
| Any statement that systemd discovers companion files "by name convention" | No longer companion files; partitions inside GPT |
| The `.roothash.p7s`-as-separate-file rationale | File no longer exists |
| References to `.squashfs.verity` (hash tree sidecar) | Hash tree now lives in the verity partition |
| Any path under `/data/` | See path migration table |

**ADD:**

| Content | Notes |
|---|---|
| DDI format definition: a GPT partition table containing three partitions | Root (squashfs), Verity (superblock + hash tree), Signature (JSON) |
| Partition type UUID references | Cite UAPI.2 (DPS) for arch-specific type UUIDs of root, verity, verity-sig partitions |
| Partition UUID encoding rule | Root partition UUID = first 128 bits of root hash; Verity partition UUID = last 128 bits |
| Signature partition JSON schema | `{"rootHash": "<hex>", "signature": "<base64 PKCS7>", "certificateFingerprint": "<sha256 hex>"}` |
| Naming convention | `<name>_<version>_<arch>.raw` + `<name>_<version>_<arch>.json` (underscore separator per UAPI.3) |
| Transport | Both files in a single zip |
| UAPI standards reference table | UAPI.2 (DPS), UAPI.3 (DDI), UAPI.11 (VOA, future); link to design session §9 |
| Statement that the squashfs content constraints (root:root ownership, `/etc/os-release`, service unit placement, `/usr/share/<name>/package.yaml`) still apply to the root partition | The DDI does not change the filesystem contents — only the wrapper |

**MODIFY:**

| Content | Change |
|---|---|
| All filename examples | Hyphen → underscore separator (e.g. `mosquitto-2.0.18-arm64.squashfs` → `mosquitto_2.0.18_arm64.raw`) |
| Any sentence stating appctl extracts 5 files to a UUID dir | Reword: appctl extracts the DDI + metadata JSON; DDI is staged as a single `.raw` file |
| Squashfs content spec section | Keep, but preface with "the DDI root partition contains a squashfs filesystem; the following constraints apply to that filesystem" |

---

### 2.2 `build.md`

Currently defines the build pipeline, backends, and convergence point. Needs
substantial updates for DDI output, the skeleton feature, and auto-generated
files.

**REMOVE:**

| Content | Reason |
|---|---|
| Backend-by-backend shell-out examples that produce 5 files | Output is now a single DDI |
| mkosi deferral language (if present) | mkosi is first-class from v1 |
| Any companion-file generation step in the pipeline diagram | Companion files no longer exist |

**ADD:**

| Content | Notes |
|---|---|
| Auto-detection of backend from project directory contents | No `--backend` flag; detect Dockerfile / mkosi.conf / build.sh / Makefile |
| mkosi as first-class backend from v1 | Cite design session §2.4 |
| Convergence-point diagram (updated) | All backends produce a rootfs directory; everything after is backend-agnostic. Use the diagram from design session §7 |
| Skeleton `rootfs/` merge step | Optional `rootfs/` directory merged into backend output **after** the backend runs; skeleton files override backend output |
| Auto-generated required files table | From design session §7: `/etc/os-release` (from name+version, generated if missing), service unit (from `command` field, generated if missing and `command` set), `package.yaml` embed (always) |
| Precedence rule for service unit | Developer-provided unit (in `rootfs/` or backend output) takes precedence; `command` ignored when unit present |
| DDI creation pipeline steps | After validation + chown + embed: (1) create squashfs (pure Go), (2) compute dm-verity hash tree + roothash (pure Go), (3) sign roothash with PKCS7 (pure Go, `go.mozilla.org/pkcs7`), (4) create DDI via `github.com/diskfs/go-diskfs` (GPT with 3 partitions, partition UUIDs from roothash halves, signature partition JSON), (5) emit `<name>_<version>_<arch>.raw` + `.json` |
| Pure-Go library list | `go-diskfs` (GPT/DDI), `KarpefsLab/squashfs` (squashfs read/write), `go.mozilla.org/pkcs7` (PKCS7 sign), custom ~200-line verity implementation |
| macOS requirement statement | Reaffirm: any Linux-only tool is forbidden from the core pipeline |

**MODIFY:**

| Content | Change |
|---|---|
| Output filenames in any example | 5-file set → `name_version_arch.raw` + `name_version_arch.json` |
| Validation step description | Still validates os-release matches, service unit exists, no `User=`/`Group=` in unit; add: validates DDI partition layout after creation |
| Build backend list | Docker / mkosi / shell / make (all in v1, no phasing) |

---

### 2.3 `security-model.md`

Currently defines the trust model, signing, and verification. The signing model
shifts from "appctl verifies at runtime" to "systemd verifies natively;
appctl only stages the cert".

**REMOVE:**

| Content | Reason |
|---|---|
| Description of custom PKCS7 verification code in appctl | Eliminated |
| Description of `/data/config/keys/` as the cert store | Replaced by `/etc/verity.d/` |
| Any description of manual `losetup` / `veritysetup` orchestration | systemd-dissect handles |
| The kernel-keyring discussion as an **open** problem | It is resolved (userspace verify is the permanent answer, now provided by systemd itself, not custom Go code) |

**ADD:**

| Content | Notes |
|---|---|
| Threat table from design session §2.3 | MITM (PKCS7 on roothash), malicious repo (2-key model), corruption (dm-verity), at-rest tamper (kernel dm-verity), physical access (not protected on Pi), root compromise (not protected) |
| Honest-boundary statement | Crypto secures the distribution path (build → repo → download → install). Cannot secure the device on Pi hardware. On x86 with UEFI Secure Boot + TPM, the full chain becomes enforceable |
| Why dm-verity stays despite Pi limitations | Platform expanding to x86 and standard ARM64 where Secure Boot is available; PKCS7 + roothash verify at install works on all hardware |
| systemd userspace verification flow (design session §3.3) | Cite `src/shared/dissect-image.c` lines 3080-3256; describe the kernel-first-then-userspace-fallback sequence |
| `/etc/verity.d/` hierarchy | `/etc/verity.d/` (admin override, highest), `/run/verity.d/` (runtime), `/usr/local/lib/verity.d/` (local vendor), `/usr/lib/verity.d/` (distro, lowest). Masking via symlink to `/dev/null` is supported |
| Signature partition JSON format reference | Pointer to `package-format.md` |
| Build-time-only PKCS7 statement | buildctl still uses `go.mozilla.org/pkcs7` to sign the roothash into the signature partition; this is build-time only, on the developer machine. No verification code at runtime |

**MODIFY:**

| Content | Change |
|---|---|
| Signing model section title and framing | From "userspace verification via go.mozilla.org/pkcs7 in appctl" to "systemd native userspace verification via `/etc/verity.d/`" |
| The "permanent design decision" statement | Keep the permanence, but change the mechanism: verification is userspace (correct), but performed by systemd using `verity.d/` certs — not by custom appctl Go code |
| Cert import flow at `appctl repo add` | Cert stored at `/etc/verity.d/<repo-name>-<key-id>.crt` (was `/data/config/keys/<repo-hash>-<key-id>.crt`) |
| 2-key signing model section | Build key still signs per-package — but now the signature goes into the DDI signature partition, not a `.roothash.p7s` companion file. Index key unchanged |

---

### 2.4 `repository.md`

Currently defines the repo index format, signing, and publish flow. Mostly
unchanged in structure; updates are around file references and cert storage
location.

**REMOVE:**

| Content | Reason |
|---|---|
| Package-entry examples referencing the 5-file set | Output is now 2 files |
| Any reference to `/data/config/keys/` as the on-device cert destination | Replaced by `/etc/verity.d/` |

**ADD:**

| Content | Notes |
|---|---|
| Statement that the full repo model is in-scope for v1 (no phasing) | Cite design session §11.2 |
| Package layout on repo: `packages/<arch>/<name>/<version>/<name>_<version>_<arch>.raw` + `.json` | Mirror the path scheme in design session §12 |
| `keys/signing-<key-id>.crt` publish target | Build cert is published here at repo bootstrap |
| Same-server rule (already in the decision records) | Reaffirm: appctl rejects any `zip_url` or `metadata_url` resolving to a different origin than `base_url` |
| `appctl repo add` flow updated | Fetches root `index.json` + `index.json.p7s`, verifies index signature (TOFU), fetches build cert from `keys/signing-<key-id>.crt`, stores at `/etc/verity.d/<repo-name>-<key-id>.crt`, fetches per-arch index, caches entries in `packages.db` |

**MODIFY:**

| Content | Change |
|---|---|
| Per-arch package entry file references | `.zip` of 5 files → `.zip` of 2 files (`.raw` + `.json`); or split `zip_url` + `metadata_url` references updated to point at the new filenames |
| Key rotation section | `signing_key_id` still in metadata JSON; cert path changes from `/data/config/keys/<repo-hash>-<key-id>.crt` to `/etc/verity.d/<repo-name>-<key-id>.crt` |
| Two-step publish description | Still `rsync` + SSH + `buildctl index update`; output filenames in the rsync example change to `.raw` + `.json` |

---

### 2.5 `user-allocation.md`

Currently defines per-app uid allocation via sysusers. The mechanism is
unchanged; the path and the runtime-mode dependency are new.

**REMOVE:**

| Content | Reason |
|---|---|
| `/data/config/sysusers.d/` as the snippet persistence path | Replaced by `/etc/sysusers.d/` or direct `systemd-sysusers` invocation |
| Any claim that uid allocation applies to all apps | Only portable mode; nspawn uses namespace isolation |

**ADD:**

| Content | Notes |
|---|---|
| Runtime-mode scoping | Per-app uid allocation applies **only to portable mode**. nspawn mode does not allocate a uid; isolation is via PID/mount/network namespace, and the user inside the container is root |
| `/etc/sysusers.d/` path resolution for OL OS | Either bind-mount `/etc/sysusers.d/` from persistent `/data/` storage, or have appctl call `systemd-sysusers` directly during rehydrate. The rehydrate call is idempotent — on a normal distro it is a harmless no-op |
| sysusers snippet format | Unchanged: `u app<uid> <uid>:"<gid>" - -` (or whatever exact syntax the current spec uses); only the destination directory changes |

**MODIFY:**

| Content | Change |
|---|---|
| All `/data/config/sysusers.d/` references | `/etc/sysusers.d/` (with the OL OS bind-mount caveat) |
| systemd-homed rejection rationale | Keep; still correct |
| "Reinstalling the same app reuses its original UID" rule | Keep; unchanged |

---

### 2.6 `resource-tracking.md`

Currently defines resource checks and the budget file. Mostly path updates.

**REMOVE:** None structurally.

**ADD:**

| Content | Notes |
|---|---|
| Note that DDI image size on disk differs from the old 5-file set | A single `.raw` plus verity partition is larger than the bare squashfs was; resource budget math should account for DDI overhead (hash tree, GPT, partition alignment) |

**MODIFY:**

| Content | Change |
|---|---|
| All `/data/config/resources.json` references | `/var/lib/appctl/resources.json` |
| Storage path references in available-storage math | Per-app storage is under `/var/lib/appctl/apps/<hash>/<name>/`; image staging is under `/var/lib/appctl/images/<uuid>/` |

---

### 2.7 `reboot-proofing.md`

Currently defines rehydration and the overlay-reset model. The rehydrate flow
changes shape because there are no companion files to restore.

**REMOVE:**

| Content | Reason |
|---|---|
| Any rehydrate step that re-stages companion files (`.roothash`, `.p7s`, `.verity`) | Companion files no longer exist |
| Any reference to restoring `/data/config/keys/` at boot | `/etc/verity.d/` is bind-mounted from persistent storage; no restore step needed |
| `restore-apps.service` references that invoke a 16-step rehydrate | Steps collapse to ~3 per app |

**ADD:**

| Content | Notes |
|---|---|
| Updated rehydrate flow per app | (1) read runtime mode from metadata, (2a) portable: `portablectl attach <ddi.raw>` + regenerate drop-in + enable; (2b) nspawn: `systemctl enable systemd-nspawn@<name>` (already persistent). systemd re-verifies signature, re-sets up verity, re-discovers units |
| `/etc/verity.d/` persistence statement | On OL OS, `/etc/verity.d/` is bind-mounted from `/data/` at boot, so certs survive the overlay reset. No re-import needed |
| Idempotent rehydrate statement | On a normal distro (no overlay reset), rehydrate is a harmless no-op — everything is already attached. On OL OS it rebuilds ephemeral state from the persistent DB |
| `/etc/sysusers.d/` persistence statement | Same bind-mount pattern; OR appctl calls `systemd-sysusers` during rehydrate (idempotent) |
| Dual-runtime rehydrate | Both portable and nspawn modes covered; cite design session §5 |

**MODIFY:**

| Content | Change |
|---|---|
| All `/data/` path references in the rehydrate description | Per path migration table |
| Rehydrate step count and complexity | Significantly reduced; cite design session §5 for the simplified flow |

---

### 2.8 `lifecycle.md`

Currently defines lifecycle hooks. Lightly affected.

**REMOVE:** None structurally.

**ADD:**

| Content | Notes |
|---|---|
| Runtime-mode awareness note | Hooks fire for both portable and nspawn modes; the hook unit names target `<name>.service` (portable) or `systemd-nspawn@<name>` (nspawn) as appropriate. appctl resolves the correct target from metadata `runtime` field |
| Lifecycle block validation rule (carry from the decision records) | `lifecycle:` block only present when hooks are actually defined. Omit entirely if no hooks. No null/tilde/empty forms. buildctl validates. Metadata JSON omits the key when no hooks declared |

**MODIFY:**

| Content | Change |
|---|---|
| Any `/data/` path references in hook examples | Per path migration table |
| Hook unit target examples | Show both portable (`<name>.service`) and nspawn (`systemd-nspawn@<name>`) variants |

---

## 3. Schema File Changes

### 3.1 `packages.sql`

Currently defines the `packages.db` schema. Needs column updates for runtime
mode and new file paths.

**REMOVE:**

| Content | Reason |
|---|---|
| Any column storing per-companion-file paths (e.g. `squashfs_path`, `roothash_path`, `p7s_path`, `verity_path`) | Single DDI replaces all |
| Any column referencing `/data/offline-lab/...` as a default or example | Replaced by FHS paths |

**ADD:**

| Column | Table | Type | Notes |
|---|---|---|---|
| `runtime` | `packages` (or wherever the installed-app row lives) | `TEXT NOT NULL DEFAULT 'portable'` | `CHECK (runtime IN ('portable', 'nspawn'))` |
| `network` | `packages` | `TEXT` nullable | `CHECK (network IS NULL OR network IN ('host', 'private', 'none'))`. Only meaningful when `runtime = 'nspawn'` |
| `raw_path` | image-staging table | `TEXT NOT NULL` | Absolute path to the staged `.raw` DDI file |
| `command` | `packages` | `TEXT` nullable | Original `command` from package.yaml, for traceability |

**MODIFY:**

| Content | Change |
|---|---|
| Image-staging path column | `image_dir` (or similar) values change from `/data/offline-lab/images/<uuid>/` to `/var/lib/appctl/images/<uuid>/` |
| App storage path column | Values change from `/data/apps/<hash>/<name>/` to `/var/lib/appctl/apps/<hash>/<name>/` |
| DB location comment / pragma | `/var/lib/appctl/packages.db` (was `/data/offline-lab/packages.db`) |
| Any `CREATE TABLE` example with old paths in comments | Update to FHS paths |
| Schema version / migration hint | Bump the schema version (whatever convention the file uses) and add a brief migration note: existing rows need their path columns rewritten and `runtime` backfilled to `'portable'` |

---

### 3.2 `package-yaml.schema.json`

Currently defines the package.yaml contract. Needs new fields for dual runtime
and auto-generated service support.

**ADD (new properties at top level):**

| Property | Type | Required | Default | Constraint |
|---|---|---|---|---|
| `runtime` | string | no | `"portable"` | enum `["portable", "nspawn"]` |
| `network` | string | no | `"host"` | enum `["host", "private", "none"]`. Only meaningful when `runtime = "nspawn"`; ignored otherwise |
| `command` | string | no | — | Absolute path to the service entrypoint. Used to auto-generate the service unit when no unit file is provided in `rootfs/` or backend output |

**MODIFY:**

| Content | Change |
|---|---|
| `$id` / version metadata | Bump to reflect additive change |
| Top-level `description` | Mention DDI output, dual runtime, skeleton `rootfs/` feature |
| Examples in the schema | Update filenames to underscore convention; add an example with `runtime: nspawn` and `network: private` |
| Validation of service unit / `User=` | Keep the rule that unit files inside the project must not contain `User=` or `Group=` (appctl injects via drop-in). Add: this rule applies to portable mode only; nspawn mode does not use a drop-in for user allocation |

**Notes:**
- Do **not** make `runtime` or `command` required. Defaults preserve backward
  compatibility with existing package.yaml examples.
- `network` is intentionally ignored when `runtime = "portable"`; document this
  in the field description so authors are not confused.

---

### 3.3 `package-metadata.schema.json`

Currently defines the metadata JSON produced by buildctl and consumed by appctl.
Must mirror the package.yaml additions and drop signature-related dead fields.

**REMOVE:**

| Field | Reason |
|---|---|
| `signature` (if still present as a reserved/null field) | Fully dead. Signing is inside the DDI signature partition, not the metadata JSON |
| Any field referencing companion files (`.roothash`, `.p7s`, `.verity` paths) | Companion files no longer exist |

**ADD:**

| Property | Type | Required | Notes |
|---|---|---|---|
| `runtime` | string | yes (no default in metadata — explicit) | enum `["portable", "nspawn"]`. buildctl copies from package.yaml (defaulting to `"portable"` if absent) |
| `network` | string | no | enum `["host", "private", "none"]`. Present only when `runtime = "nspawn"` and author set it; otherwise omitted |
| `command` | string | no | Present only when the author set it in package.yaml; used by appctl for traceability |

**MODIFY:**

| Content | Change |
|---|---|
| `signing_key_id` | Keep as reserved nullable field for key rotation (per the decision records). Update description: this is the fingerprint of the build key that signed the DDI signature partition |
| Filename patterns in any `$comment` or example | Underscore convention: `<name>_<version>_<arch>.raw` + `.json` |
| Field for the DDI filename / artifact name | If a field names the artifact, it points at `<name>_<version>_<arch>.raw` (not `.squashfs`) |
| Any `format` or `kind` discriminator | If the metadata has a format-version field, bump it |

---

### 3.4 `repo-index-root.schema.json`

Currently defines the root `index.json` (keys + arches discovery document).
Minimal changes.

**REMOVE:** None structurally.

**ADD:**

| Content | Notes |
|---|---|
| Statement (in `$description` or a comment) that build certs are served at `keys/signing-<key-id>.crt` and consumed into `/etc/verity.d/` by appctl | For clarity; the schema itself does not change |

**MODIFY:**

| Content | Change |
|---|---|
| Any example URLs in descriptions | Underscore filenames; `.raw` + `.json` not `.squashfs` + companions |
| `keys[]` entry cert URL pattern | If the schema documents where build certs live, the path is `keys/signing-<key-id>.crt` (unchanged from current; just confirm) |

**Notes:**
- The root index is a pure discovery document (keys + arch listing). It does
  not carry package entries and is essentially untouched by the format change.
- Confirm there are no `/data/` references; if any exist in examples, apply the
  path migration table.

---

### 3.5 `repo-index-arch.schema.json`

Currently defines the per-arch `index.json` (one entry per package, latest
version). Package entries change shape because the file set changed.

**REMOVE:**

| Field (from the per-package entry schema) | Reason |
|---|---|
| `squashfs_url`, `roothash_url`, `p7s_url`, `verity_url` (or however the 5 files are referenced) | Replaced by single DDI |
| Any field whose example value ends in `.squashfs`, `.roothash`, `.p7s`, or `.verity` | Old format |

**ADD:**

| Property | Type | Required | Notes |
|---|---|---|---|
| `raw_url` (or `ddi_url`) | string (URI) | yes | URL of the `.raw` DDI file. Must satisfy the same-server rule (same origin as `base_url`) |
| `metadata_url` | string (URI) | yes | URL of the `.json` metadata file. Same-server rule applies |
| `runtime` | string | no (default portable) | enum `["portable", "nspawn"]`. Mirrors package.yaml; lets `appctl search` display runtime without downloading metadata |

**MODIFY:**

| Content | Change |
|---|---|
| Per-package entry shape | 5 file URLs (or zip_url) collapse to `raw_url` + `metadata_url`. If the schema uses a `zip_url` field, keep it but the zip now contains 2 files instead of 5 |
| `size` / `sha256` fields | If present, they describe the `.raw` DDI (and optionally the metadata JSON). Document which artifact each size/hash covers |
| Same-server rule enforcement | If described in the schema, both `raw_url` and `metadata_url` must resolve to the same origin as `base_url` |
| `signing_key_id` in entry | Keep; identifies which build key signed the DDI signature partition |
| All filename examples | Underscore convention |

---

## 4. Migration Checklist

Every file below needs at least one edit. Check off each row as the change is
made. Files are grouped by directory.

### 4.1 Specs (`../../docs/specs/`)

| File | Change scope | Done |
|---|---|---|
| `package-format.md` | Heavy rewrite: 5-file → DDI; naming; signature partition JSON; UAPI references | [ ] |
| `build.md` | Update pipeline output; add skeleton feature; add auto-generated files; mkosi first-class; pure-Go libs | [ ] |
| `security-model.md` | Remove custom appctl PKCS7; add systemd `verity.d/` flow; update threat table; cert path | [ ] |
| `repository.md` | Update package entries to `.raw` + `.json`; cert destination `/etc/verity.d/`; reaffirm same-server rule | [ ] |
| `user-allocation.md` | Scope uid allocation to portable mode; `/etc/sysusers.d/` path; OL OS bind-mount caveat | [ ] |
| `resource-tracking.md` | Path migration; DDI size note | [ ] |
| `reboot-proofing.md` | Simplified rehydrate flow; dual-runtime; `/etc/verity.d/` and `/etc/sysusers.d/` persistence | [ ] |
| `lifecycle.md` | Runtime-mode hook targeting; path migration | [ ] |
| `sysext.md` | Verify no `/data/` references; confirm still out of appctl scope (cite design session §13) | [ ] |

### 4.2 Schemas (`../../docs/schemas/`)

| File | Change scope | Done |
|---|---|---|
| `packages.sql` | Add `runtime`, `network`, `command` columns; replace companion-file columns with `raw_path`; migrate all `/data/` paths; bump schema version | [ ] |
| `package-yaml.schema.json` | Add `runtime`, `network`, `command` properties; update examples to underscore naming | [ ] |
| `package-metadata.schema.json` | Add `runtime`, `network`, `command`; remove dead `signature` field; update `signing_key_id` description; bump format version | [ ] |
| `repo-index-root.schema.json` | Confirm no `/data/` refs; clarify `keys/signing-<key-id>.crt` → `/etc/verity.d/` consumption | [ ] |
| `repo-index-arch.schema.json` | Replace companion-file URLs with `raw_url` + `metadata_url`; add `runtime`; update same-server rule | [ ] |
| `resources.schema.json` | Migrate any `/data/config/resources.json` references to `/var/lib/appctl/resources.json` | [ ] |

### 4.3 Cross-referenced files (consistency updates)

These files are not in scope of the spec migration per se, but reference the old
format/paths and will become inconsistent if not updated alongside.

| File | Change scope | Done |
|---|---|---|
| `../../docs/app-filesystem.md` | Squashfs content spec is unchanged, but any reference to the 5-file wrapper or `/data/` extraction paths must update | [ ] |
| `../../docs/cli/appctl.md` | Update `repo add` cert destination; update `install` flow description; reflect dual-runtime commands | [ ] |
| `../../docs/cli/buildctl.md` | Update `build` output filenames; add `rootfs/` skeleton mention; reflect mkosi as first-class | [ ] |
| `../../docs/packages.md` | Update any 5-file references and `/data/` paths | [ ] |
| `../../docs/schemas.md` | If it enumerates schemas, note new fields and version bumps | [ ] |
| `../../docs/terminology.md` | Add terms: DDI, DPS, VOA, `verity.d/`, runtime mode (portable/nspawn); update "Repo hash" if naming changes | [ ] |
| [decision records](../adr/) | Rewrite: package-format section → DDI; signing model → systemd native; path table; add runtime-mode decision; mark old decisions superseded | [ ] |
| the project context file | Update package-format block; update path table; update signing-model paragraph; add dual-runtime and skeleton | [ ] |
| the task tracker | Audit task numbers referencing the old format/path/components; re-scope per design session §13 v1 table | [ ] |
| open questions / ADRs | Mark resolved: UAPI alignment, runtime verification, cert storage, nspawn inclusion. Carry forward: inter-app comms (already deferred) | [ ] |

### 4.4 Verification steps after migration

Run these checks against the migrated corpus before considering the migration
complete. None of these require running code — they are documentation
consistency checks.

| Check | How to verify | Done |
|---|---|---|
| No `/data/offline-lab/` or `/data/config/keys/` references remain in any spec or schema | `grep -rn '/data/offline-lab\|/data/config/keys' ../../docs/` returns nothing | [ ] |
| No `/data/apps/` references remain | `grep -rn '/data/apps/' ../../docs/` returns nothing | [ ] |
| No `.squashfs.roothash`, `.roothash.p7s`, or `.squashfs.verity` references remain | `grep -rn 'roothash\.p7s\|\.squashfs\.verity\|\.squashfs\.roothash' ../../docs/` returns nothing | [ ] |
| No hyphen-separated filename examples for packages | `grep -rnE '[a-z]+-[0-9]+\.[0-9]+\.[0-9]+-(arm64|amd64)\.' ../../docs/` returns nothing | [ ] |
| Every spec and schema that discusses signing references `/etc/verity.d/` (not `/data/config/keys/`) | Manual review of `security-model.md`, `repository.md`, `reboot-proofing.md` | [ ] |
| `runtime` field present in `package-yaml.schema.json`, `package-metadata.schema.json`, and `repo-index-arch.schema.json` | Manual review | [ ] |
| DDI format (GPT with 3 partitions) described in `package-format.md` and referenced from `build.md` and `security-model.md` | Manual review | [ ] |
| The decision records and the project context no longer describe the 5-file format as current | Manual review | [ ] |

---

## Appendix: Standards References

Cite these in `package-format.md` and `security-model.md` where appropriate.

| Spec | Title | URL |
|---|---|---|
| UAPI.2 | Discoverable Partitions Specification | https://uapi-group.org/specifications/specs/discoverable_partitions_specification/ |
| UAPI.3 | Discoverable Disk Images | https://uapi-group.org/specifications/specs/discoverable_disk_image/ |
| UAPI.11 | VOA (Verification of OS Artifacts) | https://uapi-group.org/specifications/specs/file_hierarchy_for_the_verification_of_os_artifacts/ |
| systemd | Userspace dm-verity cert verification | `src/shared/dissect-image.c`, `validate_signature_userspace()` |
