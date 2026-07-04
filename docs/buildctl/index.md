# buildctl

> **⚠ Redesigned (2026-07-05).** The implementation this section documents was
> removed and the tool redesigned — see the
> [CLI overview](../cli/buildctl.md) for the new surface and
> [ADR-0031](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0031-buildctl-rebuilt-delegated-assembly.md)
> for the decision. Headlines: **no pure-Go pipeline** (assembly delegated,
> container on macOS), backends **docker/mkosi/shell, never auto-detected**,
> **signing inside `build`**, **local-only `index init/add/update`** instead of
> `publish`. The tutorials and reference pages below describe the old tool and
> await rewrite.

buildctl builds signed [DDI](https://uapi-group.org/specifications/specs/discoverable_disk_image/) packages for Offline Lab and any systemd-based host that runs [portable services](https://systemd.io/PORTABLE_SERVICES/). It takes a project directory with a `package.yaml` and a build backend, and produces a `.raw` image with dm-verity integrity and a PKCS7 signature that systemd verifies natively at attach time.

- GPT layout per the [Discoverable Partitions Specification](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/): root + verity + signature partitions, with roothash-bound partition GUIDs.

## Where to start

**New to buildctl?** Work through [Build your first package](tutorials/first-package.md). It scaffolds, builds, and validates a complete DDI from scratch.

### Tutorials

- [Build your first package](tutorials/first-package.md): end-to-end walkthrough from `buildctl new` to a verified image.

### How-to guides

Task-focused recipes. Assume you have buildctl installed and a signing key.

- [Build a package](how-to/build.md)
- [Cross-compile for a different architecture](how-to/cross-compile.md)
- [Customize the rootfs (skeleton + `.buildignore`)](how-to/customize-rootfs.md)
- [Validate a built DDI](how-to/validate.md)
- [Publish to a repository](how-to/publish.md)

### Reference

- [Command reference](reference/commands.md)
- [`package.yaml` fields](reference/package-yaml.md)
- [Build backends](reference/backends.md)
- [DDI output and metadata](reference/ddi-output.md)
- [Repository index format](reference/repo-index.md)

### Explanation

- [Architecture and build pipeline](explanation/architecture.md)
- [Signing and trust model](explanation/signing.md)

## Related projects

buildctl is one tool in the Offline Lab ecosystem. It produces packages that [appctl](https://offline-lab.com/docs/appctl) installs and manages on devices. For the package format specification, repository model, security model, and the conceptual build pipeline, see the [Offline Lab documentation](https://offline-lab.com/docs/specs/package-format/).
