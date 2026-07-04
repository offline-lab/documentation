# Build a package

```bash
buildctl build [dir] --key <key.pem> [--arch <arch>] [--output <dir>] [--compress]
```

`dir` defaults to `.`.

## Flags

| Flag | Default | Purpose |
|---|---|---|
| `--key`, `-k` | required | PEM private key. buildctl loads the `.crt` at the same path as the signing certificate. |
| `--arch` | from `package.yaml` | Target architecture. Overrides `arch:`. |
| `--output`, `-o` | `dist` | Output directory. Created if missing. |
| `--compress` | off | Also write a `.zip` of the `.raw` and `.json`. Uses Store — the squashfs is already zstd-compressed. |

Output in `--output`:

```
<name>_<version>_<arch>.raw      ← DDI
<name>_<version>_<arch>.json     ← metadata
<name>_<version>_<arch>.zip      ← only with --compress
```

## What the build does

buildctl validates `package.yaml`, selects and runs the backend to produce a rootfs, then applies post-build transforms: skeleton merge, `.buildignore`, `os-release` and service unit generation, `package.yaml` embedding. The rootfs is packed into a squashfs, covered by a dm-verity hash tree, signed with PKCS7, and assembled into a GPT image.

See [Architecture and build pipeline](../explanation/architecture.md) for each stage in detail.

## Signing key

`--key` accepts RSA (PKCS#1), EC (SEC1), and PKCS#8 PEM. buildctl loads the `.crt` at the same base path as the signing certificate. The certificate is required; its SHA-256 fingerprint (DER encoding) is embedded in the DDI signature partition and in the metadata JSON. If no `.crt` is found alongside the key, the build fails.

## Pre-build validation

buildctl runs `package.yaml` validation before invoking the backend: required fields, enum values, semver, backend source file presence. Errors abort the build; warnings print to stderr.

See [`package.yaml` fields](../reference/package-yaml.md) for per-field rules.

## See also

- [Architecture and build pipeline](../explanation/architecture.md)
- [Build backends](../reference/backends.md)
- [Customize the rootfs](customize-rootfs.md)
- [DDI output and metadata](../reference/ddi-output.md)
