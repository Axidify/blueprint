"""Summarise the projects on this machine: what exists, what is open, what to do next.

Usage:
    python -I tools/status.py            full summary
    python -I tools/status.py --brief    short version (used by the start-up hook)
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layout  # noqa: E402  (where everything is in a project folder: either layout)


def read(path, load, problems):
    """A project file, or None when it is missing or cannot be read (then the problem is noted)."""
    if not path.exists():
        return None
    try:
        return load(path.read_text(encoding="utf-8"))
    except Exception as e:
        problems.append(f"{path.name} could not be read ({type(e).__name__}): ask Blueprint to check it")
        return None


def today():
    return dt.date.today()


def mtime(path):
    return path.stat().st_mtime


def files(folder, pattern):
    """Files matching the pattern, oldest to newest."""
    return sorted((x for x in folder.glob(pattern) if x.is_file()), key=mtime) if folder.exists() else []


def upcoming_workshop(p, problems):
    """The date of the next workshop that has an agenda (today or later), or None."""
    dates = []
    for f in files(layout.workshops_source(p), "*.json"):
        agenda = read(f, json.loads, problems)
        date = str(agenda.get("date") or "") if isinstance(agenda, dict) else ""
        if not date:
            m = re.match(r"\d{4}-\d{2}-\d{2}", f.name)
            date = m.group(0) if m else ""
        try:
            if dt.date.fromisoformat(date[:10]) >= today():
                dates.append(date[:10])
        except ValueError:
            continue
    return min(dates) if dates else None


def inbox_notes(folder, names):
    """The inbox files left there with a note of why (tools/project.py hold): {file name: reason}. The notes
    of files no longer there, and a damaged notes file, are ignored."""
    try:
        notes = json.loads((folder / ".notes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(notes, dict):
        return {}
    return {n: str(notes[n].get("reason") or "") for n in names if isinstance(notes.get(n), dict)}


def project_status(p):
    """What a project holds. A damaged file is noted under "problems" and the rest is still reported: this
    runs at the start of every session, and one bad file must not hide every project."""
    import yaml

    problems = []
    s = {"slug": p.name, "problems": problems,
         "docs": sorted(x.name for x in layout.docs_dir(p).glob("*") if x.is_file()) if layout.docs_dir(p).exists() else [],
         "layout": layout.name(p)}
    r = read(layout.register_json(p), json.loads, problems)
    if isinstance(r, dict):
        s["name"] = r.get("project") or p.name
        items = [i for i in r.get("items") or [] if isinstance(i, dict)]
        is_open = lambda i: i.get("status") not in ("resolved", "wont-fix")
        client = [i for i in items if i.get("audience") == "client" and is_open(i)]
        s["client_open"] = len(client)
        s["client_high_open"] = sum(1 for i in client if i.get("severity") == "high")
        s["internal_open"] = sum(1 for i in items if i.get("audience") == "internal" and is_open(i))
    elif r is not None:
        problems.append("register.json is not a register: ask Blueprint to check it")
    spec_file = layout.spec_file(p)
    spec = read(spec_file, yaml.safe_load, problems)
    if isinstance(spec, dict) and isinstance(spec.get("project"), dict) and spec["project"].get("version") is not None:
        s["spec_version"] = str(spec["project"]["version"])
        s["spec_mtime"] = mtime(spec_file)
    outs = files(layout.output_dir(p), "*.docx")
    if outs:
        s["latest_doc"] = outs[-1].name
        s["doc_mtime"] = mtime(outs[-1])
        m = re.search(r" v([\d.]+)\.docx$", outs[-1].name)
        s["doc_version"] = m.group(1) if m else None
    s["reviews"] = [(f.parent.name, mtime(f)) for f in files(layout.reviews_dir(p), "*/review.md")]
    estimates = files(layout.estimates_source(p), "*.json")
    if estimates:
        s["estimate_mtime"] = mtime(estimates[-1])
    s["upcoming_workshop"] = upcoming_workshop(p, problems)
    fb = read(layout.feedback_file(p), json.loads, problems)
    if isinstance(fb, list):
        # A comment taken back in the mock-up (withdrawn) is kept in the file but waits for nobody.
        s["feedback_unprocessed"] = sum(1 for i in fb if isinstance(i, dict) and not i.get("status") and not i.get("withdrawn"))
    s["actuals"] = (ROOT / "knowledge" / "actuals" / f"{p.name}.md").exists()
    issues = read(layout.issued_file(p), json.loads, problems)
    if isinstance(issues, list) and issues and isinstance(issues[-1], dict):
        s["last_issued"] = issues[-1]
    return s


def doc_reviewed(s):
    """A review written after the latest generated document, or one named after its version."""
    version = s.get("doc_version")
    named = re.compile(rf"v{re.escape(version)}(?![\d.])") if version else None
    return any(when >= s["doc_mtime"] or (named and named.search(name)) for name, when in s.get("reviews", []))


def readable_date(value):
    """'2026-11-13' as '13 Nov 2026'; anything else as it is."""
    try:
        d = dt.date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{d.day} {d.strftime('%b %Y')}"


def next_steps(s):
    """(what to do next, a hint for the lead developer or ""), each one line in plain words. The stage the
    project is at decides it, from the first document to delivery."""
    if s.get("actuals"):
        return "delivered and closed: say 'archive this project' to move it off this list", ""
    spec = s.get("spec_version")
    issued = s.get("last_issued") or {}
    issued_current = bool(issued) and (not spec or str(issued.get("version")) == spec)
    hint = ""
    if spec and not issued_current:
        if not s.get("estimate_mtime"):
            hint = "for the lead developer: no estimate yet; say 'estimate this project'"
        elif s["spec_mtime"] > s["estimate_mtime"]:
            hint = "for the lead developer: the spec changed since the last estimate; say 'estimate this project' again"
    feedback = s.get("feedback_unprocessed")
    if feedback:
        return f"{feedback} mock-up comment(s) not worked in yet: say 'apply the feedback'", hint
    if issued_current:
        return (f"v{issued.get('version', '?')} went to the client: after delivery, say 'close the project' "
                "and share the actual effort and the change requests"), ""
    high, workshop = s.get("client_high_open", 0), s.get("upcoming_workshop")
    if not spec:
        if not s.get("docs"):
            return "no documents yet: drop the brief or scope of work into the inbox and say 'process my inbox'", ""
        if not s.get("reviews"):
            return "say 'review the requirements document' for a draft, or 'build a mock-up' from a brief", ""
        if s.get("client_open") and not workshop:
            return ("reviewed: say 'build a mock-up' to show in the next workshop, then 'prepare the workshop' "
                    f"for the {s['client_open']} open client question(s)"), ""
        return "reviewed: say 'build a mock-up' to show in the next workshop", ""
    if high:
        if workshop:
            return (f"workshop on {readable_date(workshop)} is prepared: say 'present the mock-up' there, and afterwards "
                    "'apply the feedback' with the notes"), hint
        return (f"{high} high-priority client question(s) open: say 'prepare the workshop' to turn them into "
                "an agenda"), hint
    if not s.get("latest_doc"):
        rest = (f" (its Open Issues section lists the {s['client_open']} client question(s) still open)"
                if s.get("client_open") else "")
        return f"say 'generate the requirements document'{rest}", hint
    if s.get("doc_version") != spec or s["doc_mtime"] < s["spec_mtime"]:
        return "the spec changed since the document was generated: say 'generate the requirements document' again", hint
    if not doc_reviewed(s):
        return f"say 'review the generated requirements document' (v{spec}) before it goes to the client", hint
    return f"v{spec} is generated and reviewed: when it goes to the client, say 'record that v{spec} was issued'", hint


def next_step(s):
    return next_steps(s)[0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    brief = "--brief" in sys.argv
    projects_dir = ROOT / "projects"
    projects = sorted(p for p in projects_dir.glob("*") if p.is_dir() and not p.name.startswith("_")) if projects_dir.exists() else []
    archived = sorted(p.name for p in (projects_dir / "_archive").glob("*") if p.is_dir()) if (projects_dir / "_archive").exists() else []
    inbox_dir = ROOT / "inbox"
    inbox = [x.name for x in inbox_dir.glob("*") if x.is_file() and x.name != "README.md" and not x.name.startswith(".")] if inbox_dir.exists() else []
    held = inbox_notes(inbox_dir, inbox)

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
            bits.append(f"{s['client_open']} client questions open ({s['client_high_open']} high), {s['internal_open']} internal")
        if s.get("actuals"):
            bits.append("delivered, actuals logged")
        if s.get("layout") == "old" and layout.is_old_project(p):
            bits.append("old folder layout")
        line = f"- {s.get('name', s['slug'])} ({s['slug']}): " + ("; ".join(bits) or "documents only")
        print(line)
        for problem in s["problems"]:
            print(f"    ! {problem}")
        nxt, hint = next_steps(s)
        if nxt and not brief:
            print(f"    next: {nxt}")
            if hint:
                print(f"    also: {hint}")
            if s.get("layout") == "old" and layout.is_old_project(p):
                print("    folders: in the old layout; say 'migrate the folders' to put what people open in numbered "
                      "folders (both layouts work)")
        elif nxt:
            print(f"    -> {nxt}")
    if archived and not brief:
        print(f"- Archived: {', '.join(archived)}")
    new = [n for n in inbox if n not in held]
    if new:
        print(f"- inbox/ has {len(new)} file(s) waiting: {', '.join(new[:5])}{' ...' if len(new) > 5 else ''}. Say 'process my inbox'.")
    if held:
        names = sorted(held)
        print(f"- inbox/: {len(names)} file{'s' if len(names) != 1 else ''} waiting: not sure which project "
              f"({', '.join(names[:5])}{' ...' if len(names) > 5 else ''}). Say 'process my inbox' to choose.")
    if brief:
        print("New here? Type /start for the menu.")


if __name__ == "__main__":
    main()
