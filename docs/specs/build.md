# Build

**Status:** rewritten 2026-07-05 against ADR-0031/0038/0039 (T98). The
pre-pivot page (pure-Go pipeline, publish flows, backend auto-detection)
is superseded; command-level detail lives in the
[buildctl CLI overview](../cli/buildctl.md), conformance in the
[App contract](app-contract.md), distribution in the
[Index contract](index-contract.md).

---

## What building is

`buildctl build` turns a project — `package.yaml` plus a `Dockerfile`,
`mkosi.conf`, or `build.sh` — into a **conformant, signed, single-file DDI**
(ADR-0038). One motion; there is no separate sign step and no way to
produce an unsigned image (ADR-0031). buildctl builds DDIs and does nothing
else (ADR-0039): no index verbs, no transport, no network distribution I/O.

```
package.yaml + backend source
      │  backend produces a rootfs tree
      ▼
conformance layer                 ← the part that is ours
      │  validate + normalize (app contract):
      │    identity files, mount-point dirs, embedded manifest,
      │    no User=/Group=, no host mounts, root:root,
      │    unit validation (T104), additivity vs base (layered)
      ▼
assembly + signing                ← delegated to systemd-ecosystem tooling
      │  squashfs/erofs → verity → PKCS7 (SHA-256) → GPT
      │  (Linux; runs in a container/VM on macOS)
      ▼
<name>_<version>_<arch>.raw       ← the package. One file.
```

## Backends

| Backend | Source | Notes |
|---|---|---|
| `docker` | `Dockerfile` | cross-arch via buildx/binfmt |
| `mkosi` | `mkosi.conf` | systemd-native; in-container on macOS |
| `shell` | `build.sh` | the escape hatch — subsumes `make` (call it from the script) |

The backend is **never guessed**: declared in `package.yaml` or passed as
`--backend`. Marker-file auto-detection is dead — a Docker project with an
incidental Makefile must never surprise-build the wrong way.

## The two package shapes

- **Fat app** — the backend produces a complete userland.
- **Layered app** — the backend builds against the base's published build
  image and produces only the app's own files; the conformance layer
  generates the `extension-release.d/` file from the `base:` declaration
  and **fails the build on any file overlap with the base** (additivity
  gate, ADR-0034 §20). One base, two layers, no language layer.

## Keys and signing

The **build key** signs every image (roothash → PKCS7, SHA-256 digest —
OpenSSL 3.x rejects SHA-1) into the verity-sig partition. It lives on the
author's machine, never anywhere else. Trust semantics:
[Security model](security-model.md). Key roles carry no cert markings —
roles are positional in index manifests (Q-B5).

## Configuration

Per-user config file (vendor-defaults + `/etc` override + `.d/` drop-ins,
per the Configuration Files convention, ADR-0034): default build key, and
index aliases for the hand-off to the distribute tool. Precedence is
strict: **flag > config > loud error** — buildctl never guesses.

## After the build

Publishing is not buildctl's job (ADR-0039). Hand the `.raw` to the
distribute tool (`index add`) on whatever host holds the index — moving
the file there is your transport (`scp`, `rsync`, a stick).
