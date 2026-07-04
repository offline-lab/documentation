# Package Format

> **Amended (2026-07-05).** The DDI core of this page is **affirmed**
> ([ADR-0034](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0034-uapi-substrate.md)
> adopts UAPI.3 verbatim). New and normative on top: layered apps are **UAPI.4
> sysexts** (`extension-release.d/`, `SYSEXT_SCOPE=portable`, exact
> `ID`/`SYSEXT_LEVEL`/`ARCHITECTURE` match, max 3 layers, no base-on-base
> stacking); versions follow **UAPI.10** (not semver); build tooling changed
> (ADR-0031). The manifest floor shrank (storage/runtime/unit have defaults) —
> field-level spec pending.

An Offline Lab package is a systemd portable service packaged as a **DDI**
(Discoverable Disk Image, [UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/))
plus a separate metadata JSON. buildctl produces the package; appctl consumes it.

The DDI is a GPT partition image containing three partitions — root, verity, and
signature — bundling the squashfs filesystem, its dm-verity hash tree, and the
PKCS7 signature of the roothash into a single `.raw` file. systemd discovers and
verifies the image natively: there are no companion files and no custom verity or
PKCS7 verification code at runtime.

See [Security Model](security-model.md) for the trust chain and verification flow,
and [Build](build.md) for how the DDI is produced.

---

## File set

Every package consists of two files:

```
<name>_<version>_<arch>.raw      ← DDI (GPT: root squashfs + verity + signature partitions)
<name>_<version>_<arch>.json     ← package metadata
```

Both files must be present and co-located. appctl extracts them to the permanent
images directory at `/var/lib/appctl/images/<uuid>/` on install; the DDI is
staged as a single `.raw` file. The metadata JSON is the source of truth for
appctl at install time.

**Transport:** for download or USB transfer, both files are wrapped in a zip:

```
<name>_<version>_<arch>.zip
```

appctl extracts the zip once to the images directory; the zip is not retained.

---

## DDI format

The `.raw` file is a GPT (GUID Partition Table) image with a protective MBR and
exactly three partitions, per the [Discoverable Partitions Specification
(UAPI.2 / DPS)](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/):

| # | Partition | Contents | Discovered by systemd as |
|---|---|---|---|
| 1 | Root | squashfs (or erofs) filesystem — the portable service image | `root-<arch>` |
| 2 | Verity | dm-verity superblock + hash tree over partition 1 | `root-<arch>-verity` |
| 3 | Signature | JSON binding the roothash to a PKCS7 signature (see below) | `root-<arch>-verity-sig` |

systemd-dissect discovers each partition by its **type UUID** (see below). The
hash tree that previously shipped as a verity sidecar file now lives in
partition 2; the roothash and its PKCS7 signature, previously separate sidecar
files, now live together in partition 3.

### Partition type UUIDs

Partition type UUIDs are arch-specific and defined by UAPI.2 (DPS). buildctl
selects them based on the package `arch`:

| Arch | Root | Verity | Verity-sig |
|---|---|---|---|
| `arm64` | `B921B045-1DF0-41C3-AF44-4C6F280D3FAE` | `DF3300CE-D69F-4C92-978C-9BFB0F38D820` | `6DB69DE6-29F4-4758-A7A5-962190F00CE3` |
| `amd64` | `4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709` | `933AC7E1-2EB4-4F13-B844-0E14E2AEF915` | `D4E7CEDE-7F4D-4C7B-9B87-1B7A03A6AB63` |

Partition names/labels (e.g. `root-arm64-verity-sig`) are informational; discovery
is by type UUID only. The verity-sig UUIDs above are verified against
systemd-repart output on Fedora 44 — some online sources list incorrect values.

The GPT must include a **protective MBR** (`ProtectiveMBR: true` when building
with go-diskfs), otherwise systemd-dissect cannot identify the image.

### Partition UUID encoding (roothash binding)

Per DPS, the **partition GUIDs** (the unique partition identifiers, distinct from
the arch-specific type UUIDs above) of the root and verity partitions encode the
roothash:

- **Root partition GUID** = first 128 bits (16 bytes) of the roothash
- **Verity partition GUID** = last 128 bits (16 bytes) of the roothash

