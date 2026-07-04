# Architecture and build pipeline

buildctl is a thin wrapper around external build tools that produces a signed DDI. It does not contain a build system of its own; each backend delegates rootfs production to an existing tool (Docker, mkosi, bash, make). buildctl handles the rest: packaging, integrity, signing, and metadata, all in a pure-Go pipeline.

This page describes how the pieces fit together. For the conceptual design and the rationale behind choices like pure-Go and DPS partition layout, see the [build specification](https://offline-lab.com/docs/specs/build/) in the Offline Lab documentation.

## Design constraints

The pipeline is shaped by three constraints, all of them hard:

1. **Must run on macOS.** The core pipeline cannot shell out to `mksquashfs`, `veritysetup`, or `openssl`; they are Linux-only or behave differently across platforms.
2. **No daemon, no CGO.** buildctl is a single statically-linked binary. Cross-compiling it must remain a `GOOS=... GOARCH=... go build`.
3. **systemd-native verification.** The DDI must be verifiable by stock systemd without any buildctl-side runtime. No custom verifier on the device.

The first two dictate the pure-Go library choices. The third dictates the partition layout and signature format.

## Components

```
buildctl
├── cmd/buildctl/             ← cobra CLI; one file per command
├── internal/
│   ├── backend/              ← Backend interface + registry
│   │   ├── docker/           ← docker buildx + export + OCI labels
│   │   ├── shell/            ← bash build.sh
│   │   ├── gnumake/          ← make OUTDIR=...
│   │   └── mkosi/            ← mkosi --output=directory
│   ├── buildignore/          ← .buildignore pattern matcher (moby/patternmatcher)
│   ├── ddi/                  ← squashfs + verity + PKCS7 + GPT assembly
│   ├── verity/               ← vendored dm-verity encoder (Monogon, Apache-2.0)
│   └── repoindex/            ← repo scanning, index building, index writing
└── schema/                   ← PackageConfig, PackageMetadata, repo index types, validation
```

Each backend registers itself from `init()`. The pipeline package does not import any specific backend; `cmd/buildctl/commands/build.go` blank-imports the four built-in backends and `Resolve` in `internal/backend/registry.go` does the rest. See [Build backends](../reference/backends.md).

## Core pure-Go libraries

| Library | What it does |
|---|---|
| [`github.com/diskfs/go-diskfs`](https://github.com/diskfs/go-diskfs) | GPT image creation and partition writing. `ProtectiveMBR: true` is set explicitly; without it, `systemd-dissect` will not identify the image. |
| [`github.com/KarpelesLab/squashfs`](https://github.com/KarpelesLab/squashfs) | squashfs read/write with zstd. Every entry is forced to `uid=0, gid=0` via `SetOwner`. |
| [`go.mozilla.org/pkcs7`](https://github.com/mozilla-services/pkcs7) | PKCS7 signing. SHA-256 is set explicitly (`SetDigestAlgorithm(OIDDigestAlgorithmSHA256)`); the library defaults to SHA-1, which OpenSSL 3.x rejects. |
| vendored `internal/verity` | dm-verity hash tree encoder vendored from [Monogon OS](https://source.monogon.dev/osbase/verity/encoder.go) (Apache-2.0). Byte-compatible with the kernel target and `veritysetup(8)`. |

What still shells out, and why:

- `docker buildx build/create`: the Docker backend. The Docker daemon is the build tool; buildctl drives it.
- `docker run --privileged tonistiigi/binfmt`: optional, via `buildctl init`. Registers QEMU for cross-arch emulation.
- `bash build.sh`, `make`, `mkosi`: the other backends. They are the build tool by design.
- `rsync` / `ssh`: not currently invoked by buildctl; publish is currently filesystem-only.

## Build pipeline

```
package.yaml + backend source
        │
        ▼
loadAndValidateConfig           ← schema load, normalize, validate (errors/warnings)
        │
        ▼
backend.Resolve                 ← explicit 'backend:' or auto-detection
backend.Setup                   ← per-backend (Docker: ensure buildx builder)
        │
        ▼
backend.Build                   ← docker buildx | build.sh | make | mkosi
        │                         (populates a scratch directory)
        ▼
postBuildPipeline               ← backend-agnostic transforms (below)
        │
        ▼
ddi.Build                       ← squashfs → verity → PKCS7 → GPT assembly
        │
        ▼
writePackageMetadata            ← metadata JSON next to the .raw
        │
        ▼
optional createZipFromDist      ← --compress
```

### Post-build pipeline

Runs in fixed order on the scratch directory the backend populated. Each step is a separate function in [`cmd/buildctl/commands/build.go`](https://github.com/offline-lab/buildctl/blob/main/cmd/buildctl/commands/build.go).

1. **Skeleton merge**: if the project has a `rootfs/` directory, walk it and copy every entry into the scratch directory. Regular files overwrite; directories are created if missing; symlinks are recreated with relative targets only (absolute targets are rejected because the DDI mounts at unpredictable paths).
2. **`.buildignore`**: if the project has a `.buildignore`, walk the scratch directory and remove matching paths. Uses `moby/patternmatcher` so the syntax is identical to `.dockerignore`.
3. **Generate `os-release`**: if `/etc/os-release` is absent, write a minimal two-line file (`ID=<name>`, `VERSION_ID=<version>`). If it is present, do not overwrite.
4. **Generate service unit**: if `/usr/lib/systemd/system/<name>.service` is absent AND `package.yaml` has a `command:` field, write a minimal unit. If neither a unit nor a `command:` is provided, fail; a DDI must carry a service unit so `portablectl` knows what to run.
5. **Reject hardcoded User=/Group=**: scan every `.service`, `.socket`, `.timer`, `.target`, `.path` unit in `usr/lib/systemd/system/` and `etc/systemd/system/`. Any line beginning with `User=` or `Group=` (case-insensitive) is an error. appctl injects these at install time based on the allocated runtime user; hardcoding them would defeat the per-app user model.
6. **Validate `os-release` consistency**: if `/etc/os-release` is present (always, after step 3), its `ID=` and `VERSION_ID=` values must match the package name and version. A mismatch means the backend produced an image for a different package and would silently break package management.
7. **Embed `package.yaml`**: copy it to `/usr/share/<name>/package.yaml`. Lets the installed image be inspected without the source repo or the metadata JSON.

Steps 3 and 4 are gap-fillers: they only generate what is missing. A unit file supplied by the backend or the skeleton takes precedence over `command:`, so authors who want full control keep it.

### DDI assembly

[`internal/ddi/build.go`](https://github.com/offline-lab/buildctl/blob/main/internal/ddi/build.go). Five stages, each in its own function:

1. **squashfs**: walk the scratch directory, add every entry to a `squashfs.Writer` (128 KiB block, zstd), force `uid=0, gid=0` on every entry.
2. **verity hash tree**: stream the squashfs through the vendored encoder with a randomly-generated 32-byte salt. Produces the Merkle tree and the roothash.
3. **PKCS7 signature**: sign the hex-encoded roothash with `go.mozilla.org/pkcs7`, detached, SHA-256. The hex form (not the raw bytes) is what systemd reconstructs from the verity-sig partition at verify time.
4. **Signature partition JSON**: `{rootHash, signature, certificateFingerprint}`. `certificateFingerprint` is the SHA-256 of the DER encoding of the signing certificate.
5. **GPT assembly**: create the `.raw` with `go-diskfs`. Three partitions with arch-specific DPS type UUIDs. The root and verity partition GUIDs are derived from the roothash (first / last 128 bits). Protective MBR is enabled. The signature partition is sector-padded.

## Failure modes

The pipeline cleans up after itself. Intermediate files (the standalone squashfs and the standalone hash tree) are removed on the success path and on the error path. The scratch directory is removed with `defer os.RemoveAll`.

`backend.Build` returning `ErrPartialOutput` (an empty scratch directory after a "successful" build) is treated as a hard error: a backend that silently did nothing produces nothing useful.

## Where to read next

- [Build backends](../reference/backends.md): backend contract, per-backend details, how to add one.
- [DDI output and metadata](../reference/ddi-output.md): what is produced and the meaning of each field.
- [Signing and trust model](signing.md): how the PKCS7 chain reaches kernel-enforced dm-verity at attach time.
