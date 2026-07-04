# DDI output and metadata

A build produces three artifacts in the output directory, sharing a `<name>_<version>_<arch>` basename:

```
<name>_<version>_<arch>.raw     ← DDI (GPT image)
<name>_<version>_<arch>.json    ← package metadata
<name>_<version>_<arch>.zip     ← transport zip (only with --compress)
```

## DDI (`.raw`)

A GPT image with a protective MBR and exactly three partitions:

| # | Name | Type | Contents |
|---|---|---|---|
| 1 | `root` | arch-specific DPS root UUID | squashfs filesystem (zstd, 128 KiB block, all entries `root:root`) |
| 2 | `root-verity` | arch-specific DPS verity UUID | dm-verity superblock + Merkle hash tree over partition 1 (SHA-256, 4 KiB blocks, 32-byte salt) |
| 3 | `root-verity-sig` | arch-specific DPS verity-sig UUID | JSON `{rootHash, signature, certificateFingerprint}` (sector-padded) |

The partition GUIDs of partitions 1 and 2 are derived from the roothash: root GUID = first 16 bytes, verity GUID = last 16 bytes. systemd requires this binding; mismatched GUIDs cause attach to fail.

### Signature partition contents

```json
{
  "rootHash": "<32-byte hex>",
  "signature": "<base64 DER PKCS7>",
  "certificateFingerprint": "<sha256 hex of DER cert>"
}
```

The PKCS7 signature covers `rootHash` (the hex string, not raw bytes; this is what systemd reconstructs at verify time). SHA-256 is set explicitly — `go.mozilla.org/pkcs7` defaults to SHA-1, which OpenSSL 3.x rejects.

The verity salt is randomly generated per build. The same rootfs built twice produces different roothashes; this is expected.

### Single-block roothash

When the squashfs fits in a single dm-verity data block, the kernel uses zero hash-tree levels and the roothash equals `SHA256(salt + data_block)`. buildctl's vendored encoder handles this without padding.

## Architecture UUIDs

| Arch | DPS root partition type UUID |
|---|---|
| `arm64` | `B921B045-1DF0-41C3-AF44-4C6F280D3FAE` |
| `amd64` | `4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709` |
| `armv7` | `69DAD710-2CE4-4E3C-B16C-21A1D49ABED3` |
| `armv6` | `737A3E5E-7802-4B9E-9E51-9E1E3C60C6C0` |
| `i386` | `44479540-F297-41B2-9AF7-D131D5F0458A` |
| `riscv64` | `72EC70A6-CF74-40E6-BD49-4BDA08E8F224` |
| `ppc64le` | `C31C45E6-3F39-478E-8098-46DC49F7BD2A` |
| `s390x` | `08A7B11A-BAEF-4B5D-9B6D-6F4E4A4A3F2C` |

Verity and verity-sig partitions have their own arch-specific type UUIDs per the [Discoverable Partitions Specification](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/).

## Metadata JSON (`.json`)

Carries every field from `package.yaml` (except build-only fields `backend`, `backend_arguments`, `strip`), plus fields computed at build time:

| Field | Source |
|---|---|
| `format_version` | Constant `"1.0"`. |
| `ddi_artifact` | `<name>_<version>_<arch>.raw` (the DDI filename). |
| `ddi_sha256` | SHA-256 of the `.raw` file, lowercase hex. |
| `ddi_size` | Size of the `.raw` file in bytes. |
| `created_at` | Build timestamp, RFC 3339, UTC. |
| `signing_key_id` | SHA-256 of the DER encoding of the signing certificate, lowercase hex. Matches `certificateFingerprint` in the signature partition. |

`command` is included only if set; `network` only when `runtime: nspawn`. `uid`/`gid` are not included; user allocation is appctl's responsibility at install time.

For the full schema, see [`package-metadata.schema.json`](https://offline-lab.com/docs/schemas/package-metadata.schema.json).

## Transport zip (`.zip`)

`--compress` (or `buildctl compress`) writes a zip of the `.raw` and `.json` files using Store (no compression) — the squashfs is already zstd-compressed.
