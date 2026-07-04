# Build backends

A build backend has one job: produce a root filesystem tree. Everything after that (skeleton merge, `.buildignore`, required-file generation, validation, squashfs, dm-verity, signing, GPT assembly, metadata) is backend-agnostic and runs identically regardless of which backend produced the rootfs.

## Auto-detection

When `package.yaml` does not set `backend:`, buildctl probes each registered backend in priority order. The first whose `Detect(dir)` returns true wins.

| Priority | Detected from | Backend |
|---|---|---|
| 1 | `Dockerfile` present | `docker` |
| 2 | `mkosi.conf` present | `mkosi` |
| 3 | `build.sh` present | `shell` |
| 4 | `Makefile` present | `make` |

Docker beats shell so a project with both (e.g. a multi-stage template) resolves to Docker. Set `backend:` explicitly to override detection.

## Architecture support

| Backend | Cross-arch | Host requirement |
|---|---|---|
| Docker | yes (QEMU via buildx + binfmt) | `docker` with buildx |
| mkosi | no (fails if `--arch` does not match host arch) | `mkosi` (Linux) |
| shell | caller responsibility (script receives `BUILDCTL_ARCH`) | `bash` |
| make | caller responsibility (Makefile receives `BUILDCTL_ARCH`) | `make` |

See [Cross-compile for a different architecture](../how-to/cross-compile.md) for setup.

## Common environment

Every backend receives these environment variables, so build scripts and Makefiles do not need to parse `package.yaml` themselves:

| Variable | Value |
|---|---|
| `BUILDCTL_NAME` | `name` from `package.yaml` |
| `BUILDCTL_VERSION` | `version` from `package.yaml` |
| `BUILDCTL_ARCH` | the target architecture (after `--arch` override) |

The shell and make backends also pass the output directory positionally / via a variable. See below.

## Docker

Builds a container image with `docker buildx build`, exports the filesystem via `docker export`, and returns any OCI image labels as a `BuildResult`. Cross-arch builds use `--platform linux/<arch>`.

Source file: `Dockerfile`. Required dep: `docker`.

`Setup` ensures the `buildctl-builder` buildx builder exists. It does not register binfmt handlers; that is a privileged, one-time operation performed by `buildctl init`.

The backend extracts the export tarball itself. Path traversal in tar entries is collapsed; absolute symlink targets are rejected; relative symlink and hardlink targets are bounds-checked against the output directory. Character, block, fifo, and socket entries are skipped.

### `backend_arguments`

| Key | Type | Notes |
|---|---|---|
| `build_args` | map | Each entry is passed as `--build-arg <key>=<value>`. Keys are sorted for deterministic command lines. |
| `dockerfile` | string | Alternative Dockerfile path, relative to the project directory. Passed via `--file`. |
| `target` | string | Multi-stage build target. Passed via `--target`. |

Unknown keys are silently ignored.

## mkosi

Builds a filesystem tree from distribution packages with [mkosi](https://github.com/systemd/mkosi). Output is forced to `Format=directory`; if `mkosi.conf` sets a different `Format=`, the build fails.

Source file: `mkosi.conf`. Required dep: `mkosi` (Linux only).

Rejects cross-arch requests; if `--arch` does not match `runtime.GOARCH`, it returns an error pointing at the Docker backend.

### `backend_arguments`

| Key | Type | Notes |
|---|---|---|
| `extra_args` | string list | Each entry is appended verbatim to the `mkosi` command line. |

## shell

Runs `build.sh` under `bash -eu -o pipefail`. The output directory is passed as `$1`. The script is expected to populate `$1` with a rootfs tree.

Source file: `build.sh`. Required dep: `bash`. `backend_arguments` is ignored.

The scaffold template (`buildctl new --backend shell`) installs a sample binary and documents available environment variables in a comment block.

## make

Runs `make OUTDIR=<outDir>` in the project directory. The Makefile is expected to populate `OUTDIR` with a rootfs tree.

Source file: `Makefile`. Required dep: `make`.

### `backend_arguments`

| Key | Type | Notes |
|---|---|---|
| `target` | string | Makefile target to invoke. Defaults to none (the first target). |
| `extra_args` | string list | Each entry is appended verbatim to the make command line. |
