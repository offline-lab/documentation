# Decisions & design archive

Public decision + design archive for Offline Lab. Not rendered into the docs
site — browse it on GitHub.

## How to use this archive

This archive holds four kinds of material:

- **ADRs** (`adr/`) — one file per resolved decision, in a fixed format
  (Context → Decision → Consequences → Alternatives). Distilled from design
  sessions, open questions, and operator/agent discussions. Numbered
  sequentially (`adr-NNNN-short-slug.md`); once a record is published its number
  is stable. See [`adr/_template.md`](adr/_template.md) for the format.
- **Design notes** (`design/`) — longer design documents that justify a set of
  decisions (e.g. layered images, package schema, backend interface).
- **Conversations** (`conversation/`) — curated summaries of significant
  operator/agent discussions, distilled to their conclusions.
- **Rejected approaches** (`rejected/`) — proposals that were considered and
  turned down, recorded so the reasoning survives.

Decisions are **rewritten**, not pasted. Raw conversations, handoff notes, and
open-question logs are internal working material and are not published here
verbatim. A record is added to this archive only after it is resolved, and it
is written as a self-contained document so it can be understood without the
original discussion.

## Layout

- `adr/` — decision records (ADRs), one file per resolved decision.
- `design/` — longer design notes justifying a set of decisions.
- `conversation/` — curated summaries of significant discussions.
- `rejected/` — approaches considered and turned down, with reasoning.

## Entries

### ADRs (`adr/`)

| # | Decision |
|---|---|
| [0001](adr/adr-0001-package-format-ddi.md) | DDI as the package format (UAPI.3 + metadata JSON) |
| [0002](adr/adr-0002-signing-model-systemd-userspace.md) | Systemd native userspace signature verification |
| [0003](adr/adr-0003-systemd-openssl-requirement.md) | Systemd ≥ 250 built with OpenSSL required |
| [0004](adr/adr-0004-image-policy-enforcement.md) | Image policy: signed images only, no fallback |
| [0005](adr/adr-0005-fhs-standard-paths.md) | FHS standard paths (bind-mounted from /data on OL OS) |
| [0006](adr/adr-0006-two-signing-keys-per-repo.md) | Two independent signing keys per repository |
| [0007](adr/adr-0007-key-rotation-multi-cert.md) | Key rotation: gradual multi-certificate transition |
| [0008](adr/adr-0008-repository-per-arch-index.md) | Repository index: per-arch, per-class, latest only |
| [0009](adr/adr-0009-index-signing-two-step-publish.md) | Index signing: two-step publish on the repo host |
| [0010](adr/adr-0010-same-server-rule.md) | Same-origin rule for artifact URLs |
| [0011](adr/adr-0011-dual-runtime-portable-nspawn.md) | Dual runtime: portable and nspawn from v1 |
| [0012](adr/adr-0012-per-app-user-allocation.md) | Per-app user allocation (portable mode) |
| [0013](adr/adr-0013-volumes-two-keys.md) | Volumes: exactly two keys (config and data) |
| [0014](adr/adr-0014-ddi-file-ownership-root.md) | File ownership inside the DDI root: root:root |
| [0015](adr/adr-0015-no-user-group-in-unit-files.md) | No User=/Group= in DDI unit files |
| [0016](adr/adr-0016-lifecycle-block-explicit-or-absent.md) | Lifecycle block: explicit or absent |
| [0017](adr/adr-0017-package-yaml-in-ddi.md) | package.yaml embedded in the DDI |
| [0018](adr/adr-0018-skeleton-merge-file-level.md) | ~~Skeleton merge: file-level override~~ *(deprecated — buildctl removed, ADR-0031)* |
| [0019](adr/adr-0019-backend-build-result-return.md) | ~~Backend Build() returns (*BuildResult, error)~~ *(deprecated — ADR-0031)* |
| [0020](adr/adr-0020-image-storage-uuid-keyed.md) | Image storage: UUID-keyed directories |
| [0021](adr/adr-0021-reboot-proofing-overlay-wipe.md) | Reboot proofing: initramfs wipes the overlay upper |
| [0022](adr/adr-0022-firewall-nftables.md) | Firewall: nftables (inet family) |
| [0023](adr/adr-0023-sysext-confext-boxctl-only.md) | sysext/confext: boxctl-managed, not appctl |
| [0024](adr/adr-0024-buildctl-pure-go-macos.md) | ~~buildctl: pure Go, macOS required~~ *(superseded by ADR-0031)* |
| [0025](adr/adr-0025-appctl-cgo-disabled.md) | appctl: pure Go, CGO disabled |
| [0026](adr/adr-0026-appctl-file-per-record-state.md) | appctl state: file-per-record (not SQLite) |
| [0027](adr/adr-0027-implementation-decisions.md) | ~~Build & signing implementation decisions~~ *(superseded by ADR-0031; live-test facts retained)* |
| [0028](adr/adr-0028-layered-images.md) | Layered images: extensions on shared bases *(amended by 0034)* |
| [0029](adr/adr-0029-layered-appctl-lifecycle.md) | Layered appctl lifecycle *(amended by 0032)* |
| [0030](adr/adr-0030-tools-are-the-product.md) | **The pivot:** tools are the product; the OS is a customer |
| [0031](adr/adr-0031-buildctl-rebuilt-delegated-assembly.md) | buildctl rebuilt: delegated assembly, signing inside build, local-only index |
| [0032](adr/adr-0032-appctl-lifecycle-verbs.md) | appctl lifecycle: get/rm × up/down, guarded drop, no implicit anything |
| [0033](adr/adr-0033-index-terminology-trust-architecture.md) | "Index" replaces "repository"; two gates, delegation-by-inclusion, carrier vs curator |
| [0034](adr/adr-0034-uapi-substrate.md) | UAPI.3/.4/.10 adopted verbatim as the format substrate |
| [0035](adr/adr-0035-standardized-app-storage.md) | Standardized relocatable app storage + private /tmp |
| [0036](adr/adr-0036-foreign-host-baseline.md) | Foreign-host baseline; doctor + recover; OL-OS specifics move OS-side |
| [0037](adr/adr-0037-ddis-carry-trust-indexes-carry-discovery.md) | DDIs carry trust; indexes carry discovery — subscribe + import |
| [0038](adr/adr-0038-single-file-package.md) | Single-file package: metadata lives inside the DDI |
| [0039](adr/adr-0039-one-tool-per-leg.md) | One tool per leg: build / distribute / run *(amended by 0040: legs are namespaces, not binaries)* |
| [0040](adr/adr-0040-one-binary-legs-as-namespaces.md) | One binary, one name (parked); the legs become namespaces |

