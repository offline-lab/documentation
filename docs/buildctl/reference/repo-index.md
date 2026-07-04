# Repository index format

Structure and contents of the two JSON index files buildctl writes. Both are signed with the index key; see [Signing and trust model](../explanation/signing.md). Authoritative JSON schemas: [`repo-index-arch.schema.json`](https://offline-lab.com/docs/schemas/repo-index-arch.schema.json) and [`repo-index-root.schema.json`](https://offline-lab.com/docs/schemas/repo-index-root.schema.json).

## Per-arch index

Written to `packages/<arch>/index.json`. Lists the latest version of every package present for that arch. Older versions remain on disk (under `packages/<arch>/<name>/<version>/`) but are not listed in the index.

```json
{
  "format_version": "1.0",
  "arch": "arm64",
  "packages": [
    {
      "name": "mosquitto",
      "version": "2.0.18",
      "description": "Lightweight MQTT broker",
      "publisher": "offline-lab",
      "license": "EPL-2.0",
      "homepage": "https://mosquitto.org",
      "tags": ["networking", "mqtt", "iot"],
      "runtime": "portable",
      "signing_key_id": "<sha256 of DER cert>",
      "raw_url": "packages/arm64/mosquitto/2.0.18/mosquitto_2.0.18_arm64.raw",
      "metadata_url": "packages/arm64/mosquitto/2.0.18/mosquitto_2.0.18_arm64.json",
      "ddi_sha256": "<hex>",
      "ddi_size": 4194304,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

Packages are sorted by name for deterministic output. `version` is the highest semver present for that name on disk; buildctl scans every metadata JSON under `packages/<arch>/<name>/*/` and selects the latest by `golang.org/x/mod/semver` comparison.

`raw_url` and `metadata_url` are repo-relative. Clients resolve them against `base_url` from the root index.

The accompanying `index.json.p7s` is a detached PKCS7 (SHA-256) over the bytes of `index.json`, written by `buildctl index add --sign-key` or `buildctl index generate --sign-key`.

## Root index

Written to `<repo>/index.json`. Provides repository-level metadata, the list of arches present, and the list of signing keys discovered in `keys/`.

```json
{
  "format_version": "1.0",
  "repo_name": "My repo",
  "base_url": "https://packages.example.com",
  "keys": [
    {
      "key_id": "<sha256 of DER cert>",
      "cert_url": "keys/signing-<key-id>.crt",
      "fingerprint": "<sha256 of DER cert>"
    }
  ],
  "arches": ["amd64", "arm64"],
  "key_rotation": 0
}
```

`repo_name` and `base_url` come from `buildctl index generate` flags. `keys[]` is populated by scanning `<repo>/keys/*.crt`; each entry's `key_id` and `fingerprint` equal the SHA-256 of the DER encoding of that certificate. `key_rotation` is reserved; buildctl always writes `0`.

`index.json.p7s` alongside the root index is a detached PKCS7 over `index.json`, signed with the index key.

## Keys directory

```
<repo>/keys/
  signing-<sha256-of-der>.crt     ← build certificate(s)
  signing-<sha256-of-der>.crt     ← additional build certificates during rotation
```

The filename encodes the certificate's SHA-256 fingerprint, matching `certificateFingerprint` in the DDI signature partition and `signing_key_id` in the metadata JSON.

buildctl does not write certificates here automatically. Copy the build certificate once when bootstrapping:

```bash
cp ./keys/mykey.crt <repo>/keys/signing-<fingerprint>.crt
```

Multiple certificates can coexist; this is the normal state during key rotation. Devices trust every certificate in `keys/` until the rotation is complete and the old certificate is removed.
