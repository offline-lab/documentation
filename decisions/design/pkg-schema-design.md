# Design: `pkg/schema` shared Go module

> **⚠ Superseded in part (2026-07-05).** The buildctl implementation was
> removed ([ADR-0031](../adr/adr-0031-buildctl-rebuilt-delegated-assembly.md));
> the manifest floor, index formats, terminology ("index", not "repo"), and
> version scheme (UAPI.10, not semver) all changed in the
> [2026-07-04 design session](../conversation/2026-07-04-design-session.md).
> The shared-schema-module *idea* may survive; every field shape here awaits
> the new contract specs. Historical reference.

Module path: `github.com/offline-lab/pkg/schema`
Package name: `schema`

Imported by both `buildctl` (build-side) and `appctl` (device-side). Owns the
data-type contract between them: the `package.yaml` shape, the metadata JSON
shape, and the repo index formats. Pure data, validation, and (de)serialization
only. No build logic, no systemd logic, no I/O against `/var/lib/appctl/`.

Source of truth for the underlying formats:
- [design session 2026-06-15](../conversation/2026-06-15-design-session.md) (DDI shift, dual runtime, repo model)
- [`specs-ddi-migration.md`](./specs-ddi-migration.md) (field-level schema deltas)
- [`../../docs/schemas/`](../../docs/schemas/) (authoritative JSON Schemas; this Go module must round-trip with them)

---

## 1. Scope and non-goals

**In scope**
- Go types for `package.yaml` (`PackageConfig`), metadata JSON
  (`PackageMetadata`), and the four repo files (`IndexRoot`, `IndexArch`,
  `RepoConfig`, plus their entry types).
- Enum-like string types (`Runtime`, `Arch`, `Backend`, `SystemdProfile`,
  `NetworkMode`, `Protocol`, `DeviceType`, `Severity`) with `Valid()` methods.
- Validation that produces structured `Issue` lists (errors + warnings).
- Default-filling (`Normalize`) so both tools apply identical defaults.
- Load helpers (`LoadPackageConfig`, `LoadMetadata`, `LoadIndexRoot`,
  `LoadIndexArch`, `LoadRepoConfig`) that read a file and unmarshal.
- Constants for the current spec/format versions.

**Non-goals**
- No DDI/GPT/squashfs/verity code. That lives in `buildctl`.
- No PKCS7 code. Signing lives in `buildctl`; verification is systemd-native.
- No SQLite, no systemd calls, no network. That lives in `appctl`.
- No conversion `PackageConfig -> PackageMetadata`. That is a buildctl concern
  (it must populate `DDISize`, `CreatedAt`, `SigningKeyID` from build-time
  facts the schema module does not have).