### Design notes (`design/`)

| Doc | Covers |
|---|---|
| [layered-images.md](design/layered-images.md) | Extension DDIs layered on a shared base via `portablectl attach --extension`; `stack:` schema, SYSEXT_LEVEL matching, base lifecycle |
| [backend-interface.md](design/backend-interface.md) | buildctl's Backend interface: docker/mkosi/shell/make contracts and the convergence point |
| [pkg-schema-design.md](design/pkg-schema-design.md) | The shared pkg/schema Go module — package.yaml, metadata, and repo-index types |
| [inter-app-comms-outline.md](design/inter-app-comms-outline.md) | Framework/agenda for the inter-app comms design session |
| [specs-ddi-migration.md](design/specs-ddi-migration.md) | Editor's migration guide: specs/schemas from the 5-file format to UAPI DDI |
| [packaging-plan.md](design/packaging-plan.md) | buildctl multi-platform packaging: Homebrew/.deb/.rpm/.apk, GoReleaser release CI |
| [2026-07-01-archive-migration.md](design/2026-07-01-archive-migration.md) | Design note: this archive migration itself (decommission `plans/`) |

### Conversations (`conversation/`)

| Record | What was settled |
|---|---|
| [2026-06-15-design-session.md](conversation/2026-06-15-design-session.md) | Session that shifted the package format to UAPI DDI and runtime verification to systemd native |
| [2026-06-16-resolutions.md](conversation/2026-06-16-resolutions.md) | Resolves the 10 open tensions from 06-15; T1/T2/T4 verified by live test |
| [2026-07-04-design-session.md](conversation/2026-07-04-design-session.md) | **The pivot session:** tools are the product; buildctl killed & redesigned; lifecycle verbs; index terminology + trust architecture; UAPI substrate; foreign-host baseline. Distilled into ADR-0030…0036 |

### Rejected approaches (`rejected/`)

| Approach | Why rejected |
|---|---|
| [kernel-keyring.md](rejected/kernel-keyring.md) | Kernel keyring for signing verification — walled-garden CA model |
| [systemd-homed.md](rejected/systemd-homed.md) | systemd-homed for per-app home dirs — encryption, not isolation |
| [shared-uid.md](rejected/shared-uid.md) | Single shared uid 6000 across all apps — no inter-app isolation |
| [monolithic-cli.md](rejected/monolithic-cli.md) | Single monolithic offline-lab CLI — incompatible deployment contexts |
| [portablectl-verity.md](rejected/portablectl-verity.md) | Assumed portablectl verifies dm-verity natively — it doesn't; only DDIs are verified, and systemd (not appctl) does it |
| [index-sign-cmd.md](rejected/index-sign-cmd.md) | buildctl index sign as a standalone command — update+sign must be atomic |
| [early-db-schema.md](rejected/early-db-schema.md) | Early 2-table DB schema — no rollback, no index/state separation |
| [verity-in-metadata.md](rejected/verity-in-metadata.md) | Verity root hash embedded in metadata JSON — dropped; roothash + signature live in the DDI signature partition |
| [iptables-refs.md](rejected/iptables-refs.md) | iptables references in schemas/docs — the OS uses nftables |
