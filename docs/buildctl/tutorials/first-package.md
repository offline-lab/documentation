# Build your first package

This tutorial walks through scaffolding a new project, generating a signing key, building a signed DDI, and validating the result. At the end you will have a `.raw` image with dm-verity and a PKCS7 signature that systemd can attach and verify natively.

## Prerequisites

- buildctl installed ([install guide](../install.md))
- Go 1.22+ (only required if building buildctl from source)
- For this tutorial: `bash` on your PATH (used by the shell backend)

## 1. Scaffold the project

`buildctl new` writes a boilerplate project for a given backend.

```bash
buildctl new hello --backend shell
cd hello
```

The generated tree:

```
hello/
  package.yaml   ← package metadata and runtime configuration
  build.sh       ← shell backend entry point that populates the rootfs
```

The scaffolding is a complete, buildable package. Open `package.yaml` and adjust the fields as needed; the defaults are enough for the rest of this tutorial.

## 2. Generate a signing key

Every DDI is signed at build time. buildctl signs the dm-verity roothash with an RSA private key and embeds both the signature and the signing certificate fingerprint in the image.

```bash
buildctl key generate --name mykey --out ./keys
```

This produces a keypair in `./keys/`:

| File | Purpose |
|---|---|
| `mykey.key` | Private key (PEM, PKCS#1 RSA). Keep on the build machine. Never publish. |
| `mykey.crt` | Self-signed X.509 certificate. Published to the device's `/etc/verity.d/` so systemd can verify signatures. |

The certificate fingerprint (SHA-256 of the DER encoding) is shown in the command output and is what identifies this key on the device. See [Signing and trust model](../explanation/signing.md) for how the fingerprint flows through the system.

## 3. Build the DDI

```bash
buildctl build . --key ./keys/mykey.key --compress
```

buildctl runs the shell backend, applies the post-build pipeline (skeleton merge, `.buildignore`, generated `os-release` and service unit, embed `package.yaml`), and then assembles the DDI.

Output in `./dist/`:

```
hello_1.0.0_arm64.raw     ← DDI: GPT with root + verity + signature partitions
hello_1.0.0_arm64.json    ← package metadata (size, hash, runtime config)
hello_1.0.0_arm64.zip     ← transport bundle (.raw + .json), produced by --compress
```

## 4. Validate the result

`buildctl validate image` verifies the built DDI without attaching it. It confirms the partition layout, checks the embedded PKCS7 signature against a certificate, and recomputes the DDI SHA-256 against the metadata.

```bash
buildctl validate image ./dist --cert ./keys/mykey.crt
```

Expected output ends with `Validation passed`. A failure here means the image is corrupt or was signed with a different key than the one supplied via `--cert`.

The DDI is a standard GPT image; inspect it with `sgdisk -p` or `systemd-dissect` if you want to verify the partition layout directly. See [DDI output and metadata](../reference/ddi-output.md) for the full structure.

## Next steps

- [Build a package](../how-to/build.md) covers all the flags and what each pipeline stage does to the rootfs.
- [Build backends](../reference/backends.md) explains Docker, mkosi, shell, and make in detail.
- [Customize the rootfs](../how-to/customize-rootfs.md) shows how to overlay files and exclude paths from the squashfs.
- [Publish to a repository](../how-to/publish.md) covers repository layout and index signing.
