# Repository

> **⚠ Amended (2026-07-05) — rename + rewrite pending.** The thing this page
> calls a "repository" is now an **index** ecosystem-wide:
> [ADR-0033](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0033-index-terminology-trust-architecture.md).
> The static-file model below is **affirmed and hardened** (an index is a
> filesystem layout, not a service). New on top: the two-gate trust model,
> delegation-by-inclusion, identity-is-the-index-key, carrier-vs-curator
> (verbatim mirrors need no keys; catalogs are never merged), presence ≠
> authenticity, index monotonicity, **relative URLs only**, latest-only remote
> with user-configurable local retention, and UAPI.10 version ordering.
> Consumer verbs are `index trust/list/drop`; authoring is
> `buildctl index init/add/update`. Where this page conflicts, ADR-0033 wins.

An Offline Lab repository is a static directory of files. Any HTTP server, USB drive,
or local filesystem path can serve as a repository. No dynamic API is required.

A single repo can host both **bases** and **apps (images)**, or just one of the two,
or act as a **meta-repo** that points at artifact locations on different hosts via
absolute URLs in the manifest.

---

## Design principles

- **Static files only**: nginx, caddy, a Python `http.server`, or a USB drive all work
  without modification. No server-side logic.
- **Same format everywhere**: the same index works over HTTP, HTTPS, and `file://`.
  Relative URLs ensure indexes are portable across transports.
- **Two artifact classes, independent indexes**: `bases/` for layered base images and
  `images/` for apps. Each class has its own per-arch index. A repo may host one or
  both.
- **Per-arch indexes**: each architecture has its own index file per class. Devices
  download only the index for their arch and the classes they need. This bounds index
  size regardless of how many arches or packages a repo supports.
- **Signed indexes**: every index is signed via a companion `.p7s` file. The discovery
  manifest (`repository.json`) is also signed. appctl verifies before trusting any
  package entry.
- **Latest version only**: each per-arch index carries one entry per package (the
  latest published version). Version history is a client-side concern; rollback uses
  locally retained images.

---

## Repository URL rules

A repo is addressed by a single **base URL** set at `appctl repo add` time. Rules:

- Must be a well-formed `http://`, `https://`, or `file://` URL.
- May include a subpath: `https://repo.example.com/some/path/` or
  `file:///some/dir/repo/`.
- **No credentials in the URL.** Specifically forbidden:
  - `https://user:pass@host/` (basic auth in URL)
  - `https://host/?token=abc` (query-string tokens)
  - `https://host/path;param` (path parameters)
  - `https://host/#frag` (fragments)
- The base URL is the authoritative origin (trust anchor) for every download
  resolved from this repo, **unless** `repository.json` explicitly redirects a
  class to an absolute URL — see "Meta-repo pattern" below.

**Auth:** not supported in v1. If a repo requires authentication in the future, it
will be handled via environment variables or a transport wrapper, not via credentials
in the URL.

---

## Directory layout

Canonical layout — both classes hosted in the same repo:

```
/                                               ← repo root (served at base_url)
  repository.json                               ← discovery manifest
  repository.json.p7s                           ← signature over manifest
  keys/
    signing-<key-id>.crt                        ← public build cert(s); one per active key
    signing-<index-key-id>.crt                  ← public index cert
  bases/
    arm64/
      index.json                                ← arm64 bases index
      index.json.p7s
      ol-base-debian/
        1.0.2/
          ol-base-debian_1.0.2_arm64.raw
          ol-base-debian_1.0.2_arm64.json
          ol-base-debian_1.0.2_arm64.oci.tar    ← optional Docker/OCI image (build-time use)
    amd64/
      ...
  images/
    arm64/
      index.json                                ← arm64 apps index
      index.json.p7s
      mosquitto/
        2.0.18/
          mosquitto_2.0.18_arm64.zip
          mosquitto_2.0.18_arm64.json
          mosquitto_2.0.18_arm64.raw
    amd64/
      ...
```

