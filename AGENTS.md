# AGENTS.md — central documentation repository

This repository (`offline-lab/documentation`) is the **single source of truth
for all Offline Lab documentation**. It builds one unified docs site (plus the
website pages) with Zensical, and hosts the public decision/design archive.

## Build

```bash
uv run bin/docs.py build     # generate framework docs + render + copy site + fetch images -> public/
uv run bin/docs.py serve     # build, then serve public/ at http://localhost:8000
```

`bin/docs.py build` runs, in order:

0. **Generate framework docs** (pull model — below) into `docs/framework/`.
1. Zensical renders `docs/` → `public/docs/`.
2. Copies the hand-written `site/` HTML → `public/`.
3. Fetches image assets from `offline-lab/media` → `public/images/`.

`public/` is generated output (gitignored). The hand-written source trees are
`docs/` (markdown) and `site/` (website HTML). `docs/framework/` is also
generated (gitignored) — **never hand-edit it**.

### Framework docs — pull model (no tokens)

Framework docs are **generated from `offline-lab/framework` at build time**,
not committed here. `bin/docs.py` locates the framework source in this order:
the `FRAMEWORK_PATH` env var → a `../framework` sibling checkout → a clone into
`.cache/repos/framework/`. It then runs the framework's
`bin/generate-docs --output-dir docs/framework/`.

- Edit framework source → the docs regenerate on the next build (local and CI).
- Framework devs previewing their own changes: `FRAMEWORK_PATH=../framework uv run bin/docs.py serve`.
- CI clones the public framework repo — **no cross-repo tokens**.

The same pattern (clone + copy `<repo>/docs/`) can be extended to other tools
later if their docs move back into their own repos.

## Repository layout

```
docs/                              # hand-written markdown (rendered); one subdir per section
  index.md, about.md, ...          # central "Offline Lab OS" section
  specs/ schemas/                  # specifications + JSON schemas
  appctl/ buildctl/ disco/ ...     # per-tool docs (hand-edited)
  framework/                       # GENERATED at build (gitignored) — do not edit
decisions/                         # public decision/design archive (NOT rendered; GitHub only)
  README.md adr/ design/ conversation/ rejected/
site/                              # hand-written website HTML
zensical.toml                      # the ONE build config (theme + nav)
bin/docs.py                        # the ONE build script
.github/workflows/build-deploy.yml # CI: build + deploy to GitHub Pages
```

## The docs ↔ code contract

**Code lives in each tool's own repository; documentation lives here.** Two modes:

- **Hand-edited** (operating-system, appctl, buildctl, bootconf, disco): edit
  the matching `docs/<tool>/` page here directly.
- **Generated** (framework): edit the framework source in
  `offline-lab/framework`; the docs regenerate here at build time. Never
  hand-edit `docs/framework/`.

| Tool repo (code) | Docs here | Mode | Update docs when you change… |
|---|---|---|---|
| `offline-lab/operating-system` | `docs/` + `docs/kernel.md` | hand-edit | OS image layout, boot flow, config, kernel |
| `offline-lab/appctl` | `docs/appctl/` | hand-edit | appctl CLI, lifecycle, install flow |
| `offline-lab/bootconf` | `docs/bootconf/` | hand-edit | bootconf modules, config schema |
| `offline-lab/buildctl` | `docs/buildctl/` | hand-edit | buildctl commands, `package.yaml`, backends, DDI |
| `offline-lab/disco` | `docs/disco/` | hand-edit | disco CLI, config, NSS, protocol |
| `offline-lab/framework` | `docs/framework/` | **generated** | framework library functions, `boxctl` commands (edit source → auto-regen) |

**Rule:** a change to a tool's user-facing surface MUST be reflected in its
docs — by editing the page here (hand-edited tools) or the source (generated
tools). The `docs-sync` skill (`offline-lab/.agents/skills/docs-sync/`) reports
whether a docs section is stale relative to the tool's current surface.

## Decision archive (`decisions/`)

Non-rendered, public on GitHub: ADRs (`adr/`), design notes (`design/`),
curated conversations (`conversation/`), and rejected approaches (`rejected/`).
Start at `decisions/README.md`. Entries are rewritten, not pasted; internal
paths are stripped. Live planning (`TODO.md`, `OPEN-QUESTIONS.md`, `BACKLOG.md`)
lives at the offline-lab project root, not in this repo.

> **Repo name:** `offline-lab/documentation` (confirmed). `zensical.toml`'s
> `repo_url`/`edit_uri` and the `repository.md` archive links point at it.

## Deploy

A push to `main` (or the nightly schedule) triggers
`.github/workflows/build-deploy.yml`: it builds the site — cloning the framework
repo to regenerate `docs/framework/` — and deploys `public/` to GitHub Pages.
One-time setup: set the repo's Pages source to "GitHub Actions" (Settings → Pages).
