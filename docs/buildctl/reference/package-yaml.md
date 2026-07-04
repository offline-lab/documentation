# `package.yaml` reference

`package.yaml` is the build-time package definition that lives at the root of a project directory. buildctl loads it during `build` and `validate`, validates it, and uses its fields to drive backend selection, rootfs generation, metadata output, and DDI assembly.

The same schema is also available as JSON (`package.json`). If both files are present, buildctl exits with an error. If neither is present, buildctl exits with an error.

For the authoritative JSON schema and runtime semantics (how appctl consumes each field at install time), see the [Offline Lab documentation](https://offline-lab.com/docs/specs/package-format/).

## Field reference

### Identity (required)

| Field | Type | Validation |
|---|---|---|
| `spec_version` | string | Must be `"1"`. |
| `name` | string | `^[a-z0-9][a-z0-9-]*$` (lowercase alphanumerics and hyphens, starting alphanumeric). Used in artifact filenames, os-release `ID=`, systemd unit names, and repo paths. |
| `version` | string | Valid [semver](https://semver.org/) (`MAJOR.MINOR.PATCH`, optional pre-release and build metadata). Used in artifact filenames and os-release `VERSION_ID=`. |
| `arch` | string | One of `arm64`, `armv7`, `armv6`, `amd64`, `i386`, `riscv64`, `ppc64le`, `s390x`. Drives DPS partition type UUIDs in the DDI. |
| `description` | string | Single line. Non-empty. |
| `publisher` | string | Publisher organisation. Non-empty. |

### Publisher and contact (optional, recommended)

| Field | Type | Notes |
|---|---|---|
| `publisher_url` | string | Publisher homepage URL. |
| `maintainer` | string | Package maintainer. Convention: `"Name <email>"`. |
| `source_url` | string | Source repository URL. |
| `security_contact` | string | Email or URL for vulnerability reports. Warning if missing. |
| `sbom_url` | string \| null | URL to a published SBOM for this package. |
| `homepage` | string | Project homepage URL. Warning if missing. |
| `license` | string | SPDX identifier (e.g. `Apache-2.0`, `MIT`). Warning if missing. |
| `tags` | string[] | Free-form tags for repo search and filtering. |

### Build options

| Field | Type | Default | Notes |
|---|---|---|---|
| `backend` | string | auto-detect | One of `docker`, `mkosi`, `shell`, `make`. See [Build backends](backends.md). Warning if not set; buildctl will auto-detect. |
| `backend_arguments` | map | _empty_ | Per-backend arguments. Unknown keys are ignored. See [Build backends](backends.md) for what each backend accepts. |
| `systemd_profile` | string | `default` | One of `default`, `strict`, `trusted`, `nonetwork`, `custom`. Forwarded to metadata. |

### Runtime

| Field | Type | Default | Notes |
|---|---|---|---|
| `runtime` | string | `portable` | One of `portable`, `nspawn`. Selects how appctl attaches the image. |
| `network` | string | `host` (for `nspawn`) | One of `host`, `private`, `none`. Only meaningful when `runtime: nspawn`; warned as ignored otherwise. |
| `command` | string | _none_ | Absolute path to the service entrypoint. Used to auto-generate a service unit when none is provided in the rootfs. Warned if set to a relative path. |
| `socket_activation` | boolean | `false` | If `true`, appctl expects a `.socket` unit inside the image. |

### Resources declared at install time

These fields do not affect the DDI build. They are forwarded to the metadata JSON for appctl to consume.

| Field | Type | Notes |
|---|---|---|
| `ports` | list | Each entry: `port` (1–65535, required), `protocol` (`tcp` or `udp`, required), `expose` (boolean), `description`. |
| `volumes` | map | Exactly two keys: `config` and `data`. Each is a namespace path inside the service filesystem. Warned if relative. |
| `devices` | list | Each entry: `type` (one of `audio`, `video`, `bluetooth`, `gpio`, `i2c`, `spi`, `serial`, `usb`, required), `required` (boolean), `description`. |
| `resources` | map | Three tiers: `low`, `moderate`, `heavy`. Each tier has `cpu_percent`, `memory_mb`, `storage_mb`. Used by appctl for pre-install capacity checks. |
| `lifecycle` | map | Systemd unit names for `pre_start`, `post_start`, `pre_update`, `post_update`, `pre_remove`. Each must exist inside the image. An empty block is warned; omit it instead. |

## Validation severities

Validation produces two lists:

- **Errors**: block the build. Identity fields, enum values, port ranges, etc.
- **Warnings**: printed to stderr, build proceeds. Missing recommended metadata (`license`, `homepage`, `security_contact`), non-absolute `command`, empty `lifecycle` block, `network` set without `runtime: nspawn`.

`buildctl validate` runs the same checks and exits non-zero if any errors are present.

## Normalization

Before validation, buildctl fills defaults:

- `runtime` → `portable` if empty.
- `systemd_profile` → `default` if empty.
- `network` → `host` if empty AND `runtime: nspawn`.
- `lifecycle` → removed if it is an empty block.

## Docker label fallbacks

For the Docker backend, buildctl populates empty `package.yaml` fields from OCI image labels on the built image. Explicit `package.yaml` values always win.

| OCI label | Filled into |
|---|---|
| `org.opencontainers.image.description` | `description` |
| `org.opencontainers.image.url` | `homepage` |
| `org.opencontainers.image.licenses` | `license` |
| `org.opencontainers.image.source` | `source_url` |
| `org.opencontainers.image.authors` | `maintainer` |

Labels are read after the backend produces the image; fields you set explicitly are never overwritten.

## Minimal example

```yaml
spec_version: "1"
name: hello
version: "1.0.0"
arch: arm64
description: Hello world test service
publisher: example
runtime: portable
command: /usr/bin/hello
```

See the [package format spec](https://offline-lab.com/docs/specs/package-format/) for a full example with all optional fields.
