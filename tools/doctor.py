"""Check that this machine can run everything in the repo, and say how to fix what is missing.

Usage:
    python -I tools/doctor.py

Exit code 0 when the required parts are present (Word is optional).
"""
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_MODULES = {"yaml": "pyyaml", "docx": "python-docx", "openpyxl": "openpyxl", "pymupdf": "pymupdf", "PIL": "pillow"}
EDGE_PATHS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
              Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]


def check():
    results = []  # (ok, required, label, fix)

    ok = sys.version_info >= (3, 10)
    results.append((ok, True, f"Python {sys.version.split()[0]}", "Install Python 3.12 from https://www.python.org/downloads/ and tick 'Add to PATH'."))

    for module, package in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module)
            results.append((True, True, f"Python package {package}", ""))
        except Exception:
            results.append((False, True, f"Python package {package}", "Run setup.cmd again (it installs requirements.txt)."))

    node = shutil.which("node")
    results.append((bool(node), True, "Node.js", "Install Node.js LTS from https://nodejs.org/ (used only for screenshots)."))
    pw = (ROOT / "node_modules" / "playwright-core").exists()
    results.append((pw, True, "playwright-core (screenshots)", "Run setup.cmd again (it runs npm install)."))

    edge = any(p.exists() for p in EDGE_PATHS)
    results.append((edge, True, "Microsoft Edge (screenshots)", "Install Microsoft Edge."))

    word = False
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "[bool](Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\\Word.Application' -ErrorAction SilentlyContinue)"],
                           capture_output=True, text=True, timeout=30)
        word = r.stdout.strip().lower() == "true"
    except Exception:
        pass
    results.append((word, False, "Microsoft Word (optional: table of contents and PDF)", "Without Word the SRS is still generated; open it and update the table of contents yourself."))

    import os

    font_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
    system_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    fonts_ok = all((font_dir / f).exists() or (system_fonts / f).exists() for f in ("Geist-Regular.ttf", "GeistMono-Regular.ttf"))
    results.append((fonts_ok, False, "Geist fonts (SRS design)", "Run setup.cmd again; without them Word shows the SRS in a fallback font."))

    claude = shutil.which("claude")
    results.append((bool(claude), False, "Claude Code command line (optional if you use the desktop app)", "Install Claude Code: https://claude.com/claude-code"))

    sys.path.insert(0, str(ROOT / "tools"))
    import workspace

    ws = workspace.workspace_dir()
    results.append((ws.exists(), True, f"Workspace ({ws})", "Run setup.cmd; it creates the workspace, or check workspace_dir in .blueprint-local.json."))
    co = workspace.company()
    named = (ws / "company.yaml").exists() and co["name"] != "Your Company Sdn. Bhd."
    results.append((named, False, f"Company profile ({co['name']})", f"Edit {ws / 'company.yaml'} and put in your company name."))
    for name in ("projects", "knowledge", "inbox"):
        link = ROOT / name
        ok = link.exists() and (link.resolve() == (ws / name).resolve())
        results.append((ok, True, f"{name}/ linked to the workspace", "Run setup.cmd again (it re-creates the links, e.g. after the folder was moved or renamed)."))
    return results


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    results = check()
    missing_required = False
    for ok, required, label, fix in results:
        mark = "OK " if ok else ("MISSING" if required else "optional")
        print(f"  [{mark}] {label}")
        if not ok:
            print(f"           -> {fix}")
            missing_required |= required
    print()
    print("Ready. Open this folder in Claude Code and type /start." if not missing_required else "Fix the MISSING items above, then run setup.cmd again.")
    sys.exit(1 if missing_required else 0)


if __name__ == "__main__":
    main()
