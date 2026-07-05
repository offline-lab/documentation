# Package Format

**Status:** rewritten 2026-07-05 against the
[App contract](app-contract.md) and ADR-0034/0037/0038 (T98). This page
specifies the **wire format**: what the file *is*. What makes it an *app*
(manifest fields, run intent, storage, conformance) is the app contract;
how it is catalogued and distributed is the [Index contract](index-contract.md).

---

## One file

**A package is a single file:**

```
<name>_<version>_<arch>.raw
```

It is a **DDI** ([UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/)):
a GPT image containing the root filesystem, its dm-verity hash tree, and the
PKCS7 signature over the roothash — self-describing, self-verifying, signed.
There is **no metadata file beside it and no transport wrapper** (ADR-0038):
the package metadata is the manifest embedded *inside* the image, and the
payload is already compressed (zstd squashfs / erofs), so no `.zip` exists.
systemd discovers and verifies the image natively; no custom verification
code exists anywhere in the tools.

## DDI layout

A GPT (with **protective MBR** — without it `systemd-dissect` cannot
identify the image) and exactly three partitions, per the
[Discoverable Partitions Specification (UAPI.2 / DPS)](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/):

| # | Partition | Contents | Discovered as |
|---|---|---|---|
| 1 | Root | squashfs (or erofs) filesystem | `root-<arch>` |
| 2 | Verity | dm-verity superblock + hash tree over partition 1 | `root-<arch>-verity` |
| 3 | Signature | JSON binding the roothash to a PKCS7 signature | `root-<arch>-verity-sig` |

Discovery is by **partition type UUID only**; names/labels are informational.

### Partition type UUIDs

Type UUIDs are arch-specific, defined by DPS. Live-verified values:

| Arch | Root | Verity | Verity-sig | Verified |
|---|---|---|---|---|
| `arm64` | `B921B045-1DF0-41C3-AF44-4C6F280D3FAE` | `DF3300CE-D69F-4C92-978C-9BFB0F38D820` | `6DB69DE6-29F4-4758-A7A5-962190F00CE3` | ✓ live test, systemd 259 / Fedora 44 |

> **Other arches:** take the values from DPS / `systemd-repart` output on the
> target — do **not** copy them from secondary sources. A previous revision of
> this page listed an amd64 verity UUID that was actually DPS's *home*
> partition type; online sources get these wrong. Verify before use.

### Partition GUIDs encode the roothash

Per DPS, the **partition GUIDs** (unique IDs, distinct from the type UUIDs)
of the root and verity partitions are derived from the roothash:

- Root partition GUID = **first** 128 bits of the roothash
- Verity partition GUID = **last** 128 bits of the roothash

systemd **enforces** this: mismatched GUIDs make attach fail. The assembler
therefore computes the roothash before writing the GPT. Live-verified
example (systemd 259):

```
Roothash:  ef87a379dc7560ab95325f7ef84d0d45a0e8d81ba68e64dfaa1ff69dba8c82cb
Root   GUID: ef87a379-dc75-60ab-9532-5f7ef84d0d45   (first 128 bits)
Verity GUID: a0e8d81b-a68e-64df-aa1f-f69dba8c82cb   (last 128 bits)
```

### Signature partition

A single JSON object binding the roothash to the build signature:

```json
{
  "rootHash": "<lowercase hex>",
  "signature": "<base64 DER PKCS7>"
}
```

The PKCS7 blob carries the signer's certificate, which enables
show-and-accept at import (ADR-0037); trust still comes only from the
consumer's accepted-cert store (`/etc/verity.d/`, VOA — see
[Security model](security-model.md)). systemd verifies the signature
natively (`validate_signature_userspace()`), then activates dm-verity;
the kernel enforces block integrity at runtime.

> **PKCS7 digest MUST be SHA-256.** OpenSSL 3.x rejects SHA-1 digests
> ("invalid digest") under default security policies. Any signer used by the
> build pipeline must produce SHA-256 PKCS7.

Additional JSON fields in this partition are ignored by systemd; producers
should emit the two standard fields.

## Two package shapes