Packages and bases are nested under `<class>/<arch>/<name>/<version>/` to bound the
number of files per directory. Flat arch-level directories degrade on USB and SD card
filesystems as a repo grows. Files keep their full `<name>_<version>_<arch>.*` names
(underscore separator per UAPI.3) for readability when copying or backing up.

**Single-class repos:** if a repo hosts only bases or only apps, omit the unused
subtree and the corresponding URL in `repository.json` (see below). appctl treats a
missing class as "this repo does not serve that artifact type."

---

## `repository.json` (discovery manifest)

The root `repository.json` is a lightweight discovery document. appctl fetches it at
`repo add` time to learn:

- Where each artifact class lives (`bases` and `images` URLs)
- Which signing keys are active for this repo

It does not contain package entries.

### Field reference

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec_version` | string | yes | Always `"1"` |
| `name` | string | yes | Human-readable repo name |
| `updated_at` | string | yes | ISO 8601 timestamp |
| `bases` | string \| null | no | Relative or absolute URL to the bases subtree. Omit or `null` if this repo does not serve bases. |
| `images` | string \| null | no | Relative or absolute URL to the apps/images subtree. Omit or `null` if this repo does not serve apps. |
| `keys` | array | yes | All currently valid signing certs. See below. |
| `key_rotation` | integer | no | Incremented on each key rotation. Default 0. |

At least one of `bases` or `images` must be present. A repo that serves neither is
invalid.

**URL forms** for `bases` and `images`:

- **Relative path** (default): `"bases/"`, `"images/"`. Resolved against the repo root
  URL. Same host. appctl appends `<arch>/index.json` to build the per-arch index URL.
- **Absolute URL** (meta-repo pattern): `"https://bases.example.com/"`,
  `"https://apps.example.com/"`. The class lives on a different host. The base URL of
  the repo is still the trust anchor for the manifest, but the per-class artifacts are
  fetched from the absolute URL. Same-origin rules still apply within each class.

**keys entries**

| Field | Type | Required | Notes |
|---|---|---|---|
| `key_id` | string | yes | Cert fingerprint (SHA-256 of DER, hex) |
| `type` | string | yes | `"build"` or `"index"`. See below. |
| `cert_url` | string | yes | Relative URL to the cert file in `keys/` |
| `active` | boolean | yes | True if this key is currently used to sign new packages or indexes |
| `expires_at` | string \| null | no | ISO 8601. appctl removes this cert once all packages signed by it have been updated and this date has passed. |

**Key types:**

- `"build"`: signs the DDI signature partition JSON for each package. Lives on the
  build machine; never copied to the repo server. systemd uses the cert at attach
  time to verify the DDI signature partition via `/etc/verity.d/`.
- `"index"`: signs `repository.json.p7s` and every per-arch `index.json.p7s` after
  each publish. Lives on the repo host. A compromised index key cannot forge package
  content; systemd always re-verifies the build-key signature in the DDI signature
  partition at attach time.

At least one `"build"` key and one `"index"` key must have `active: true`. During key
rotation, both the old cert (`active: false`, `expires_at`) and the new cert
(`active: true`) are listed. Each key type is rotated independently.

### Full example (full repo — both classes)

```json
{
  "spec_version": "1",
  "name": "Offline Lab Packages",
  "updated_at": "2026-01-15T10:00:00Z",

  "bases":  "bases/",
  "images": "images/",

  "key_rotation": 0,

  "keys": [
    {
      "key_id": "a1b2c3d4e5f6",
      "type": "build",
      "cert_url": "keys/signing-a1b2c3d4e5f6.crt",
      "active": true,
      "expires_at": null
    },
    {
      "key_id": "f6e5d4c3b2a1",
      "type": "index",
      "cert_url": "keys/signing-f6e5d4c3b2a1.crt",
      "active": true,
      "expires_at": null
    }
  ]
}
```

### Example: meta-repo (classes on different hosts)

```json
{
  "spec_version": "1",
  "name": "Offline Lab Meta",
  "updated_at": "2026-06-18T10:00:00Z",

  "bases":  "https://bases.offline-lab.com/",
  "images": "https://apps.offline-lab.com/",

  "keys": [ ... ]
}
```

The repo root (where `repository.json` and `keys/` live) can be a third host
(e.g. `https://repo.offline-lab.com/`); the per-class URLs point elsewhere.

