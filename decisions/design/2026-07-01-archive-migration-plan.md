# Archive migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. **Commit gates:** both repos forbid auto-commit (global CLAUDE.md + `tools/framework/CLAUDE.md`). The executor stages; the **user** commits. Design rationale: `2026-07-01-archive-migration.md` (this directory).

**Goal:** Decommission `plans/`; promote its durable value into a non-rendered `decisions/` archive; fix the pre-existing broken-link warnings; give agents a lean link-driven orientation.

**Repo roots (referenced below):**
- `website/` — the docs repo (future `offline-lab/documentation`); holds `docs/` (rendered) and the new `decisions/`.
- `tools/framework/` — the framework tool repo (has the doc generator).
- `plans/` — the workspace being decommissioned (at the offline-lab root).

**Verification style:** no unit tests apply (markdown + a 2-line generator change). Verification = the docs build is warning-free + link/grep checks. The `repo_name` is assumed `offline-lab/documentation` (open per `DUPLICATION.md`); GitHub URLs in repointed links depend on it.

---

## Phase 0 — Bootstrap the `decisions/` structure

### Task 0.1: Create the archive skeleton

**Files:**
- Create: `website/decisions/README.md`
- Create dirs: `website/decisions/{adr,design,conversation,rejected}/`

**Step 1:** Create the directory tree (Write creates parents):

```
website/decisions/
  README.md
  adr/_template.md
  design/
  conversation/
  rejected/
```

**Step 2:** `README.md` — a curated index placeholder (one line per entry, links to full docs). Start with just the layered-images row (added in Phase 2); leave a "How to use this archive" note pointing at the design note.

**Step 3:** Move `website/docs/decisions/_template.md` → `website/decisions/adr/_template.md` (relocate, not copy). Delete `website/docs/decisions/index.md` (its content folds into `decisions/README.md`).

**Verify:** `ls website/decisions` shows the tree; `website/docs/decisions/` is gone.

### Task 0.2: Remove the rendered Decisions nav entry

**Files:**
- Modify: `website/zensical.toml` (the `{ "Decisions" = [...] }` block, ~lines 195-197)

**Step 1:** Delete the `Decisions` nav block (the archive is no longer rendered). If you want a single landing page on the site instead, create `website/docs/decisions.md` with one paragraph + a link to `decisions/README.md` on GitHub, and point the nav entry at it. (Default: delete the block.)

**Verify:** `bin/docs.py build` succeeds; the site nav no longer lists Decisions.

---

## Phase 1 — Fix the framework doc generator (kills 18 warnings)

Independent of the archive work; do it first to clear the bulk of the noise.

### Task 1.1: Patch the two link f-strings

**Files:**
- Modify: `tools/framework/bin/generate-docs:528`
- Modify: `tools/framework/bin/generate-docs:534`

**Step 1:** Line 528 — change `({cmd.name}.md)` to `(boxctl/{cmd.name}.md)` in the table-row link.
**Step 2:** Line 534 — change `({cmd.name}.md)` to `(boxctl/{cmd.name}.md)` in the heading link. (Matches the already-correct line 574.)

### Task 1.2: Regenerate + verify + lint

**Step 1 (workdir `tools/framework`):** `bin/generate-docs`
**Step 2:** `grep -c 'boxctl/[a-z]*\.md' docs/commands.md` → expect `18`. `grep -nE '\]\((confext|config|diagnose|firewall|logs|net|power|reboot|rollback|screen|service|status|sysext|update)\.md\)' docs/commands.md` → expect no matches.
**Step 3:** `bin/test-framework --lint` (required by framework CLAUDE.md).

### Task 1.3: Sync into the website

**Step 1:** `diff -rq tools/framework/docs website/docs/framework --exclude public --exclude overrides`. If anything besides `commands.md`/`index.md` differs, **stop** and flag (hand-edit or drift → human decision).
**Step 2:** `cp tools/framework/docs/commands.md website/docs/framework/commands.md` and same for `index.md`.
**Step 3 (workdir `website`):** `bin/docs.py build 2>&1 | grep -c 'framework/commands.md'` → expect `0`.

### Task 1.4: Commit gate

Stage `tools/framework` (generator + regenerated `docs/`) and `website` (`docs/framework/`); hand to user. *(No auto-commit.)*

---

## Phase 2 — Migrate durable content into `decisions/`

Each task is **curate-then-place**: strip raw tool-call JSON, local paths (`/Users/...`, `buildbox`, key paths), and internal relative links; rewrite the result as a self-contained entry; add a one-line summary to `decisions/README.md`.

### Task 2.1: Layered images design → `design/` (also fixes the 3 `repository.md` links)

**Files:**
- Create: `website/decisions/design/layered-images.md` (curated from `plans/2026-06-18-layered-images-design.md`)

**Step 1:** Copy the source into `decisions/design/layered-images.md`.
**Step 2:** Repoint internal links to public docs: `../br2-builder/docs/specs/{package-format,security-model,repository}.md` → `../../docs/specs/{...}.md`. Replace the internal `2026-06-18-layered-tasks.md` reference with plain text ("tracked separately").
**Step 3:** `grep -nE '\.\./(br2-builder|plans)|layered-tasks\.md' website/decisions/design/layered-images.md` → expect none. Confirm `## 9.` heading survives (needed by the deep link).