- No policy enforcement beyond shape/enum/regex validation. Cross-field
  semantic rules that depend on runtime context (e.g. "this device has enough
  memory for `resources.heavy`") belong in `appctl`.

---

## 2. Module layout

```
pkg/schema/
├── go.mod
├── go.sum
├── doc.go              package overview, version constants
├── enums.go            Runtime, NetworkMode, Backend, SystemdProfile,
│                       Protocol, DeviceType, Arch, Severity
├── config.go           PackageConfig + Port, Volumes, Device,
│                       ResourceTier, Resources, Lifecycle
├── metadata.go         PackageMetadata
├── repo.go             IndexRoot, IndexArch, IndexKey, IndexPackage, RepoConfig
├── validate.go         Issue, ValidatePackageConfig
├── normalize.go        (*PackageConfig).Normalize()
├── load.go             Load* helpers (file → struct)
└── validate_test.go    table-driven tests for ValidatePackageConfig
```

One package, one concern per file. No sub-packages in v1; if signing helpers or
DDI constants ever need to live here, they get their own sub-package
(`schema/ddi`, `schema/signing`) under the same module.

### `go.mod`

```
module github.com/offline-lab/pkg/schema

go 1.22

require (
    golang.org/x/mod v0.17.0
    gopkg.in/yaml.v3 v3.0.1
)
```

Two dependencies, both boring:
- `gopkg.in/yaml.v3` — `package.yaml` and `repo.yaml` parsing.
- `golang.org/x/mod/semver` — semver validation (the only correct way to
  validate semver in Go; do not hand-roll a regex).

`encoding/json` from the stdlib covers metadata JSON and the two index JSONs.

No `modernc.org/sqlite`, no `go.mozilla.org/pkcs7`, no `go-diskfs` — those are
consumers' concerns. Keeping this module thin is what makes it safe to share
between a macOS-built binary (`buildctl`) and a cross-compiled-from-Buildroot
binary (`appctl`, `CGO_ENABLED=0`).

---

## 3. File contents

### 3.1 `doc.go`

```go
package schema

const (
    SpecVersion = "1"
    MetadataFormatVersion = "1.0"
    IndexFormatVersion = "1.0"
    RepoConfigVersion = "1.0"
)

const ModulePath = "github.com/offline-lab/pkg/schema"
```

`SpecVersion` is the value `package.yaml`'s `spec_version` field must equal.
`MetadataFormatVersion` / `IndexFormatVersion` / `RepoConfigVersion` are
parallel versioning for the JSON formats. They are emitted by producers and
checked by consumers; see §5.

### 3.2 `enums.go`

```go
package schema

import (
    "fmt"
    "strings"
)

type Runtime string

const (
    RuntimePortable Runtime = "portable"
    RuntimeNspawn   Runtime = "nspawn"
)

func (r Runtime) Valid() bool {
    switch r {
    case RuntimePortable, RuntimeNspawn:
        return true
    }
    return false
}

type NetworkMode string

const (
    NetworkHost    NetworkMode = "host"
    NetworkPrivate NetworkMode = "private"
    NetworkNone    NetworkMode = "none"
)

func (n NetworkMode) Valid() bool {
    switch n {
    case NetworkHost, NetworkPrivate, NetworkNone:
        return true
    }
    return false
}

type Backend string

const (
    BackendDocker Backend = "docker"
    BackendShell  Backend = "shell"
    BackendMake   Backend = "make"
    BackendMkosi  Backend = "mkosi"
)

func (b Backend) Valid() bool {
    switch b {
    case BackendDocker, BackendShell, BackendMake, BackendMkosi:
        return true
    }
    return false
}

type SystemdProfile string

const (
    ProfileDefault SystemdProfile = "default"
    ProfileStrict  SystemdProfile = "strict"
    ProfileTrusted SystemdProfile = "trusted"
    ProfileNoNet   SystemdProfile = "nonetwork"
    ProfileCustom  SystemdProfile = "custom"
)

func (p SystemdProfile) Valid() bool {
    switch p {
    case ProfileDefault, ProfileStrict, ProfileTrusted, ProfileNoNet, ProfileCustom:
        return true
    }
    return false
}

type Protocol string

const (
    ProtocolTCP Protocol = "tcp"
    ProtocolUDP Protocol = "udp"
)

func (p Protocol) Valid() bool {
    switch p {
    case ProtocolTCP, ProtocolUDP:
        return true
    }
    return false
}

type DeviceType string

const (
    DeviceAudio     DeviceType = "audio"
    DeviceVideo     DeviceType = "video"
    DeviceBluetooth DeviceType = "bluetooth"
    DeviceGPIO      DeviceType = "gpio"
    DeviceI2C       DeviceType = "i2c"
    DeviceSPI       DeviceType = "spi"
    DeviceSerial    DeviceType = "serial"
    DeviceUSB       DeviceType = "usb"
)

func (d DeviceType) Valid() bool {
    switch d {
    case DeviceAudio, DeviceVideo, DeviceBluetooth, DeviceGPIO,
        DeviceI2C, DeviceSPI, DeviceSerial, DeviceUSB:
        return true
    }
    return false
}

type Arch string

const (
    ArchArm64   Arch = "arm64"
    ArchArmV7   Arch = "armv7"
    ArchArmV6   Arch = "armv6"
    ArchAmd64   Arch = "amd64"
    ArchI386    Arch = "i386"
    ArchRiscV64 Arch = "riscv64"
    ArchPpc64LE Arch = "ppc64le"
    ArchS390x   Arch = "s390x"
)

func (a Arch) Valid() bool {
    switch a {
    case ArchArm64, ArchArmV7, ArchArmV6, ArchAmd64,
        ArchI386, ArchRiscV64, ArchPpc64LE, ArchS390x:
        return true
    }
    return false
}

func ParseArch(s string) (Arch, error) {
    a := Arch(strings.ToLower(strings.TrimSpace(s)))
    if !a.Valid() {
        return "", fmt.Errorf("schema: invalid arch %q", s)
    }
    return a, nil
}

type Severity string

const (
    SeverityError   Severity = "error"
    SeverityWarning Severity = "warning"
)
```

### 3.3 `config.go`

The block types (`*Volumes`, `*Resources`, `*Lifecycle`) are pointers so that
`omitempty` actually drops the key when the block is absent. This is what
makes "lifecycle block only present when hooks are defined" (see
[the decision records](../adr/)) fall out of marshalling naturally: the
producer sets the pointer to nil and the key disappears.

```go
package schema

type PackageConfig struct {
    SpecVersion      string                 `json:"spec_version" yaml:"spec_version"`
    Name             string                 `json:"name" yaml:"name"`
    Version          string                 `json:"version" yaml:"version"`
    Arch             Arch                   `json:"arch" yaml:"arch"`
    Description      string                 `json:"description" yaml:"description"`
    Publisher        string                 `json:"publisher" yaml:"publisher"`
    Homepage         string                 `json:"homepage,omitempty" yaml:"homepage,omitempty"`
    License          string                 `json:"license,omitempty" yaml:"license,omitempty"`
    Tags             []string               `json:"tags,omitempty" yaml:"tags,omitempty"`
    PublisherURL     string                 `json:"publisher_url,omitempty" yaml:"publisher_url,omitempty"`
    Maintainer       string                 `json:"maintainer,omitempty" yaml:"maintainer,omitempty"`
    SourceURL        string                 `json:"source_url,omitempty" yaml:"source_url,omitempty"`
    SecurityContact  string                 `json:"security_contact,omitempty" yaml:"security_contact,omitempty"`
    SBOMURL          *string                `json:"sbom_url" yaml:"sbom_url"`
    Backend          Backend                `json:"backend,omitempty" yaml:"backend,omitempty"`
    BackendArguments map[string]any         `json:"backend_arguments,omitempty" yaml:"backend_arguments,omitempty"`
    SystemdProfile   SystemdProfile         `json:"systemd_profile,omitempty" yaml:"systemd_profile,omitempty"`
    Runtime          Runtime                `json:"runtime,omitempty" yaml:"runtime,omitempty"`
    Network          NetworkMode            `json:"network,omitempty" yaml:"network,omitempty"`
    Command          string                 `json:"command,omitempty" yaml:"command,omitempty"`
    SocketActivation bool                   `json:"socket_activation,omitempty" yaml:"socket_activation,omitempty"`
    Ports            []Port                 `json:"ports,omitempty" yaml:"ports,omitempty"`
    Volumes          *Volumes               `json:"volumes,omitempty" yaml:"volumes,omitempty"`
    Devices          []Device               `json:"devices,omitempty" yaml:"devices,omitempty"`
    Resources        *Resources             `json:"resources,omitempty" yaml:"resources,omitempty"`
    Lifecycle        *Lifecycle             `json:"lifecycle,omitempty" yaml:"lifecycle,omitempty"`
}

type Port struct {
    Port     int      `json:"port" yaml:"port"`
    Protocol Protocol `json:"protocol" yaml:"protocol"`
    Expose   bool     `json:"expose,omitempty" yaml:"expose,omitempty"`
}

type Volumes struct {
    Config string `json:"config,omitempty" yaml:"config,omitempty"`
    Data   string `json:"data,omitempty" yaml:"data,omitempty"`
}

type Device struct {
    Type        DeviceType `json:"type" yaml:"type"`
    Required    bool       `json:"required,omitempty" yaml:"required,omitempty"`
    Description string     `json:"description,omitempty" yaml:"description,omitempty"`
}

type ResourceTier struct {
    CPUPercent int `json:"cpu_percent,omitempty" yaml:"cpu_percent,omitempty"`
    MemoryMB   int `json:"memory_mb,omitempty" yaml:"memory_mb,omitempty"`
    StorageMB  int `json:"storage_mb,omitempty" yaml:"storage_mb,omitempty"`
}

type Resources struct {
    Low      *ResourceTier `json:"low,omitempty" yaml:"low,omitempty"`
    Moderate *ResourceTier `json:"moderate,omitempty" yaml:"moderate,omitempty"`
    Heavy    *ResourceTier `json:"heavy,omitempty" yaml:"heavy,omitempty"`
}

type Lifecycle struct {
    PreStart   string `json:"pre_start,omitempty" yaml:"pre_start,omitempty"`
    PostStart  string `json:"post_start,omitempty" yaml:"post_start,omitempty"`
    PreUpdate  string `json:"pre_update,omitempty" yaml:"pre_update,omitempty"`
    PostUpdate string `json:"post_update,omitempty" yaml:"post_update,omitempty"`
    PreRemove  string `json:"pre_remove,omitempty" yaml:"pre_remove,omitempty"`
}
```

Notes on deliberate choices:
- `SBOMURL` is `*string` with **no** `omitempty`. JSON Schema marks it
  nullable; we want marshalling to emit `"sbom_url": null` so consumers can
  distinguish "explicitly no SBOM" from "field omitted". Same pattern for
  `SigningKeyID` in metadata.
- `Backend` is `omitempty` (not required) because `buildctl` auto-detects the
  backend from the project directory ([design session 2026-06-15](../conversation/2026-06-15-design-session.md) §2.4).
  Validation warns rather than errors on absence.
- `Protocol` and `Type` (in `Port` and `Device`) use the enum types, not bare
  `string`. Invalid values surface as parse or validation failures with the
  enum's own message.
- `Expose` and `Required` get `omitempty` so a YAML author can write
  `expose: true` and not have to write `false` everywhere else.

### 3.4 `metadata.go`

`PackageMetadata` is **not** `PackageConfig` minus a few fields plus a few
fields. It is a separate type, because:
- `backend` / `backend_arguments` are build-time-only and must not leak into
  the artifact metadata (an `appctl` operator does not care which backend
  produced the image).
- `runtime` becomes required (no defaulting on the consumer side; the spec
  migration explicitly says "no default in metadata — explicit").
- `ddi_size`, `created_at`, `signing_key_id` are producer-supplied.

Keeping them as separate structs prevents accidental marshalling of build-only
fields into the artifact and prevents `appctl` from ever reading fields it
shouldn't.

```go
package schema

type PackageMetadata struct {
    FormatVersion    MetadataFormatVersionTag `json:"format_version" yaml:"format_version"`
    SpecVersion      string                   `json:"spec_version" yaml:"spec_version"`
    Name             string                   `json:"name" yaml:"name"`
    Version          string                   `json:"version" yaml:"version"`
    Arch             Arch                     `json:"arch" yaml:"arch"`
    Description      string                   `json:"description" yaml:"description"`
    Publisher        string                   `json:"publisher" yaml:"publisher"`
    Homepage         string                   `json:"homepage,omitempty" yaml:"homepage,omitempty"`
    License          string                   `json:"license,omitempty" yaml:"license,omitempty"`
    Tags             []string                 `json:"tags,omitempty" yaml:"tags,omitempty"`
    PublisherURL     string                   `json:"publisher_url,omitempty" yaml:"publisher_url,omitempty"`
    Maintainer       string                   `json:"maintainer,omitempty" yaml:"maintainer,omitempty"`
    SourceURL        string                   `json:"source_url,omitempty" yaml:"source_url,omitempty"`
    SecurityContact  string                   `json:"security_contact,omitempty" yaml:"security_contact,omitempty"`
    SBOMURL          *string                  `json:"sbom_url" yaml:"sbom_url"`
    SystemdProfile   SystemdProfile           `json:"systemd_profile" yaml:"systemd_profile"`
    Runtime          Runtime                  `json:"runtime" yaml:"runtime"`
    Network          NetworkMode              `json:"network,omitempty" yaml:"network,omitempty"`
    Command          string                   `json:"command,omitempty" yaml:"command,omitempty"`
    SocketActivation bool                     `json:"socket_activation,omitempty" yaml:"socket_activation,omitempty"`
    Ports            []Port                   `json:"ports,omitempty" yaml:"ports,omitempty"`
    Volumes          *Volumes                 `json:"volumes,omitempty" yaml:"volumes,omitempty"`
    Devices          []Device                 `json:"devices,omitempty" yaml:"devices,omitempty"`
    Resources        *Resources               `json:"resources,omitempty" yaml:"resources,omitempty"`
    Lifecycle        *Lifecycle               `json:"lifecycle,omitempty" yaml:"lifecycle,omitempty"`
    DDIArtifact      string                   `json:"ddi_artifact" yaml:"ddi_artifact"`
    DDISHA256        string                   `json:"ddi_sha256" yaml:"ddi_sha256"`
    DDISize          int64                    `json:"ddi_size" yaml:"ddi_size"`
    CreatedAt        string                   `json:"created_at" yaml:"created_at"`
    SigningKeyID     *string                  `json:"signing_key_id" yaml:"signing_key_id"`
}

type MetadataFormatVersionTag string
```

Notes:
- `Runtime`, `SystemdProfile`, `DDIArtifact`, `DDISHA256`, `DDISize`,
  `CreatedAt` are all required in metadata (no `omitempty`). They are
  producer-set and mandatory; if `appctl` reads a metadata file missing any of
  them, that is a buildctl bug, not a recoverable absence.
- `DDIArtifact` carries the relative filename (`<name>_<version>_<arch>.raw`)
  so the same metadata file works whether the `.raw` and `.json` are sitting
  side-by-side in a directory, inside a zip, or staged under
  `/var/lib/appctl/images/<uuid>/`.
- `DDISHA256` is the SHA-256 of the `.raw` file. Used by `appctl` to verify
  download integrity independently of the dm-verity roothash (which lives
  inside the DDI). Cheap defense against transport corruption before the DDI
  is even opened.
- `Network` keeps `omitempty`: the field is only present when
  `runtime == nspawn` and the author set it. `appctl` reads it only in nspawn
  mode.
- `SigningKeyID` is `*string` (nullable in v1 per the decision records); reserved
  for key rotation, never populated by buildctl v1.
- `MetadataFormatVersionTag` is a named string type rather than a raw string
  so callers can't accidentally compare it against the package-format
  `SpecVersion`. In v1 the only valid value is `"1.0"`, equal to the
  `MetadataFormatVersion` constant.

### 3.5 `repo.go`

Five types, one per file format on the repo host. Field shapes follow
[`specs-ddi-migration.md`](./specs-ddi-migration.md) §3.4–§3.5 (the DDI
migration replaces the 5-file URLs with `raw_url` + `metadata_url`, keeps
`zip_url` for repos that serve zips, adds `runtime` to the per-arch entry).

```go
package schema

type IndexRoot struct {
    FormatVersion string     `json:"format_version" yaml:"format_version"`
    RepoName      string     `json:"repo_name" yaml:"repo_name"`
    BaseURL       string     `json:"base_url" yaml:"base_url"`
    Keys          []IndexKey `json:"keys" yaml:"keys"`
    Arches        []string   `json:"arches" yaml:"arches"`
    KeyRotation   int        `json:"key_rotation" yaml:"key_rotation"`
    GeneratedAt   string     `json:"generated_at,omitempty" yaml:"generated_at,omitempty"`
}

type IndexKey struct {
    KeyID       string `json:"key_id" yaml:"key_id"`
    CertURL     string `json:"cert_url" yaml:"cert_url"`
    Fingerprint string `json:"fingerprint" yaml:"fingerprint"`
}

type IndexArch struct {
    FormatVersion string         `json:"format_version" yaml:"format_version"`
    Arch          string         `json:"arch" yaml:"arch"`
    Packages      []IndexPackage `json:"packages" yaml:"packages"`
    GeneratedAt   string         `json:"generated_at,omitempty" yaml:"generated_at,omitempty"`
}

type IndexPackage struct {
    Name         string   `json:"name" yaml:"name"`
    Version      string   `json:"version" yaml:"version"`
    Description  string   `json:"description,omitempty" yaml:"description,omitempty"`
    Publisher    string   `json:"publisher,omitempty" yaml:"publisher,omitempty"`
    License      string   `json:"license,omitempty" yaml:"license,omitempty"`
    Homepage     string   `json:"homepage,omitempty" yaml:"homepage,omitempty"`
    Tags         []string `json:"tags,omitempty" yaml:"tags,omitempty"`
    Runtime      Runtime  `json:"runtime,omitempty" yaml:"runtime,omitempty"`
    SigningKeyID string   `json:"signing_key_id" yaml:"signing_key_id"`
    RawURL       string   `json:"raw_url" yaml:"raw_url"`
    MetadataURL  string   `json:"metadata_url" yaml:"metadata_url"`
    ZipURL       string   `json:"zip_url,omitempty" yaml:"zip_url,omitempty"`
    DDISHA256    string   `json:"ddi_sha256,omitempty" yaml:"ddi_sha256,omitempty"`
    DDISize      int64    `json:"ddi_size,omitempty" yaml:"ddi_size,omitempty"`
    CreatedAt    string   `json:"created_at,omitempty" yaml:"created_at,omitempty"`
}

type RepoConfig struct {
    ConfigVersion string `json:"config_version" yaml:"config_version"`
    RepoPath      string `json:"repo_path" yaml:"repo_path"`
    BaseURL       string `json:"base_url" yaml:"base_url"`
    RepoName      string `json:"repo_name" yaml:"repo_name"`
    IndexKey      string `json:"index_key" yaml:"index_key"`
    IndexCert     string `json:"index_cert" yaml:"index_cert"`
}
```

Notes:
- `IndexRoot` carries `KeyRotation` so `appctl repo refresh` can detect a bump
  and re-verify all build certs (see the decision records, "Key rotation: multi-cert
  option A"). Defaults to `0`; bumped manually by the repo operator.
- `IndexPackage.SigningKeyID` is a plain `string`, not `*string`, because every
  published package must have been signed by exactly one build key. Nullable
  semantics do not apply on the index, only on the in-band metadata v1 stub.
- `RawURL`, `MetadataURL`, `SigningKeyID` are required (no `omitempty`). The
  same-server rule (per the decision records) is enforced in `appctl` at fetch time, not
  in this module — it needs the `base_url` of the repo the index was
  downloaded from, which is runtime context the schema does not have.
- `ZipURL` is `omitempty`: optional convenience for repos that pre-package the
  `.raw` + `.json` into a single zip. `appctl` prefers `RawURL` + 
  `MetadataURL` when present (smaller delta when refreshing).
- `RepoConfig` is YAML only (never serialized as JSON). Paths in `IndexKey`
  and `IndexCert` are filesystem paths on the repo host, not URLs.

### 3.6 `validate.go`

Returns `(errors, warnings)` as two slices for caller convenience (most CLI
flows want to fail fast on errors and print warnings after). Each `Issue`
also carries its own `Severity` so a caller that wants a single list can
combine them losslessly.

```go
package schema

import (
    "fmt"
    "path/filepath"
    "regexp"

    "golang.org/x/mod/semver"
)

var nameRegexp = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*$`)

func ValidatePackageConfig(cfg *PackageConfig) (errors []Issue, warnings []Issue) {
    if cfg == nil {
        return []Issue{{
            Severity: SeverityError,
            Field:    "",
            Message:  "package config is nil",
        }}, nil
    }

    addErr := func(field, msg string) {
        errors = append(errors, Issue{
            Severity: SeverityError,
            Field:    field,
            Message:  msg,
        })
    }
    addWarn := func(field, msg string) {
        warnings = append(warnings, Issue{
            Severity: SeverityWarning,
            Field:    field,
            Message:  msg,
        })
    }

    if cfg.SpecVersion == "" {
        addErr("spec_version", "is required")
    } else if cfg.SpecVersion != SpecVersion {
        addErr("spec_version", fmt.Sprintf("must be %q (got %q)", SpecVersion, cfg.SpecVersion))
    }

    if cfg.Name == "" {
        addErr("name", "is required")
    } else if !nameRegexp.MatchString(cfg.Name) {
        addErr("name", fmt.Sprintf("must match %q", nameRegexp.String()))
    }

    if cfg.Version == "" {
        addErr("version", "is required")
    } else if !semver.IsValid("v" + cfg.Version) {
        addErr("version", fmt.Sprintf("%q is not valid semver", cfg.Version))
    }

    if cfg.Arch == "" {
        addErr("arch", "is required")
    } else if !cfg.Arch.Valid() {
        addErr("arch", fmt.Sprintf("%q is not a supported arch", cfg.Arch))
    }

    if cfg.Description == "" {
        addErr("description", "is required")
    }

    if cfg.Publisher == "" {
        addErr("publisher", "is required")
    }

    if cfg.Backend == "" {
        addWarn("backend", "not set; buildctl will auto-detect from project directory")
    } else if !cfg.Backend.Valid() {
        addErr("backend", fmt.Sprintf("%q is not a supported backend", cfg.Backend))
    }

    if cfg.SystemdProfile == "" {
        addWarn("systemd_profile", "not set; defaults to \"default\"")
    } else if !cfg.SystemdProfile.Valid() {
        addErr("systemd_profile", fmt.Sprintf("%q is not a supported profile", cfg.SystemdProfile))
    }

    if cfg.Runtime != "" && !cfg.Runtime.Valid() {
        addErr("runtime", fmt.Sprintf("%q is not a supported runtime", cfg.Runtime))
    }

    if cfg.Network != "" {
        if !cfg.Network.Valid() {
            addErr("network", fmt.Sprintf("%q is not a supported network mode", cfg.Network))
        } else if cfg.Runtime != RuntimeNspawn {
            addWarn("network", "ignored unless runtime is \"nspawn\"")
        }
    }

    if cfg.Command != "" && !filepath.IsAbs(cfg.Command) {
        addWarn("command", fmt.Sprintf("%q is not an absolute path", cfg.Command))
    }

    for index, port := range cfg.Ports {
        field := fmt.Sprintf("ports[%d]", index)
        if port.Port < 1 || port.Port > 65535 {
            addErr(field+".port", "must be between 1 and 65535")
        }
        if port.Protocol == "" {
            addErr(field+".protocol", "is required")
        } else if !port.Protocol.Valid() {
            addErr(field+".protocol", fmt.Sprintf("%q must be tcp or udp", port.Protocol))
        }
    }

    if cfg.Volumes != nil {
        if cfg.Volumes.Config != "" && !filepath.IsAbs(cfg.Volumes.Config) {
            addWarn("volumes.config", "should be an absolute path inside the service filesystem")
        }
        if cfg.Volumes.Data != "" && !filepath.IsAbs(cfg.Volumes.Data) {
            addWarn("volumes.data", "should be an absolute path inside the service filesystem")
        }
    }

    for index, device := range cfg.Devices {
        field := fmt.Sprintf("devices[%d].type", index)
        if device.Type == "" {
            addErr(field, "is required")
        } else if !device.Type.Valid() {
            addErr(field, fmt.Sprintf("%q is not a supported device type", device.Type))
        }
    }

    if cfg.Lifecycle != nil && *cfg.Lifecycle == (Lifecycle{}) {
        addWarn("lifecycle", "block present but empty; omit the block instead")
    }

    if cfg.License == "" {
        addWarn("license", "recommended for redistributable packages")
    }
    if cfg.SecurityContact == "" {
        addWarn("security_contact", "recommended for vulnerability reporting")
    }
    if cfg.Homepage == "" {
        addWarn("homepage", "recommended for discoverability")
    }

    return errors, warnings
}

type Issue struct {
    Severity Severity `json:"severity" yaml:"severity"`
    Field    string   `json:"field" yaml:"field"`
    Message  string   `json:"message" yaml:"message"`
}

func (i Issue) String() string {
    if i.Field == "" {
        return fmt.Sprintf("%s: %s", i.Severity, i.Message)
    }
    return fmt.Sprintf("%s: %s: %s", i.Severity, i.Field, i.Message)
}
```

The semver prefix trick (`"v" + cfg.Version`) is required because
`golang.org/x/mod/semver` follows the Go-module convention of requiring a
leading `v`. `package.yaml` uses bare semver (`1.0.0`, not `v1.0.0`), so we
prepend for validation only.

### 3.7 `normalize.go`

```go
package schema

func (c *PackageConfig) Normalize() {
    if c.Runtime == "" {
        c.Runtime = RuntimePortable
    }
    if c.SystemdProfile == "" {
        c.SystemdProfile = ProfileDefault
    }
    if c.Network == "" && c.Runtime == RuntimeNspawn {
        c.Network = NetworkHost
    }
    if c.Lifecycle != nil && *c.Lifecycle == (Lifecycle{}) {
        c.Lifecycle = nil
    }
}
```

Single source of truth for the four defaults. Both tools must agree on what
"absent" means, otherwise `buildctl` writes metadata with one default and
`appctl` reads it with another. `buildctl` calls `Normalize` before
marshalling metadata; `appctl` does **not** need to call it on metadata
(metadata fields are explicit) but may call it on a freshly-parsed
`PackageConfig` before displaying.

### 3.8 `load.go`

```go
package schema

import (
    "encoding/json"
    "fmt"
    "os"

    "gopkg.in/yaml.v3"
)

func LoadPackageConfig(path string) (*PackageConfig, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("schema: read %s: %w", path, err)
    }
    var cfg PackageConfig
    if err := yaml.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("schema: parse %s: %w", path, err)
    }
    return &cfg, nil
}

