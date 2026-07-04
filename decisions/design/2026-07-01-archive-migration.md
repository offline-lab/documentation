# Archive migration — decommission `plans/`, establish `decisions/`

**Status:** Approved 2026-07-01.
**Type:** Design note.
**Supersedes:** the working `plans/` directory at the project root.

---

## Context

The project accumulated a `plans/` workspace of ~1.6 MB / 22,000 lines of
agent working material: raw session transcripts, distilled decisions, design
docs, a generated "fact base", and orphaned scaffold code. It has two problems:

1. **Token cost.** Agents are repeatedly told (via handoffs and skills) to read
   `plans/context.md` (17 KB) before touching code. Two byte-identical raw
   transcripts (`more.md`, `session-ses_135c.md`) alone account for 846 KB.
2. **Mixed content.** Durable decisions, design rationale, rejected approaches,
   live task lists, and raw tool-call noise are all interleaved, with stale
   internal paths and no curation bar.

The docs site (`docs/`, rendered to `offline-lab.com`) is public, and the org
is open-source — so the goal is not secrecy, but **avoiding overload of the
rendered site** while keeping the full record accessible.

## Decision

Four components.

### 1. A non-rendered `decisions/` archive

A new `decisions/` directory, sibling to `docs/`, holding the full public
record. It is **public on GitHub but not rendered to HTML** — zensical renders
only `docs_dir = "docs"`, and the build script copies only `site/`, so
`decisions/` is automatically excluded from `public/`. Curated summaries in the
rendered docs link to the originals via the GitHub UI.

```
decisions/
  README.md        # curated index: one-line summary per entry → links to the full doc
  adr/             # decisions distilled from questions/resolutions (adr-NNNN-slug.md)
  _template.md     # ADR template (Context → Decision → Consequences → Alternatives)
  design/          # design notes that justify a set of decisions
  conversation/    # cleaned agent-operator discussions (design sessions, resolutions)
  rejected/        # deprecated / rejected approaches
```

**Curation bar for every entry:** strip raw tool-call JSON and local paths; no
secrets ever; each entry gets a one-line summary in `README.md`.

### 2. Lean, link-driven agent orientation

Replace the monolithic 17 KB `context.md` with a **small context file** plus
updated **per-tool `AGENTS.md`** files. These are *link hubs*, not content
dumps: they point into `docs/` (rendered articles) and `decisions/` (full
archive). Because `decisions/` is not on the rendered site, the orientation
layer includes **clone instructions** so a fresh agent can obtain a local
checkout (or fetch raw files) to follow links into the archive. Agents orient
by reading the small entry file, then following links to specifics.

### 3. `docs/` changes

- Relocate the existing `docs/decisions/` (`index.md` + `_template.md`) into
  `decisions/` → becomes `README.md` + `adr/_template.md`.
- Remove the `Decisions` nav entry in `zensical.toml`, or replace it with a
  single "Decision archive" page that links to `decisions/` on GitHub.
- Fix the pre-existing broken-link warnings: the `framework/commands.md`
  generator bug (`tools/framework/bin/generate-docs:528,534`) is fixed at the
  source; the `repository.md` links to the layered-images design repoint to
  `decisions/design/layered-images.md`.

### 4. Deletion + routing from `plans/`

- **Promote** (rewrite/curate into `decisions/`): `decisions.md` +
  `open-questions.md` → `adr/`; design docs → `design/`; design sessions and
  resolutions → `conversation/`; `output/deprecated/*` → `rejected/`.
- **Cross-check then delete:** `output/facts/*` against `docs/specs/*` (delete
  where already covered; surface gaps as issues).
- **Route to GitHub Issues/Projects:** live planning (`backlog.md`, `tasks.md`,
  `layered-tasks.md`) — an archive is not a tracker.
- **Delete outright:** duplicate transcripts, `thread.md`, `scaffold/*.go`
  (orphaned; the real `schemas/` module lives elsewhere), and handoffs once
  their decisions are extracted.
- Delete the `plans/` directory itself once empty.

## Alternatives considered

- **Private archive** (keep raw conversations in a private repo). Rejected — the
  org is open-source; openness by default.
- **Bulk-paste everything into the rendered docs.** Rejected — overloads the
  website, violates the archive's "rewritten, not pasted" principle, and
  publishes uncurated internal cruft.
- **A large `CONTEXT.md` glossary.** Rejected — recreates the token-sink
  problem. Replaced by a lean link-hub context file.
- **No context file at all.** Rejected — agents need an easy, documented entry
  point and clone instructions to reach the non-rendered archive.

## Consequences

- Agents orient by following links from a small entry file, not by reading a
  monolithic context.
- `decisions/` is GitHub-only (not on the rendered website) — agents and
  readers need a local clone or raw-file access to follow links into it.
- Migration is **incremental triage**, human-in-loop per entry, not a one-shot
  bulk move. The volume and the curation bar make bulk infeasible.

## Migration

Tracked as a phased workflow — see the companion implementation plan
(`2026-07-01-archive-migration-plan.md`) and, if preferred, GitHub issues
derived from it.
