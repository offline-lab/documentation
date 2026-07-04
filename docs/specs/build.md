# Build

> **⚠ Superseded (2026-07-05) — rewrite pending.** The buildctl this page
> describes was removed and redesigned:
> [ADR-0031](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0031-buildctl-rebuilt-delegated-assembly.md)
> and the [2026-07-04 design session](https://github.com/offline-lab/documentation/blob/main/decisions/conversation/2026-07-04-design-session.md) (§12).
> What changed: **no pure-Go pipeline** (image assembly is delegated to
> systemd-ecosystem tooling, in a container/VM on macOS); backends are
> **docker / mkosi / shell** (make cut), **never auto-detected**; **signing is
> inside `build`** (unsigned images cannot exist); **no publish transport**
> (`buildctl index init/add/update` operate on local directories only; moving
> bytes is the operator's tool); versions are **UAPI.10**, not semver. Where
> this page conflicts with those records, the records win.

This page describes how app packages are built and published using `buildctl`. It covers
the build flow, the backend model, the DDI creation pipeline, the signing model, and the
publish workflow.

Full buildctl documentation (command reference, flags, configuration) lives in
`buildctl.git`. This page covers the concepts and the design decisions that implementors
need to understand.

---

## What buildctl does

`buildctl` is the developer-side CLI tool for building and publishing Offline Lab app
packages. It runs on a developer workstation or CI machine, not on an Offline Lab device.

1. Produces a root filesystem tree from a backend-specific source (Dockerfile, mkosi,
   shell script, or Makefile)
2. Merges an optional `rootfs/` skeleton and generates any missing required files
3. Creates a squashfs image (pure Go)
4. Computes the dm-verity hash tree and roothash (pure Go)
5. Signs the roothash with the build key as a PKCS7 signature (pure Go, SHA256)
6. Assembles the DDI: a GPT image with root + verity + signature partitions (pure Go)
7. Generates the package metadata JSON
8. Publishes to a repo via rsync + SSH index update

The output of a build is a two-file package — a `.raw` DDI and a `.json` metadata file —
wrapped in a `.zip` for transport. See [Package Format](package-format.md).

---

## Pure Go, macOS required

The entire core pipeline (squashfs, verity, PKCS7 signing, GPT assembly) is implemented
in pure Go. No `mksquashfs`, no `veritysetup`, no `openssl` shell-out for the security-
critical path. This is a hard requirement: **buildctl must run on macOS**, and any
Linux-only tool is forbidden from the core pipeline.

Pure-Go libraries used:

| Library | Purpose |
|---|---|
| `github.com/diskfs/go-diskfs` | GPT / DDI creation. The partition `Table` MUST set `ProtectiveMBR: true` or systemd-dissect cannot identify the image. |
| `github.com/KarpelesLab/squashfs` (v1.2.0, MIT) | squashfs read/write with zstd compression. All entries forced to `root:root` via `SetOwner(path, 0, 0)`. |
| `go.mozilla.org/pkcs7` | PKCS7 signing (build-time only). MUST use SHA256 — see [Package Format: Signature partition](package-format.md#signature-partition). |
| vendored dm-verity encoder | ~430-line encoder vendored from Monogon OS (Apache-2.0) at `internal/verity/encoder.go`. Byte-compatible with the kernel dm-verity target. |

What still shells out (unavoidable, and outside the core pipeline):

- `docker buildx build` / `docker buildx create` — the Docker backend (Docker daemon)
- `docker run --privileged tonistiigi/binfmt` — binfmt handlers for cross-arch emulation
- `bash build.sh` / `make` / `mkosi` — backend build commands
- `rsync` / `ssh` — the publish step

---

## Build backends

A **build backend** is responsible for exactly one thing: producing a root filesystem
tree. Everything after that (skeleton merge, required-file generation, squashfs
conversion, dm-verity computation, signing, GPT assembly, metadata generation) is
backend-agnostic and handled by buildctl regardless of which backend was used.

The backend contract:
> Given a source directory and a target arch, produce a root filesystem tree (or tar
> archive). buildctl takes it from there.

This separation means the packaging pipeline only needs to be implemented once. Adding a
new backend means implementing the filesystem production step. Nothing else changes.

### Backend auto-detection

buildctl auto-detects the backend from the project directory contents. There is no
required `--backend` flag. Detection precedence:

| Priority | Detected from | Backend |
|---|---|---|
| 1 | `Dockerfile` present | `docker` |
| 2 | `mkosi.conf` present | `mkosi` |
| 3 | `build.sh` present | `shell` |
| 4 | `Makefile` present | `make` |

An explicit `backend:` field in `package.yaml` overrides auto-detection when a project
contains markers for more than one backend, or to force a specific backend:

```yaml
# package.yaml
backend: mkosi    # optional override; otherwise auto-detected
```

`backend_arguments` passes optional, per-backend arguments as a freeform map. buildctl
validates the key names it knows about for the selected backend and ignores unknown keys
with a warning. Per-backend arguments are documented alongside each backend below.

```yaml
backend: docker
backend_arguments:
  no_cache: true
  build_args:
    VERSION: "2.0.18"
```

### Supported backends (all in v1)

| Backend | Use when |
|---|---|
| `docker` | You have a Dockerfile; standard container workflow. Default when a Dockerfile is present. |
| `mkosi` | You want a systemd-native image built from distro packages without a container runtime. |
| `shell` | You have a `build.sh` script that produces a root filesystem. |
| `make` | You have a `Makefile` with a target that produces a root filesystem. |

All four backends are first-class from v1; there is no phasing. mkosi is a first-class
alternative from the start — it is developed by the systemd project and produces clean,
minimal filesystem trees from distribution packages with explicit package manifests and
no Docker dependency.

### Package config file

buildctl reads the package config from `package.yaml` or `package.json` in the source
directory. Both formats use the same schema (`docs/schemas/package-yaml.schema.json`);
`package.json` is JSON-encoded rather than YAML. If both files are present, buildctl
exits with an error. If neither is present, buildctl exits with an error.

### .buildignore

A `.buildignore` file in the source directory lists files and directories to exclude
from the squashfs. buildctl applies these rules **after the backend exports the root
filesystem, before the squashfs is written**. The format is identical to `.dockerignore`:

- One pattern per line
- Lines starting with `#` are comments
- `!` prefix negates a pattern (re-include after a previous exclusion)
- Standard glob patterns; `**` matches any number of path segments

The `.buildignore` file affects the squashfs contents only. It does not affect what the
backend sees during its own build step (for Docker, use `.dockerignore` for that).

### Docker backend

The Docker backend builds a container image from a `Dockerfile` and exports the
filesystem using `docker buildx`. It requires Docker with buildx.

**Source layout:**

```
myapp/
  Dockerfile           ← builds the service image
  package.yaml         ← package metadata and runtime configuration
  .buildignore         ← optional: files to exclude from the squashfs
```

The Dockerfile is the maintainer's responsibility. buildctl does not generate it.

**Cross-compilation:** the Docker backend uses `docker buildx` with QEMU emulation.
On macOS and x86 Linux machines, building for `arm64` requires:

```
docker buildx create --use
docker run --privileged --rm tonistiigi/binfmt --install arm64
```

After setup, `buildctl build --arch arm64` transparently builds for arm64 via buildx.
No separate toolchain or native arm64 machine is needed for standard Dockerfiles.
For Dockerfiles that invoke native compilers, emulation is slow; a native arm64
build machine is faster for those cases.

### mkosi backend

[mkosi](https://github.com/systemd/mkosi) builds filesystem trees directly from
distribution packages, without a container runtime. It is developed by the systemd
project and produces clean, minimal images with explicit package manifests. No Docker
installation is required on the build machine.

For portable services, mkosi is a strong fit: images are built from distro packages
(not layers), the result is a plain filesystem tree, and integration with systemd
tooling is first-class.

**Source layout:**

```
myapp/
  mkosi.conf           ← mkosi configuration (packages, release, etc.)
  package.yaml         ← package metadata and runtime configuration
  .buildignore         ← optional: files to exclude from the squashfs
```

**Cross-compilation guard:** mkosi builds for the host architecture by default. When
the requested `arch` does not match the build host arch, buildctl surfaces a clear
error rather than silently producing a wrong-arch tree. Cross-arch mkosi builds
require a matching native toolchain or a cross-build setup outside buildctl's scope.

### shell backend

Runs `build.sh` from the source directory. The script must produce a root filesystem
tree (or tar archive) at a location buildctl reads. Suitable for projects that assemble
a rootfs with their own tooling.

### make backend

Invokes a `Makefile` target that produces a root filesystem tree. The target name and
output location are passed via `backend_arguments`.

---

## Skeleton `rootfs/` merge

An optional `rootfs/` directory in the project is merged into the backend output
**after** the backend runs and **before** required-file generation. Skeleton files
override backend output.

This lets developers provide custom configs, service units, or anything else that
should take precedence over what the backend built, uniformly across all backends.
buildctl handles the merge, not the backends.

```
myapp/
  Dockerfile
  package.yaml
  rootfs/               ← optional skeleton; merged over backend output
    etc/
      mosquitto/
        mosquitto.conf
```

---

## Auto-generated required files

buildctl generates any **missing** required files in the merged rootfs:

| File | Generated from | Condition |
|---|---|---|
| `/etc/os-release` | `package.yaml` (`name`, `version`) | Generated if missing; validated if present (`ID=<name>`, `VERSION_ID=<version>` must match the metadata) |
| `/usr/lib/systemd/system/<name>.service` | `package.yaml` (`command` field) | Generated if missing AND `command` is set |
| `/usr/share/<name>/package.yaml` | Always embedded by buildctl | Always |

**Service unit precedence:** a developer-provided unit (in `rootfs/` or backend
output) takes precedence. When a unit is present, `command` is ignored. The developer
has full control when they want it; buildctl only fills the gap when no unit exists.

---

## Build pipeline (backend-agnostic)

Once the backend produces a filesystem tree, buildctl runs the same pipeline regardless
of which backend was used:

```
buildctl build <dir>
```

```
                 ┌─ Docker / mkosi / shell / make   ─┐
                 │   produces a rootfs tree           │
                 └────────────────────────────────────┘
                                   │
                                   ↓   CONVERGENCE POINT: validated rootfs directory
                                   ↓
       1. merge rootfs/ skeleton (if provided; skeleton overrides backend output)
       2. generate missing required files (os-release, service unit from command)
       3. validate contents (os-release match, service unit present, no User=/Group=)
       4. chown 0:0 -R
       5. embed package.yaml at /usr/share/<name>/package.yaml
       6. create squashfs (pure Go, zstd)
       7. compute dm-verity hash tree + roothash (pure Go)
       8. sign roothash with PKCS7 (pure Go, go.mozilla.org/pkcs7, SHA256)
       9. create DDI: GPT(root + verity + signature partitions), protective MBR
          set partition GUIDs from roothash (root = first 128 bits, verity = last 128 bits)
          write signature partition JSON: {rootHash, signature, certificateFingerprint}
      10. generate metadata JSON (<name>_<version>_<arch>.json)
```

Output:

```
<name>_<version>_<arch>.raw
<name>_<version>_<arch>.json
```

Output directory: `./dist/` by default, configurable with `--out`.

### dm-verity single-block roothash

When the squashfs fits in a single data block (`num_data_blocks == 1`), the kernel's
dm-verity uses zero hash-tree levels: the roothash **is** the leaf hash
(`SHA256(salt + data_block)`), not `SHA256(salt + hash_block)`. The vendored verity
encoder handles this special case; buildctl does not pad to force a multi-block tree.

---

## Signing keys

### Build key (high trust, build machine only)

The build key signs the roothash into the DDI signature partition for every package. It
never leaves the build machine.

Generate a build keypair:

```
buildctl key generate --name <repo-name> --out ./keys/
```

Produces `<repo-name>.key` (private, keep secret) and `<repo-name>.crt` (public,
published to repo). The `.key` file must never be:
- Copied to the repo server
- Committed to version control
- Accessible to CI systems without a secrets manager

Treat it like a CA private key.

The **key identifier** is the SHA-256 of the DER-encoded certificate, lowercase hex
(not the certificate serial number). This is what appctl uses for per-key cert lookup
during key rotation, and what populates `certificateFingerprint` in the signature
partition.

### Index key (lower trust, repo host)

The index key signs `index.json.p7s` for each arch index after each publish. It lives on
the repo host and is used automatically by the index update step of `buildctl publish`.

Generate an index keypair on the repo host:

```
buildctl key generate --name <repo-name>-index --index --out ./keys/
```

Produces `<repo-name>-index.key` and `<repo-name>-index.crt`. The `--index` flag marks
this cert as an index-signing key. Store the `.key` on the repo host, publish the
`.crt` alongside the build cert in `keys/`.

A compromised index key cannot forge package signatures; systemd always verifies the
build-key signature inside the DDI at install time. The blast radius of an index key
compromise is limited to catalog manipulation (advertise stale versions, hide packages);
it does not allow injecting malicious package content.

---

## Publish flow

Publishing has two distinct steps, on two different machines.

### Step 1: Push package files (build machine to repo host)

```
buildctl publish --repo <host>:<path> <dist-dir>/<package-files>
```

Rsyncs the package files (the `.raw` DDI + `.json` metadata + `.zip`) to the correct
path on the repo host:

```
rsync -az dist/ <user>@<host>:<repo-root>/images/<arch>/<name>/<version>/
```

The on-repo layout (apps live under `images/`; bases live under `bases/` —
see [Repository](repository.md)):

```
images/<arch>/<name>/<version>/<name>_<version>_<arch>.raw
images/<arch>/<name>/<version>/<name>_<version>_<arch>.json
images/<arch>/<name>/<version>/<name>_<version>_<arch>.zip
```

No index writing happens in this step. No index key is needed on the build machine.

### Step 2: Update the index (repo host, via SSH)

```
buildctl index update --repo <host>:<path> --class images --package <name> --arch <arch>
```

SSHs to the repo host and runs an atomic index update there:

1. Acquire a local lock (`flock`) on the repo's index lock file to prevent concurrent writers
2. Download the current per-arch `images/<arch>/index.json`
3. Add or replace the entry for `<name>` with the new version data (`raw_url`,
   `metadata_url`, `runtime`, `signing_key_id`, size/hash)
4. Write the updated `index.json`
5. Sign it with the index key (local to the repo host):
   ```
   buildctl index sign images/<arch>/index.json --key <repo-name>-index.key
   ```
6. If `repository.json` needs updating (new key, `key_rotation` bump), update and
   re-sign it: `buildctl index sign repository.json --key <repo-name>-index.key`
7. Release the lock

The index key never leaves the repo host. The build machine does not need it.

### Combined publish shorthand

```
buildctl publish --repo <host>:<path> --push --update-index <dist-dir>/
```

Runs both steps in sequence. Equivalent to calling the two commands above.

---

## Incremental index update

`buildctl index update` downloads the current index, patches one entry, and re-signs.
It does not require all packages to be present locally. This is the normal publish
workflow. Full regeneration from scratch is only needed when bootstrapping a new repo
or after an option B key rotation.

---

## Validation

buildctl provides two validation subcommands covering different phases of the build lifecycle.

### buildctl validate project <dir>

Pre-build validation. Checks the source directory without invoking any backend.

- Detects `package.yaml` or `package.json` (error if both present, error if neither present)
- Validates all required fields are present and correctly typed
- Validates `runtime` and `network` are members of their enums
- Validates `lifecycle` block: absent or all values are non-empty unit name strings
- Validates `systemd_profile` is one of the known values
- Validates `resources` estimates are within plausible bounds (advisory warning, not error)
- Validates `version` is valid semver
- Auto-detects the backend (or honors explicit `backend:`) and checks the matching
  source file exists (`Dockerfile`, `mkosi.conf`, `build.sh`, or `Makefile`)
- If `.buildignore` is present: validates pattern syntax

Build fails on any validation error. Warnings are printed but do not block the build.

### buildctl validate image <dist-dir>

Post-build validation. Checks the output in `dist/` after a successful `buildctl build`.

- Verifies the DDI `.raw` and `.json` metadata files are present and correctly named
  (underscore convention)
- Validates the metadata JSON against the package metadata schema
- Validates the DDI partition layout: a protective MBR + GPT with root, verity, and
  signature partitions, each carrying the correct arch-specific type UUID
- Verifies the root and verity partition GUIDs encode the roothash (first / last 128 bits)
- Lists the root partition contents and checks required files inside the image:
  - `/etc/os-release` with `ID=<name>` and `VERSION_ID=<version>` matching the metadata
  - `/usr/lib/systemd/system/<name>.service`
  - `/usr/lib/systemd/system/<name>.socket` if `socket_activation: true`
  - All lifecycle hook unit files declared in the metadata
- Verifies the PKCS7 signature in the signature partition against the provided build
  certificate (SHA256 digest)
- Verifies the dm-verity hash tree against the roothash

```
buildctl validate image ./dist --cert ./keys/myrepo.crt
```

Path comparisons inside the root partition are always case-sensitive, regardless of the
host filesystem. This matters on macOS (HFS+ is case-insensitive by default).

---

## Dockerfile labels (optional)

buildctl reads standard OCI labels from the Docker image to populate metadata fields.
If a label is present and the matching `package.yaml` field is empty, the label value
is used. Explicit `package.yaml` fields always win.

| OCI label | package.yaml field |
|---|---|
| `org.opencontainers.image.title` | `name` |
| `org.opencontainers.image.version` | `version` |
| `org.opencontainers.image.description` | `description` |
| `org.opencontainers.image.url` | `homepage` |
| `org.opencontainers.image.source` | `source_url` |
| `org.opencontainers.image.licenses` | `license` |
| `org.opencontainers.image.vendor` | `publisher` |

These labels are standard practice in Dockerfile authoring; buildctl will use them
if present. They are not required.

---

## Key rotation

See [Security Model: Key Rotation](security-model.md#key-rotation) for the full design.

For builds: `buildctl build --key <new-key>` uses the specified build key. New packages
are signed with the new key; old packages keep their existing signatures. Both certs
must be published in the repo's `keys[]` during the transition window.

For option B (re-sign all): `buildctl rebuild --all` (T65, backlog) re-signs every
package in a local checkout with the current build key and triggers a full index update.
This is documented as an alternative for operators who prefer a clean cut-over on small
repos; option A (gradual rotation) is recommended for most cases.

---

## Distributing buildctl

buildctl is distributed as a Debian package for developer workstations and CI machines.
Install with:

```
apt install buildctl
```

The Debian package is built from `buildctl.git` and published to the Offline Lab
package server. It is not an app package; it is a host-side development tool and does
not use the DDI / portablectl app format.