func LoadMetadata(path string) (*PackageMetadata, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("schema: read %s: %w", path, err)
    }
    var meta PackageMetadata
    if err := json.Unmarshal(data, &meta); err != nil {
        return nil, fmt.Errorf("schema: parse %s: %w", path, err)
    }
    return &meta, nil
}

func LoadIndexRoot(path string) (*IndexRoot, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("schema: read %s: %w", path, err)
    }
    var idx IndexRoot
    if err := json.Unmarshal(data, &idx); err != nil {
        return nil, fmt.Errorf("schema: parse %s: %w", path, err)
    }
    return &idx, nil
}

func LoadIndexArch(path string) (*IndexArch, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("schema: read %s: %w", path, err)
    }
    var idx IndexArch
    if err := json.Unmarshal(data, &idx); err != nil {
        return nil, fmt.Errorf("schema: parse %s: %w", path, err)
    }
    return &idx, nil
}

func LoadRepoConfig(path string) (*RepoConfig, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, fmt.Errorf("schema: read %s: %w", path, err)
    }
    var cfg RepoConfig
    if err := yaml.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("schema: parse %s: %w", path, err)
    }
    return &cfg, nil
}
```

Two formats, deliberately:
- `package.yaml` and `repo.yaml` → YAML (human-authored).
- Metadata JSON, both index JSONs → JSON (machine-authored, machine-signed).
  The `.p7s` files live alongside them and the signing step hashes bytes;
  keeping the canonical form as JSON means the signed payload is the literal
  on-disk file, not a re-serialization.

Stream-decoding is **not** used. Rationale: the largest artifact here is a
per-arch index on a 512 MB Pi Zero 2W. A few hundred package entries parse in
well under a megabyte of working set; the spec for repo indexes (latest
version per package per arch, per the decision records) bounds the size by design.
Stream-decoding would complicate the API for no measurable win. If a future
"all versions" index is added, revisit.

### 3.9 `validate_test.go` (sketch)

Table-driven, one case per validation rule. Each case asserts the exact
`Field` and `Severity` of the first matching issue. Kept in this module so a
schema regression is caught here, not downstream in `buildctl` or `appctl`.

Cases to cover (non-exhaustive):
- nil config → one error with empty `Field`
- spec_version missing / wrong / correct
- name missing / invalid (`Foo`, `_x`, `mosquitto_2`) / valid
- version missing / invalid (`1.0`, `1.2.3.4`) / valid (`1.2.3`, `1.0.0-rc1`)
- arch missing / unsupported (`mips`) / supported
- description, publisher missing
- backend missing (warning) / unsupported / supported
- systemd_profile missing (warning) / unsupported / supported
- runtime unsupported / supported
- network unsupported / supported-with-portable (warning) / supported-with-nspawn
- command relative path (warning)
- ports: out-of-range, missing protocol, unsupported protocol
- volumes: relative paths (warning per key)
- devices: missing type, unsupported type
- lifecycle: empty block (warning)
- license / security_contact / homepage missing (warnings)

---

## 4. Import and usage

### 4.1 In `buildctl`

```
require github.com/offline-lab/pkg/schema v1.0.0
```

```go
import "github.com/offline-lab/pkg/schema"

