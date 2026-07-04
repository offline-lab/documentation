# Validate a built DDI

## Pre-build validation

```bash
buildctl validate [dir]
```

Runs the same `package.yaml` validation that `buildctl build` runs up front, plus backend source file presence and missing dependency checks. Does not invoke the backend. Exits non-zero if any errors are present.

See [`package.yaml` fields](../reference/package-yaml.md) for per-field rules.

## Post-build validation

```bash
buildctl validate image <dist-dir> --cert <path-to.crt>
```

Verifies the DDI and its metadata without attaching the image. `<dist-dir>` is a directory containing one package's `.raw` and `.json` files.

Checks performed:

1. **Partition layout**: opens the GPT and finds the three DPS partitions by type UUID (root, verity, verity-sig).
2. **Signature partition JSON**: parses `{rootHash, signature, certificateFingerprint}` and rejects malformed payloads.
3. **Certificate fingerprint**: SHA-256 of the DER encoding of `--cert` must match `certificateFingerprint` in the signature partition.
4. **PKCS7 signature**: verifies the detached signature against the roothash using the provided certificate as the trust anchor.
5. **Metadata integrity**: recomputes SHA-256 of the `.raw` and compares it to `ddi_sha256` in the metadata JSON.

`FAIL:` is printed for each failed check; `Validation passed` means all checks succeeded.
