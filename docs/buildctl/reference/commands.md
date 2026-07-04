# Command reference

Top-level commands and their flags. All commands accept `--help` for a complete listing.

```
buildctl <command> [flags] [args]
```

## buildctl build

Build a signed DDI from a project directory.

```
buildctl build [dir] --key <key.pem> [--arch <arch>] [--output <dir>] [--compress]
```

| Flag | Default | Description |
|---|---|---|
| `--key`, `-k` | _required_ | PEM private key for signing. Adjacent `.crt` loaded as the signing certificate. |
| `--arch` | from `package.yaml` | Target architecture. Overrides the `arch:` field. |
| `--output`, `-o` | `dist` | Output directory. Created if missing. |
| `--compress` | off | Also write a `.zip` containing the `.raw` and `.json` outputs. |

See [Build a package](../how-to/build.md) for behavior and failure modes.

## buildctl validate

Pre-build validation. Loads `package.yaml`, runs field validation, resolves the backend, checks the backend source file is present, and reports missing external dependencies. Does not invoke the backend.

```
buildctl validate [dir]
```

No flags. The directory defaults to `.`.

## buildctl validate image

Post-build verification of a DDI without attaching it. Checks GPT layout, signature, certificate fingerprint, and metadata integrity.

```
buildctl validate image <dist-dir> --cert <path-to.crt>
```

| Flag | Default | Description |
|---|---|---|
| `--cert` | _required_ | Path to the build certificate (`.crt`) to verify against. |

See [Validate a built DDI](../how-to/validate.md).

## buildctl new

Scaffold a new project for a given backend. Writes the backend's templates into the output directory. Fails if any target file already exists.

```
buildctl new <name> --backend <b> [--dir <dir>]
```

| Flag | Default | Description |
|---|---|---|
| `--backend`, `-b` | `shell` | One of `docker`, `shell`, `make`, `mkosi`. |
| `--dir`, `-d` | `.` | Output directory. Created if missing. |

## buildctl key generate

Generate an RSA keypair and a self-signed X.509 certificate. Defaults are sized for build keys; pass `--index` for an index-signing key.

```
buildctl key generate [--name <n>] [--out <dir>] [--bits <n>] [--days <n>] [--index]
```

| Flag | Default | Description |
|---|---|---|
| `--name` | `build` | Filename prefix. Produces `<name>.key` and `<name>.crt`. |
| `--out`, `-o` | `.` | Output directory. Created if missing. |
| `--bits` | `4096` | RSA key size. |
| `--days` | `3650` | Certificate validity in days. Capped at 9000 to avoid int64 overflow. |
| `--index` | off | Marks the certificate organization as `Offline Lab (Index)` to distinguish index keys from build keys. The key type is informational; the same key format is used for both. |

Output:

```
<name>.key    ← RSA private key (PEM, PKCS#1)
<name>.crt    ← self-signed X.509 certificate (PEM)
```

The key ID (SHA-256 of the DER certificate) is printed and is the canonical identifier for this key.

## buildctl init

Check that backend dependencies are installed and configure Docker for cross-arch builds if Docker is present.

```
buildctl init
```

No flags. For each backend, prints whether its external tool is on `PATH`. When Docker is present, buildctl ensures the `buildctl-builder` buildx builder exists and offers to register binfmt handlers for cross-architecture emulation if they are missing.

## buildctl index

Repo index management. Has two subcommands.

### index add

Copy a package from a `dist/` directory into the canonical repo layout and rebuild the affected indexes.

```
buildctl index add <repo-path> --from <dist-dir> [--sign-key <key.pem>]
```

| Flag | Default | Description |
|---|---|---|
| `--from` | _required_ | Dist directory containing the `.raw` and `.json` for one package. |
| `--sign-key` | _none_ | Index key for signing `index.json` files. Omit to leave indexes unsigned. |

### index generate

Rebuild every per-arch index and the root index from scratch.

```
buildctl index generate <repo-path> [--name <n>] [--base-url <url>] [--sign-key <key.pem>]
```

| Flag | Default | Description |
|---|---|---|
| `--name` | _none_ | Repository display name (root index `repo_name`). |
| `--base-url` | _none_ | Base URL clients prepend to relative `raw_url` / `metadata_url` values. |
| `--sign-key` | _none_ | Index key for signing. |

See [Publish to a repository](../how-to/publish.md) for the workflow and [Repository index format](repo-index.md) for the file structure.

## buildctl compress

Create a transport `.zip` from a `dist/` directory. Equivalent to passing `--compress` to `buildctl build`.

```
buildctl compress <dist-dir>
```

No flags. Looks for one `.raw` and one `.json` in the directory and writes `<basename>.zip` alongside them. The zip uses `Store` (no double compression); the squashfs root filesystem is already zstd-compressed.

## buildctl version

Print buildctl version, commit, and build time.

```
buildctl version
```

No flags. The version string is injected at compile time from git describe (see [Makefile](https://github.com/offline-lab/buildctl/blob/main/Makefile)).
