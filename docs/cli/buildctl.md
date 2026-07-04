# buildctl

buildctl is the developer- and publisher-side CLI: it builds signed DDI app
images and authors the signed indexes they are published in. It runs on a
workstation or CI machine — never on the device.

Source: [github.com/offline-lab/buildctl](https://github.com/offline-lab/buildctl)

> **Status:** redesigned 2026-07-05 ([ADR-0031](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0031-buildctl-rebuilt-delegated-assembly.md));
> implementation pending. This page describes the designed surface.

## What it does

- **Build:** turns a project (`package.yaml` + a Dockerfile, `mkosi.conf`, or
  `build.sh`) into a conformant, **signed** DDI plus metadata — one motion.
  There is no separate sign step and no way to produce an unsigned image.
  Image assembly is delegated to systemd-ecosystem tooling; on macOS it runs
  inside a Linux container.
- **Index authoring:** creates and maintains signed indexes (the distribution
  format — [ADR-0033](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0033-index-terminology-trust-architecture.md)).
  **Local directories only** — buildctl performs no distribution transport;
  moving files to an index host is `scp`/`rsync`/a USB stick, your choice.

## Commands

| Command | What it does |
|---|---|
| `build [--backend=docker\|mkosi\|shell] [--key=…] <dir>` | Backend rootfs → validated conformant tree → **signed** DDI + metadata |
| `index init <dir>` | Authoring ceremony: index layout + index keypair + signed manifest |
| `index add [--repo=<alias\|path>] <artifact…>` | File an artifact into the index at its derived path, verify its build signature against the manifest's delegation set, re-sign the index |
| `index update <dir>` | Full rescan/repair of a local index; re-sign |

The backend is **never guessed** — declare it in `package.yaml` or pass
`--backend`. A per-user config file holds index aliases (one default) and the
default build key; precedence is strict: **flag > config > loud error**.

## Publish flow

```
buildctl build .                          # signed DDI in ./dist/
scp dist/hello_1.0.0_arm64.raw host:/tmp/ # your transport (or a USB stick)
ssh host buildctl index add /tmp/hello_1.0.0_arm64.raw
```

No paths to remember: the artifact knows its own name/version/arch. `index add`
is also where curation trust is enforced — artifacts from builders not listed
in the signed manifest are refused.

## Versioning

Versions follow [UAPI.10](https://uapi-group.org/specifications/specs/version_format_specification/)
(`~` pre-release, `^` post-release); "latest" in an index is the UAPI.10
maximum. Not semver.
