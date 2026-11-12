# AGENTS.md — offline-lab.com

This repository holds the **offline-lab.com** website: one static landing
page. It intentionally says little: who we are and what we do, with no
project, tool, roadmap or documentation details.

## Layout

```
site/
  index.html     # the whole page (styles inline)
  favicon.svg    # logo mark
  CNAME          # offline-lab.com
decisions/       # public decision/design archive (GitHub only, not deployed)
.github/workflows/build-deploy.yml   # deploys site/ to GitHub Pages
```

## Preview

```bash
python3 -m http.server -d site 8000   # http://localhost:8000
```

## Deploy

A push to `main` uploads `site/` as-is to GitHub Pages. There is no build step.

## Guidelines

- Keep it a single page. Don't add docs, roadmaps, or pages about
  individual tools/projects.
- Keep the copy high-level. Don't name components, CLIs, or target hardware.
