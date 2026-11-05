"""Summarise the projects on this machine: what exists, what is open, what to do next.

Usage:
    python -I tools/status.py            full summary
    python -I tools/status.py --brief    short version (used by the start-up hook)
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_status(p):
    s = {"slug": p.name, "docs": sorted(x.name for x in (p / "docs").glob("*") if x.is_file()) if (p / "docs").exists() else []}
    reg = p / "register.json"
    if reg.exists():
        r = json.loads(reg.read_text(encoding="utf-8"))
        s["name"] = r.get("project", p.name)
        items = r.get("items", [])
        c = Counter((i["audience"], i["status"] in ("resolved", "wont-fix")) for i in items)
        s["client_open"] = c[("client", False)]
        s["internal_open"] = c[("internal", False)]
        s["high_open"] = sum(1 for i in items if i["severity"] == "high" and i["status"] not in ("resolved", "wont-fix"))
    spec = p / "spec" / "app.yaml"
    if spec.exists():
        import yaml
        s["spec_version"] = (yaml.safe_load(spec.read_text(encoding="utf-8")).get("project") or {}).get("version")
    outs = sorted((p / "output").glob("*.docx"), key=lambda x: x.stat().st_mtime) if (p / "output").exists() else []
    if outs:
        s["latest_srs"] = outs[-1].name
    fb = p / "feedback" / "feedback.json"
    if fb.exists():
        items = json.loads(fb.read_text(encoding="utf-8"))
        s["feedback_unprocessed"] = sum(1 for i in items if not i.get("status"))
    s["actuals"] = (ROOT / "knowledge" / "actuals" / f"{p.name}.md").exists()
    iss = p / "output" / "issued.json"
    if iss.exists():
        issues = json.loads(iss.read_text(encoding="utf-8"))
        if issues:
            s["last_issued"] = issues[-1]
    return s


def next_step(s):
    if s.get("actuals"):
        return ""
    if s.get("feedback_unprocessed"):
        return f"{s['feedback_unprocessed']} mock-up comments not processed yet: say 'apply the feedback'"
    if s.get("spec_version") and not s.get("latest_srs"):
        return "mock-up exists: present it (present.cmd) or say 'generate the SRS'"
    if not s.get("spec_version") and s.get("docs"):
        return "documents in docs/: say 'review the SRS' or 'build a mock-up'"
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
        s = project_status(p)
        bits = []
        if s.get("spec_version"):
            bits.append(f"spec v{s['spec_version']}")
        if s.get("last_issued"):
            li = s["last_issued"]
            bits.append(f"v{li['version']} issued to {li['to']} on {li['date']}")
        elif s.get("latest_srs"):
            bits.append("SRS generated, not issued")
        if "client_open" in s:
            bits.append(f"{s['client_open']} client questions open ({s['high_open']} high), {s['internal_open']} internal")
        if s.get("actuals"):
            bits.append("delivered, actuals logged")
        line = f"- {s.get('name', s['slug'])} ({s['slug']}): " + ("; ".join(bits) or "documents only")
        print(line)
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