### Example: bases-only repo

```json
{
  "spec_version": "1",
  "name": "Offline Lab Base Images",
  "updated_at": "2026-06-18T10:00:00Z",

  "bases": "bases/",
  "images": null,

  "keys": [ ... ]
}
```

---

## Per-arch per-class index

Each class has one index per arch it serves. Devices fetch only their arch and only
the classes they need.

```
<bases-url>/<arch>/index.json            ← bases index for this arch
<bases-url>/<arch>/index.json.p7s        ← signature

<images-url>/<arch>/index.json           ← apps index for this arch
<images-url>/<arch>/index.json.p7s       ← signature
```

`<bases-url>` and `<images-url>` are resolved from `repository.json`.

### Common index fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec_version` | string | yes | Always `"1"` |
| `type` | string | yes | `"bases"` or `"apps"` — discriminates the index type. |
| `arch` | string | yes | Architecture this index covers |
| `updated_at` | string | yes | ISO 8601 timestamp of last update |
| `key_rotation` | integer | no | Incremented on each key rotation. Default 0. |
| `packages` | array | **apps only** | One entry per package (latest version). |
| `bases` | array | **bases only** | One entry per base (latest version per sysext_level). |

The `type` field is required and lets appctl detect mismatches (e.g. an apps URL
returning a bases index).