### Task 2.2: Repoint `repository.md` to the archive (GitHub URLs)

**Files:** `website/docs/specs/repository.md` lines 265, 478, 598

The archive isn't rendered, so links must be **absolute GitHub URLs** (zensical doesn't warning-check external URLs; GitHub renders heading anchors):
- `../../../plans/2026-06-18-layered-images-design.md` → `https://github.com/offline-lab/documentation/blob/main/decisions/design/layered-images.md`
- line 478 keeps `#9-base-lifecycle-on-device-appctl` suffix.

**Verify (workdir `website`):** `bin/docs.py build 2>&1 | grep -c 'specs/repository.md'` → expect `0`. *(Repo-name dependent — update URLs if `offline-lab/documentation` is renamed.)*

### Task 2.3: Remaining design docs → `design/`

Curate each into `website/decisions/design/` (same curation bar): `backend-interface.md`, `pkg-schema-design.md`, `inter-app-comms-outline.md`, `specs-ddi-migration.md`, `packaging-plan.md`. One README row each.

### Task 2.4: Decisions + questions → `adr/`

Distill `plans/decisions.md` + `plans/open-questions.md` + `plans/RESOLUTIONS-2026-06-16.md` into numbered ADRs (`adr/adr-NNNN-slug.md`, using `adr/_template.md`). Resolved questions become decisions; genuinely-open questions are deferred to Phase 5 (issues), not inventing answers.

### Task 2.5: Conversations → `conversation/`

Clean `plans/DESIGN-SESSION-2026-06-15.md` and the resolution discussion into `website/decisions/conversation/`. Keep the substance (the debate and outcome); strip agent tool-call noise and local paths.

### Task 2.6: Rejected approaches → `rejected/`

Move `plans/output/deprecated/*.md` → `website/decisions/rejected/` (light curation: each already explains why it was rejected). Consolidate `output/deprecated/INDEX.md` into a `rejected/README.md`.

### Task 2.7: Fact-base cross-check

Compare `plans/output/facts/*.md` against `website/docs/specs/*`. Delete facts already covered by specs; for any fact missing from specs, open an issue (don't silently merge into specs). `output/discrepancies.md` and `output/evolution.md` feed issues / the archive README.

### Task 2.8: Commit gate

Stage `website/decisions/` + `website/docs/specs/repository.md`; hand to user.

---

## Phase 3 — Orientation layer

### Task 3.1: Lean context file (link hub)

**Files:** a small root context file in `website/` (enrich existing `website/AGENTS.md`, or a lean `CONTEXT.md` — confirm with user).

Content: (a) what lives where (`docs/` rendered; `decisions/` archive; per-tool `AGENTS.md`); (b) **clone instructions** — repo URL + how to obtain a local checkout so links into `decisions/` resolve; (c) a link map to the high-value docs/decisions. **No content dump** — links only.

### Task 3.2: Update per-tool `AGENTS.md` files

Update project-level agent files (e.g. `website/AGENTS.md`, `tools/framework/CLAUDE.md`) to link into `docs/` + `decisions/` for tool-specific context, instead of inlining or pointing at `plans/`.

**Verify:** every link from the context/AGENTS files resolves (local file exists or is a valid GitHub URL).

---

## Phase 4 — Route live planning to GitHub Issues

`plans/backlog.md`, `plans/tasks.md`, `plans/2026-06-18-layered-tasks.md`, and any still-open questions from Task 2.4 → GitHub Issues/Projects (the org uses Projects boards per existing context). An archive is not a tracker.

---

## Phase 5 — Delete `plans/` remnants

After Phases 2-4 extract all durable value:

**Delete outright:** `more.md`, `session-ses_135c.md` (dup transcripts), `thread.md`, `scaffold/` (orphaned Go; real `schemas/` module lives elsewhere), `SESSION-HANDOFF-*.md`, `skills-lock.json`, `system.md`, `tools/`, `README.md`, `context.md`, `packaging-plan.md` (once promoted), and the superseded earlier plan `2026-07-01-docs-broken-links-cleanup.md` (absorbed here).
**Remove** the now-empty `plans/output/` and finally `plans/` itself.

> The offline-lab root is not a git repo; deletion is a local filesystem op (confirm with user before `rm`).

---

## Phase 6 — Final verification

**Step 1 (workdir `website`):** `bin/docs.py build 2>&1 | tee /tmp/b.log; grep -c 'page does not exist' /tmp/b.log` → expect `0`.
**Step 2:** `ls public/docs` does **not** contain a `decisions/` dir (archive excluded from the rendered site).
**Step 3:** `ls plans` → no such directory.
**Step 4:** Spot-check 3 links from the orientation file resolve.
**Step 5:** Update `website/DUPLICATION.md` — mark the broken-link worklist and the plans-decommission resolved.

---

## Out of scope

- `tools/buildctl/` uncommitted Go changes — unrelated workstream; do not touch.
- The husk `offline-lab/framework/` (not the tool source).
- Third framework-docs copy in the builder repo (benefits from the generator fix on its next regen; not synced here).
- Making the initial commit in the `website` repo (separate explicit decision).