This binds each partition cryptographically to the roothash that protects it.
After systemd loads the signature partition and obtains the roothash, it verifies
both partition GUIDs against the roothash-derived values. buildctl therefore
computes the roothash **before** writing the GPT and sets both partition GUIDs
accordingly. This is not optional — it is enforced by systemd; mismatched GUIDs
cause attach/mount to fail.

Example (from a live verification on systemd 259):

```
Roothash:  ef87a379dc7560ab95325f7ef84d0d45a0e8d81ba68e64dfaa1ff69dba8c82cb

Root partition:
  GUID:     ef87a379-dc75-60ab-9532-5f7ef84d0d45
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ = first 128 bits

Verity partition:
  GUID:     a0e8d81b-a68e-64df-aa1f-f69dba8c82cb
                                          ^^^^^^^^^^^^^^^^^^^ = last 128 bits
```

### Signature partition

The signature partition contains a single JSON object that binds the roothash to
a PKCS7 signature produced by the build key:

```json
{
  "rootHash": "<hex>",
  "signature": "<base64 PKCS7>",
  "certificateFingerprint": "<sha256 hex>"
}
```

| Field | Format | Notes |
|---|---|---|
| `rootHash` | lowercase hex string | The dm-verity roothash of partition 1 |
| `signature` | base64-encoded DER PKCS7 | PKCS7 signature over `rootHash`, produced at build time by buildctl with `go.mozilla.org/pkcs7`. **MUST use SHA256** as the digest algorithm — see note below |
| `certificateFingerprint` | lowercase sha256 hex | SHA-256 of the DER-encoded signing certificate; identifies which build key signed this package and drives per-key cert lookup during key rotation |

systemd reads this partition, verifies the PKCS7 signature against certificates
installed under `/etc/verity.d/` (see [Security Model](security-model.md)), and
uses the verified roothash to activate dm-verity over partition 1. There is no
verification code in appctl — systemd performs the verification natively via
`validate_signature_userspace()` in `src/shared/dissect-image.c`. The kernel
enforces block integrity at runtime via dm-verity.

> **PKCS7 digest algorithm: SHA256.** `go.mozilla.org/pkcs7` v0.9.0 defaults to
> SHA1. OpenSSL 3.x (used by systemd for userspace verity verification) rejects
> SHA1 with "invalid digest" because SHA1 is disabled in the default security
> provider. buildctl MUST call
> `SetDigestAlgorithm(pkcs7.OIDDigestAlgorithmSHA256)` before signing.

---

## Root partition content (squashfs) constraints

The DDI does not change the filesystem contents — it only changes the wrapper.
The root partition contains a squashfs filesystem subject to the same constraints
that have always applied to Offline Lab portable service images. The full content
spec lives in [App Filesystem Layout](../app-filesystem.md); summarized:

- **All files owned `root:root`** (uid 0, gid 0). buildctl forces this via
  `SetOwner(path, 0, 0)` when writing the squashfs.
- `/etc/os-release` with `ID=<name>` and `VERSION_ID=<version>` matching the
  package metadata exactly. (Required by portablectl for image identification.)
- `/usr/lib/systemd/system/<name>.service` — the main service unit. Unit files
  must **not** contain `User=` or `Group=` directives; appctl injects the
  allocated runtime user via a drop-in at install time (portable mode only).
- `/usr/lib/systemd/system/<name>.socket` when `socket_activation: true`.
- `/usr/share/<name>/package.yaml` — the build-time package definition, embedded
  by buildctl for build-time provenance without requiring the source repository.
- All lifecycle hook unit files declared in the metadata.

