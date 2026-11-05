"""Project folder housekeeping: issue versions, file client documents, archive, and check the layout.

Usage:
    python -I tools/project.py issue    <slug> [--to "<recipient>"] [--date YYYY-MM-DD] [--note "<text>"]
    python -I tools/project.py issued   <slug>
    python -I tools/project.py file     <slug> "<file>" --kind "<what it is>" [--responds-to 1.3] [--date YYYY-MM-DD] [--copy]
    python -I tools/project.py archive  <slug>
    python -I tools/project.py restore  <slug>
    python -I tools/project.py check    [<slug>] [--fix]

issue    records that the current SRS version (the spec's project.version) went to the client, and makes
         its files read-only. The generator then refuses to overwrite that version: bump the version first.
issued   lists the versions issued so far.
file     moves a document into the project's docs/ with a dated, descriptive name, e.g.
         "2026-11-12 client comments on v1.3.docx". --copy keeps the original.
archive  moves a delivered project to projects/_archive/ (out of the status list); restore brings it back.
check    reports projects that don't match the standard layout; --fix creates what is missing.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
ARCHIVE = PROJECTS / "_archive"
LAYOUT = ("docs", "reviews", "spec", "feedback")


def project_dir(slug, archived_ok=False):
    p = PROJECTS / slug
    if p.exists():
        return p
    if archived_ok and (ARCHIVE / slug).exists():
        return ARCHIVE / slug
    sys.exit(f"No project '{slug}'. Projects: {', '.join(active_slugs()) or 'none'}")


def active_slugs():
    return sorted(p.name for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith("_")) if PROJECTS.exists() else []


def spec_project(p):
    import yaml

    spec = p / "spec" / "app.yaml"
    if not spec.exists():
        return {}
    return (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("project") or {}


def issues_file(p):
    return p / "output" / "issued.json"


def load_issues(p):
    f = issues_file(p)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def is_issued(p, version):
    """The issue record for this version, or None. Used by the SRS generator to refuse overwriting."""
    return next((i for i in load_issues(p) if str(i["version"]) == str(version)), None)


def read_only(path, on=True):
    mode = os.stat(path).st_mode
    os.chmod(path, (mode & ~stat.S_IWRITE) if on else (mode | stat.S_IWRITE))


# ------------------------------------------------------------------ commands
def cmd_issue(a):
    p = project_dir(a.slug)
    P = spec_project(p)
    version = str(P.get("version") or "")
    if not version:
        sys.exit("The project has no spec version to issue.")
    if is_issued(p, version):
        sys.exit(f"v{version} was already issued. Bump project.version in the spec for the next version.")
    files = sorted(f for f in (p / "output").glob(f"* v{version}.*") if f.suffix in (".docx", ".pdf"))
    if not files:
        sys.exit(f"No generated SRS for v{version} in output/. Generate it first.")
    issues = load_issues(p)
    record = {"version": version, "date": a.date or dt.date.today().isoformat(),
              "to": a.to or P.get("client_short") or P.get("client", ""), "files": [f.name for f in files], "note": a.note or ""}
    issues.append(record)
    issues_file(p).write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")
    snap = p / "output" / f"spec-v{version}.yaml"
    for f in files + ([snap] if snap.exists() else []):
        read_only(f)
    print(f"Issued v{version} to {record['to']} on {record['date']}: {', '.join(record['files'])}")
    print("Those files are now read-only, and the generator will not overwrite this version.")


def cmd_issued(a):
    p = project_dir(a.slug, archived_ok=True)
    issues = load_issues(p)
    if not issues:
        print("Nothing issued yet.")
    for i in issues:
        print(f"v{i['version']}  {i['date']}  to {i['to']}  {', '.join(i['files'])}" + (f"  ({i['note']})" if i.get("note") else ""))


def cmd_file(a):
    p = project_dir(a.slug)
    src = Path(a.file)
    if not src.exists():
        sys.exit(f"No such file: {src}")
    date = a.date or dt.date.fromtimestamp(src.stat().st_mtime).isoformat()
    kind = re.sub(r"[\\/:*?\"<>|]+", "-", a.kind.strip())
    name = f"{date} {kind}" + (f" on v{a.responds_to.lstrip('v')}" if a.responds_to else "") + src.suffix.lower()
    dest = p / "docs" / name
    n = 2
    while dest.exists():
        dest = p / "docs" / f"{Path(name).stem} ({n}){src.suffix.lower()}"
        n += 1
    dest.parent.mkdir(exist_ok=True)
    (shutil.copy2 if a.copy else shutil.move)(str(src), str(dest))
    print(f"Filed {src.name} as docs/{dest.name}")


def cmd_archive(a):
    p = project_dir(a.slug)
    ARCHIVE.mkdir(exist_ok=True)
    shutil.move(str(p), str(ARCHIVE / a.slug))
    print(f"Archived {a.slug} to projects/_archive/. Restore with: python -I tools/project.py restore {a.slug}")


def cmd_restore(a):
    src = ARCHIVE / a.slug
    if not src.exists():
        sys.exit(f"No archived project '{a.slug}'.")
    if (PROJECTS / a.slug).exists():
        sys.exit(f"projects/{a.slug} already exists.")
    shutil.move(str(src), str(PROJECTS / a.slug))
    print(f"Restored {a.slug} to projects/.")


def check_one(slug, fix):
    p = PROJECTS / slug
    problems, fixed = [], []
    for d in LAYOUT:
        if not (p / d).is_dir():
            if fix:
                (p / d).mkdir()
                fixed.append(f"created {d}/")
            else:
                problems.append(f"no {d}/ folder")
    reg = p / "register.json"
    if not reg.exists():
        if fix:
            P = spec_project(p)
            reg.write_text(json.dumps({"project": P.get("name") or slug.replace("-", " ").title(),
                                       "client": P.get("client", ""), "items": []}, indent=2), encoding="utf-8")
            fixed.append("created an empty register")
        else:
            problems.append("no register.json")
    else:
        r = json.loads(reg.read_text(encoding="utf-8"))
        if r.get("project", "").lower() == slug and fix:
            P = spec_project(p)
            if P.get("name"):
                r["project"] = P["name"]
                reg.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
                fixed.append("set the register's project name from the spec")
    P = spec_project(p)
    version = str(P.get("version") or "")
    issued = {str(i["version"]) for i in load_issues(p)}
    generated = sorted({m.group(1) for f in (p / "output").glob("*.docx") if (m := re.search(r" v([\d.]+)\.docx$", f.name))}) if (p / "output").exists() else []
    notes = []
    if version and version in issued:
        notes.append(f"v{version} is issued: bump project.version before changing the spec")
    loose = [f.name for f in (p / "docs").glob("*") if f.is_file() and not re.match(r"\d{4}-\d{2}-\d{2} ", f.name)] if (p / "docs").exists() else []
    if loose:
        notes.append(f"{len(loose)} document(s) in docs/ without a date in the name (fine for originals; new files are filed with dates)")
    if generated and not issued:
        notes.append(f"SRS versions generated ({', '.join('v' + g for g in generated)}) but none recorded as issued")
    return problems, fixed, notes


def cmd_check(a):
    slugs = [a.slug] if a.slug else active_slugs()
    if not slugs:
        print("No projects.")
    bad = 0
    for slug in slugs:
        if not (PROJECTS / slug).exists():
            sys.exit(f"No project '{slug}'.")
        problems, fixed, notes = check_one(slug, a.fix)
        state = "fixed" if fixed else ("needs fixing" if problems else "OK")
        print(f"{slug}: {state}")
        for x in problems:
            print(f"  - {x}")
        for x in fixed:
            print(f"  + {x}")
        for x in notes:
            print(f"  · {x}")
        bad += bool(problems)
    if bad and not a.fix:
        print("\nRun with --fix to create what is missing.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("issue"); s.add_argument("slug"); s.add_argument("--to"); s.add_argument("--date"); s.add_argument("--note")
    s = sub.add_parser("issued"); s.add_argument("slug")
    s = sub.add_parser("file"); s.add_argument("slug"); s.add_argument("file"); s.add_argument("--kind", required=True)
    s.add_argument("--responds-to"); s.add_argument("--date"); s.add_argument("--copy", action="store_true")
    s = sub.add_parser("archive"); s.add_argument("slug")
    s = sub.add_parser("restore"); s.add_argument("slug")
    s = sub.add_parser("check"); s.add_argument("slug", nargs="?"); s.add_argument("--fix", action="store_true")
    a = ap.parse_args()
    {"issue": cmd_issue, "issued": cmd_issued, "file": cmd_file, "archive": cmd_archive, "restore": cmd_restore, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
