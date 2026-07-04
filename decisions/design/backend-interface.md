# Design: buildctl Backend Interface

> **⚠ Superseded (2026-07-05).** The buildctl implementation this document
> specified was removed and the tool redesigned — see
> [ADR-0031](../adr/adr-0031-buildctl-rebuilt-delegated-assembly.md) and the
> [2026-07-04 design session](../conversation/2026-07-04-design-session.md)
> (§12). Assembly is delegated (no pure-Go pipeline), backends are
> docker/mkosi/shell (make cut), and the backend is never auto-detected.
> Kept for historical reference.

Package path: `github.com/offline-lab/buildctl/internal/backend`
Imported by: `cmd/buildctl/*` and `internal/build/*` (the pipeline driver).

This module owns the contract between buildctl and the four build backends
(Docker, mkosi, shell, make). A backend produces exactly one artifact: a
**rootfs directory**. Everything after that — skeleton merge, os-release /
service-unit generation, validation, chown, package.yaml embed, squashfs,
dm-verity, PKCS7 signing, DDI creation — is owned by buildctl and is identical
regardless of which backend produced the tree.

Source of truth for the surrounding pipeline:
- [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §2.4 (backends
  are first-class), §7 (convergence point), §10 (thinnest POC `build.sh` form),
  §14.6 (this design is on the critical path).
- [`pkg-schema-design.md`](./pkg-schema-design.md) §3.2 (`Backend` enum),
  §3.3 (`PackageConfig.Backend` / `BackendArguments`).
- [`specs-ddi-migration.md`](./specs-ddi-migration.md) §2.2 (what `build.md`
  must say about backends post-DDI migration).

> **Doc-debt note.** An earlier internal buildctl design note describes an
> earlier Backend interface without a `Build` method, lists mkosi as backlog
> (T67), and gives auto-detect order as `docker > shell > make > mkosi`. That
> file predates the DDI design session. The order and four-backend scope below
> supersede it.

---

## 1. Scope and non-goals

**In scope**
- The `Backend` Go interface, the `TemplateFile` type, and the sentinel errors.
- The registry: `Register`, `Get`, `Resolve`, `All`.
- The per-backend contracts (Setup, Detect, Build, Templates, RequiredDeps) for
  docker, mkosi, shell, make.
- The **convergence contract**: what `outDir` must contain after `Build`
  returns nil, and what buildctl does to it next.
- Backend lifecycle rules (statelessness, ctx propagation, partial output).

**Non-goals**
- The post-Build pipeline itself (squashfs, verity, signing, DDI). That is
  `internal/build`, specified separately. This doc only defines where that
  pipeline picks up.
- `schema.PackageConfig` validation. Lives in `pkg/schema`.
- Template *content* design (which keys, what defaults). Templates are shown as
  illustrative skeletons; final wording is a `buildctl new` concern, tracked
  separately.
- Future backends (koji, nix, bazel). The interface is designed so they slot
  in via `Register`; their contracts are out of scope here.

---

## 2. The convergence point

Every backend, regardless of how it builds, hands buildctl the same shape:

```
Dockerfile  ─→ docker buildx build → docker export ──→ rootfs dir ─┐
mkosi.conf  ─→ mkosi --output=directory             ──→ rootfs dir ─┤
build.sh    ─→ bash build.sh <outDir>               ──→ rootfs dir ─┤
Makefile    ─→ make OUTDIR=<outDir>                 ──→ rootfs dir ─┘
                                                                    │
                            ┌───────────────────────────────────────┘
                            │  CONVERGENCE POINT
                            ↓
                    buildctl pipeline (backend-agnostic):
                      merge rootfs/ skeleton (skeleton wins)
                      generate missing os-release / service unit
                      validate (os-release match, unit exists, no User=)
                      apply .buildignore
                      chown 0:0 -R
                      embed package.yaml at /usr/share/<name>/package.yaml
                      squashfs → dm-verity → PKCS7 → DDI
```

The backend's `Build` method is the only backend-specific step. It runs once
per `buildctl build` invocation, per arch. It receives an empty `outDir`
(created by buildctl) and must populate it with a filesystem tree that looks
like the root of a Linux system (`/usr/...`, `/etc/...`, etc.).

---

## 3. The Backend interface

```go
package backend

import (
    "context"
    "fmt"
    "os"

    "github.com/offline-lab/pkg/schema"
)

type Backend interface {
    Name() string
    SourceFile() string
    Detect(dir string) bool
    RequiredDeps() []string
    Setup(cfg *schema.PackageConfig, dir string) error
    Templates() []TemplateFile
    Build(ctx context.Context, cfg *schema.PackageConfig, srcDir string, arch string, outDir string, args map[string]any) (*BuildResult, error)
}

type TemplateFile struct {
    Path    string
    Content string
    Mode    os.FileMode
}

// BuildResult carries structured post-build data from the backend to the
// pipeline driver. Backends with nothing to report return &BuildResult{}, nil.
type BuildResult struct {
    // OCILabels carries Docker OCI image labels when the docker backend
    // is used. Used for metadata fallbacks (description, license, source
    // URL). Explicit package.yaml fields always win. nil for non-docker
    // backends.
    OCILabels map[string]string

    // ImageDigest is the docker image digest (sha256:...) when the docker
    // backend is used. Empty for other backends.
    ImageDigest string
}

var (
    ErrUnknownBackend = fmt.Errorf("backend: unknown backend")
    ErrNoBackend      = fmt.Errorf("backend: no backend detected and none specified in package.yaml")
    ErrPartialOutput  = fmt.Errorf("backend: build produced partial output")
)
```

Method contracts:

| Method | Pure? | When called | Notes |
|---|---|---|---|
| `Name()` | yes | registry key, logging, error messages | Constant per implementation. Matches a `schema.Backend` enum value. |
| `SourceFile()` | yes | `validate project`, `Detect` fallback, template rendering | The conventional filename this backend looks for (`Dockerfile`, `mkosi.conf`, `build.sh`, `Makefile`). Lowercase, exact match. |
| `Detect(dir)` | yes, must touch only `dir` | `Resolve` (when `cfg.Backend` empty); `validate project` | Returns true iff this backend can drive the project. See §6 for the per-backend predicate. |
| `RequiredDeps()` | yes | `buildctl init`, `buildctl build` (preflight) | External binaries the backend shells out to. buildctl reports missing deps; never installs. |
| `Setup(cfg, dir)` | side-effectful, idempotent | `buildctl init`, first `buildctl build` per machine | One-time host configuration (buildx builder, binfmt handlers, mkosi cache warmup, etc.). Re-running must be a no-op or near-no-op. |
| `Templates()` | yes | `buildctl new` | Files to write into a fresh project for this backend. Always includes `package.yaml` plus the backend's source file. |
| `Build(...)` | side-effectful, populates `outDir` | `buildctl build`, once per arch | THE method. Returns `*BuildResult` carrying structured post-build data (OCI labels, image digest). See §12 for the contract on `outDir`. |

The interface is deliberately stateless on the receiver: a `Backend` instance
is a singleton registered at process start (see §5) and may be invoked
concurrently by separate `buildctl build` processes or future parallel-arch
builds. Per-build data (container IDs, image digests, OCI labels) must NOT
live on the struct; it flows through the `*BuildResult` return value (see §11).

---

## 4. Auto-detection order and `Resolve`

```go
package backend

import (
    "github.com/offline-lab/pkg/schema"
)

var detectionOrder = []string{
    string(schema.BackendDocker),
    string(schema.BackendMkosi),
    string(schema.BackendShell),
    string(schema.BackendMake),
}

func Resolve(cfg *schema.PackageConfig, dir string) (Backend, error) {
    if cfg.Backend != "" {
        return Get(string(cfg.Backend))
    }
    for _, name := range detectionOrder {
        candidate, err := Get(name)
        if err != nil {
            continue
        }
        if candidate.Detect(dir) {
            return candidate, nil
        }
    }
    return nil, ErrNoBackend
}
```

Order rationale (`docker > mkosi > shell > make`):

1. **docker** — most common entry point for app authors; a `Dockerfile` is an
   unambiguous signal. Honored first to avoid surprises when a project happens
   to also contain a `Makefile` (e.g. for unrelated dev tasks).
2. **mkosi** — systemd ecosystem native; `mkosi.conf` is unambiguous and rarely
   appears incidentally. Honored before shell/make so a systemd-native project
   isn't accidentally picked up by the more generic backends.
3. **shell** — `build.sh` is generic but the conventional name is specific
   enough that false positives are rare. Honored before make because a project
   with both `build.sh` and `Makefile` almost always intends `build.sh` to be
   the entry point and `Makefile` to be a wrapper.
4. **make** — `Makefile` is the most overloaded filename in the Unix world;
   detected last so a project that uses make for unrelated purposes (docs,
   tests, packaging) only gets the make backend when nothing else fits.

`Resolve` is called once per `buildctl build`, after `config.Load` +
`schema.Validate`. If `cfg.Backend` is set, `Resolve` skips detection entirely
and goes straight to `Get` — this is the override path for projects that
intentionally keep multiple backend source files (e.g. a `Dockerfile` for
production and a `Makefile` for dev). `Get` on an unknown name returns
`ErrUnknownBackend`; the caller surfaces it as a `package.yaml` validation
error.

---

## 5. Registry

```go
package backend

import (
    "sort"
    "sync"
)

var (
    registryMu sync.RWMutex
    registry   = map[string]Backend{}
)

func Register(b Backend) {
    registryMu.Lock()
    defer registryMu.Unlock()
    registry[b.Name()] = b
}

func Get(name string) (Backend, error) {
    registryMu.RLock()
    defer registryMu.RUnlock()
    b, ok := registry[name]
    if !ok {
        return nil, fmt.Errorf("%w: %q", ErrUnknownBackend, name)
    }
    return b, nil
}

func All() []Backend {
    registryMu.RLock()
    defer registryMu.RUnlock()
    out := make([]Backend, 0, len(registry))
    names := make([]string, 0, len(registry))
    for name := range registry {
        names = append(names, name)
    }
    sort.Strings(names)
    for _, name := range names {
        out = append(out, registry[name])
    }
    return out
}
```

Registration is performed by each backend package's `init()`:

```go
package docker

import "github.com/offline-lab/buildctl/internal/backend"

func init() {
    backend.Register(Backend{})
}
```

The top-level binary pulls them in with blank imports so the `init` functions
run:

```go
package main

import (
    _ "github.com/offline-lab/buildctl/internal/backend/docker"
    _ "github.com/offline-lab/buildctl/internal/backend/make"
    _ "github.com/offline-lab/buildctl/internal/backend/mkosi"
    _ "github.com/offline-lab/buildctl/internal/backend/shell"
)
```

This pattern keeps the registry open for extension (a future out-of-tree
backend could `Register` itself the same way) while making the default set
discoverable in one place. `All()` returns a deterministic, alphabetically
sorted slice for `buildctl new --help` and `buildctl init` listing.

---

## 6. The `Detect` predicates

Each backend's `Detect` is a single `os.Stat` of its `SourceFile`. No fuzzy
matching, no content sniffing. The conventional filename is the contract.

```go
package docker

import (
    "os"
    "path/filepath"
)

func (Backend) Detect(dir string) bool {
    info, err := os.Stat(filepath.Join(dir, "Dockerfile"))
    return err == nil && !info.IsDir()
}
```

The same shape applies to mkosi (`mkosi.conf`), shell (`build.sh`), make
(`Makefile`). The `!info.IsDir()` guard rejects the rare case of a
`Makefile/` directory (some monorepo layouts use this); the backend then
falls through and the next detector runs.

Detect must not parse file contents. Reason: detection runs on every
`buildctl build` and `validate project`; parsing is wasted work and creates
false positives (a `Dockerfile` with a syntax error is still a Docker
project — the error surfaces at `Build`, where it belongs).

---

## 7. Backend: docker

| Aspect | Value |
|---|---|
| `Name()` | `"docker"` |
| `SourceFile()` | `"Dockerfile"` |
| `RequiredDeps()` | `["docker"]` (buildx is configured by `Setup`, not assumed) |
| `Setup` side effects | `docker buildx create --use` (idempotent); `docker run --privileged --rm tonistiigi/binfmt --install all` (idempotent) |

### 7.1 Type, metadata methods, and helpers

```go
package docker

import (
    "fmt"
    "path/filepath"
    "strings"

    "github.com/offline-lab/pkg/schema"
)

type Backend struct{}

func (Backend) Name() string       { return "docker" }
func (Backend) SourceFile() string { return "Dockerfile" }

func (Backend) RequiredDeps() []string { return []string{"docker"} }

var archToPlatform = map[schema.Arch]string{
    schema.ArchArm64:   "linux/arm64",
    schema.ArchArmV7:   "linux/arm/v7",
    schema.ArchArmV6:   "linux/arm/v6",
    schema.ArchAmd64:   "linux/amd64",
    schema.ArchI386:    "linux/386",
    schema.ArchRiscV64: "linux/riscv64",
    schema.ArchPpc64LE: "linux/ppc64le",
    schema.ArchS390x:   "linux/s390x",
}

func (Backend) platform(arch string) (string, error) {
    platform, ok := archToPlatform[schema.Arch(arch)]
    if !ok {
        return "", fmt.Errorf("docker: unsupported arch %q", arch)
    }
    return platform, nil
}

func safeJoin(base string, name string) (string, error) {
    cleaned := filepath.Clean(string(filepath.Separator) + name)
    if strings.HasPrefix(cleaned, "..") {
        return "", fmt.Errorf("tar: path escapes root: %q", name)
    }
    return filepath.Join(base, cleaned), nil
}
```

The `safeJoin` helper rejects tar entries whose cleaned form escapes `base`.
A header named `../../etc/passwd` is cleaned to `/etc/passwd` (the leading
`/` is prepended, then `filepath.Clean` normalizes), then joined inside
`outDir`; the result can never land outside `outDir`. Symlink targets are
not dereferenced at extraction time — that is the docker daemon's job; we
trust the daemon's export.

### 7.2 `Setup`

```go
package docker

import (
    "fmt"
    "os/exec"

    "github.com/offline-lab/pkg/schema"
)

func (Backend) Setup(cfg *schema.PackageConfig, dir string) error {
    if err := ensureBuilder(); err != nil {
        return fmt.Errorf("docker setup: buildx builder: %w", err)
    }
    if err := ensureBinfmt(); err != nil {
        return fmt.Errorf("docker setup: binfmt: %w", err)
    }
    return nil
}

func ensureBuilder() error {
    cmd := exec.Command("docker", "buildx", "inspect", "--bootstrap", "buildctl")
    if cmd.Run() == nil {
        return nil
    }
    create := exec.Command("docker", "buildx", "create", "--name", "buildctl", "--use")
    return create.Run()
}

func ensureBinfmt() error {
    cmd := exec.Command("docker", "run", "--privileged", "--rm", "tonistiigi/binfmt", "--install", "all")
    return cmd.Run()
}
```

`buildx inspect --bootstrap` exits non-zero if the named builder does not
exist, so the create step runs only when needed. Re-running `buildctl init`
on an already-configured host is a no-op apart from a `buildx inspect` call
(cheap) and a binfmt install that re-registers already-registered handlers
(also cheap; the kernel dedupes).

The `--install all` form registers every QEMU handler tonistiigi/binfmt
ships, not just `arm64`. Cost is identical on first run and makes the host
ready for any future arch without re-running setup. If a minimal install is
desired later, swap to `--install arm64,arm,v7` etc. — local decision.

### 7.3 `Build`

```go
package docker

import (
    "archive/tar"
    "context"
    "encoding/json"
    "fmt"
    "io"
    "os"
    "os/exec"
    "path/filepath"
    "strings"

    "github.com/offline-lab/buildctl/internal/backend"
    "github.com/offline-lab/pkg/schema"
)

func (b Backend) Build(ctx context.Context, cfg *schema.PackageConfig, srcDir string, arch string, outDir string, args map[string]any) (*backend.BuildResult, error) {
    tag := fmt.Sprintf("buildctl-%s:%s-%s", cfg.Name, cfg.Version, arch)
    platform, err := b.platform(arch)
    if err != nil {
        return nil, err
    }

    buildArgs, dockerfile, target := parseArgs(args)
    buildCmd := exec.CommandContext(ctx, "docker", "buildx", "build")
    buildCmd.Args = append(buildCmd.Args,
        "--platform", platform,
        "--tag", tag,
        "--load",
    )
    for _, pair := range buildArgs {
        buildCmd.Args = append(buildCmd.Args, "--build-arg", pair)
    }
    if dockerfile != "" {
        buildCmd.Args = append(buildCmd.Args, "--file", filepath.Join(srcDir, dockerfile))
    }
    if target != "" {
        buildCmd.Args = append(buildCmd.Args, "--target", target)
    }
    buildCmd.Args = append(buildCmd.Args, srcDir)
    buildCmd.Stdout = os.Stderr
    buildCmd.Stderr = os.Stderr
    if err := buildCmd.Run(); err != nil {
        return nil, fmt.Errorf("docker build: %w", err)
    }

    containerID, err := createContainer(ctx, tag)
    if err != nil {
        return nil, err
    }
    defer func() {
        _ = exec.CommandContext(ctx, "docker", "rm", "-f", containerID).Run()
    }()

    if err := exportContainer(ctx, containerID, outDir); err != nil {
        return nil, err
    }

    labels, err := inspectLabels(ctx, tag)
    if err != nil {
        return nil, err
    }
    return &backend.BuildResult{OCILabels: labels}, nil
}

func createContainer(ctx context.Context, tag string) (string, error) {
    cmd := exec.CommandContext(ctx, "docker", "create", "--entrypoint", "/bin/true", tag)
    var out strings.Builder
    cmd.Stdout = &out
    cmd.Stderr = os.Stderr
    if err := cmd.Run(); err != nil {
        return "", fmt.Errorf("docker create: %w", err)
    }
    return strings.TrimSpace(out.String()), nil
}

func exportContainer(ctx context.Context, containerID string, outDir string) error {
    cmd := exec.CommandContext(ctx, "docker", "export", containerID)
    cmd.Stderr = os.Stderr
    pipe, err := cmd.StdoutPipe()
    if err != nil {
        return err
    }
    if err := cmd.Start(); err != nil {
        return fmt.Errorf("docker export: %w", err)
    }
    if err := extractTar(pipe, outDir); err != nil {
        _ = cmd.Process.Kill()
        return fmt.Errorf("docker export: extract: %w", err)
    }
    return cmd.Wait()
}

func extractTar(reader io.Reader, outDir string) error {
    tr := tar.NewReader(reader)
    for {
        header, err := tr.Next()
        if err == io.EOF {
            return nil
        }
        if err != nil {
            return err
        }
        path, err := safeJoin(outDir, header.Name)
        if err != nil {
            continue
        }
        switch header.Typeflag {
        case tar.TypeDir:
            if err := os.MkdirAll(path, os.FileMode(header.Mode)&0o777|0o700); err != nil {
                return err
            }
        case tar.TypeSymlink:
            if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
                return err
            }
            if err := os.Symlink(header.Linkname, path); err != nil && !os.IsExist(err) {
                return err
            }
        case tar.TypeReg, tar.TypeRegA:
            if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
                return err
            }
            file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, os.FileMode(header.Mode)&0o777|0o600)
            if err != nil {
                return err
            }
            if _, err := io.Copy(file, tr); err != nil {
                file.Close()
                return err
            }
            file.Close()
        default:
            if _, err := io.Copy(io.Discard, tr); err != nil {
                return err
            }
        }
    }
}

func inspectLabels(ctx context.Context, tag string) (map[string]string, error) {
    cmd := exec.CommandContext(ctx, "docker", "inspect", "--format", "{{json .Config.Labels}}", tag)
    var out strings.Builder
    cmd.Stdout = &out
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("docker inspect: %w", err)
    }
    raw := strings.TrimSpace(out.String())
    if raw == "null" || raw == "" {
        return nil, nil
    }
    var labels map[string]string
    if err := json.Unmarshal([]byte(raw), &labels); err != nil {
        return nil, fmt.Errorf("docker inspect: parse labels: %w", err)
    }
    return labels, nil
}

func parseArgs(args map[string]any) (buildArgs []string, dockerfile string, target string) {
    if args == nil {
        return nil, "", ""
    }
    if raw, ok := args["build_args"].(map[string]any); ok {
        for key, value := range raw {
            buildArgs = append(buildArgs, fmt.Sprintf("%s=%v", key, value))
        }
    }
    if s, ok := args["dockerfile"].(string); ok {
        dockerfile = s
    }
    if s, ok := args["target"].(string); ok {
        target = s
    }
    return
}
```

Notes on the implementation:

- `docker buildx build --load` is correct because each `Build` invocation
  targets exactly one arch; `--load` is the documented single-platform loader.
  Multi-arch manifest lists are a repo/index concern, not a buildctl concern.
- `docker create` (not `docker run`) avoids starting the container's
  entrypoint. `--entrypoint /bin/true` defends against images whose default
  entrypoint would error on a missing cmd. We never start the container.
- The container is removed in a `defer`; `docker rm -f` on an already-removed
  ID is a harmless no-op. This guarantees no container accumulation across
  builds, including build failure and ctrl-C.
- `extractTar` rejects paths that escape `outDir` via `safeJoin` (defined in
  §7.1). `tar` extraction is the classic path-traversal vector; the docker
  daemon is trusted, but a maliciously-crafted image layer could still carry
  `../../etc/passwd` entries.
  The mode bits are masked so a hostile tar header setting mode `0o777` on a
  directory cannot create a world-writable tree.
- stdout/stderr of `buildx build` and `docker export` are streamed to
  `os.Stderr` (the buildctl progress channel), not buffered. CI logs would be
  useless otherwise. Only `docker create` (container ID) and `docker inspect`
  (labels) capture stdout, because their stdout is the data we parse.

### 7.4 OCI label escape via BuildResult

`inspectLabels` reads OCI image labels from the built image. The labels flow
back to the pipeline driver through `BuildResult.OCILabels` — no sidecar file,
no separate read step. buildctl's pipeline driver applies the OCI label
fallbacks to the metadata being assembled (explicit `package.yaml` fields
always win) immediately after `Build` returns.

The `inspectLabels` function itself is unchanged:

```go
func inspectLabels(ctx context.Context, tag string) (map[string]string, error) {
    cmd := exec.CommandContext(ctx, "docker", "inspect", "--format", "{{json .Config.Labels}}", tag)
    var out strings.Builder
    cmd.Stdout = &out
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("docker inspect: %w", err)
    }
    raw := strings.TrimSpace(out.String())
    if raw == "null" || raw == "" {
        return nil, nil
    }
    var labels map[string]string
    if err := json.Unmarshal([]byte(raw), &labels); err != nil {
        return nil, fmt.Errorf("docker inspect: parse labels: %w", err)
    }
    return labels, nil
}
```

If `inspectLabels` returns `nil` (image has no labels), `BuildResult.OCILabels`
is nil and the fallback step is a no-op. See §11 for why `*BuildResult` was
chosen over a sidecar file or optional interface.

### 7.5 Templates

```go
package docker

import "os"

func (Backend) Templates() []backend.TemplateFile {
    return []backend.TemplateFile{
        {
            Path:    "Dockerfile",
            Mode:    0o644,
            Content: dockerfileTemplate,
        },
        {
            Path:    "package.yaml",
            Mode:    0o644,
            Content: packageYamlTemplate,
        },
    }
}

const dockerfileTemplate = `FROM {{ .RuntimeBaseImage | default "debian:stable-slim" }} AS build
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY . /src
WORKDIR /src
RUN make install DESTDIR=/out

FROM {{ .RuntimeBaseImage | default "debian:stable-slim" }}
COPY --from=build /out/ /
RUN mkdir -p /etc /usr/lib/systemd/system
LABEL org.opencontainers.image.title="{{ .Name }}"
      org.opencontainers.image.version="{{ .Version }}"
      org.opencontainers.image.description="{{ .Description }}"
      org.opencontainers.image.vendor="{{ .Publisher }}"
`

const packageYamlTemplate = `spec_version: "1"
name: {{ .Name }}
version: {{ .Version }}
arch: {{ .Arch }}
description: {{ .Description }}
publisher: {{ .Publisher }}
backend: docker
runtime: portable
command: /usr/local/bin/{{ .Name }}
`
```

The Dockerfile template builds in a separate stage and copies only the
`DESTDIR`-installed output into a clean runtime image. This is the canonical
multi-stage pattern that yields a small rootfs free of build dependencies —
which matters because buildctl's squashfs includes *everything* in the image's
final layer.

### 7.6 Cross-arch

Cross-architecture builds rely on the binfmt handlers registered in `Setup`.
`b.platform(arch)` (omitted) maps `schema.Arch` to the `linux/<arch>` form
Docker expects:

| `schema.Arch` | Docker platform |
|---|---|
| `arm64` | `linux/arm64` |
| `armv7` | `linux/arm/v7` |
| `armv6` | `linux/arm/v6` |
| `amd64` | `linux/amd64` |
| `i386` | `linux/386` |
| `riscv64` | `linux/riscv64` |
| `ppc64le` | `linux/ppc64le` |
| `s390x` | `linux/s390x` |

buildctl calls `Build` once per arch in `cfg.Arch` (today: exactly one). The
binfmt path is transparent — `buildx build --platform linux/arm64` on an
amd64 host routes through QEMU automatically once handlers are registered.

---

## 8. Backend: mkosi

| Aspect | Value |
|---|---|
| `Name()` | `"mkosi"` |
| `SourceFile()` | `"mkosi.conf"` |
| `RequiredDeps()` | `["mkosi"]` (v22+ required) |
| `Setup` side effects | none (no-op) |

mkosi is the systemd ecosystem's image builder. Unlike docker, it has no
runtime daemon and no cross-arch emulation layer; it assembles a rootfs from
distro package repositories (debootstrap, dnf, pacman, etc.) on the host
directly. This makes it the natural choice for systemd-native apps and for
apps that ship as distro packages rather than container images.

### 8.1 Critical constraint: directory output

mkosi can emit many output formats (tar, squashfs, disk image with GPT, plain
directory). buildctl requires the **directory** form. mkosi must not produce a
squashfs or a disk image; that is buildctl's job and buildctl does it
byte-compatibly across all backends. The mkosi backend enforces this by
passing `--output=directory` on the command line, overriding anything in
`mkosi.conf`.

```go
package mkosi

import (
    "context"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"
    "strings"

    "github.com/offline-lab/buildctl/internal/backend"
    "github.com/offline-lab/pkg/schema"
)

type Backend struct{}

func init() {
    backend.Register(Backend{})
}

func (Backend) Name() string       { return "mkosi" }
func (Backend) SourceFile() string { return "mkosi.conf" }

func (Backend) RequiredDeps() []string { return []string{"mkosi"} }

func (Backend) Detect(dir string) bool {
    info, err := os.Stat(filepath.Join(dir, "mkosi.conf"))
    return err == nil && !info.IsDir()
}

func (Backend) Setup(cfg *schema.PackageConfig, dir string) error {
    return nil
}

func (b Backend) Build(ctx context.Context, cfg *schema.PackageConfig, srcDir string, arch string, outDir string, args map[string]any) (*backend.BuildResult, error) {
    if err := b.checkOutputConflict(srcDir); err != nil {
        return nil, err
    }
    cmd := exec.CommandContext(ctx, "mkosi",
        "--output=directory",
        "--output-directory="+outDir,
    )
    if extra, ok := args["extra_args"].([]any); ok {
        for _, value := range extra {
            if s, ok := value.(string); ok {
                cmd.Args = append(cmd.Args, s)
            }
        }
    }
    cmd.Dir = srcDir
    cmd.Stdout = os.Stderr
    cmd.Stderr = os.Stderr
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("mkosi: %w", err)
    }
    return &backend.BuildResult{}, nil
}

func (Backend) checkOutputConflict(srcDir string) error {
    data, err := os.ReadFile(filepath.Join(srcDir, "mkosi.conf"))
    if err != nil {
        return nil
    }
    for _, line := range strings.Split(string(data), "\n") {
        trimmed := strings.TrimSpace(line)
        if strings.HasPrefix(trimmed, "Output=") && !strings.EqualFold(trimmed, "Output=directory") {
            return fmt.Errorf("mkosi: mkosi.conf sets %q; buildctl requires Output=directory (the squashfs/DDI step is buildctl's job)", trimmed)
        }
    }
    return nil
}
```

The `checkOutputConflict` guard refuses to silently override an explicit
`Output=` line in `mkosi.conf`. If a packager wrote `Output=squashfs` and
buildctl overrode it, the resulting DDI would not match what they intended.
Bail loudly instead.

### 8.2 Cross-arch

mkosi has no QEMU bridge. Cross-arch builds require either running buildctl on
a host of the target arch, or wrapping mkosi in `qemu-user-static` /
`systemd-nspawn -M` chroots manually. The mkosi backend does not implement
either; if `arch != runtime.GOARCH`, `Build` returns an explicit error
explaining that mkosi cross-arch is the packager's responsibility. This is
honest: a half-working cross-arch path would be worse than none. docker is
the recommended backend for cross-arch builds from a single host.

### 8.3 Templates

```go
const mkosiConfTemplate = `[Distribution]
Distribution=debian
Release=bookworm

[Output]
Format=directory

[Content]
Packages=
        {{ .Name }}
        systemd
        systemd-sysusers
        dbus
WithDocs=no
CleanPackageMetadata=yes

[Config]
ImageVersion={{ .Version }}
`
```

The mkosi template sets `Format=directory` (mkosi's INI synonym for the
`--output=directory` CLI flag) so the two agree even if the user removes the
CLI guard. `ImageVersion=` wires mkosi's own versioning to package.yaml's.

---

## 9. Backend: shell

| Aspect | Value |
|---|---|
| `Name()` | `"shell"` |
| `SourceFile()` | `"build.sh"` |
| `RequiredDeps()` | `["bash"]` |
| `Setup` side effects | none (no-op) |

The shell backend is the thinnest possible contract: buildctl invokes a
script with one argument (the absolute path to `outDir`), and the script is
responsible for populating that directory with a rootfs tree. This is the
backend used in the thinnest POC ([design session 2026-06-15](../conversation/2026-06-15-design-session.md) §10).

```go
package shell

import (
    "context"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"

    "github.com/offline-lab/buildctl/internal/backend"
    "github.com/offline-lab/pkg/schema"
)

type Backend struct{}

func init() {
    backend.Register(Backend{})
}

func (Backend) Name() string       { return "shell" }
func (Backend) SourceFile() string { return "build.sh" }

func (Backend) RequiredDeps() []string { return []string{"bash"} }

func (Backend) Detect(dir string) bool {
    info, err := os.Stat(filepath.Join(dir, "build.sh"))
    return err == nil && !info.IsDir()
}

func (Backend) Setup(cfg *schema.PackageConfig, dir string) error {
    return nil
}

func (Backend) Build(ctx context.Context, cfg *schema.PackageConfig, srcDir string, arch string, outDir string, args map[string]any) (*backend.BuildResult, error) {
    scriptPath := filepath.Join(srcDir, "build.sh")
    cmd := exec.CommandContext(ctx, "bash", "-eu", "-o", "pipefail", scriptPath, outDir)
    cmd.Dir = srcDir
    cmd.Stdout = os.Stderr
    cmd.Stderr = os.Stderr
    cmd.Env = append(os.Environ(),
        "BUILDCTL_ARCH="+arch,
        "BUILDCTL_NAME="+cfg.Name,
        "BUILDCTL_VERSION="+cfg.Version,
    )
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("build.sh: %w", err)
    }
    return &backend.BuildResult{}, nil
}
```

Notes:

- `bash -eu -o pipefail` enforces strict mode at the wrapper level. A
  `build.sh` that begins with `set -eu` is unaffected; one that *relied* on
  unset variables or non-zero returns continuing silently would break. That
  breakage is desirable: rootfs construction is the wrong place for
  lenient-shell behavior.
- `outDir` is passed as `$1`. The thinnest POC script reads it via
  `out="$1"`. The script must `mkdir -p` its own subtrees; buildctl hands it
  an empty directory.
- The three `BUILDCTL_*` env vars are conveniences for scripts that want to
  parameterize without re-parsing `package.yaml`. They are advisory; the
  script is free to ignore them and read `package.yaml` directly via yq or
  similar.
- `args["interpreter"]` could swap `bash` for `sh`, `python`, or another
  interpreter. This is **not** implemented in v1: `build.sh` means bash,
  full stop. Adding interpreter swapping opens an unbounded surface (Python
  build scripts would deserve their own backend, not an env var). The field
  is reserved in `args` but ignored.

### 9.1 Templates

```go
const buildShTemplate = `#!/usr/bin/env bash
set -euo pipefail

out="$1"

mkdir -p "$out/usr/bin" "$out/usr/lib/systemd/system" "$out/etc"

install -m 0755 /dev/stdin "$out/usr/bin/{{ .Name }}" <<'EOF'
#!/usr/bin/env bash
while true; do
    echo "{{ .Name }} running"
    sleep 1
done
EOF

cat > "$out/usr/lib/systemd/system/{{ .Name }}.service" <<EOF
[Unit]
Description={{ .Description }}

[Service]
ExecStart=/usr/bin/{{ .Name }}
Restart=always

[Install]
WantedBy=multi-user.target
EOF
`
```

The shell template intentionally does not write `/etc/os-release` or embed
`package.yaml`: both are buildctl's job (see §12). Templates teach the
author the *script-level* contract, not the *rootfs-level* one.

---

## 10. Backend: make

| Aspect | Value |
|---|---|
| `Name()` | `"make"` |
| `SourceFile()` | `"Makefile"` |
| `RequiredDeps()` | `["make"]` (GNU make required; BSD make will not do) |
| `Setup` side effects | none (no-op) |

The make backend exists for projects that already have a Makefile as the
canonical build entry point (most C/C++ apps, many Go apps, anything
originating in a distro packaging workflow). buildctl invokes the default
target with `OUTDIR=<outDir>` overriding an empty variable; the Makefile's
default target installs into `$(OUTDIR)`.

```go
package gnumake

import (
    "context"
    "fmt"
    "os"
    "os/exec"
    "path/filepath"

    "github.com/offline-lab/buildctl/internal/backend"
    "github.com/offline-lab/pkg/schema"
)

type Backend struct{}

func init() {
    backend.Register(Backend{})
}

func (Backend) Name() string       { return "make" }
func (Backend) SourceFile() string { return "Makefile" }

func (Backend) RequiredDeps() []string { return []string{"make"} }

func (Backend) Detect(dir string) bool {
    info, err := os.Stat(filepath.Join(dir, "Makefile"))
    return err == nil && !info.IsDir()
}

func (Backend) Setup(cfg *schema.PackageConfig, dir string) error {
    return nil
}

func (Backend) Build(ctx context.Context, cfg *schema.PackageConfig, srcDir string, arch string, outDir string, args map[string]any) (*backend.BuildResult, error) {
    cmd := exec.CommandContext(ctx, "make", "OUTDIR="+outDir)
    if target, ok := args["target"].(string); ok && target != "" {
        cmd.Args = append(cmd.Args, target)
    }
    if extra, ok := args["extra_args"].([]any); ok {
        for _, value := range extra {
            if s, ok := value.(string); ok {
                cmd.Args = append(cmd.Args, s)
            }
        }
    }
    cmd.Dir = srcDir
    cmd.Stdout = os.Stderr
    cmd.Stderr = os.Stderr
    cmd.Env = append(os.Environ(),
        "BUILDCTL_ARCH="+arch,
        "BUILDCTL_NAME="+cfg.Name,
        "BUILDCTL_VERSION="+cfg.Version,
    )
    if err := cmd.Run(); err != nil {
        return nil, fmt.Errorf("make: %w", err)
    }
    return &backend.BuildResult{}, nil
}
```

Notes:

- `make OUTDIR=<outDir>` passes `OUTDIR` as a command-line variable
  assignment, which (per POSIX make) overrides any assignment inside the
  Makefile and is exported to recipe commands. The Makefile reads `$(OUTDIR)`
  in make context and `$OUTDIR` in shell recipes.
- No explicit target means the default (first) target runs. The Makefile
  template makes that the install target. `args["target"]` lets a project
  override (e.g. `target: package` if the project has a dedicated
  rootfs-producing target).
- GNU make is required. BSD make has incompatible directive syntax (`!=` vs
  `$(shell ...)`, no `define`/`endef` recipe blocks). The dep check should
  verify `make --version` reports GNU make; omitted here for brevity.

### 10.1 Package naming

The Go package containing this backend is named `gnumake`, not `make` —
`make` is a Go predeclared builtin and reserved as a package name. The
directory is `internal/backend/make/` (directories have no reserved-word
restriction and the on-disk path is the user-facing one). An earlier internal buildctl design note suggested `make_`; trailing
underscores violate the Go style guide and are discouraged. `gnumake` is
honest about what it wraps (GNU Make, not POSIX make, not BSD make).

### 10.2 Templates

```go
const makefileTemplate = `.PHONY: all install clean

OUTDIR ?= 
DESTDIR ?= $(OUTDIR)
PREFIX ?= /usr

all: install

install:
	@echo "OUTDIR=$(OUTDIR)"
	@[ -n "$(OUTDIR)" ] || { echo "OUTDIR is empty"; exit 1; }
	install -d "$(OUTDIR)$(PREFIX)/bin"
	install -d "$(OUTDIR)$(PREFIX)/lib/systemd/system"
	install -d "$(OUTDIR)/etc"
	install -m 0755 {{ .Name }} "$(OUTDIR)$(PREFIX)/bin/{{ .Name }}"
	sed -e 's,@PREFIX@,$(PREFIX),' \
	    {{ .Name }}.service.in > "$(OUTDIR)$(PREFIX)/lib/systemd/system/{{ .Name }}.service"

clean:
	rm -rf "$(OUTDIR)"
`
```

The `OUTDIR ?=` line lets a developer run `make OUTDIR=/tmp/foo` ad-hoc
without buildctl; the `@[ -n "$(OUTDIR)" ]` guard fails loudly if the
default target is invoked bare. Both patterns make the Makefile useful as a
standalone project file, not just a buildctl hook.

---

## 11. Structured post-build data via BuildResult

`Build` returns `(*BuildResult, error)`, not just `error`. This section
documents why a return value was chosen over the two alternatives.

**Option A — return value (chosen).** `Build` returns `*BuildResult` carrying
OCI labels, image digest, and any future structured post-build data. The
struct is open for extension: adding fields doesn't break existing backends.

**Option B — sidecar file.** The backend writes `<outDir>.oci-labels.json`
next to `outDir`. buildctl reads it after `Build` returns, then deletes it
before squashfs.

**Option C — optional interface via type assertion.** A `MetadataProvider`
interface that only the docker backend implements; buildctl type-asserts.

**Why A wins:**

1. **Statelessness preserved.** All three options keep singletons stateless.
   Option A's `*BuildResult` is a return value, not struct state — no race
   condition on concurrent builds. (This was the concern that originally
   pushed toward the sidecar, but it doesn't apply to return values.)
2. **Open/closed.** Adding fields to `BuildResult` is a non-breaking change.
   A future backend that produces SBOM fragments adds a field; old backends
   return zero values.
3. **No accidental complexity.** The sidecar (Option B) adds a file naming
   convention, JSON encode/decode, and a cleanup step. Option A is one struct.
4. **Discoverable.** `BuildResult` is a public type visible in IDE autocomplete
   and godoc. The sidecar convention (Option B) requires reading this document
   to discover. Option C is discoverable but adds a second interface to the
   public surface for a single consumer.

**Why B was originally chosen:** the initial design prompt fixed the interface
signature as `Build(...) error`. The sidecar was a workaround for not changing
the signature. With the design now owned by this document, the signature change
is unblocked.

**Contract:** backends return `&BuildResult{}` (zero-value) when they have no
structured data. The pipeline driver treats nil `OCILabels` as "no fallbacks
available" — not an error.

---

## 12. The convergence contract

The following statements are invariants buildctl relies on. A backend that
violates any of them is buggy; the resulting package is undefined.

**Inputs to `Build`:**

- `cfg` is a fully-validated, normalized `*schema.PackageConfig`. `cfg.Backend`
  matches `b.Name()`.
- `srcDir` is the absolute path to the project directory. It contains
  `package.yaml` and `b.SourceFile()`.
- `arch` is a single `schema.Arch`. `Build` is called once per arch.
- `outDir` is an absolute path to an **empty, existing directory** created by
  buildctl. The backend does not create `outDir`; it populates it.
- `args` is `cfg.BackendArguments` (possibly nil). Backend-specific keys are
  documented per backend (§7.3, §8.1, §9, §10).
- `ctx` is cancelled if the user interrupts the build or the build timeout
  expires. Backends MUST propagate ctx to every subprocess via
  `exec.CommandContext`.

**Outputs on success (`Build` returns `(*BuildResult, error)` with nil error):**

- `outDir` contains a tree that looks like a Linux root: top-level entries
  are FHS-standard directories (`usr`, `etc`, `bin`, `lib`, `var`, ...).
  Symlinks are permitted and preserved.
- The tree need not be complete by buildctl's standards: `/etc/os-release`,
  the service unit, and the embedded `package.yaml` may be missing — buildctl
  generates them. The backend MAY include them (a `build.sh` that installs a
  custom unit file is legitimate); buildctl respects what's there.
- The tree MUST NOT contain:
  - Anything that depends on the build host's uid/gid for correctness
    (buildctl chowns everything to `0:0` unconditionally).
  - Anything that requires a runtime package manager. There is no package
    manager at runtime; if the app needs a library, the backend must install
    the library's files into the tree.
  - The DDI, the squashfs, or any buildctl-owned artifact. Backends that emit
    disk images (mkosi with `Output=disk`) are a contract violation, not a
    feature.

**Outputs on failure (`Build` returns non-nil):**

- `outDir` may be partially populated. buildctl treats the entire scratch
  directory as garbage on failure and removes it; partial state never
  propagates to the pipeline.
- The returned error MUST wrap the underlying failure (subprocess exit,
  missing dep, parse error) with `fmt.Errorf("<backend>: %w", err)`. buildctl
  unwraps once for the user-facing message.
- The backend SHOULD NOT attempt cleanup of `outDir` on failure; buildctl
  owns its lifecycle. (Docker's `defer rm -f` in §7.3 removes the
  intermediate *container*, which is host state outside `outDir` and so is
  the backend's responsibility.)

**Side-effects outside `outDir`:**

- Docker: creates and removes a container via the daemon; leaves the
  `--load`ed image in the local daemon cache (buildctl does not prune it;
  a future `buildctl build --no-cache` flag could).
- mkosi: writes to its own cache (`~/.cache/mkosi` or `$XDG_CACHE_HOME/mkosi`)
  as a side effect of package resolution; this is mkosi's normal behavior
  and buildctl does not manage it.
- shell / make: no side effects outside `outDir` beyond whatever the
  script/Makefile does (which is the author's responsibility).

---

## 13. Post-Build validation pipeline

After `Build` returns successfully, buildctl runs the backend-agnostic pipeline
described in [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §7. The backend has no further
involvement. For reference, the steps in order:

1. **Skeleton merge.** If `srcDir/rootfs/` exists, overlay it onto `outDir`.
   Skeleton files override backend output file-for-file. Directories are
   merged. Symlinks in the skeleton replace symlinks in the backend output.
2. **Generate missing required files.**
   - `/etc/os-release`: generate `ID=<name>` and `VERSION_ID=<version>` if
     absent. If present, validate that the values match `cfg.Name` /
     `cfg.Version` (mismatch is an error, not a warning).
   - `/usr/lib/systemd/system/<name>.service`: generate from `cfg.Command`
     if absent AND `cfg.Command` is non-empty. If `cfg.Command` is empty and
     the unit is absent, that is a validation error — the package cannot
     run.
   - `/usr/share/<name>/package.yaml`: always embedded (overwrites any file
     the backend placed there).
3. **Validate.** Run the `[]ImageCheckFn` set against the merged tree:
   - `/etc/os-release` present and `ID=` / `VERSION_ID=` match.
   - Main service unit exists at the canonical path.
   - Socket unit exists iff `cfg.SocketActivation` is true.
   - Each lifecycle hook unit referenced in `cfg.Lifecycle` exists.
   - No unit file contains `User=` or `Group=` (error, not warning — these
     are injected by appctl at install time).
4. **Apply `.buildignore`.** If `srcDir/.buildignore` exists, prune matching
   paths from `outDir`. `.dockerignore`-format syntax via
   `github.com/moby/patternmatcher`. Applied to the merged tree, not the
   backend's pre-merge output.
5. **chown `0:0` -R.** Unconditional, recursive, across the whole tree. The
   squashfs is read-only; uid/gid are immaterial at runtime but the
   portable-service contract requires `root:root` ownership.
6. **Embed `package.yaml`.** Write the canonical `package.yaml` (from
   `srcDir`) to `/usr/share/<name>/package.yaml`.
7. **squashfs / verity / PKCS7 / DDI.** Pure-Go pipeline; not the backend
   interface's concern.

This sequence is what justifies the convergence contract: the backend does
the minimum (produce files) and buildctl does the rest (normalize, validate,
package). Each step is independently testable; each can fail without leaving
the scratch dir in a usable-but-wrong state.

---

## 14. Required dependencies and `buildctl init`

`RequiredDeps()` is consumed by `buildctl init` (and as a preflight in
`buildctl build`):

```go
package exec

import "os/exec"

func CheckBinary(name string) (string, error) {
    return exec.LookPath(name)
}

func CheckAll(names []string) (missing []string, present []string) {
    for _, name := range names {
        if _, err := exec.LookPath(name); err != nil {
            missing = append(missing, name)
        } else {
            present = append(present, name)
        }
    }
    return
}
```

`buildctl init` prints a table of present/missing deps, exits 1 if any are
missing, and **never installs anything** — not `apt-get install`, not
`brew install`, nothing. This is the explicit contract from
the earlier buildctl design note's "Key design decisions" and the design session. The user
installs; buildctl reports.

After the dep check passes, `init` calls `b.Setup(cfg, dir)`. For docker this
configures buildx and binfmt (§7.2); for the other three backends it is a
no-op. `Setup` is idempotent: running `buildctl init` twice does the same
thing as running it once, modulo cheap re-verification commands.

---

## 15. Error handling and partial output

Errors are returned, not panicked. The pattern is consistent across backends:

```go
if err := cmd.Run(); err != nil {
    return fmt.Errorf("%s: %w", b.Name(), err)
}
```

buildctl's top-level error handler unwraps once and prints
`<backend>: <underlying error>`. The underlying error from
`exec.CommandContext.Run()` is an `*exec.ExitError` whose `Stderr` field is
populated when stderr was captured (it was not — we stream it), so the user
sees the backend's own stderr in the build log plus a one-line exit-code
summary from buildctl. That is enough; replaying stderr into the error
message would duplicate it.

`ErrPartialOutput` is defined but **not returned by backends**. It is a
pipeline-level sentinel: buildctl's pipeline driver returns it if `Build`
succeeded but the resulting `outDir` is suspiciously empty (zero files, or
zero directories). That catches the silent-failure mode where a `build.sh`
exits 0 without writing anything (forgotten `set -e`, swallowed error).
Backends themselves cannot reliably detect this — they don't know what the
script was supposed to produce.

`ctx` cancellation handling: every `exec.CommandContext` kills its subprocess
when the context cancels. The docker backend's `defer rm -f` still runs in
this case (defers run during panic and ctx-cancellation unwind), so no
container leaks. mkosi, shell, and make leave no host state to clean up.

---

## 16. Backend lifecycle and concurrency

A `Backend` instance is registered once at process start (§5) and reused
across every build invocation in that process. Today buildctl runs one build
per process, but the interface is designed for future parallel-arch builds
within one process:

- Backends MUST NOT store per-build state on the receiver.
- Per-build state flows through the `*BuildResult` return value or lives in
  the scratch directory (`outDir`).
- Backends MUST be safe for concurrent `Build` calls. The only shared mutable
  state is the registry itself (guarded by `registryMu`) and the host
  environment (the docker daemon, mkosi's cache directory), neither of which
  the backend owns.

`Setup` is called once per host, not once per build. buildctl's `build`
command MAY call `Setup` defensively if it has never been called before (e.g.
first run after install), but the canonical invocation point is
`buildctl init`. `Setup` is not in the per-build hot path.

---

## 17. Testing strategy

| Concern | Approach |
|---|---|
| `Detect` | For each backend: temp dir with the source file present → true; absent → false; the source file as a directory → false. |
| `Resolve` order | Temp dir with `Dockerfile` + `Makefile` → docker. `mkosi.conf` + `Makefile` → mkosi. `build.sh` + `Makefile` → shell. `Makefile` alone → make. Empty dir → `ErrNoBackend`. |
| `RequiredDeps` | Assert each backend's slice contains exactly its documented deps (no `bash` slipping into docker, no `docker` slipping into shell). |
| `Setup` idempotency | Mock exec; assert that the second call makes no exec calls for docker (both `buildx inspect` succeeds and binfmt is already registered — second invocation is the inspect plus a no-op install). For shell/make/mkosi, assert zero exec calls. |
| `Build` (docker) | Integration: requires a running docker daemon. Tagged for `// +build integration`. Build a 1-line Dockerfile (`FROM scratch; COPY x /x`), assert `outDir/x` exists. Skip on CI without docker. |
| `Build` (shell) | Pure unit test. Write a `build.sh` that does `mkdir -p "$1/usr/bin"; echo hi > "$1/usr/bin/x"`, call `Build`, assert `outDir/usr/bin/x` contents. |
| `Build` (make) | Pure unit test if GNU make is installed (it is on every dev platform). Same shape as shell. |
| `Build` (mkosi) | Integration only; needs network for debootstrap. Skip by default. |
| Tar extraction safety | Unit test `extractTar` with a crafted tar containing `../../escape` and `../sibling` paths; assert they are rejected or normalized inside `outDir`. |
| BuildResult | After docker `Build` (integration), assert `result.OCILabels` is non-nil and round-trips. After shell `Build`, assert `result.OCILabels` is nil. |
| ctx cancellation | Start a shell `Build` whose script sleeps 10s; cancel ctx after 100ms; assert `Build` returns within 500ms and the script process is gone. |
| Convergence contract | After each backend's `Build` returns successfully, assert `outDir` exists, is a directory, and is non-empty. This is the pipeline-driver's preflight check; testing it here catches silent-failure scripts. |

The Docker and mkosi integration tests are tagged separately so the
default `go test ./...` runs only the pure-Go parts (Detect, Resolve,
RequiredDeps, shell Build, make Build, tar safety, BuildResult). CI runs the
full set on a Linux host with docker installed; macOS dev runs the subset.

---

## 18. Open considerations for review

These are points where the design makes a choice a reviewer might want to
push back on. Flagged here, not buried in code.

1. **Auto-detect order (`docker > mkosi > shell > make`).** The chosen order
   prioritizes specificity. The loser is `make`, which is detected only when
   nothing else matches. A project with a `Makefile` that wraps a Dockerfile
   build (common!) gets the docker backend; the Makefile is ignored. That is
   usually correct (the Dockerfile is the source of truth) but can surprise.
   `cfg.Backend: make` overrides; document this prominently in
   `buildctl new --help`.

2. **mkosi cross-arch is unsupported.** Honest (§8.2) but a real limitation
   for packagers who want mkosi and cross-arch. The workaround is to run
   buildctl on a host of each target arch (CI matrix). If mkosi grows a
   QEMU bridge, revisit; until then docker is the cross-arch path.

3. **`buildctl init` never installs deps.** Hard rule (§14). The cost is a
   worse first-run experience: a user has to read the missing-deps table and
   install manually. The benefit is no surprises (no `brew install` on a
   machine the tool was not asked to mutate). If onboarding data shows this
   is a real friction point, the answer is better error messages, not auto-
   install.

4. **Backend package directory vs package name for make.** `internal/backend/make/`
   containing `package gnumake` is the recommendation (§10.1). The older
   buildctl design note suggested `package make_`. `gnumake` is more honest
   (it IS GNU make that's required) and follows the Go style guide; `make_`
   is technically valid but discouraged. Minor, but worth a brief review
   before the buildctl repo gets its first commit on this path.

5. **`args` map is freeform.** Consistent with `schema.BackendArguments
   map[string]any`, but it means typos in `backend_arguments` (e.g.
   `dockerfile: ./Dockerfile.production` when the backend expects
   `dockerfile: Dockerfile.production`) fail silently — the key is ignored.
   The defense is documentation: each backend's accepted keys are listed in
   its CLI reference page. A future tightening could introduce typed structs
   per backend via `schema/backendargs/<backend>.go`, but that is premature
   with one consumer (buildctl) and four backends whose keys are not yet
   stable. Defer until the v1 backends ship and the real-world key set is
   known.

6. **`.buildignore` is applied post-merge, not pre-Build.** This means a
   backend sees the full `srcDir` (no `.buildignore` filtering at build
   time). For docker this is wrong-looking: docker has its own
   `.dockerignore`. Resolution: docker's `.dockerignore` governs what
   `docker buildx build` sees; buildctl's `.buildignore` governs what
   survives into the squashfs. The two operate at different layers and may
   legitimately overlap or diverge. Document this clearly; do not try to
   unify them.