Services must not perform internal privilege dropping (`setuid`/`setgid`/`initgroups`
to a named user defined in the image's own `/etc/passwd`), and every runtime-writable
path must be declared as a volume in `package.yaml`. See
[App Filesystem Layout](../app-filesystem.md) for the rationale and details.

---

## Naming convention

| Field | Rules | Example |
|---|---|---|
| `name` | Lowercase, alphanumeric and hyphens only; must start with alphanumeric | `mosquitto` |
| `version` | Valid semver | `2.0.18` |
| `arch` | Enum: `arm64`, `armv7`, `armv6`, `amd64` | `arm64` |

The three fields are joined with an **underscore** separator (per UAPI.3), not a
hyphen:

```
mosquitto_2.0.18_arm64.raw
mosquitto_2.0.18_arm64.json
mosquitto_2.0.18_arm64.zip
```

---

## package.yaml

`package.yaml` is the build-time package definition. Package authors write it;
buildctl reads it to build the DDI and generate the metadata JSON.

buildctl embeds `package.yaml` inside the root partition at
`/usr/share/<name>/package.yaml`. This provides build-time provenance without
requiring access to the source repository. The Dockerfile (if any) is not
included; publishing it is the maintainer's responsibility.

Fields not set in `package.yaml` fall back to Docker labels baked into the image
(see [Build: Dockerfile labels](build.md#dockerfile-labels-optional)), then to
defaults where applicable.

### Field reference

**Identity**

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec_version` | string | yes | Always `"1"` |
| `name` | string | yes | Lowercase, alphanumeric + hyphens |
| `version` | string | yes | Semver |
| `arch` | string | yes | See naming convention above |
| `description` | string | yes | Single line |
| `homepage` | string | no | URL |
| `license` | string | no | SPDX identifier (e.g. `Apache-2.0`) |
| `tags` | string[] | no | Used for repo search and filtering |

**Publisher and contact**

| Field | Type | Required | Notes |
|---|---|---|---|
| `publisher` | string | yes | Publisher organisation (e.g. `offline-lab`) |
| `publisher_url` | string | no | Publisher homepage URL |
| `maintainer` | string | no | Package maintainer, format `"Name <email>"` |
| `source_url` | string | no | Source repository URL |
| `security_contact` | string | no | Email or URL for vulnerability reports |
| `sbom_url` | string | no | URL to a published SBOM for this package |

**Runtime**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `runtime` | string | no | `portable` | `portable` or `nspawn`. Selects how appctl runs the image (see below) |
| `network` | string | no | `host` | `host`, `private`, or `none`. Only meaningful when `runtime: nspawn`; ignored for `portable` |
| `command` | string | no | — | Absolute path to the service entrypoint. Used to auto-generate the service unit when no unit file is provided in `rootfs/` or backend output |
| `systemd_profile` | string | no | `strict` | `default`, `strict`, `trusted`, `nonetwork`, `custom` |
| `socket_activation` | boolean | no | `false` | If true, a `.socket` unit must exist inside the root partition |

**Runtime modes.** `runtime: portable` (default) attaches the DDI with
`portablectl attach`; appctl allocates a dedicated `app<uid>` system user and
generates a drop-in (`User=`, `Group=`, `BindPaths=`, `RootImage=`).
`runtime: nspawn` runs the image under `systemd-nspawn`; isolation is via PID /
mount / network namespaces and there is no per-app uid allocation (the process
inside the container is root in the namespace). The `network` field only applies
to nspawn mode. Both modes use the same DDI and the same `/etc/verity.d/` cert
store; systemd re-verifies the signature and re-sets up dm-verity in both paths.

`systemd_profile: "custom"` means the unit files inside the root partition carry
their own security directives. The tooling attaches with `--profile=default` as a
baseline. Full security responsibility shifts to the app author. Custom-profile
packages are flagged in `appctl list` output and in the repo index.

**Service unit precedence.** If the developer provides a service unit (in
`rootfs/` or in backend output), it takes precedence and `command` is ignored.
`command` is only consulted to auto-generate a unit when none is present.

**Volumes**

| Field | Type | Required | Notes |
|---|---|---|---|
| `volumes.config` | string | no | Namespace path for the config volume (e.g. `/etc/mosquitto`) |
| `volumes.data` | string | no | Namespace path for the data volume (e.g. `/var/lib/mosquitto`) |

Exactly two keys: `config` and `data`. No freeform paths. appctl generates `BindPaths=`
from these at install time and backs them with persistent storage under
`/var/lib/appctl/apps/<hash>/<name>/`. See [User Allocation](user-allocation.md)
for the system path layout and drop-in format.

Apps log via stderr/stdout to the systemd journal. No log volume is provided.

**Ports** (array, may be empty)

| Field | Type | Required | Notes |
|---|---|---|---|
| `port` | integer | yes | 1–65535 |
| `protocol` | string | yes | `tcp` or `udp` |
| `description` | string | no | |
| `expose` | boolean | yes | If true, an nftables accept rule is applied on install |

**Devices** (array, may be empty)

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | string | yes | `audio`, `video`, `bluetooth`, `gpio`, `i2c`, `spi`, `serial`, `usb` |
| `required` | boolean | yes | If false, service starts even if device is absent |
| `description` | string | no | |

**Resources** (optional)

Declares expected resource usage at three load levels. Used by appctl for pre-install
capacity checks. See [Resource Tracking](resource-tracking.md).

```yaml
resources:
  low:
    cpu_percent: 2
    memory_mb: 24
    storage_mb: 45
  moderate:
    cpu_percent: 15
    memory_mb: 64
    storage_mb: 45
  heavy:
    cpu_percent: 40
    memory_mb: 128
    storage_mb: 45
```

If omitted, appctl skips the resource check and proceeds with a warning.

**Lifecycle** (optional)

Each value is a systemd unit name that must exist inside the root partition. Omit
any hook the app does not need. Omit the entire `lifecycle:` block if the app has
no hooks. See [Lifecycle Hooks](lifecycle.md) for sequencing and execution
context.

| Field | When appctl starts it |
|---|---|
| `pre_start` | After portablectl attach, before enable and first start |
| `post_start` | After the service is running for the first time |
| `pre_update` | After new image is attached, before service restart |
| `post_update` | After the service is running on the new image |
| `pre_remove` | Before the service is stopped and the image is detached |

**Build options**

| Field | Type | Notes |
|---|---|---|
| `strip.enabled` | boolean | Remove unused shared libraries after build. Default false. |
| `strip.keep` | string[] | Library paths to preserve during stripping (e.g. dlopen'd libs). |

`strip` is build-time only; it does not appear in the generated metadata JSON.

### Full example

```yaml
spec_version: "1"

name: mosquitto
version: 2.0.18
arch: arm64
description: Lightweight MQTT broker
homepage: https://mosquitto.org
license: EPL-2.0
tags: [networking, mqtt, iot]

publisher: offline-lab
publisher_url: https://offline-lab.com
maintainer: "Flip Hess <flip@fliphess.com>"
source_url: https://github.com/offline-lab/apps
security_contact: security@offline-lab.com
sbom_url: ~

runtime: portable
systemd_profile: strict
socket_activation: false

volumes:
  config: /etc/mosquitto
  data:   /var/lib/mosquitto

ports:
  - port: 1883
    protocol: tcp
    description: MQTT
    expose: true

devices: []

resources:
  low:      { cpu_percent: 2,  memory_mb: 24,  storage_mb: 45 }
  moderate: { cpu_percent: 15, memory_mb: 64,  storage_mb: 45 }
  heavy:    { cpu_percent: 40, memory_mb: 128, storage_mb: 45 }

# lifecycle: omitted (mosquitto uses ExecStartPre= in its unit file for first-run init)
```

---

## Metadata JSON

The metadata JSON (`<name>_<version>_<arch>.json`) is generated by buildctl from
`package.yaml` and is **immutable after publication**. It is the source of truth
for appctl at install time. It does not duplicate information that lives inside
the root partition (unit file directives, internal capabilities); only fields the
tooling needs to act on.

The metadata JSON does not carry the signature. Signing lives inside the DDI
signature partition (see above), not in the metadata JSON. The metadata JSON also
does not include `uid` or `gid` — user allocation is appctl's responsibility at
install time, not the package author's. See [User Allocation](user-allocation.md).

### Field reference

All fields from `package.yaml` carry over to the metadata JSON, except `strip`
(build input only). The following fields are added by buildctl at build time:

| Field | Type | Notes |
|---|---|---|
| `format_version` | string | Package format version. `"1"` = DDI format. Distinguishes this from the legacy 5-file format (which had no `format_version`). |
| `ddi_artifact` | string | DDI filename: `<name>_<version>_<arch>.raw`. |
| `ddi_sha256` | string | SHA-256 of the `.raw` DDI file, lowercase hex. Download-integrity check, independent of the PKCS7 signature. |
| `ddi_size` | integer | Size of the `.raw` DDI file in bytes (GPT + root squashfs + verity + signature partitions). Used for pre-install storage checks. |
| `created_at` | string | ISO 8601 build timestamp. |

The following fields carry over from the new `package.yaml` runtime block when set:

| Field | Type | Notes |
|---|---|---|
| `runtime` | string | Always present in metadata (buildctl defaults to `"portable"`). Enum `["portable", "nspawn"]`. |
| `network` | string | Present only when `runtime = "nspawn"` and the author set it; otherwise omitted. |
| `command` | string | Present only when the author set it in `package.yaml`; kept for traceability. |

The following field is reserved (nullable in v1) for key rotation:

| Field | Notes |
|---|---|
| `signing_key_id` | Reserved. Will identify the fingerprint (SHA-256 of the DER certificate) of the build key that signed the DDI signature partition. See [Security Model](security-model.md). |

### Full example

```json
{
  "spec_version": "1",

  "name": "mosquitto",
  "version": "2.0.18",
  "arch": "arm64",
  "description": "Lightweight MQTT broker",
  "homepage": "https://mosquitto.org",
  "license": "EPL-2.0",
  "tags": ["networking", "mqtt", "iot"],

  "publisher": "offline-lab",
  "publisher_url": "https://offline-lab.com",
  "maintainer": "Flip Hess <flip@fliphess.com>",
  "source_url": "https://github.com/offline-lab/apps",
  "security_contact": "security@offline-lab.com",
  "sbom_url": null,

  "signing_key_id": null,

  "format_version": "1",
  "ddi_artifact": "mosquitto_2.0.18_arm64.raw",
  "ddi_sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "ddi_size": 5242880,
  "created_at": "2026-01-15T10:00:00Z",

  "runtime": "portable",
  "systemd_profile": "strict",
  "socket_activation": false,

  "volumes": {
    "config": "/etc/mosquitto",
    "data": "/var/lib/mosquitto"
  },

  "ports": [
    {
      "port": 1883,
      "protocol": "tcp",
      "description": "MQTT",
      "expose": true
    }
  ],

  "devices": [],

  "resources": {
    "low":      { "cpu_percent": 2,  "memory_mb": 24,  "storage_mb": 45 },
    "moderate": { "cpu_percent": 15, "memory_mb": 64,  "storage_mb": 45 },
    "heavy":    { "cpu_percent": 40, "memory_mb": 128, "storage_mb": 45 }
  }
}
```

---

## Path resolution

All paths use standard Linux FHS conventions. On Offline Lab OS, the standard
FHS paths are bind-mounted from persistent `/data/` storage at boot, because
`/etc` is ephemeral (its overlayfs upper is wiped each boot). On any other
systemd host these paths work natively. The complexity lives in the OS layer,
not in appctl.

| Purpose | Path |
|---|---|
| Staged DDI images | `/var/lib/appctl/images/<uuid>/` |
| Per-app persistent storage | `/var/lib/appctl/apps/<hash>/<name>/` |
| appctl state (file-per-record JSON) | `/var/lib/appctl/state/` |
| Signing cert store | `/etc/verity.d/` |

---

## Standards references

| Spec | Title | Relevance |
|---|---|---|
| [UAPI.2](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/) | Discoverable Partitions Specification (DPS) | Partition type UUIDs for root / verity / verity-sig; partition GUID encoding of the roothash |
| [UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/) | Discoverable Disk Images (DDI) | The overall DDI format and the underscore naming convention |
| [UAPI.11](https://uapi-group.org/specifications/specs/file_hierarchy_for_the_verification_of_os_artifacts/) | Verification of OS Artifacts (VOA) | Future: native cert hierarchy for verity. Currently superseded for Offline Lab by the systemd `verity.d/` flow |
| systemd | Userspace dm-verity cert verification | `src/shared/dissect-image.c`, `validate_signature_userspace()` |
