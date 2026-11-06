#!/usr/bin/env bash
# Blueprint setup for macOS and Linux. Run ./setup.sh in a terminal, or double-click setup.command on a Mac.
# (On Windows, double-click setup.cmd instead.) Safe to run again at any time: it only installs what is missing.
set -euo pipefail
cd "$(dirname "$0")"
echo
echo "Blueprint setup"
echo "------------------"

# 1. Python 3.10 or newer, in an environment of Blueprint's own (.venv), so nothing is installed system-wide
#    and the Python that ships with macOS or Homebrew is left alone.
python=""
for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    python="$cmd"
    break
  fi
done
if [ -z "$python" ]; then
  echo "Python 3.10 or newer was not found."
  echo "Install Python 3.12 from https://www.python.org/downloads/ (or with Homebrew: brew install python), then run setup again."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  echo "Creating Blueprint's Python environment (.venv)..."
  "$python" -m venv .venv
fi
echo "Installing Python packages..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

# 2. Node: screenshot tooling, the document fonts and the checks Claude Code runs at the start of a session.
if command -v node >/dev/null 2>&1; then
  echo "Installing screenshot tooling and fonts..."
  # --no-save: install exactly what package-lock.json lists and never rewrite it, so the folder stays as it was
  # cloned (a rewritten lock file would stop the next git pull).
  npm install --no-save --no-audit --no-fund --silent
else
  echo "Node.js not found: install the LTS version from https://nodejs.org/ (or: brew install node) and run setup again."
  echo "It is needed for screenshots, the fonts and Blueprint's checks in Claude Code."
fi

# 2b. Fonts used by the document design (Geist and Geist Mono, SIL Open Font License), for this user only.
font_src="node_modules/geist/dist/fonts"
if [ -d "$font_src" ]; then
  if [ "$(uname)" = "Darwin" ]; then font_dir="$HOME/Library/Fonts"; else font_dir="$HOME/.local/share/fonts"; fi
  mkdir -p "$font_dir"
  added=0
  for f in geist-sans/Geist-Regular.ttf geist-sans/Geist-Italic.ttf geist-sans/Geist-Medium.ttf geist-sans/Geist-SemiBold.ttf \
           geist-sans/Geist-Bold.ttf geist-sans/Geist-BoldItalic.ttf geist-mono/GeistMono-Regular.ttf geist-mono/GeistMono-Medium.ttf; do
    if [ -f "$font_src/$f" ] && [ ! -f "$font_dir/$(basename "$f")" ]; then
      cp "$font_src/$f" "$font_dir/"
      added=$((added + 1))
    fi
  done
  if [ "$added" -gt 0 ]; then echo "Installed $added font files (Geist, Geist Mono). Restart Word if it is open."; fi
fi

# 3. Workspace: company profile, branding, knowledge, projects and inbox.
#    ./workspace by default; set "workspace_dir" in .blueprint-local.json to use a shared folder (for example
#    OneDrive or SharePoint) so the whole team works on the same projects and knowledge.
if [ ! -f .blueprint-local.json ]; then printf '{ "workspace_dir": "" }\n' > .blueprint-local.json; fi
.venv/bin/python - <<'PYTHON'
import json
import os
import shutil
from pathlib import Path

root = Path.cwd()
configured = json.loads((root / ".blueprint-local.json").read_text(encoding="utf-8-sig")).get("workspace_dir")
ws = Path(configured).expanduser() if configured else root / "workspace"
templates = root / "templates"
for name in ("", "branding", "projects", "inbox", "knowledge"):
    (ws / name).mkdir(parents=True, exist_ok=True)
if not (ws / "company.yaml").exists():
    shutil.copy(templates / "company.yaml", ws / "company.yaml")
    print(f"Created {ws / 'company.yaml'} - put your company name in it.")
# Files renamed in 0.4.0 (SRS -> requirements document). Rename them in place so nothing is lost.
for old, new in (("knowledge/srs-standard.md", "knowledge/requirements-standard.md"),
                 ("branding/srs-template.docx", "branding/document-template.docx"),
                 ("branding/srs-boilerplate.yaml", "branding/document-boilerplate.yaml"),
                 ("branding/srs-format.yaml", "branding/document-format.yaml")):
    if (ws / old).exists() and not (ws / new).exists():
        (ws / old).rename(ws / new)
        print(f"Renamed {old} to {new}")
# Seed the knowledge base with the starter files the workspace does not have yet (never overwrite).
for src in (templates / "knowledge").rglob("*"):
    target = ws / "knowledge" / src.relative_to(templates / "knowledge")
    if src.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, target)
# projects/, knowledge/ and inbox/ in the app folder are links into the workspace (re-made on every run, so
# they survive the app folder being moved or renamed).
for name in ("projects", "knowledge", "inbox"):
    link, target = root / name, ws / name
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        if any(link.iterdir()):
            print(f"{name}/ is a real folder with files in it. Move its contents into {target}, delete it, then run setup again.")
            continue
        link.rmdir()
    os.symlink(target, link, target_is_directory=True)
print(f"Workspace: {ws}")
PYTHON
# Where Blueprint is on this machine, for the "Open the mock-up" shortcut in each project folder: the workspace
# is shared, and the app can be in a different place on each person's machine.
mkdir -p "$HOME/.blueprint" && pwd > "$HOME/.blueprint/app-path"

# 4. Check everything
echo
.venv/bin/python -I tools/doctor.py