### Apps index `packages` entries

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Package name |
| `version` | string | yes | Semver |
| `description` | string | yes | Single-line description |
| `tags` | string[] | no | Used for search and filtering |
| `runtime` | string | no | `portable` (default) or `nspawn` |
| `stack` | array \| null | no | Layered mode: declared base stack. `null` (or omitted) = single-image app. See [Layered design](https://github.com/offline-lab/documentation/blob/main/decisions/design/layered-images.md). |
| `ddi_size` | integer | yes | Bytes of the `.raw` DDI file; used for pre-install storage check |
| `ddi_sha256` | string | yes | Hex SHA-256 of the `.raw` DDI file; integrity check independent of PKCS7 |
| `signing_key_id` | string | yes | `key_id` of the build cert used to sign this package's DDI signature partition |
| `custom_profile` | boolean | no | True if `systemd_profile: custom`. Default false. |
| `metadata_url` | string | yes | Relative path to the `.json` metadata file |
| `zip_url` | string | yes | Relative path to the `.zip` transport archive (contains DDI + metadata) |
| `raw_url` | string | no | Relative path to the `.raw` DDI file. Required if `zip_url` is not used. |

Relative paths in `metadata_url`, `zip_url`, and `raw_url` are relative to the
**class URL** (`<images-url>`), not to the index file itself. All three must resolve
to the same origin as the class URL (same-server rule; see Trust rules below).

### Apps index example

```json
{
  "spec_version": "1",
  "type": "apps",
  "arch": "arm64",
  "updated_at": "2026-01-15T10:00:00Z",
  "key_rotation": 0,

  "packages": [
    {
      "name": "mosquitto",
      "version": "2.0.18",
      "description": "Lightweight MQTT broker",
      "tags": ["networking", "mqtt", "iot"],
      "runtime": "portable",
      "stack": null,
      "ddi_size": 5242880,
      "ddi_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
      "signing_key_id": "a1b2c3d4e5f6",
      "custom_profile": false,
      "metadata_url": "mosquitto/2.0.18/mosquitto_2.0.18_arm64.json",
      "zip_url": "mosquitto/2.0.18/mosquitto_2.0.18_arm64.zip",
      "raw_url": "mosquitto/2.0.18/mosquitto_2.0.18_arm64.raw"
    },
    {
      "name": "myservice",
      "version": "1.0",
      "description": "Example layered service",
      "runtime": "portable",
      "stack": [
        {"name": "ol-base-debian",        "sysext_level": "1.0"},
        {"name": "ol-base-debian-python", "sysext_level": "1.0"}
      ],
      "ddi_size": 2097152,
      "ddi_sha256": "...",
      "signing_key_id": "a1b2c3d4e5f6",
      "metadata_url": "myservice/1.0/myservice_1.0_arm64.json",
      "zip_url": "myservice/1.0/myservice_1.0_arm64.zip",
      "raw_url": "myservice/1.0/myservice_1.0_arm64.raw"
    }
  ]
}
```

### Bases index `bases` entries

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Base name (e.g. `ol-base-debian`) — matches `ID=` in the base's os-release. |
| `version` | string | yes | Semver |
| `sysext_level` | string | yes | Compatibility version (SONAME-like); extensions match on this. |
| `description` | string | no | Human-readable flavor/runtime description. |
| `tags` | string[] | no | e.g. `["debian", "python"]` for filtering. |
| `ddi_size` | integer | yes | Bytes of the `.raw` DDI. |
| `ddi_sha256` | string | yes | Hex SHA-256 of the `.raw`. |
| `oci_size` | integer | no | Bytes of the `.oci.tar` build-time artifact. |
| `oci_sha256` | string | no | Hex SHA-256 of the `.oci.tar`. |
| `signing_key_id` | string | yes | `key_id` of the build cert. |
| `metadata_url` | string | yes | Relative path to the `.json` metadata. |
| `raw_url` | string | yes | Relative path to the `.raw` runtime DDI. |
| `oci_url` | string | no | Relative path to the `.oci.tar` build-time Docker image. Required if the base is intended to be used as a build-time `FROM` target by app Dockerfiles. |

Relative paths are relative to `<bases-url>`.

### Bases index example

```json
{
  "spec_version": "1",
  "type": "bases",
  "arch": "arm64",
  "updated_at": "2026-06-18T10:00:00Z",
  "key_rotation": 0,

  "bases": [
    {
      "name": "ol-base-debian",
      "version": "1.0.2",
      "sysext_level": "1.0",
      "description": "Minimal Debian base (libc, openssl, ca-certs, bash)",
      "tags": ["debian"],
      "ddi_size": 52428800,
      "ddi_sha256": "...",
      "oci_size": 60397977,
      "oci_sha256": "...",
      "signing_key_id": "a1b2c3d4e5f6",
      "metadata_url": "ol-base-debian/1.0.2/ol-base-debian_1.0.2_arm64.json",
      "raw_url":    "ol-base-debian/1.0.2/ol-base-debian_1.0.2_arm64.raw",
      "oci_url":    "ol-base-debian/1.0.2/ol-base-debian_1.0.2_arm64.oci.tar"
    },
    {
      "name": "ol-base-debian-python",
      "version": "1.0",
      "sysext_level": "1.0",
      "description": "Python 3 runtime on ol-base-debian",
      "tags": ["debian", "python"],
      "ddi_size": 31457280,
      "ddi_sha256": "...",
      "oci_size": 38063616,
      "oci_sha256": "...",
      "signing_key_id": "a1b2c3d4e5f6",
      "metadata_url": "ol-base-debian-python/1.0/ol-base-debian-python_1.0_arm64.json",
      "raw_url":    "ol-base-debian-python/1.0/ol-base-debian-python_1.0_arm64.raw",
      "oci_url":    "ol-base-debian-python/1.0/ol-base-debian-python_1.0_arm64.oci.tar"
    }
  ]
}
```

---

## Index signatures

Both `repository.json` and every per-arch per-class `index.json` are signed with
companion `.p7s` files generated by `buildctl index sign`. This command runs on the
**repo host** using the repo's **index key**, not the build key.

appctl verifies:

- `repository.json.p7s` against the index cert at every `repo refresh` (and at `repo
  add` time as trust-on-first-use).
- Every per-arch per-class `index.json.p7s` against the same index cert before
  trusting any package or base entry.

Verification is performed by appctl directly (pure-Go PKCS7); the index cert is
stored in the repo's state record at `state/repos/<hash>.json`:

```
# Conceptual flow — appctl uses pure-Go PKCS7 internally, not openssl
appctl verify-index \
    --cert <stored-index-cert> \
    --signature <url>/index.json.p7s \
    --content   <url>/index.json
```

Package content is verified separately at attach time by systemd against the build
cert (type `"build"`) stored at `/etc/verity.d/<repo-name>-<key-id>.crt`. The two
verification paths are independent and use different code paths (appctl verifies the
index; systemd verifies the DDI).

An unsigned or unverifiable index is rejected. There is no `--force`, `--skip-verify`,
or equivalent flag to bypass signature verification. A flag to skip it would make
the entire signing model optional and therefore meaningless.

---

## Client flow

### appctl repo add \<url\> --name \<alias\>

1. Fetch `<url>/repository.json` and `<url>/repository.json.p7s`.
2. Parse `repository.json`. Determine which artifact classes are served (`bases` and
   `images` URLs).
3. For each entry in `keys[]`:
   - Fetch `<url>/<cert_url>` (certs live under `keys/` relative to the repo root).
   - **Build certs** are stored at `/etc/verity.d/<repo-alias>-<key-id>.crt`
     (systemd reads them at attach time).
   - **Index certs** are stored in the repo's state record
     (`state/repos/<hash>.json`); appctl uses them for ongoing verification.
4. Verify `repository.json.p7s` against the active `"index"` cert
   (trust-on-first-use on first contact).
5. Resolve `bases` and `images` URLs:
   - Relative paths → resolved against `<url>` (the repo root).
   - Absolute URLs → used as-is (meta-repo pattern).
6. For each class the repo serves, determine device arch and fetch
   `<class-url>/<arch>/index.json` + `.p7s`.
7. Verify each per-arch index `.p7s` against the stored index cert.
8. Write the repo record to `state/repos/<hash>.json` with the resolved class URLs,
   the key set, and cached package/base entries.

`<url>` becomes the authoritative origin for this repo for the manifest and keys.
Per-class URLs may point at different origins (meta-repo pattern) — the per-class
indexes themselves become the trust anchors for artifacts under those URLs, signed
by the same index cert.

### appctl repo refresh

1. Fetch fresh `repository.json` and `.p7s`.
2. Verify against the stored index cert.
3. Detect `key_rotation` counter changes. If incremented: mark all installed packages
   and bases from this repo for re-verification on next reattach.
4. Check `keys[]` for new `key_id` values not yet stored locally; fetch and store them.
5. For each served class, fetch fresh `<class-url>/<arch>/index.json` + `.p7s`.
6. Verify each per-arch index `.p7s` against the stored index cert.
7. Update the cached entries in the repo's state record.

### appctl search \<term\>

Filters the cached **apps** index by name, description, and tags. Sorted by name.
Custom-profile packages are flagged in output. Bases are not included in search
results — operators use `appctl list-bases` to inspect installed/available bases.

### appctl install \<name\>

1. Find the entry for `<name>` in the cached apps (`images`) index for this device's
   arch.
2. If the entry's `stack` field is non-null, this is a layered app — follow the
   layered install flow (see
   [Layered design §9](https://github.com/offline-lab/documentation/blob/main/decisions/design/layered-images.md#9-base-lifecycle-on-device-appctl)).
3. Otherwise, single-image install:
   - Check `ddi_size` against available storage.
   - Verify `zip_url` (and `raw_url`/`metadata_url`, if used) resolve to the same
     origin as the class URL (same-server rule).
   - Download `zip_url` to a temp location.
   - Extract: verify the DDI (`.raw`) and metadata (`.json`) are present and
     correctly named; verify the DDI SHA-256 matches `ddi_sha256`.
   - (Optional) pre-verify the DDI signature partition against the build cert
     matching `signing_key_id` for early failure.
   - Stage DDI to `/var/lib/appctl/images/<uuid>/`.
   - Continue with install flow (see [Lifecycle](lifecycle.md)); systemd performs
     the authoritative PKCS7 verification at attach time.

### appctl install \<name\>@\<version\>

Same as above. The index only carries the latest version; pinned installs of older
versions must use a `file://` repo pointing to the specific version directory.

---

## Key rotation

See [Security Model: Key Rotation](security-model.md#key-rotation) for the full flow.

In brief:

- **Option A (recommended):** generate a new key, sign new packages/bases going
  forward, publish both old and new certs in `repository.json` `keys[]` (old with
  `active: false` + `expires_at`, new with `active: true`). Devices pick up the new
  cert on next `repo refresh`. Installed packages transition at their own pace.
- **Option B (clean cut-over):** re-sign all packages/bases, increment `key_rotation`
  in `repository.json`, `repo refresh` triggers re-verification of all installed
  packages and bases.

Both old and new cert remain listed during the transition window so devices that
haven't refreshed yet can still verify already-downloaded packages.

---

## Trust rules

**Same-server rule (per class):** appctl rejects any `metadata_url`, `zip_url`,
`raw_url`, or `oci_url` that resolves to a different origin than the class URL
declared in `repository.json`. Per-class URLs may be on different hosts (meta-repo
pattern), but each class's artifacts must come from a single origin.

**No cross-origin redirects:** HTTP redirects to a different origin are rejected.
Redirects within the same origin (e.g. HTTP to HTTPS on the same host) are permitted.

**Single trust anchor for the manifest:** the `base_url` from `repo add` is the trust
anchor for `repository.json` and `keys/`. Per-class URLs declared in
`repository.json` become the trust anchors for artifacts under those URLs (signed by
the same index cert that signs the manifest).

**Allowed protocols:** HTTP, HTTPS, and `file://`. Content integrity comes from PKCS7
signatures regardless of transport. HTTP is safe for offline and LAN repos where
HTTPS is impractical. `file://` is required for USB and air-gapped use.

---

## Local index generation

`buildctl index generate <path>` scans a local repo directory and produces valid
index files for each class present:

1. Detect which classes are present: look for `bases/` and `images/` subdirectories.
2. For each class and each arch:
   - Walk `<class>/<arch>/<name>/<version>/` for `.json` metadata files.
   - Build an entries list keeping only the latest version per `name` (and per
     `sysext_level` for bases).
   - Write `<class>/<arch>/index.json`.
3. Sign each per-arch index: `buildctl index sign <class>/<arch>/index.json --key <index-key>`.
4. Write `repository.json` with the resolved class URLs (typically `bases/` and
   `images/` for a single-host repo).
5. Sign `repository.json`: `buildctl index sign repository.json --key <index-key>`.

**Incremental update:** `buildctl publish <package-dir> --repo <url> --class <bases|images>`
adds or updates a single package or base without requiring all artifacts locally:

1. Download the current per-arch index for the target class from the repo.
2. Add or replace the entry for this artifact.
3. Sign the updated index.
4. Upload the artifact files and the new index.
5. If `repository.json`'s `key_rotation` should bump (Option B rotation), update and
   re-sign it too.

This is the normal publish workflow. Full regeneration from scratch is only needed
when bootstrapping a new repo or after Option B key rotation.

---

## Repo status

Each repo's state record at `state/repos/<hash>.json` carries a `status` field:

| Status | Behaviour |
|---|---|
| `active` | Normal; refresh, install, update all permitted |
| `paused` | No automatic refresh or updates; manual install still works |
| `blocked` | All operations rejected; already-installed packages continue to run |

`appctl repo pause <name>` and `appctl repo block <name>` set this field.

A repo's status applies equally to both classes — you cannot pause just bases while
allowing apps from the same repo. If granular control is needed, use separate repos.

---

## Standards references

| Spec | Title | Relevance |
|---|---|---|
| [UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/) | Discoverable Disk Images | The `.raw` artifact format and the underscore naming convention |
| [PKCS#7](https://datatracker.ietf.org/doc/html/rfc2315) | Cryptographic Message Syntax | The `.p7s` signature format |
| systemd | Userspace dm-verity cert verification | `src/shared/dissect-image.c`, `validate_signature_userspace()` |

Related specs:
- [Package Format](package-format.md) — DDI internals, package.yaml, metadata JSON
- [Security Model](security-model.md) — trust chain, key rotation, signature verification
- [Layered design](https://github.com/offline-lab/documentation/blob/main/decisions/design/layered-images.md) — bases, extensions, `stack:` field
- [On-device state format](../schemas/on-device-state.md) — repo state record schema
