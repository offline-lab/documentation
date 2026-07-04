# ADR-0026 — appctl state: file-per-record (not SQLite)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None (replaces a prior SQLite decision, not another ADR) |

## Context

appctl persists its state (repos, packages, bases, images, locks) on devices
that use SD-card storage — media prone to localized corruption and fsync
failures. The previous design used SQLite. SQLite is a single binary file: one
bad sector or failed fsync can corrupt the entire state database, and recovery
requires the `sqlite3` CLI. Additionally, the most common pure-Go SQLite
binding (`modernc.org/sqlite`) adds roughly 20 MB to the binary, and appctl
must build with `CGO_ENABLED=0` (ADR-0025). At device scale (10–50 records)
the query power of SQL is unnecessary.

## Decision

appctl's persistent state lives under `/var/lib/appctl/state/` as **one JSON
file per record** (repos, packages, bases, images, locks). This mirrors the
pattern used by dpkg, apk, pacman, and brew.

Reasons:

- **Corruption blast radius.** A single bad sector or fsync failure takes out
  one record, not the whole state. SQLite's binary format loses everything on
  corruption.
- **Recovery.** Operators can `cat`, edit, or `rm` a single record file with
  standard tools. SQLite recovery needs the `sqlite3` CLI and may be
  incomplete.
- **Binary size.** Drops `modernc.org/sqlite` (~20 MB). Uses pure stdlib
  (`encoding/json`).
- **Sufficient performance.** At 10–50 records per device, every query is a
  directory listing plus a few small file reads — sub-millisecond.
- **Precedent.** Every major package manager uses file-per-record.

## Consequences

- Corruption is isolated to individual records.
- Operators can inspect and repair state with plain text tools.
- The binary stays small and pure-Go.
- **Lost:** indexes, SQL queries, ACID transactions. None of these matter at
  single-device scale with a single writer.

## Alternatives considered

### SQLite

The previous decision. Rejected on corruption blast radius, recovery
difficulty, binary size (~20 MB via the pure-Go binding), and the cgo build
constraint. SQL query power is unnecessary at device scale.

## References

- On-device state schema.
- Related: ADR-0025 (CGO disabled).
- Original discussion: internal (not published).
