#!/usr/bin/env -S uv run python
# /// script
# dependencies = ["zensical"]
# ///
"""Build the unified Offline Lab site.

One build produces the whole web root in ``public/``:

  0. framework docs are generated into docs/framework/ (pull model: the build
     uses a local framework checkout if present, otherwise clones
     offline-lab/framework into .cache/repos/framework/)
  1. zensical renders the markdown docs -> public/docs/
  2. the hand-written website HTML is copied -> public/        (from site/)
  3. image assets are fetched from the media repo -> public/images/

``public/`` is pure build output (gitignored). ``docs/framework/`` is also
generated (gitignored); the rest of ``docs/`` is hand-written source.
"""

import functools
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_SRC = ROOT / "site"
PUBLIC = ROOT / "public"
IMAGES_OUT = PUBLIC / "images"

MEDIA_REPO = "https://github.com/offline-lab/media.git"
MEDIA_BRANCH = "main"

FRAMEWORK_REPO = "https://github.com/offline-lab/framework.git"
FRAMEWORK_BRANCH = "main"


def _ensure_uv():
    """Make sure the script runs under uv so the zensical dependency is present.

    The ``env -S`` shebang is unreliable (it looks up ``uv`` on a minimal PATH),
    so ``bin/docs.py serve`` may land in a bare Python that lacks zensical. If
    zensical is not importable, re-exec the script through
    ``uv run --script``, which installs it from the PEP 723 header. Guarded by
    an import check, so it never re-execs once the dependency is available.
    """
    try:
        import zensical  # noqa: F401
        return
    except ImportError:
        pass
    uv_bin = shutil.which("uv")
    if not uv_bin:
        raise SystemExit(
            "uv is required to build the docs (it installs zensical). "
            "Install uv, or run: uv run bin/docs.py serve"
        )
    os.execv(
        uv_bin,
        ["uv", "run", "--script", str(Path(__file__).resolve()), *sys.argv[1:]],
    )


_ensure_uv()


def clean_public():
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)


def build_docs():
    """Render markdown docs into public/docs/ via the zensical CLI."""
    subprocess.run(
        [sys.executable, "-m", "zensical", "build"],
        cwd=ROOT,
        check=True,
    )


def copy_website():
    """Copy hand-written website HTML from site/ to the web root."""
    if not SITE_SRC.is_dir():
        raise SystemExit(f"site/ not found at {SITE_SRC}")
    shutil.copytree(SITE_SRC, PUBLIC, dirs_exist_ok=True)


def fetch_images():
    """Fetch image assets from the media repo into public/images/.

    Non-fatal: a slow/hanging or failed clone warns and continues, so `serve`
    still starts (without fresh images) instead of hanging forever.
    """
    print("Fetching images from media repo (timeout 60s)...")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", "--branch", MEDIA_BRANCH, MEDIA_REPO, tmp],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            print("Warning: image fetch timed out — continuing without fresh images.")
            return
        if result.returncode != 0:
            print(f"Warning: image fetch failed ({result.stderr.strip()}) — continuing without fresh images.")
            return

        src = Path(tmp) / "images"
        if not src.is_dir():
            print(f"Warning: no images/ directory in {MEDIA_REPO} — continuing without fresh images.")
            return

        shutil.copytree(src, IMAGES_OUT, dirs_exist_ok=True)


def framework_source_dir() -> Path:
    """Locate the framework source (pull model, no tokens).

    Order: ``FRAMEWORK_PATH`` env var -> ``../framework`` sibling checkout ->
    clone/update ``offline-lab/framework`` into ``.cache/repos/framework/``.
    """
    env_path = os.environ.get("FRAMEWORK_PATH")
    if env_path:
        candidate = Path(env_path)
        if (candidate / "bin" / "generate-docs").exists():
            return candidate
        print(f"Warning: FRAMEWORK_PATH={env_path} has no bin/generate-docs; falling back.")

    sibling = ROOT.parent / "framework"
    if (sibling / "bin" / "generate-docs").exists():
        return sibling

    cache = ROOT / ".cache" / "repos" / "framework"
    if (cache / ".git").exists():
        print("Updating cached framework repo...")
        subprocess.run(
            ["git", "-C", str(cache), "pull", "--ff-only"],
            check=False,
            timeout=60,
        )
    else:
        print("Cloning framework repo (cached at .cache/repos/framework for next time)...")
        cache.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth=1", "--branch", FRAMEWORK_BRANCH, FRAMEWORK_REPO, str(cache)],
            check=True,
            timeout=120,
        )
    return cache


def generate_framework_docs():
    """Regenerate docs/framework/ from the framework repo's library source."""
    fw = framework_source_dir()
    out = ROOT / "docs" / "framework"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Generating framework docs from {fw} -> {out}...")
    subprocess.run(
        [sys.executable, str(fw / "bin" / "generate-docs"), "--output-dir", str(out)],
        check=True,
    )


def build():
    clean_public()
    generate_framework_docs()
    build_docs()
    copy_website()
    fetch_images()


def serve(bind="127.0.0.1", port=8000):
    print(f"Serving {PUBLIC} at http://{bind}:{port}/ (building...)")
    try:
        build()
        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(PUBLIC)
        )
        with http.server.HTTPServer((bind, port), handler) as httpd:
            print(f"Ready: http://{bind}:{port}/")
            httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(1)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve()
    else:
        build()


if __name__ == "__main__":
    main()