| | Fat app | Layered app |
|---|---|---|
| Carries | complete userland | only the app's own files |
| Identity file | `/etc/os-release` (`ID=<name>`, `VERSION_ID=<version>`) | `/usr/lib/extension-release.d/extension-release.<name>` — **no os-release** |
| Runs | alone | on exactly **one base** (2 layers max, ADR-0034 §20) |
| Extra rules | — | [UAPI.4](https://uapi-group.org/specifications/specs/extension_image/) sysext: `ID=` equals the base's (never `_any`), `SYSEXT_LEVEL=` (the base's ABI promise), `ARCHITECTURE=`, `SYSEXT_SCOPE=portable`; **purely additive** over the base (file overlap = build error) |

Bases themselves are specified separately (T96); a base is a UAPI.4-matchable
base DDI, independently signed — it vouches for itself.

## DDI metadata (the embedded manifest)

The manifest (`package.yaml`) is embedded at
`/usr/share/<name>/package.yaml` (ADR-0017) and **is** the package
metadata — "DDI metadata," an essential part of the format. Field semantics
live in the [App contract](app-contract.md); machine-validatable shapes in
the JSON schemas (T95).

Reading it follows the ADR-0038 order — **verification first, always**:

1. Probe the GPT (type UUIDs; no content read).
2. Verify the PKCS7 signature against the accepted-cert store.
3. Verity-verify the root partition.
4. Only then extract the manifest (`systemd-dissect --copy-from`, image
   policy enforced).

Filenames are untrusted; identity comes from the verified manifest. Indexes
project the searchable fields out of the manifest once, at `index add` —
nothing ever scans DDIs at search or resolution time.

## Root partition content constraints

Summarized from the [App contract](app-contract.md) (conformance §):

- All files owned `root:root` (ADR-0014).
- Identity file per the package shape (exactly one of the two).
- `/usr/lib/systemd/system/<name>.service` (and `<name>.socket` iff
  `socket_activation`); every declared lifecycle-hook unit exists.
- **No `User=`/`Group=`** in any unit (ADR-0015) and **no host-path mounts**
  — the runtime's generated drop-in owns placement (ADR-0036).
- Empty mount-point dirs `/etc/<name>/` and `/var/lib/<name>/` exist
  (bind targets; a mount point cannot be created on a read-only squashfs).
- Optional pristine config defaults at `/usr/share/factory/etc/<name>/`
  (seeded into the config volume on first provision).
- The embedded manifest at `/usr/share/<name>/package.yaml`.
- Layered shape: additive over the base — no file overlap.

## Naming

| Field | Rules | Example |
|---|---|---|
| `name` | lowercase, alphanumeric + hyphens, starts alphanumeric | `mosquitto` |
| `version` | [UAPI.10](https://uapi-group.org/specifications/specs/version_format_specification/) (`~` pre-release, `^` post-release) — **not semver**. The version of the *DDI*, not of the software inside | `2.0.18` |
| `arch` | open, pattern-validated string; officially supported set documented separately | `arm64` |

Joined with **underscores** (UAPI.3): `mosquitto_2.0.18_arm64.raw`.

This naming is **`systemd-vpick`-native**: a `mosquitto.raw.v/` directory of
such files is resolved to the newest version by systemd itself
(UAPI.10 ordering, arch filtering) — relevant to the upgrade design (T103).

## Host paths (consumer side)

| Purpose | Path |
|---|---|
| App storage (config/data) | `<root>/apps/<index-hash>/<name>/` — relocatable `<root>`, default `/var/lib/appctl` (ADR-0035) |
| Runtime state | file-per-record under `<root>` (ADR-0026); source of truth for `recover` |
| Trust store (up-gate) | `/etc/verity.d/` (systemd-consumed today) |
| Tool trust material | VOA hierarchy (UAPI.11), per ADR-0034 |

On Offline Lab OS the persistence of these paths is the OS's duty
(`OS-CONFORMANCE.md`); the format knows nothing about overlay wipes.

## Standards references

| Spec | Relevance |
|---|---|
| [UAPI.2 (DPS)](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/) | partition type UUIDs; roothash-derived partition GUIDs |
| [UAPI.3 (DDI)](https://uapi-group.org/specifications/specs/discoverable_disk_image/) | the image format; underscore naming |
| [UAPI.4 (Extension Images)](https://uapi-group.org/specifications/specs/extension_image/) | layered-app shape (sysext, extension-release matching) |
| [UAPI.10 (Version Format)](https://uapi-group.org/specifications/specs/version_format_specification/) | version syntax + ordering |
| [UAPI.11 (VOA)](https://uapi-group.org/specifications/specs/file_hierarchy_for_the_verification_of_os_artifacts/) | trust-material layout (tool-side now; up-gate when systemd consumes VOA — T99) |
| systemd | `systemd-dissect`, `validate_signature_userspace()`, `systemd-vpick` |
