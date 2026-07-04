# Signing and trust model

DDIs are signed at build time and verified by systemd at attach time. This page covers what buildctl does (key generation, signing, certificate fingerprinting, index signing) and how those artifacts flow to the device. For the full trust model, certificate store layout, and key rotation procedures, see the [security model spec](https://offline-lab.com/docs/specs/security-model/) in the Offline Lab documentation.

## Two keys, two roles

| Key | Generated with | Lives on | Signs |
|---|---|---|---|
| **Build key** | `buildctl key generate --name <repo>` | Build machine. Never copied to the repo host, never committed. | The DDI signature partition for every package. |
| **Index key** | `buildctl key generate --name <repo>-index --index` | Repo host. | The detached PKCS7 over every `index.json` after each publish. |

Both are RSA keypairs (default 4096-bit) with self-signed X.509 certificates. The `--index` flag is informational: it tags the certificate's organization as `Offline Lab (Index)` so the two roles are visually distinguishable. The on-disk format is identical.

The split exists because the two keys have very different blast radii.

### Build key compromise

A stolen build key can sign malicious package content that devices will accept as genuine. Treat it like a CA private key: never leaves the build machine, never accessible to CI without a secrets manager, never copied to the repo host.

### Index key compromise

A stolen index key cannot forge package signatures. systemd always verifies the DDI signature partition against the build certificate at install time, regardless of what the index claims. The blast radius is limited to catalog manipulation: hiding packages, advertising stale versions, reordering entries. Recovery is straightforward: re-sign the indexes with a new index key and publish the new index certificate to devices.

## Key identifier

The canonical identifier for either key is the SHA-256 of the DER encoding of the X.509 certificate, lowercase hex. This value appears in three places, all consistent:

- `certificateFingerprint` in the DDI signature partition (`root-verity-sig` partition JSON).
- `signing_key_id` in the package metadata JSON.
- The filename of the certificate in `<repo>/keys/signing-<key-id>.crt`.
- The `key_id` and `fingerprint` of each entry in the root index.

buildctl prints this identifier when generating a keypair:

```
buildctl key generate --name mykey --out ./keys
...
  Key ID:       <sha256 hex of the DER certificate>
```

## The signing chain

```
build machine                          repo host                        device
─────────────                          ─────────                        ──────
buildctl build
  --key build.key
    │
    ▼
  DDI signature partition  ─── rsync ──▶  packages/<arch>/<name>/<v>/
    {rootHash,                              │
     signature,                             │
     certificateFingerprint}                │
                                            ▼
                                          buildctl index add
                                            --sign-key index.key
                                              │
                                              ▼
                                            index.json.p7s  ─── http ──▶  appctl repo add
                                              index.json                   │
                                                                            ▼
                                                                          verify index.json.p7s
                                                                            against index cert(s)
                                                                            │
                                                                            ▼
                                                                          download package
                                                                            │
                                                                            ▼
                                                                          portablectl attach
                                                                            │
                                                                            ▼
                                                                          systemd reads sig partition,
                                                                            verifies PKCS7 against
                                                                            /etc/verity.d/*.crt,
                                                                            activates dm-verity
```

The chain has two independent verifications on the device:

1. **Index signature**: `index.json.p7s` verified against the index certificates the device trusts. Confirms the index is authentic and complete.
2. **DDI signature**: PKCS7 in the verity-sig partition verified against the build certificates in `/etc/verity.d/`. Confirms the package content matches the roothash.

A compromised index key can lie about what packages exist but cannot get a malicious package accepted; the second check fails. A compromised build key can sign malicious packages but cannot reach devices without a legitimate index entry; the first check fails (assuming the index key is intact).

## What is signed

The PKCS7 signature in the DDI signature partition is **detached** and covers the hex-encoded roothash, not the raw 32 bytes. This is deliberate: it is what systemd reconstructs as the signed content when verifying, so the verification code path needs no special-casing for our format.

```go
sd, _ := pkcs7.NewSignedData([]byte(rootHashHex))
sd.SetDigestAlgorithm(pkcs7.OIDDigestAlgorithmSHA256)
sd.SignWithoutAttr(cert, signer, pkcs7.SignerInfoConfig{})
sd.Detach()
sigDER, _ := sd.Finish()
```

`SetDigestAlgorithm(SHA256)` is set explicitly. `go.mozilla.org/pkcs7` defaults to SHA-1; OpenSSL 3.x (used by systemd for userspace verity verification) rejects SHA-1 under default security policies.

The index signature covers the raw bytes of `index.json`. Re-signing after any change (including whitespace) produces a different signature. Always re-sign through `buildctl index add` or `buildctl index generate` so the bytes buildctl wrote are exactly the bytes that were signed.

## dm-verity at runtime

Once systemd has verified the PKCS7 signature and obtained the roothash, it activates the kernel's dm-verity target over the root partition. The kernel enforces block-level integrity from that point on: any on-disk block that does not match the Merkle tree causes a read error.

buildctl is no longer in the loop. There is no custom verifier running on the device at runtime; the kernel is the enforcement layer.

## Random salt

The dm-verity salt is 32 random bytes from `crypto/rand`, regenerated per build. Every leaf hash in the Merkle tree is `SHA256(salt + data_block)`. The salt prevents pre-computation attacks against known filesystem layouts; the same rootfs content built twice produces different roothashes, different partition GUIDs, and different signatures. This is expected, not a problem.

## See also

- [Security model spec](https://offline-lab.com/docs/specs/security-model/): full trust chain, key rotation procedures, attack surface analysis.
- [Package format spec, signature partition](https://offline-lab.com/docs/specs/package-format/#signature-partition): schema and field-level details.
- [DDI output and metadata](../reference/ddi-output.md): what buildctl writes and where.
- [Publish to a repository](../how-to/publish.md): operational publish workflow.
