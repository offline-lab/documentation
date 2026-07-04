# ADR-0031 — buildctl rebuilt: delegated image assembly, signing inside build

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | ADR-0024, ADR-0027 (deprecates ADR-0018, ADR-0019) |

## Context

The first buildctl reimplemented squashfs, dm-verity, PKCS7 and GPT assembly
in pure Go (ADR-0024/0027) to be macOS-native. mkosi and systemd-repart — built
by the project that defines the DDI format — already do this better. The result
was "three tools in a coat", unmaintainable, and a master of none. The code is
removed.

## Decision

buildctl keeps its name and is rebuilt around what is irreducibly ours:

- **Image assembly is delegated** to systemd-ecosystem tooling (mkosi /
  systemd-repart class). On macOS it runs in a Linux container or build VM;
  the pure-Go/macOS-native property is abandoned.
- **Backends: `docker`, `mkosi`, `shell`** (shell subsumes make — a `build.sh`
  can call `make`). The backend is **never guessed**: declared in
  `package.yaml` or `--backend`. Marker-file auto-detection is dead.
- **Signing happens inside `build`.** There is no separate sign step and no
  way to produce an unsigned image; unsigned images do not exist in the
  ecosystem.
- **Index authoring is local-only**: `index init` (explicit ceremony: layout +
  index keypair + signed manifest), `index add <artifact…>` (files the
  artifact at its derived path, verifies its build signature against the
  manifest's delegation set, re-signs the index), `index update` (full
  rescan/repair). **buildctl performs no distribution transport** — moving
  bytes to an index host is the operator's tool (`scp`, `rsync`, USB); the
  ssh/rsync publish automation of ADR-0009 is superseded (the two-step
  concept — files first, index second, index key never leaves its host —
  survives).
- **Per-user config file** with an index section (named aliases + default,
  default build key). Precedence: **flag > config > loud error**. Never guess.
- Key roles are **positional in the signed manifest** (index key = identity;
  build certs = delegation set) — resolves Q-B5; certs need no marking.

Build+index stay in one codebase (`repoctl` split rejected for now).

## Consequences

- macOS builds require Docker/a VM. Accepted trade.
- Manifest floor shrinks (storage/runtime/unit defaults exist); catalog
  hygiene (description/publisher/license) is enforced at `index add`, not at
  `build`.
- ADR-0018 (skeleton merge) and ADR-0019 (Backend/BuildResult interface) are
  deprecated with the deleted code; authoring conveniences will be re-decided
  in the new design if needed.

## Alternatives considered

### Keep the pure-Go pipeline
Rejected: competing with mkosi on its home turf; unmaintainable; no product
value in the assembly itself.

### Separate repoctl
Rejected for now: one codebase tests easier; the `index` keyword already
separates the vocabulary.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§1, §12).
- ADR-0033 (index/trust architecture), ADR-0034 (UAPI substrate).
