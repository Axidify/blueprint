"""Summarise the projects on this machine: what exists, what is open, what to do next.

Usage:
    python -I tools/status.py            full summary
    python -I tools/status.py --brief    short version (used by the start-up hook)
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path, load, problems):
    """A project file, or None when it is missing or cannot be read (then the problem is noted)."""
    if not path.exists():
        return None
    try:
        return load(path.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append(f"{path.name} could not be read ({type(e).__name__}): ask Blueprint to check it")
        return None


def project_status(p):
    """What a project holds. A damaged file is noted under "problems" and the rest is still reported: this
    runs at the start of every session, and one bad file must not hide every project."""
    import yaml

    problems = []
    s = {"slug": p.name, "problems": problems,
         "docs": sorted(x.name for x in (p / "docs").glob("*") if x.is_file()) if (p / "docs").exists() else []}
    r = read(p / "register.json", json.loads, problems)
    if isinstance(r, dict):
        s["name"] = r.get("project") or p.name
        items = [i for i in r.get("items") or [] if isinstance(i, dict)]
        closed = lambda i: i.get("status") in ("resolved", "wont-fix")
        s["client_open"] = sum(1 for i in items if i.get("audience") == "client" and not closed(i))
        s["internal_open"] = sum(1 for i in items if i.get("audience") == "internal" and not closed(i))
        s["high_open"] = sum(1 for i in items if i.get("severity") == "high" and not closed(i))
    elif r is not None:
        problems.append("register.json is not a register: ask Blueprint to check it")
    spec = read(p / "spec" / "app.yaml", yaml.safe_load, problems)
    if isinstance(spec, dict):
        s["spec_version"] = (spec.get("project") or {}).get("version")
    outs = sorted((p / "output").glob("*.docx"), key=lambda x: x.stat().st_mtime) if (p / "output").exists() else []
    if outs:
        s["latest_doc"] = outs[-1].name
    fb = read(p / "feedback" / "feedback.json", json.loads, problems)
    if isinstance(fb, list):
        s["feedback_unprocessed"] = sum(1 for i in fb if isinstance(i, dict) and not i.get("status"))
    s["actuals"] = (ROOT / "knowledge" / "actuals" / f"{p.name}.md").exists()
    issues = read(p / "output" / "issued.json", json.loads, problems)
    if isinstance(issues, list) and issues and isinstance(issues[-1], dict):
        s["last_issued"] = issues[-1]
    return s


def next_step(s):
    if s.get("actuals"):
        return ""
    if s.get("feedback_unprocessed"):
        return f"{s['feedback_unprocessed']} mock-up comments not processed yet: say 'apply the feedback'"
    if s.get("spec_version") and not s.get("latest_doc"):
        present = "present.cmd" if os.name == "nt" else "./present.sh"
        return f"mock-up exists: present it ({present}) or say 'generate the requirements document'"
    if not s.get("spec_version") and s.get("docs"):
        return "documents in docs/: say 'review the requirements document' or 'build a mock-up'"
    if s.get("client_open"):
        return f"{s['client_open']} client questions open: give the register to the BA"
    return ""


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    brief = "--brief" in sys.argv
    projects_dir = ROOT / "projects"
    projects = sorted(p for p in projects_dir.glob("*") if p.is_dir() and not p.name.startswith("_")) if projects_dir.exists() else []
    archived = sorted(p.name for p in (projects_dir / "_archive").glob("*") if p.is_dir()) if (projects_dir / "_archive").exists() else []
    inbox = [x.name for x in (ROOT / "inbox").glob("*") if x.is_file() and x.name != "README.md"] if (ROOT / "inbox").exists() else []

    print("Blueprint status")
    if not projects:
        print("- No projects on this machine yet. Type /start to create one.")
    for p in projects:
        try:
            s = project_status(p)
        except Exception as e:  # whatever is wrong with one project, the others are still shown
            print(f"- {p.name}: could not be read ({type(e).__name__}): ask Blueprint to check this project")
            continue
        bits = []
        if s.get("spec_version"):
            bits.append(f"spec v{s['spec_version']}")
        if s.get("last_issued"):
            li = s["last_issued"]
            bits.append(f"v{li.get('version', '?')} issued to {li.get('to', '?')} on {li.get('date', '?')}")
        elif s.get("latest_doc"):
            bits.append("document generated, not issued")
        if "client_open" in s:
            bits.append(f"{s['client_open']} client questions open ({s['high_open']} high), {s['internal_open']} internal")
        if s.get("actuals"):
            bits.append("delivered, actuals logged")
        line = f"- {s.get('name', s['slug'])} ({s['slug']}): " + ("; ".join(bits) or "documents only")
        print(line)
        for problem in s["problems"]:
            print(f"    ! {problem}")
        nxt = next_step(s)
        if nxt and not brief:
            print(f"    next: {nxt}")
        elif nxt:
            print(f"    -> {nxt}")
    if archived and not brief:
        print(f"- Archived: {', '.join(archived)}")
    if inbox:
        print(f"- inbox/ has {len(inbox)} file(s) waiting: {', '.join(inbox[:5])}{' ...' if len(inbox) > 5 else ''}. Say 'process my inbox'.")
    if brief:
        print("New here? Type /start for the menu.")


if __name__ == "__main__":
    main()
