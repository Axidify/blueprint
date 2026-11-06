"""Check that this machine can run everything in the repo, and say how to fix what is missing.

Usage:
    python -I tools/doctor.py

Exit code 0 when the required parts are present (Word is optional). Works on Windows, macOS and Linux.
"""
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_MODULES = {"yaml": "pyyaml", "docx": "python-docx", "openpyxl": "openpyxl", "pymupdf": "pymupdf", "PIL": "pillow"}
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
SETUP = "setup.cmd" if WINDOWS else "./setup.sh"


def browser():
    """The name of the browser the screenshot tool can use (Microsoft Edge first, then Google Chrome), or None."""
    if WINDOWS:
        roots = [os.environ.get(v) for v in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        places = {"Microsoft Edge": [Path(r) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for r in roots if r],
                  "Google Chrome": [Path(r) / "Google" / "Chrome" / "Application" / "chrome.exe" for r in roots if r]}
    elif MAC:
        apps = [Path("/Applications"), Path.home() / "Applications"]
        places = {"Microsoft Edge": [a / "Microsoft Edge.app" for a in apps], "Google Chrome": [a / "Google Chrome.app" for a in apps]}
    else:
        places = {"Microsoft Edge": [Path(p) for p in (shutil.which("microsoft-edge"), shutil.which("microsoft-edge-stable"), "/opt/microsoft/msedge/msedge") if p],
                  "Google Chrome": [Path(p) for p in (shutil.which("google-chrome"), shutil.which("google-chrome-stable"), "/opt/google/chrome/chrome") if p]}
    return next((name for name, paths in places.items() if any(p.exists() for p in paths)), None)


def word():
    """(installed, what it means on this system)."""
    if WINDOWS:
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "[bool](Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\\Word.Application' -ErrorAction SilentlyContinue)"],
                               capture_output=True, text=True, timeout=30)
            return r.stdout.strip().lower() == "true", "optional: table of contents and PDF"
        except Exception:
            return False, "optional: table of contents and PDF"
    if MAC:
        found = any((a / "Microsoft Word.app").exists() for a in (Path("/Applications"), Path.home() / "Applications"))
        return found, "optional: on a Mac you update the table of contents and save the PDF yourself"
    return False, "optional: Windows only"


def font_folders():
    if WINDOWS:
        return [Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts", Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
    if MAC:
        return [Path.home() / "Library" / "Fonts", Path("/Library/Fonts")]
    return [Path.home() / ".local" / "share" / "fonts", Path.home() / ".fonts", Path("/usr/share/fonts"), Path("/usr/local/share/fonts")]


def check():
    results = []  # (ok, required, label, fix)

    ok = sys.version_info >= (3, 10)
    results.append((ok, True, f"Python {sys.version.split()[0]}",
                    "Install Python 3.12 from https://www.python.org/downloads/ and tick 'Add to PATH'." if WINDOWS
                    else f"Install Python 3.12 from https://www.python.org/downloads/ (on a Mac also: brew install python), then run {SETUP} again."))

    for module, package in REQUIRED_MODULES.items():
        try:
            importlib.import_module(module)
            results.append((True, True, f"Python package {package}", ""))
        except Exception:
            results.append((False, True, f"Python package {package}", f"Run {SETUP} again (it installs requirements.txt)."))

    node = shutil.which("node")
    results.append((bool(node), True, "Node.js", "Install Node.js LTS from https://nodejs.org/ (screenshots, and Blueprint's checks in Claude Code)."))
    pw = (ROOT / "node_modules" / "playwright-core").exists()
    results.append((pw, True, "playwright-core (screenshots)", f"Run {SETUP} again (it installs the Node packages)."))

    found = browser()
    results.append((bool(found), True, f"{found or 'Microsoft Edge or Google Chrome'} (screenshots)", "Install Microsoft Edge or Google Chrome."))

    has_word, meaning = word()
    results.append((has_word, False, f"Microsoft Word ({meaning})", "Without Word the requirements document is still generated; open it and update the table of contents yourself."))

    fonts_ok = all(any((folder / f).exists() for folder in font_folders()) for f in ("Geist-Regular.ttf", "GeistMono-Regular.ttf"))
    results.append((fonts_ok, False, "Geist fonts (document design)", f"Run {SETUP} again; without them Word shows the requirements document in a fallback font."))

    claude = shutil.which("claude")
    results.append((bool(claude), False, "Claude Code command line (optional if you use the desktop app)", "Install Claude Code: https://claude.com/claude-code"))

    sys.path.insert(0, str(ROOT / "tools"))
    import workspace

    ws = workspace.workspace_dir()
    results.append((ws.exists(), True, f"Workspace ({ws})", f"Run {SETUP}; it creates the workspace, or check workspace_dir in .blueprint-local.json."))
    co = workspace.company()
    named = (ws / "company.yaml").exists() and co["name"] != "Your Company Sdn. Bhd."
    results.append((named, False, f"Company profile ({co['name']})", f"Edit {ws / 'company.yaml'} and put in your company name."))
    for name in ("projects", "knowledge", "inbox"):
        link = ROOT / name
        ok = link.exists() and (link.resolve() == (ws / name).resolve())
        results.append((ok, True, f"{name}/ linked to the workspace", f"Run {SETUP} again (it re-creates the links, e.g. after the folder was moved or renamed)."))
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
    print("Ready. Open this folder in Claude Code and type /start." if not missing_required else f"Fix the MISSING items above, then run {SETUP} again.")
    sys.exit(1 if missing_required else 0)


if __name__ == "__main__":
    main()