func loadAndCheck(projectDir string) (*schema.PackageConfig, error) {
    cfg, err := schema.LoadPackageConfig(filepath.Join(projectDir, "package.yaml"))
    if err != nil {
        return nil, err
    }
    errs, warns := schema.ValidatePackageConfig(cfg)
    for _, w := range warns {
        log.Printf("warning: %s", w)
    }
    if len(errs) > 0 {
        for _, e := range errs {
            log.Printf("error: %s", e)
        }
        return nil, fmt.Errorf("package.yaml has %d validation error(s)", len(errs))
    }
    cfg.Normalize()
    return cfg, nil
}
```

`buildctl` uses `PackageConfig` for input and `PackageMetadata` for output.
The conversion happens inside `buildctl`'s build pipeline, after it knows the
`DDISize`, `DDISHA256`, `CreatedAt`, and `SigningKeyID` — values the schema
module has no way to supply.

### 4.2 In `appctl`

```
require github.com/offline-lab/pkg/schema v1.0.0
```

```go
import "github.com/offline-lab/pkg/schema"

func loadInstalledMetadata(uuid string) (*schema.PackageMetadata, error) {
    path := filepath.Join("/var/lib/appctl/images", uuid, "metadata.json")
    meta, err := schema.LoadMetadata(path)
    if err != nil {
        return nil, err
    }
    if meta.FormatVersion != schema.MetadataFormatVersion {
        return nil, fmt.Errorf("unsupported metadata format_version %q", meta.FormatVersion)
    }
    if meta.SpecVersion != schema.SpecVersion {
        return nil, fmt.Errorf("unsupported spec_version %q", meta.SpecVersion)
    }
    return meta, nil
}
```

`appctl` is the consumer side: it reads `PackageMetadata`, `IndexRoot`,
`IndexArch`, `RepoConfig`. It does not read or write `PackageConfig`. The
`runtime` field selects the `PortableRuntime` vs `NspawnRuntime`
implementation (per [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.4).

### 4.3 Why a shared module, not a shared mono-repo

Per [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.1, after the DDI shift the two tools
share almost nothing but these structs. Forcing them into one binary would
drag `go-diskfs`, `pkcs7`, and the squashfs/verity code onto the device just
so `appctl` can read a metadata file. A separate, minimal module is the
correct boundary: thin enough that bumping it has no blast radius, structured
enough that the contract between the tools is checked by the compiler.

---

## 5. Versioning strategy

There are **three** independent version axes. Conflating them is the easiest
way to break either tool at a future upgrade. They are kept separate on
purpose.

| Axis | Where it lives | What bumps it | Example values |
|---|---|---|---|
| Go module version | `git tag v1.2.3` on this repo | Any API change (incl. additive) | `v1.0.0`, `v1.1.0`, `v2.0.0` |
| `spec_version` | `package.yaml` field; `schema.SpecVersion` constant | Breaking change to the package.yaml format | `"1"`, (future) `"2"` |
| `format_version` | metadata JSON, `index.json` files; `schema.MetadataFormatVersion` / `IndexFormatVersion` | Breaking change to those JSON shapes | `"1.0"`, (future) `"2.0"` |

### 5.1 Go module version

Standard Go modules semver. Tag-driven.

- **Patch** (`v1.0.1`): bug fixes in validation, doc changes, no API surface
  change. Both tools should pick this up via `go get -u=patch` with zero
  code review.
- **Minor** (`v1.1.0`): additive API changes — new struct fields with
  `omitempty`, new enum values, new helper functions. Both tools pick this up
  via `go get -u` with no code changes required. Existing serialized data
  round-trips unchanged.
- **Major** (`v2.0.0`): breaking API changes — renamed fields, removed
  fields, changed types. Go modules enforces a `/v2` import-path suffix;
  both tools must update their imports and code at the same time.

The module stays at `v0.x.x` until the package format itself is frozen
post-Phase-5 (first real apps validated end-to-end). Until then the
`v0`-prefix means "no compatibility promise", which is honest.

### 5.2 `spec_version` (package.yaml)

Currently `"1"`. Bumped only on **breaking** changes to the package author's
contract:
- A previously-required field is removed.
- A field's semantic meaning changes (e.g. `command` going from
  shell-string to exec-array).
- A field is renamed.

**Additive changes do not bump it.** Adding `network: none` as a new enum
value, adding a new optional field like `capabilities`, adding a new backend
type — these are all `spec_version: "1"` forever. Old `buildctl` reading a
new package.yaml simply ignores unknown fields; old `appctl` reading metadata
produced by newer `buildctl` ignores unknown fields.

Forward compatibility: when a tool reads `spec_version: "2"` (future), it
**refuses** with a clear error pointing the user at upgrade instructions. It
does not attempt to interpret the unknown format.

### 5.3 `format_version` (JSON files)

Same rules as `spec_version`, scoped to each JSON file independently. The
metadata file can grow a `format_version: "1.1"` minor bump for additive
fields, or a `"2.0"` major bump for breaking changes. `appctl` checks
`meta.FormatVersion` against `schema.MetadataFormatVersion` on every load
and refuses mismatches it does not understand.

Minor version compatibility rule for JSON: a consumer advertising support for
`"1.0"` MUST accept any `"1.x"` (additive only, all new fields optional and
`omitempty`). It MAY refuse `"1.x"` for `x` greater than what it knows if a
specific new field is semantically required — but the default is accept.

### 5.4 Backward and forward compatibility matrix

| Producer → | Consumer ↓ | Behavior |
|---|---|---|
| Older buildctl | Newer appctl | Always works. Newer appctl ignores fields it does not yet know about (Go's JSON decoder drops unknowns silently by default). |
| Newer buildctl | Older appctl | Works for additive changes (older appctl ignores new fields). Fails cleanly for breaking changes (older appctl sees `format_version: "2.0"`, refuses with explicit error). |
| Same version | Same version | Always works. |

The combination that must never silently corrupt: **newer buildctl writes a
newly-required field, older appctl does not see it**. The defense is the
`format_version` major bump: any field that older consumers cannot safely
ignore mandates a major version bump, which older consumers reject
explicitly.

---

## 6. Decisions deferred or out of scope

- **`backend_arguments` typing.** Kept as `map[string]any` for v1. Each
  backend (docker, mkosi, shell, make) will define its own arguments shape.
  When those shapes stabilize, they can move into a `schema/backendargs`
  sub-package with typed structs per backend and the field becomes a tagged
  union. For now, freeform is honest.
- **Strip optimization.** Per [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §13, deferred.
  No field in the schema; if it returns, it goes in `PackageConfig` as
  `strip: bool` plus optional rules, and `spec_version` does not need to bump
  (additive, optional).
- **`appctl compose` and inter-app communication.** Deferred per design
  session §11.3. No types here; will land as `schema.ComposeFile` or similar
  in a future minor version when the design session happens.
- **`sbom_url` enrichment.** Currently a single nullable URL. If a future
  version supports inline SBOM (CycloneDX or SPDX JSON embedded), it becomes
  a oneof-ish `SBOM *SBOMRef` struct. Additive, minor bump only.
- **Operator-side runtime override** (the decision records say the packager
  decides). No field; if added later, `spec_version` does not bump
  (operator-side state, not in `package.yaml`).
- **JSON Schema regeneration.** The authoritative JSON Schemas in
  [`../../docs/schemas/`](../../docs/schemas/) are
  hand-maintained per `specs-ddi-migration.md`. This Go module is a downstream
  consumer of those schemas, not a source. A future task could generate one
  from the other (gostruct → jsonschema via `invopop/jsonschema` or
  equivalent), but for v1 they are kept in sync by hand and tested via
  round-trip fixtures.

---

## 7. Open considerations for review

These are points where the design above makes a choice that a reviewer might
want to push back on. Flagged here, not buried in code.

1. **`int64` for `DDISize`.** The prompt says "integer". `int` on a 64-bit
   host is 64 bits, but `int64` is explicit and survives 32-bit builds
   (relevant if anyone ever cross-compiles `appctl` to a 32-bit ARM target
   without GOARCH=arm64). The cost is one extra type at the call site. Worth
   it.
2. **`SBOMURL` / `SigningKeyID` as `*string` rather than a custom `Nullable`
   type.** A custom `type NullableString struct{ Value string; Set bool }`
   would distinguish null from absent more cleanly, but it adds API surface
   for a distinction neither producer nor consumer currently exploits.
   `*string` with no `omitempty` (so null is emitted, absent is not) is the
   pragmatic middle ground. Revisit if the distinction starts mattering.
3. **`FormatVersion` as a distinct named string type per file.** Three
   types (`MetadataFormatVersionTag`, plus implicit string types for the two
   index files) is more ceremony than one shared `FormatVersion` string.
   Justification: a future cross-wire (comparing a metadata format_version
   against an index format_version) should be a compile error, not a silent
   truthiness check. If reviewers find it precious, collapse to one type.
4. **No `Validate*` for metadata or index files.** Only `PackageConfig` gets
   a validator. Rationale: metadata and indexes are machine-produced, so the
   producer (`buildctl`, `buildctl index update`) is the right place to
   enforce shape — and the producer always has a `PackageConfig` in hand.
   Adding `ValidateMetadata` would invite `appctl` to be lenient about
   upstream bugs. Counter-argument: defensive validation on the
   resource-constrained consumer is cheaper than debugging a malformed
   metadata file on a Pi. Lean toward adding them if the consumer side
   turns out to be fragile.
5. **`backend` is optional in `PackageConfig`.** This follows the auto-detect
   decision in [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §2.4, but it means a
   `package.yaml` with no backend and no detectable backend file produces a
   warning here and an error in `buildctl`. The split is intentional
   (schema does not know about project directory contents) but worth noting.
6. **Single module vs `github.com/offline-lab/pkg` meta-module.** The path
   above implies one module per repo. If `pkg/signing`, `pkg/ddi`, or
   `pkg/repo` ever emerge as additional shared packages, the cleaner
   refactor is a single `github.com/offline-lab/pkg` module with subdirectories
   — same import paths for consumers, simpler `go.mod` management. Not worth
   doing pre-emptively; only one shared package exists today.
