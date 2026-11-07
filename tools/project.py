"""Project folder housekeeping: issue versions, file client documents, archive, and check the layout.

Usage:
    python -I tools/project.py ready    <slug>
    python -I tools/project.py issue    <slug> [--to "<recipient>"] [--date YYYY-MM-DD] [--note "<text>"] [--without-pdf] [--anyway "<why>"]
    python -I tools/project.py issued   <slug>
    python -I tools/project.py file     <slug> "<file>" --kind "<what it is>" [--responds-to 1.3] [--date YYYY-MM-DD] [--copy]
    python -I tools/project.py archive  <slug>
    python -I tools/project.py restore  <slug>
    python -I tools/project.py find     "<system name>" [--client "<client>"]
    python -I tools/project.py match    "<file>" [--text <extracted text.md>] [--json]
    python -I tools/project.py hold     "<file>" --reason "<why it stays in the inbox>"
    python -I tools/project.py check    [<slug>] [--fix]
    python -I tools/project.py migrate  <slug> | --all [--dry-run] [--undo]

ready    whether the current version can go to the client for signature. It stops on a client question still
         marked "Blocks sign-off" (open, high), a settled item with no agreed decision (the document would
         print the client's raw answer as what is signed), or a document older than the spec or register.
         It also lists what to look at: answered items still open, questions that look the same, a field
         whose choices differ from the ones the client listed, "the agreed …" or "to be confirmed" in a
         requirement with nothing tracking it, and a side with nobody to sign.
issue    records that the current document version (the spec's project.version) went to the client, and makes
         its files read-only. The generator then refuses to overwrite that version: bump the version first.
         It needs the version's PDF (--without-pdf issues the Word file alone), and refuses a version written
         without quotes in the spec (1.10 would read as 1.1). It runs ready first and issues nothing while
         something stops it, unless --anyway "<why>" is given; the reason is kept with the issue.
issued   lists the versions issued so far.
file     moves a document into the project's client documents ("1 Client documents", docs/ in a project
         not yet migrated) with a dated, descriptive name, e.g. "2026-11-12 client comments on v1.3.docx".
         --copy keeps the original. A file open in another program is not filed (nothing is copied), and
         --date must be a date (YYYY-MM-DD).
archive  moves a delivered project to projects/_archive/ (out of the status list); restore brings it back.
find     lists earlier work on the same or a similar system: active and archived projects, and delivered
         ones in the knowledge base (knowledge/actuals/ and the projects log). Run it before starting a project.
         Names are compared without hyphens or dots ("E-PASS" is "EPASS"), and one distinctive word in common
         is enough ("XYZ EPASS" finds "ABC E-PASS System"); words many systems share ("request", "booking")
         are not. --client puts that client's own earlier projects first and says so.
match    which active project a file (in the inbox, say) belongs to: every project scored on what in the file
         points to it, with the evidence, and a verdict: clear, likely or unknown. Archived projects and
         systems delivered before are listed apart, never as a place to file it. --text reads an extraction
         made earlier instead of the file; --json is for the process-inbox skill.
hold     leaves a file where it is with a note of why (in a hidden .notes.json beside it); filing the file
         later removes the note.
check    reports projects that don't match the standard layout, and projects still in the old folder
         layout (with the command that moves them); --fix creates what is missing.
migrate  moves a project in the old folder layout (docs/, spec/, mockup/, output/ ... at the top) to the new
         one: what people open at the top in numbered folders (1 Client documents, 2 Reviews, 3 Workshops,
         4 Mock-up screenshots, 5 Requirements document, 6 UAT, 7 Change requests, and "Internal – estimates
         and change requests"), and Blueprint's working files in _blueprint/. --dry-run lists every move and
         moves nothing. --undo moves a project back to the old layout. --all does every active project.
         Nothing moves while the project's mock-up is open or a live session runs, while one of its Word,
         Excel or PDF files is open (here or, through the ~$ lock file, on a teammate's computer), or when a
         folder of the other layout is already there; it says why. Issued files stay read-only, comments keep
         their ids, a log of the moves is kept in _blueprint/migration.json, and the overview page and the
         Open the mock-up shortcuts are made again. Both layouts work with every tool.
"""
import argparse
import datetime as dt
import difflib
import errno
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
ARCHIVE = PROJECTS / "_archive"
LAYOUT = ("docs", "reviews", "spec", "feedback")  # the old layout's folders that `check --fix` creates
sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (where everything is in a project folder)


def project_dir(slug, archived_ok=False):
    p = PROJECTS / slug
    if p.exists():
        return p
    if archived_ok and (ARCHIVE / slug).exists():
        return ARCHIVE / slug
    sys.exit(f"No project '{slug}'. Projects: {', '.join(active_slugs()) or 'none'}")


def active_slugs():
    return sorted(p.name for p in PROJECTS.iterdir() if p.is_dir() and not p.name.startswith("_")) if PROJECTS.exists() else []


def knowledge_dir():
    """The knowledge base sits beside projects/ (both are links into the workspace)."""
    return PROJECTS.parent / "knowledge"


# Words that say nothing about which system it is: "Leave Request System" and "leave request" are the same.
FILLER = {"system", "systems", "the", "a", "an", "of", "for", "and", "app", "application", "apps", "portal",
          "project", "phase", "module", "solution", "new", "online"}
# Words many systems and screens share: on their own they never say which project something is about ("User",
# "Location", "Summary", "Details" are on half the mock-ups there are, "Request" in half the system names).
GENERIC = {"user", "users", "location", "locations", "summary", "details", "detail", "list", "lists", "home",
           "dashboard", "profile", "settings", "setting", "search", "report", "reports", "history", "inbox",
           "task", "tasks", "form", "forms", "request", "requests", "requester", "management", "manager", "admin",
           "administrator", "approver", "approval", "approvals", "reviewer", "officer", "staff", "employee",
           "employees", "status", "type", "types", "category", "categories", "name", "title", "description",
           "remarks", "remark", "comment", "comments", "notes", "note", "attachment", "attachments", "date",
           "time", "start", "end", "reference", "email", "phone", "address", "department", "company", "amount",
           "quantity", "total", "reason", "priority", "action", "actions", "view", "edit", "create", "update",
           "delete", "draft", "submitted", "pending", "approved", "rejected", "cancelled", "completed", "closed",
           "open", "active", "inactive", "record", "records", "item", "items", "booking", "bookings", "tracking",
           "claim", "claims", "service", "services", "information", "info", "data", "master", "setup", "config",
           "configuration", "mobile", "web", "internal", "general", "main", "overview", "minutes", "meeting",
           "workshop", "client", "document", "documents", "process", "workflow"}
LINKED = re.compile(r"[a-z0-9]+(?:[-.'’][a-z0-9]+)+")


def name_words(text):
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [w for w in words if w not in FILLER and not re.fullmatch(r"v?\d+", w)]


def name_keys(text, whole=True):
    """The words of a name with the ways it is written evened out: "E-PASS", "E.PASS", "E PASS" and "EPASS" all
    give "epass" (each word, each hyphen- or dot-linked word joined up, and the whole name joined up)."""
    words = name_words(text)
    keys = set(words)
    for linked in LINKED.findall(str(text or "").lower()):
        joined = re.sub(r"[^a-z0-9]", "", linked)
        if joined not in FILLER and not re.fullmatch(r"v?\d+", joined):
            keys.add(joined)
    if whole and len(words) > 1:
        keys.add("".join(words))
    return keys


def distinctive(text, whole=True):
    """The words of a name that can say which system it is: not filler, not generic, not a number, 4+ letters.
    whole=False leaves out the whole text joined up (for a document's text rather than a name)."""
    return {k for k in name_keys(text, whole) if len(k) >= 4 and k not in GENERIC and not k.isdigit()}


def likeness(a, b):
    """"same" when two system names say the same thing, "similar" when one is part of the other, they are
    spelled almost alike or they share a distinctive word ("ABC E-PASS" and "XYZ EPASS System" both say
    "epass"), otherwise None. Hyphens, dots and spaces inside a name do not count."""
    wa, wb = name_words(a), name_words(b)
    if not wa or not wb:
        return None
    if wa == wb or "".join(wa) == "".join(wb):
        return "same"
    sa, sb = set(wa), set(wb)
    if sa <= sb or sb <= sa or difflib.SequenceMatcher(None, " ".join(wa), " ".join(wb)).ratio() >= 0.8:
        return "similar"
    if distinctive(a) & distinctive(b):
        return "similar"
    return None


def project_names(p):
    """The names a project folder goes by: its folder name, the register's project and the spec's name."""
    names = [p.name.replace("-", " ")]
    reg = layout.register_json(p)
    try:
        if reg.exists():
            names.append(json.loads(reg.read_text(encoding="utf-8")).get("project") or "")
        names.append(spec_project(p).get("name") or "")
    except Exception:  # a damaged file must not stop the search
        pass
    return [n for n in names if n]


def project_clients(p):
    """A project folder's client names (the spec's client and short name, the register's client) as flat text."""
    names = []
    try:
        P = spec_project(p)
        names += [P.get("client"), P.get("client_short")]
        reg = layout.register_json(p)
        if reg.exists():
            names.append(json.loads(reg.read_text(encoding="utf-8")).get("client"))
    except Exception:  # a damaged file must not stop the search
        pass
    return {flat(n).strip() for n in names if n and flat(n).strip()}


def find_earlier(name, skip=None, client=None):
    """Earlier work on the same or a similar system, best match first: dicts with kind ("active",
    "archived", "actuals", "log"), title, where, how alike ("same" or "similar") and same_client (a project
    for the client named, when one is given). Of two equally alike, the same client's comes first."""
    found = []
    client_key = flat(client).strip() if client else ""

    def best(names):
        found_ = [likeness(name, n) for n in names]
        return "same" if "same" in found_ else ("similar" if "similar" in found_ else None)

    for kind, folder in (("active", PROJECTS), ("archived", ARCHIVE)):
        for p in sorted(folder.iterdir()) if folder.exists() else []:
            if not p.is_dir() or p.name.startswith("_") or (kind == "active" and p.name == skip):
                continue
            names = project_names(p)
            how = best(names)
            if how:
                where = f"projects/{p.name}" if kind == "active" else f"projects/_archive/{p.name}"
                found.append({"kind": kind, "slug": p.name, "title": names[-1], "where": where, "how": how,
                              "same_client": bool(client_key) and client_key in project_clients(p)})
    kdir = knowledge_dir()
    for f in sorted((kdir / "actuals").glob("*.md")) if (kdir / "actuals").exists() else []:
        try:
            heading = next((l[2:].split("–")[0].strip() for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("# ")), "")
        except OSError:
            heading = ""
        how = best([f.stem.replace("-", " "), heading])
        if how:
            found.append({"kind": "actuals", "slug": f.stem, "title": heading or f.stem, "where": f"knowledge/actuals/{f.name}",
                          "how": how, "same_client": False})
    log = kdir / "projects-log.md"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not line.lstrip().startswith("|") or not cells[0] or set(cells[0]) <= set("-: ") or cells[0] == "Project":
                continue
            how = likeness(name, cells[0])
            if how:
                found.append({"kind": "log", "slug": "", "title": " | ".join(c for c in cells[:3] if c),
                              "where": "knowledge/projects-log.md", "how": how, "same_client": False})
    return sorted(found, key=lambda f: (f["how"] != "same", not f["same_client"]))


def describe(f):
    """One plain line for a match from find_earlier."""
    alike = ("same name" if f["how"] == "same" else "similar name") + (", same client" if f.get("same_client") else "")
    if f["kind"] == "active":
        return f"active project {f['title']} ({f['where']}, {alike}): carry on there rather than starting again"
    if f["kind"] == "archived":
        return (f"archived project {f['title']} ({f['where']}, {alike}): bring it back with "
                f"python -I tools/project.py restore {f['slug']}, or start a new phase that refers to it")
    if f["kind"] == "actuals":
        return (f"delivered before: {f['title']} ({f['where']}, {alike}): its actual effort, change requests and "
                "lessons are the most useful context for the new work")
    return f"projects log row: {f['title']} ({f['where']}, {alike})"


def spec_project(p):
    import yaml

    spec = layout.spec_file(p)
    if not spec.exists():
        return {}
    return (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("project") or {}


def issues_file(p):
    return layout.issued_file(p)


def load_issues(p):
    """Every version issued, from issued.json and from any copy OneDrive or SharePoint made of it when two
    people issued at about the same time (issued-<computer>.json): a version issued on either side stays locked."""
    f = issues_file(p)
    found, seen = [], set()
    paths = ([f] if f.exists() else []) + (sorted(x for x in f.parent.glob("issued*.json") if x != f) if f.parent.is_dir() else [])
    for path in paths:
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            if path == f:
                raise
            continue  # a damaged sync copy: issued.json itself still counts
        for record in records if isinstance(records, list) else []:
            if isinstance(record, dict) and str(record.get("version")) not in seen:
                seen.add(str(record.get("version")))
                found.append(record)
    return found


def write_issues(p, issues):
    """Write issued.json in one step (a file of its own beside it, then put in its place): a stop part-way never
    leaves the record of what was issued half written."""
    f = issues_file(p)
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".issued-", suffix=".tmp", dir=f.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(json.dumps(issues, indent=2, ensure_ascii=False))
        os.replace(tmp, f)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def version_of(P):
    """The spec's version as text. A version written without quotes is read by YAML as a number, so 1.10 becomes
    1.1 and would be named, locked and overwritten as v1.1: that is refused with how to write it."""
    version = P.get("version")
    if isinstance(version, float):
        sys.exit(f"The spec's project.version is written without quotes, so it reads as the number {version}: "
                 f"a version such as 1.10 would become 1.1. Write it in quotes, for example version: \"{version}\" "
                 "(or \"1.10\" if that is what was meant), then run this again.")
    return str(version or "")


def issued_files(p, version):
    """The generated requirements document of this version: its Word file and PDF, by their exact names (not a
    version that only starts the same, nor Word's ~$ lock file or a leftover from the PDF step)."""
    folder = layout.output_dir(p)
    ends = (f" v{version}.docx", f" v{version}.pdf")
    return sorted(f for f in folder.iterdir() if f.is_file() and f.name.endswith(ends) and not f.name.startswith("~$")) \
        if folder.is_dir() else []


def is_issued(p, version):
    """The issue record for this version, or None. Used by the requirements document generator to refuse overwriting."""
    return next((i for i in load_issues(p) if str(i["version"]) == str(version)), None)


def safe_name(text):
    """Text as part of a file name Windows can store: \\ / : * ? " < > | become a hyphen. A colon is the
    dangerous one: Windows accepts it and writes the file where nobody can see it. Also used for the name
    of the generated requirements document."""
    return re.sub(r"[\\/:*?\"<>|]+", "-", str(text).strip()).rstrip(". ")


def read_only(path, on=True):
    mode = os.stat(path).st_mode
    os.chmod(path, (mode & ~stat.S_IWRITE) if on else (mode | stat.S_IWRITE))


# ------------------------------------------------------------------ which project a file belongs to
# A file that does not name its project is never filed on a guess: one client often has several projects, and
# a confidential document in the wrong project is worse than a question. `match` scores a file against every
# active project; points add up per project, from the evidence below (strongest first).
#
#   comments made on a project's mock-up build (the `build` stamp of a comments export)     100
#   comments on screens only that project's spec has                                       15 a screen, at most 45
#   an id (R-, FB-, UAT-, CR-, a requirement id) of the project, with the words around it
#     matching that item's topic                                                            25 (20 when another
#                                                                                           project has the id), at most 75
#   an id only that project has, the words around it not matching its topic                 5, at most 15
#   the system name / short name, only that project's                                       30 / 15
#   not the whole name but a distinctive word of it ("EPASS" for "ABC E-PASS System")       10
#   its role names, screen titles, status names, field labels (only that project's)         8 / 6 / 4 / 2 each,
#                                                                                           halved for one word, at most 40;
#                                                                                           a word as common as "User" or
#                                                                                           "Details" (GENERIC) never counts
#   the client's name: 12 when only one project is for that client, otherwise 5
#   names of its people (sample users, signatories, workshop attendees) / e-mail domains    4 / 12 each, at most 12 / 24
#   the file name containing the system name, short name or folder name                     20
#   ... or only a distinctive word of them (hyphens and dots evened out)                    15
#   commented screens missing from its spec                                                 -10 each, at most -30
#
# Verdict: "clear" when the best project has at least CLEAR points, CLEAR_LEAD more than the next and at least
# twice its score (and no archived project comes close); "likely" when it has at least LIKELY and LIKELY_LEAD
# more than the next; otherwise "unknown". Only "clear" may be planned without asking about the file.
CLEAR, CLEAR_LEAD, LIKELY, LIKELY_LEAD = 40, 25, 15, 8
ID = re.compile(r"\b[A-Z][A-Z0-9]{0,7}(?:-[A-Z0-9]{1,8})*-\d{1,5}\b")
EMAIL = re.compile(r"\b[\w.+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")
PUBLIC_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
               "me.com", "proton.me", "protonmail.com", "example.com"}
TERM_WEIGHT = {"role": 8, "screen": 6, "status": 4, "field": 2}
TEXT_LIMIT = 500_000  # characters read from a file: plenty to recognise it, and keeps match fast
NOTES = ".notes.json"  # beside the files left in a folder (the inbox): {file name: {date, reason}}


def flat(text):
    """Text as lower-case words between single spaces, padded, so a phrase is found with `in`."""
    return " " + " ".join(re.findall(r"[^\W_]+", str(text or "").lower())) + " "


def tools_import(name):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return __import__(name)


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _labels(node, out):
    """Field and column labels anywhere under screens and dialogs."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("fields", "columns") and isinstance(value, list):
                out.extend(str(f["label"]) for f in value if isinstance(f, dict) and f.get("label"))
            _labels(value, out)
    elif isinstance(node, list):
        for value in node:
            _labels(value, out)
    return out


def profile(p, archived=False):
    """What a project folder is recognised by: names, spec words, screens, mock-up builds, ids and people."""
    import yaml

    spec_text = ""
    try:
        spec_text = layout.spec_file(p).read_text(encoding="utf-8")
        spec = yaml.safe_load(spec_text) or {}
    except Exception:  # a missing or damaged spec still leaves the register and the rest
        spec = {}
    spec = spec if isinstance(spec, dict) else {}
    P = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    reg = _json(layout.register_json(p))
    reg = reg if isinstance(reg, dict) else {}
    lst = lambda key: [x for x in spec.get(key) or [] if isinstance(x, dict)] if isinstance(spec.get(key), list) else []
    terms = [("role", r.get("name")) for r in lst("roles")]
    terms += [("screen", s.get(k)) for s in lst("screens") + lst("dialogs") for k in ("title", "menu")]
    terms += [("status", s.get("name")) for s in lst("statuses")]
    terms += [("field", label) for label in _labels([lst("screens"), lst("dialogs")], [])]
    version = str(P.get("version") or "")
    prof = {"slug": p.name, "where": f"projects/_archive/{p.name}" if archived else f"projects/{p.name}",
            "archived": archived, "name": str(P.get("name") or reg.get("project") or p.name.replace("-", " ")),
            "short": str(P.get("short_name") or ""), "client": str(P.get("client") or reg.get("client") or ""),
            "client_short": str(P.get("client_short") or ""), "version": version,
            "terms": {}, "screens": {str(s.get("id")) for s in lst("screens") if s.get("id")},
            "versions": {version} if version else set(), "builds": {}, "ids": {}, "people": set(), "domains": set()}
    for cat, label in terms:
        key = flat(label).strip()
        if len(key) >= 4 and key not in prof["terms"]:
            prof["terms"][key] = (cat, str(label))
    mock = layout.mockup_dir(p)
    for folder in [mock] + sorted((mock / "versions").glob("v*")) if (mock / "versions").exists() else [mock]:
        label = folder.name if folder != mock else (f"v{version}" if version else "current")
        if folder != mock:
            prof["versions"].add(folder.name[1:])
        try:
            stamp = (folder / ".built-from").read_text(encoding="utf-8").strip()
        except OSError:
            stamp = ""
        if stamp:
            prof["builds"].setdefault(stamp, label)
    ids = prof["ids"]
    for it in reg.get("items") or []:
        if isinstance(it, dict) and it.get("id"):
            ids[str(it["id"])] = ("register item", " ".join(str(it.get(k) or "") for k in ("title", "question", "finding")))
    fb = _json(layout.feedback_file(p))
    for c in fb if isinstance(fb, list) else []:
        if isinstance(c, dict) and c.get("id"):
            ids[str(c["id"])] = ("mock-up comment", f"{c.get('element') or ''} {c.get('text') or ''}")
    for r in lst("requirements"):
        if r.get("id"):
            items = " ".join(str(i.get("text") if isinstance(i, dict) else i) for i in r.get("items") or [])
            ids[str(r["id"])] = ("requirement", f"{r.get('title') or ''} {items}")
    for f in sorted(layout.uat_source(p).glob("*.json")) if layout.uat_source(p).exists() else []:
        u = _json(f)
        for c in u.get("cases") or [] if isinstance(u, dict) else []:
            if isinstance(c, dict) and c.get("id"):
                ids[str(c["id"])] = ("UAT script", str(c.get("title") or ""))
    crs = _json(layout.cr_log(p))
    for c in crs.get("crs") or [] if isinstance(crs, dict) else []:
        if isinstance(c, dict) and c.get("id"):
            ids[str(c["id"])] = ("change request", f"{c.get('title') or ''} {c.get('request') or ''}")
    people = [r.get("user") for r in lst("roles")] + [s.get("name") for s in lst("signoff")]
    raw = [spec_text, json.dumps(reg, ensure_ascii=False)]
    for f in sorted(layout.workshops_source(p).glob("*.json")) if layout.workshops_source(p).exists() else []:
        w = _json(f)
        if isinstance(w, dict):
            people += [a.get("name") for a in w.get("attendees") or [] if isinstance(a, dict)]
            raw.append(json.dumps(w, ensure_ascii=False))
    prof["people"] = {k for k in (flat(n).strip() for n in people if n) if len(k) >= 5}
    prof["domains"] = {d.lower() for d in EMAIL.findall("\n".join(raw))} - PUBLIC_MAIL
    return prof


def read_for_match(path, text_file=None):
    """(text, comments): the file's text, and its comments when it is a mock-up comments export (else None).
    Word, PDF and Excel are read with extract.py's readers; --text gives an extraction made earlier."""
    path = Path(path)
    if text_file:
        return Path(text_file).read_text(encoding="utf-8", errors="replace")[:TEXT_LIMIT], None
    ext = path.suffix.lower()
    if ext == ".json":
        data = _json(path)
        items = data.get("items") or data.get("comments") if isinstance(data, dict) else data
        if isinstance(items, list) and items and all(isinstance(c, dict) for c in items) and any("screen" in c and "text" in c for c in items):
            lines = [" ".join(str(c.get(k) or "") for k in ("id", "screen", "element", "text", "author")) for c in items]
            return "\n".join(lines)[:TEXT_LIMIT], items
        return (json.dumps(data, ensure_ascii=False) if data is not None else "")[:TEXT_LIMIT], None
    extract = tools_import("extract")
    if ext == ".docx":
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "images").mkdir()
            return extract.Docx(path, Path(tmp)).run()[0][:TEXT_LIMIT], None
    if ext == ".pdf":
        import pymupdf  # the text layer only: extract.py also renders pages to pictures, which match does not need

        parts, size = [], 0
        for page in pymupdf.open(path):
            parts.append(page.get_text("text"))
            size += len(parts[-1])
            if size > TEXT_LIMIT:
                break
        return "\n".join(parts)[:TEXT_LIMIT], None
    if ext in (".xlsx", ".xlsm"):
        return extract.extract_xlsx(path)[0][:TEXT_LIMIT], None
    if ext in (".md", ".txt", ".csv", ".vtt", ".srt", ".eml", ".html", ".htm"):
        return extract.read_text(path)[0][:TEXT_LIMIT], None
    return "", None  # a picture or an unknown type: only its name can say anything


def _on_topic(context, topic):
    register = tools_import("register")
    a, b = register.words(context), register.words(topic)
    shared = a & b
    if len(shared) < 2 or len(shared) / max(1, min(len(a), len(b))) < 0.3:
        return []
    said = re.findall(r"[a-z0-9]+", re.sub(r"(?<=\w)[-'’](?=\w)", "", context.lower()))
    return list(dict.fromkeys(w for w in said if register.stem(w) in shared))  # as written, not as stems


def id_contexts(text):
    """{id: the lines it is on}, for every id-like word of the text (R-012, FB-003, UAT-001, FR-APP-001 ...)."""
    found = {}
    for line in text.splitlines():
        for rid in set(ID.findall(line)):
            found.setdefault(rid, []).append(line)
    return found


def score(prof, others, text, comments, file_name, contexts=None):
    """[(points, what matched)] for one project, `others` being the other active projects."""
    ev = []
    contexts = id_contexts(text) if contexts is None else contexts
    ftext = flat(text)
    other_terms = set().union(*(o["terms"] for o in others)) if others else set()
    other_screens = set().union(*(o["screens"] for o in others)) if others else set()

    # (a) a mock-up comments export
    if comments is not None:
        builds = {str(c.get("build")) for c in comments if c.get("build")}
        made_on = sorted({prof["builds"][b] for b in builds if b in prof["builds"]})
        if made_on:
            ev.append((100, f"comments made on this project's mock-up ({', '.join(made_on)})"))
        shown = {str(c.get("screen")) for c in comments if c.get("screen")}
        mine = shown & prof["screens"]
        only = sorted(mine - other_screens)
        if only:
            ev.append((min(45, 15 * len(only)), f"comments on screens only this project has: {', '.join(only[:6])}"))
        elif mine:
            ev.append((min(6, 2 * len(mine)), f"comments on screens other projects have too: {', '.join(sorted(mine)[:6])}"))
        missing = sorted(shown - prof["screens"])
        if missing and prof["screens"]:
            ev.append((-min(30, 10 * len(missing)), f"commented screens not in its spec: {', '.join(missing[:6])}"))
        versions = {str(c.get("version")) for c in comments if c.get("version") not in (None, "")} & prof["versions"]
        if versions and mine:
            ev.append((3, f"made on version {', '.join(sorted(versions))}, which this project has"))

    # (b) ids of its register, comments, requirements, UAT scripts and change requests
    topical = plain = 0
    for rid in sorted(set(contexts) & set(prof["ids"])):
        kind, topic = prof["ids"][rid]
        context = " ".join(contexts[rid])[:2000].replace(rid, " ")
        elsewhere = any(rid in o["ids"] for o in others)
        shared = _on_topic(context, topic)
        if shared and topical < 75:
            pts = min(20 if elsewhere else 25, 75 - topical)
            topical += pts
            ev.append((pts, f"{rid} ({kind}) with its topic: {', '.join(shared[:4])}"
                            + (" (other projects have that id too)" if elsewhere else "")))
        elif not shared and not elsewhere and plain < 15:
            plain += 5
            ev.append((5, f"{rid}: only this project has a {kind} with that id (the words around it do not match it)"))

    # (c) words of its spec
    def unique_phrase(value, pts, what, case=False):
        key = flat(value).strip()
        if len(key) < 2:
            return
        if case:  # a short name: as written, a word of its own ("LRS", not "lrs" inside another word)
            found = re.search(rf"(?<![^\W_]){re.escape(value)}(?![^\W_])", text)
        else:
            found = f" {key} " in ftext
        if found and not any(key in (flat(o["name"]).strip(), flat(o["short"]).strip()) for o in others):
            ev.append((pts, f"{what} \"{value}\""))
    if prof["name"]:
        unique_phrase(prof["name"], 30, "system name")
    # Not the whole name but a distinctive word of it ("EPASS" for "ABC E-PASS System"): a hint, not proof.
    others_words = set().union(*(distinctive(o[k]) for o in others for k in ("name", "short", "slug"))) if others else set()
    own_words = (distinctive(prof["name"]) | distinctive(prof["short"]) | distinctive(prof["slug"].replace("-", " "))) - others_words
    if own_words and not any(w.startswith("system name") for _, w in ev):
        said = sorted(own_words & distinctive(text, whole=False))
        if said:
            ev.append((10, f"a word of its system name: {', '.join(said[:3])}"))
    if len(prof["short"]) >= 2:
        unique_phrase(prof["short"], 15, "short name", case=True)
    got = 0
    hits = {}
    for key, (cat, label) in prof["terms"].items():
        if key in other_terms or f" {key} " not in ftext or (" " not in key and key in GENERIC):
            continue  # a word as common as "User" or "Details" says nothing about which project
        pts = TERM_WEIGHT[cat] if " " in key else (TERM_WEIGHT[cat] + 1) // 2
        pts = min(pts, 40 - got)
        if pts <= 0:
            break
        got += pts
        hits.setdefault(cat, []).append((pts, label))
    for cat in ("role", "screen", "status", "field"):
        if hits.get(cat):
            names = ", ".join(f'"{label}"' for _, label in hits[cat][:6]) + (" …" if len(hits[cat]) > 6 else "")
            ev.append((sum(p for p, _ in hits[cat]), f"{cat} {'names' if cat in ('role', 'status') else 'titles' if cat == 'screen' else 'labels'} only this project has: {names}"))
    for client in dict.fromkeys(c for c in (prof["client"], prof["client_short"]) if c):
        key = flat(client).strip()
        found = (f" {key} " in ftext) if client == prof["client"] else re.search(rf"(?<![^\W_]){re.escape(client)}(?![^\W_])", text)
        if found and len(key) >= 2:
            same = sum(1 for o in others if key in (flat(o["client"]).strip(), flat(o["client_short"]).strip()))
            ev.append((5, f"client \"{client}\" (also the client of {same} other project{'s' if same != 1 else ''}: on its own it does not say which)")
                      if same else (12, f"client \"{client}\" (no other active project is for this client)"))
            break

    # (d) people, e-mail domains and the file name
    other_people = set().union(*(o["people"] for o in others)) if others else set()
    met = sorted(n for n in prof["people"] - other_people if f" {n} " in ftext)
    if met:
        ev.append((min(12, 4 * len(met)), f"people of this project: {', '.join(n.title() for n in met[:4])}"))
    other_domains = set().union(*(o["domains"] for o in others)) if others else set()
    domains = sorted({d.lower() for d in EMAIL.findall(text)} & (prof["domains"] - other_domains))
    if domains:
        ev.append((min(24, 12 * len(domains)), f"e-mail addresses at {', '.join(domains[:3])}"))
    stem_words = set(name_words(Path(file_name).stem))
    for value, what in ((prof["name"], "system name"), (prof["short"], "short name"), (prof["slug"].replace("-", " "), "folder name")):
        words_ = set(name_words(value))
        if words_ and words_ <= stem_words and not any(set(name_words(o[k])) == words_ for o in others for k in ("name", "short", "slug")):
            ev.append((20, f"the file name has its {what} \"{value}\""))
            break
    else:
        named = sorted(own_words & distinctive(Path(file_name).stem))
        if named:
            ev.append((15, f"the file name has a word of its system name: {', '.join(named[:3])}"))
    return sorted(ev, key=lambda e: -e[0])


def match_file(path, text_file=None):
    """Which project a file belongs to: {file, kind, verdict, best, summary, projects, archived, delivered, note}."""
    path = Path(path)
    text, comments = read_for_match(path, text_file)
    contexts = id_contexts(text)
    active = [profile(p) for p in sorted(PROJECTS.iterdir()) if p.is_dir() and not p.name.startswith("_")] if PROJECTS.exists() else []
    old = [profile(p, archived=True) for p in sorted(ARCHIVE.iterdir()) if p.is_dir()] if ARCHIVE.exists() else []

    def rank(profs, others_of):
        out = []
        for prof in profs:
            ev = score(prof, others_of(prof), text, comments, path.name, contexts)
            out.append({"slug": prof["slug"], "name": prof["name"], "where": prof["where"],
                        "score": sum(p for p, _ in ev), "evidence": [{"points": p, "what": w} for p, w in ev]})
        return sorted(out, key=lambda r: (-r["score"], r["slug"]))

    ranked = rank(active, lambda prof: [o for o in active if o is not prof])
    # An archived project is scored against the other archived ones: one close to an active project (an earlier
    # phase of the same system) must show up, so that the file is asked about rather than filed.
    archived = [r for r in rank(old, lambda prof: [o for o in old if o is not prof]) if r["score"] >= LIKELY]
    best = ranked[0]["score"] if ranked else 0
    second = ranked[1]["score"] if len(ranked) > 1 else 0
    if ranked and best >= CLEAR and best - second >= CLEAR_LEAD and best >= 2 * second:
        verdict = "clear"
        if archived and archived[0]["score"] > best - CLEAR_LEAD:
            verdict = "likely"
    elif ranked and best >= LIKELY and best - second >= LIKELY_LEAD:
        verdict = "likely"
    else:
        verdict = "unknown"
    top = ranked[0] if ranked and verdict != "unknown" else None
    kind = "mock-up comments export" if comments is not None else ""
    summary = ""
    if top:
        lead = top["evidence"][0]["what"] if top["evidence"] else ""
        if kind and lead.startswith("comments made on"):
            versions = sorted({str(c.get("version")) for c in comments if c.get("version")})
            summary = f"comments export from {top['name']} mock-up {', '.join('v' + v for v in versions) or ''}".rstrip() + f" → {top['slug']}"
        else:
            summary = "; ".join(e["what"] for e in top["evidence"][:2] if e["points"] > 0) + f" → {top['slug']}"
    seen = {r["slug"] for r in archived}
    delivered = [{"kind": f["kind"], "title": f["title"], "where": f["where"], "how": f["how"], "slug": f["slug"]}
                 for f in find_earlier(path.stem) if f["kind"] != "active" and not (f["kind"] == "archived" and f["slug"] in seen)]
    note = read_notes(path.parent).get(path.name)
    return {"file": path.name, "kind": kind, "verdict": verdict, "best": top["slug"] if top else None,
            "summary": summary, "thresholds": {"clear": CLEAR, "clear_lead": CLEAR_LEAD, "likely": LIKELY, "likely_lead": LIKELY_LEAD},
            "projects": [r for r in ranked if r["score"] > 0 or r["evidence"]], "archived": archived, "delivered": delivered,
            "note": note}


# ------------------------------------------------------------------ notes on files left in the inbox
def _hidden(path, on):
    """Hide the notes file in Windows Explorer (a dot name already hides it on macOS and Linux)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        k = ctypes.windll.kernel32
        attrs = k.GetFileAttributesW(str(path))
        if attrs not in (-1, 0xFFFFFFFF):
            k.SetFileAttributesW(str(path), (attrs | 2) if on else (attrs & ~2))
    except Exception:
        pass


def read_notes(folder):
    notes = _json(Path(folder) / NOTES)
    return notes if isinstance(notes, dict) else {}


def write_notes(folder, notes):
    """Write the notes of a folder, dropping those of files no longer there; no notes, no file."""
    f = Path(folder) / NOTES
    notes = {name: n for name, n in notes.items() if (Path(folder) / name).is_file()}
    if not notes:
        if f.exists():
            _hidden(f, False)
            f.unlink()
        return
    if f.exists():
        _hidden(f, False)  # Windows refuses to overwrite a hidden file
    f.write_text(json.dumps(notes, indent=2, ensure_ascii=False), encoding="utf-8")
    _hidden(f, True)


def drop_note(path):
    path = Path(path)
    notes = read_notes(path.parent)
    if path.name in notes:
        del notes[path.name]
        write_notes(path.parent, notes)


# ------------------------------------------------------------------ commands
# ------------------------------------------------------------------ ready for sign-off
# What a version needs before it goes to the client for signature, from what an end-to-end test found in a
# version that went out too early: a question still marked "Blocks sign-off", the client's raw answers printed
# as the agreed decisions, a field offering other choices than the ones the client listed, "the agreed time"
# with no time agreed anywhere. "stop" holds the issue back; "check" is for the BA to look at.
PLACEHOLDER = re.compile(r"\b(?:the agreed(?: \w+)?|as agreed|to be (?:confirmed|agreed|decided|defined)|TBC|TBD)\b", re.I)
LIST_SPLIT = re.compile(r"\s*[,;]\s*")
LAST_SPLIT = re.compile(r"\s+(?:or|and)\s+", re.I)


def answer_list(text):
    """The choices a client listed in an answer ("Vehicle problem, Dealer closed, Other (with remarks)"), lower
    case, without remarks in brackets; only the short ones, as a list of choices is made of."""
    text = re.sub(r"\([^)]*\)", "", str(text or ""))
    text = re.sub(r"^\s*TEST ANSWER:\s*", "", text, flags=re.I)
    if ":" in text:
        text = text.split(":", 1)[1]
    parts = [c for c in LIST_SPLIT.split(text) if c.strip(" .")]
    # "A, B or C": the last "or" joins the last two choices. Inside the list "Road or weather" is one choice.
    if len(parts) > 1:
        parts = parts[:-1] + LAST_SPLIT.split(parts[-1])
    return {c.strip(" .").lower() for c in parts if c.strip(" .") and len(c.split()) <= 5}


def spec_fields(spec):
    """(where, field) for every field of every screen section and dialog."""
    for s in spec.get("screens") or []:
        for sec in s.get("sections") or []:
            for f in sec.get("fields") or []:
                yield f"screen '{s.get('title') or s.get('id')}'", f
    for d in spec.get("dialogs") or []:
        for f in d.get("fields") or []:
            yield f"dialog '{d.get('title') or d.get('id')}'", f


def readiness(p):
    """What stands between the current version and the client's signature, as (level, text): "stop" or "check"."""
    import yaml

    out = []
    spec_path = layout.spec_file(p)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
    spec = spec or {}
    P = spec.get("project") or {}
    reg_path = layout.register_json(p)
    items = (_json(reg_path) or {}).get("items", []) if reg_path.exists() else []
    client = [it for it in items if it.get("audience") == "client"]

    # The document must show the spec and register as they are now.
    version = str(P.get("version") or "")
    docs = [f for f in issued_files(p, version) if f.suffix == ".docx"] if version and layout.output_dir(p).exists() else []
    if not docs:
        out.append(("stop", f"There is no requirements document for v{version} yet: generate it first."))
    else:
        changed = [x for x in (spec_path, reg_path) if x.exists() and x.stat().st_mtime > docs[0].stat().st_mtime]
        if changed:
            out.append(("stop", f"The {' and the '.join('spec' if x == spec_path else 'register' for x in changed)} changed "
                                f"after v{version} was generated: generate it again so the document shows them."))

    # Open questions: one the client must answer before signing holds it back; an answer waiting for us is ours.
    for it in client:
        if it.get("status") in ("open", "asked", "answered") and it.get("severity") == "high":
            # An answered item still prints as "Blocks sign-off" until it is resolved.
            got = " It has an answer: resolve it with its decision if that settles it." if it.get("status") == "answered" else ""
            out.append(("stop", f"{it['id']} still blocks sign-off: {short_text(it.get('question') or it.get('finding'))}{got} "
                                "Otherwise settle it, or lower its severity if the client agrees to sign without it."))
        elif it.get("status") == "answered":
            out.append(("check", f"{it['id']} has an answer but is still open in the document: resolve it with its decision "
                                 "if the answer settles it, or keep it and add the follow-up question."))
    # Settled items go into the signed document as decisions: in one agreed line, not the client's raw answer.
    raw = [it["id"] for it in client
           if it.get("status") == "resolved" and str(it.get("answer") or "").strip() and not str(it.get("decision") or "").strip()]
    if raw:
        which = f"{raw[0]} is" if len(raw) == 1 else f"{len(raw)} items are"
        listed = "" if len(raw) == 1 else f" ({', '.join(raw)})"
        out.append(("stop", f"{which} settled with no agreed decision, so the document prints the client's own answer as what "
                            f"is signed{listed}. Write each one's decision in one line: "
                            f"register.py update {p.name} {raw[0]} --set decision=\"...\""))

    # Two open questions asking the same thing.
    open_q = [it for it in client if it.get("status") in ("open", "asked", "answered") and it.get("question")]
    try:
        import register as register_tool
        for i, one in enumerate(open_q):
            for other in open_q[i + 1:]:
                if register_tool.similarity(one, other) >= register_tool.DUPLICATE:
                    out.append(("check", f"{one['id']} and {other['id']} look like the same question: merge them, or close one."))
    except Exception:
        pass

    # A choice list on a screen that differs from the one the client gave.
    fields = [(w, f) for w, f in spec_fields(spec) if isinstance(f.get("options"), list) and len(f["options"]) >= 2]
    for it in client:
        if it.get("status") not in ("resolved", "answered"):
            continue
        said = answer_list(it.get("decision") or it.get("answer"))
        if len(said) < 2:
            continue
        for where, f in fields:
            offered = {str(o).strip().lower() for o in f["options"]}
            both = said & offered
            if len(both) >= 2 and len(both) * 2 >= len(offered) and said != offered:
                missing = sorted(o for o in said - offered)
                extra = [str(o) for o in f["options"] if str(o).strip().lower() not in said]
                parts = ([f"leaves out {', '.join(missing)}"] if missing else []) + ([f"adds {', '.join(extra)}"] if extra else [])
                if parts:
                    out.append(("check", f"{where}, field '{f.get('label') or f.get('id')}': its choices differ from {it['id']}'s answer "
                                         f"(it {' and '.join(parts)}). Make them match, or record why they differ."))

    out += sow_readiness(p, spec)

    # "The agreed time" with no time agreed: a requirement that waits on something must say what, through a register item.
    for g in spec.get("requirements") or []:
        for n, item in enumerate(g.get("items") or [], 1):
            text_ = item.get("text") if isinstance(item, dict) else item
            if isinstance(text_, str) and PLACEHOLDER.search(text_) and not (isinstance(item, dict) and item.get("tbc")):
                found = PLACEHOLDER.search(text_).group(0)
                out.append(("check", f"{g.get('id')}.{n} says \"{found}\" with nothing tracking it: write the value, or link the "
                                     "register item that settles it (tbc: R-…)."))

    # Both sides sign.
    signers = spec.get("signoff") or []
    orgs = " ".join(str(s.get("organisation") or "") for s in signers).lower()
    client_names = [str(P.get(k) or "").lower() for k in ("client", "client_short") if P.get(k)]
    try:
        import workspace
        co = workspace.company()
        own_names = [str(co.get(k) or "").lower() for k in ("name", "short_name") if co.get(k)]
    except Exception:
        own_names = []
    if not signers:
        out.append(("check", "The spec names nobody to sign (signoff): add the client's signatories and your own."))
    else:
        if client_names and not any(n and n in orgs for n in client_names):
            out.append(("check", "Nobody signs for the client in the spec's signoff."))
        if own_names and not any(n and n in orgs for n in own_names):
            out.append(("check", "Nobody signs for your side in the spec's signoff."))
    return out


def sow_readiness(p, spec):
    """Whether everything the scope of work sold is specified: a stop for an item with no requirement and nothing
    agreed about leaving it out, a check for a requirement that no item of the scope of work asked for."""
    import generate_requirements as gen

    out = []
    items = gen.sow_items(spec)
    if not items:
        # The scope of work may only be in an estimate, with its lines; or nowhere in the project yet.
        lines = []
        src = layout.estimates_source(p)
        for f in sorted(src.glob("*.json")) if src.exists() else []:
            lines = ((_json(f) or {}).get("sow") or {}).get("lines") or lines
        if lines:
            out.append(("check", f"The scope of work's {len(lines)} lines are in the estimate but not in the spec, so nothing "
                                 "checks that each is specified. Copy their ref and item (never the mandays) to the spec's sow, "
                                 "and name them on the requirement groups (sow: …)."))
        else:
            out.append(("check", "The spec lists no scope of work items (sow), so nothing checks that everything sold is "
                                 "specified. Add them from the scope of work, if there is one."))
        return out
    cover = gen.sow_coverage(spec)
    known = {str(x["ref"]).strip() for x in items if x.get("ref") is not None}
    for x in items:
        ref = str(x.get("ref")).strip()
        if not cover.get(ref) and not x.get("deferred"):
            out.append(("stop", f"Scope of work item {ref} \"{short_text(x.get('item'), 70)}\" has no requirement. Write its "
                                "requirements and name it on them (sow: \"" + ref + "\"), or, if the client agrees to leave it out "
                                "of this version, say so on the item (deferred: …)."))
    for ref in sorted(set(cover) - known):
        out.append(("stop", f"{', '.join(cover[ref])} name{'s' if len(cover[ref]) == 1 else ''} scope of work item {ref}, "
                            "which the spec's sow does not have."))
    loose = [str(g.get("id")) for g in spec.get("requirements") or []
             if isinstance(g, dict) and not gen.sow_refs(g) and not any(gen.sow_refs(i) for i in g.get("items") or [])]
    if loose:
        out.append(("check", f"{', '.join(loose)} name{'s' if len(loose) == 1 else ''} no scope of work item: link "
                             f"{'it' if len(loose) == 1 else 'each'} to the item it specifies (sow: …), or, if the scope of "
                             "work did not sell it, it may be a change request."))
    return out


def short_text(text, width=110):
    text = " ".join(str(text or "").split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def show_readiness(found):
    stops = [t for level, t in found if level == "stop"]
    checks = [t for level, t in found if level == "check"]
    if stops:
        print(f"Not ready for sign-off ({len(stops)} to fix first):")
        for t in stops:
            print(f"  - {t}")
    if checks:
        print(f"To look at before it goes out ({len(checks)}):")
        for t in checks:
            print(f"  - {t}")
    if not found:
        print("Ready for sign-off: nothing open blocks it, every decision is written, and the document is up to date.")
    return stops


def cmd_ready(a):
    p = project_dir(a.slug)
    stops = show_readiness(readiness(p))
    if stops:
        print("Fix those, generate the document again, and run this again. To issue it anyway: "
              f"project.py issue {a.slug} --anyway \"<why>\".")
        sys.exit(1)


def cmd_issue(a):
    p = project_dir(a.slug)
    P = spec_project(p)
    version = version_of(P)
    if not version:
        sys.exit("The project has no spec version to issue.")
    if is_issued(p, version):
        sys.exit(f"v{version} was already issued. Bump project.version in the spec for the next version.")
    files = issued_files(p, version)
    if not files:
        sys.exit(f"No generated requirements document for v{version} in {layout.shown(p, layout.output_dir(p))}/. Generate it first.")
    if not any(f.suffix == ".pdf" for f in files) and not a.without_pdf:
        sys.exit(f"v{version} has no PDF (the Word step did not finish), so its contents and page numbers may not be "
                 "up to date. Generate it again where Word is available, then issue it. To issue the Word file alone, "
                 "add --without-pdf. Nothing was issued.")
    stops = show_readiness(readiness(p))
    if stops and not (a.anyway or "").strip():
        sys.exit(f"Nothing was issued. Fix the points above first, or, if the client signs it as it is, issue it with "
                 f"--anyway \"<why>\" (the reason is kept with the issue).")
    note = a.note or ""
    if stops:
        note = (note + " " if note else "") + f"Issued with {len(stops)} point(s) open: {a.anyway.strip()}"
    issues = load_issues(p)
    record = {"version": version, "date": a.date or dt.date.today().isoformat(),
              "to": a.to or P.get("client_short") or P.get("client", ""), "files": [f.name for f in files], "note": note}
    issues.append(record)
    write_issues(p, issues)
    snap = layout.snapshot(p, version)
    for f in files + ([snap] if snap.exists() else []):
        read_only(f)
    print(f"Issued v{version} to {record['to']} on {record['date']}: {', '.join(record['files'])}")
    print("Those files are now read-only, and the generator will not overwrite this version.")
    try:  # the project's overview page follows what was just written; it never stops this command
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import overview; overview.refresh(p)
    except Exception:
        pass


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
    try:
        date = dt.date.fromisoformat(a.date).isoformat() if a.date else dt.date.fromtimestamp(src.stat().st_mtime).isoformat()
    except ValueError:
        sys.exit(f"--date {a.date} is not a date: write it as YYYY-MM-DD. Nothing was filed.")
    kind = safe_name(a.kind)
    name = f"{date} {kind}" + (f" on v{safe_name(a.responds_to.lstrip('v'))}" if a.responds_to else "") + src.suffix.lower()
    docs = layout.docs_dir(p)
    dest = docs / name
    n = 2
    while dest.exists():
        dest = docs / f"{Path(name).stem} ({n}){src.suffix.lower()}"
        n += 1
    dest.parent.mkdir(exist_ok=True)
    if a.copy:
        shutil.copy2(str(src), str(dest))
    else:
        move_file(src, dest)
    drop_note(src)  # a file left in the inbox with a note of why: filed now, so the note goes
    print(f"Filed {src.name} as {layout.shown(p, dest)}")
    try:  # the project's overview page follows what was just written; it never stops this command
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import overview; overview.refresh(p)
    except Exception:
        pass


def move_file(src, dest):
    """Move one file, never leaving it in both places. A rename moves it in one step; only to another drive is it
    copied, and the copy is taken back if the original cannot then be removed."""
    stop = (f"Nothing was filed: {src.name} is open in another program (or OneDrive is syncing it). "
            "Close it, then run this again.")
    try:
        os.rename(src, dest)
        return
    except PermissionError:
        sys.exit(stop)
    except OSError as e:
        if e.errno != errno.EXDEV and getattr(e, "winerror", None) != 17:  # 17: not the same drive
            sys.exit(f"Nothing was filed: {src.name} could not be moved ({e.strerror or type(e).__name__}).")
    shutil.copy2(str(src), str(dest))
    try:
        src.unlink()
    except OSError:
        dest.unlink(missing_ok=True)
        sys.exit(stop)


def move_whole(src, dest, done):
    """Move a project folder in one step, or not at all. A rename never copies: when something in the folder is
    open (the register in Excel, a document in Word, OneDrive syncing), Windows refuses it and nothing moves,
    where a copy-then-delete would leave half the project in each place."""
    try:
        os.rename(src, dest)
    except OSError as e:
        sys.exit(f"Nothing was {done}: {src.name} could not be moved ({e.strerror or type(e).__name__}). Something in "
                 "the folder is probably open: close its files in Excel and Word, let OneDrive finish syncing, "
                 "then run this again.")


def cmd_archive(a):
    p = project_dir(a.slug)
    if (ARCHIVE / a.slug).exists():
        sys.exit(f"An archived project called '{a.slug}' already exists (projects/_archive/{a.slug}), so nothing was "
                 f"moved. To keep both, rename this project's folder first (for example {a.slug}-phase-2), then archive it.")
    ARCHIVE.mkdir(exist_ok=True)
    move_whole(p, ARCHIVE / a.slug, "archived")
    print(f"Archived {a.slug} to projects/_archive/. Restore with: python -I tools/project.py restore {a.slug}")


def cmd_restore(a):
    src = ARCHIVE / a.slug
    if not src.exists():
        sys.exit(f"No archived project '{a.slug}'.")
    if (PROJECTS / a.slug).exists():
        sys.exit(f"projects/{a.slug} already exists.")
    move_whole(src, PROJECTS / a.slug, "restored")
    print(f"Restored {a.slug} to projects/.")


def cmd_find(a):
    found = find_earlier(a.name, client=a.client)
    if not found:
        print(f"No earlier project or delivered system matches '{a.name}': start it as a new project.")
        return
    print(f"Earlier work on a system like '{a.name}':")
    for f in found:
        print(f"- {describe(f)}")
    print("Ask the user whether to carry on with it, start a new phase linked to it, or start fresh.")


VERDICT = {
    "clear": "clear: it belongs to {best}. Show it in the plan with its evidence; file it once the user says go ahead.",
    "likely": "likely {best}, but not clear: ask the user about this file (the guesses above, New project, Leave in the inbox).",
    "unknown": "unknown: nothing says clearly which project. Ask the user about this file; unanswered, it stays in the inbox.",
}


def cmd_match(a):
    path = Path(a.file)
    if not path.is_file():
        sys.exit(f"No such file: {path}")
    if a.text and not Path(a.text).is_file():
        sys.exit(f"No such text file: {a.text}")
    try:
        m = match_file(path, a.text)
    except Exception as e:  # a file that cannot be read is matched on nothing rather than guessed
        sys.exit(f"{path.name} could not be read ({type(e).__name__}: {e}). Extract it first and pass --text, or ask the user.")
    if a.json:
        print(json.dumps(m, indent=2, ensure_ascii=False))
        return
    print(f"{m['file']}" + (f" ({m['kind']})" if m["kind"] else ""))
    if not m["projects"]:
        print("  No active project matches anything in it.")
    for n, r in enumerate(m["projects"], 1):
        print(f"  {n}. {r['slug']} ({r['name']}): {r['score']} points")
        for e in r["evidence"]:
            print(f"     {e['points']:+4d}  {e['what']}")
    for r in m["archived"]:
        print(f"  Archived, not a place to file it unless restored first: {r['slug']} ({r['name']}), {r['score']} points; "
              f"python -I tools/project.py restore {r['slug']}")
        for e in r["evidence"][:3]:
            print(f"     {e['points']:+4d}  {e['what']}")
    for f in m["delivered"]:
        print(f"  Earlier work: {describe(f)}")
    if m["note"]:
        print(f"  Left in the inbox on {m['note'].get('date', '?')}: {m['note'].get('reason', '')}")
    print("Verdict: " + VERDICT[m["verdict"]].format(best=m["best"] or "?"))
    if m["summary"]:
        print(f"Plan line: {m['summary']}")


def cmd_hold(a):
    path = Path(a.file)
    if not path.is_file():
        sys.exit(f"No such file: {path}")
    notes = read_notes(path.parent)
    notes[path.name] = {"date": dt.date.today().isoformat(), "reason": " ".join(a.reason.split())}
    write_notes(path.parent, notes)
    print(f"Left {path.name} where it is, with a note of why ({path.parent.name}/{NOTES}): {notes[path.name]['reason']}")


def check_one(slug, fix):
    p = PROJECTS / slug
    problems, fixed, notes = [], [], []
    new = layout.is_new(p)
    if new:
        needed = [(layout.spec_dir(p), f"{layout.MACHINE}/spec/"), (layout.feedback_dir(p), f"{layout.MACHINE}/feedback/"),
                  (layout.docs_dir(p), f"{layout.DOCS}/")]
    else:
        needed = [(p / d, f"{d}/") for d in LAYOUT]
    for folder, label in needed:
        if not folder.is_dir():
            if fix:
                folder.mkdir(parents=True)
                fixed.append(f"created {label}")
            else:
                problems.append(f"no {label} folder")
    if new and not (p / layout.MACHINE / layout.README).exists():
        if fix:
            layout.write_readme(p)
            fixed.append(f"wrote {layout.MACHINE}/{layout.README}")
        else:
            problems.append(f"no {layout.MACHINE}/{layout.README}")
    reg = layout.register_json(p)
    if not reg.exists():
        if fix:
            P = spec_project(p)
            reg.write_text(json.dumps({"project": P.get("name") or slug.replace("-", " ").title(),
                                       "client": P.get("client", ""), "items": []}, indent=2), encoding="utf-8")
            fixed.append("created an empty register")
        else:
            problems.append(f"no {layout.shown(p, reg)}")
    else:
        r = json.loads(reg.read_text(encoding="utf-8"))
        if r.get("project", "").lower() == slug and fix:
            P = spec_project(p)
            if P.get("name"):
                r["project"] = P["name"]
                reg.write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")
                fixed.append("set the register's project name from the spec")
    if not new:
        notes.append(f"in the old folder layout: to move it to the new one, say 'migrate the folders' "
                     f"(python -I tools/project.py migrate {slug} --dry-run lists the moves first). Both layouts work")
    P = spec_project(p)
    version = str(P.get("version") or "")
    issued = {str(i["version"]) for i in load_issues(p)}
    out = layout.output_dir(p)
    generated = sorted({m.group(1) for f in out.glob("*.docx") if (m := re.search(r" v([\d.]+)\.docx$", f.name))}) if out.exists() else []
    if version and version in issued:
        notes.append(f"v{version} is issued: bump project.version before changing the spec")
    docs = layout.docs_dir(p)
    loose = [f.name for f in docs.glob("*") if f.is_file() and not re.match(r"\d{4}-\d{2}-\d{2} ", f.name)] if docs.exists() else []
    if loose:
        notes.append(f"{len(loose)} document(s) in {layout.shown(p, docs)}/ without a date in the name (fine for originals; new files are filed with dates)")
    if generated and not issued:
        notes.append(f"document versions generated ({', '.join('v' + g for g in generated)}) but none recorded as issued")
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


def migrate_one(p, dry_run, back):
    """Move one project between the layouts, or list the moves. Returns True when it moved (or would)."""
    result = (layout.undo if back else layout.migrate)(p, dry_run=dry_run)
    where = "the old layout" if back else "the new layout"
    if result["refusals"]:
        print(f"{p.name}: not moved to {where}, because")
        for r in result["refusals"]:
            print(f"  - {r}")
        return False
    print(f"{p.name}: {'would move' if dry_run else 'moved'} to {where}" + (" (dry run: nothing moved)" if dry_run else ""))
    for src, dst in result["moves"]:
        print(f"  {src}  ->  {dst}")
    for rel in result.get("removes") or []:
        if (p / rel).exists() or not dry_run:
            print(f"  {'would remove' if dry_run else 'removed'} {rel} (Blueprint made it; nothing of the project's)")
    for name in result.get("stays") or []:
        print(f"  left where it is: {name}")
    if not dry_run:
        for rel in result.get("made") or []:
            print(f"  made {rel}")
        print(f"  Issued files are still read-only, and comments keep their ids. The overview page and the Open the mock-up "
              f"shortcuts were made again." + ("" if back else f" The moves are logged in {layout.MACHINE}/{layout.MIGRATION_LOG}; "
                                                f"to move it back: python -I tools/project.py migrate {p.name} --undo"))
    return True


def cmd_migrate(a):
    if bool(a.slug) == bool(a.all):
        sys.exit("Name one project, or --all for every active project.")
    if a.all:
        slugs = [s for s in active_slugs() if (layout.is_new(PROJECTS / s) if a.undo else layout.is_old_project(PROJECTS / s))]
        if not slugs:
            print("No active project to move: " + ("none is in the new layout." if a.undo else "every one is in the new layout already."))
            return
    else:
        project_dir(a.slug)
        slugs = [a.slug]
    failed = 0
    for slug in slugs:
        try:
            ok = migrate_one(PROJECTS / slug, a.dry_run, a.undo)
        except RuntimeError as e:
            print(f"{slug}: not moved: {e}")
            ok = False
        failed += not ok
    if failed:
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("issue"); s.add_argument("slug"); s.add_argument("--to"); s.add_argument("--date"); s.add_argument("--note")
    s.add_argument("--without-pdf", action="store_true"); s.add_argument("--anyway")
    s = sub.add_parser("ready"); s.add_argument("slug")
    s = sub.add_parser("issued"); s.add_argument("slug")
    s = sub.add_parser("file"); s.add_argument("slug"); s.add_argument("file"); s.add_argument("--kind", required=True)
    s.add_argument("--responds-to"); s.add_argument("--date"); s.add_argument("--copy", action="store_true")
    s = sub.add_parser("archive"); s.add_argument("slug")
    s = sub.add_parser("restore"); s.add_argument("slug")
    s = sub.add_parser("find"); s.add_argument("name"); s.add_argument("--client")
    s = sub.add_parser("match"); s.add_argument("file"); s.add_argument("--text"); s.add_argument("--json", action="store_true")
    s = sub.add_parser("hold"); s.add_argument("file"); s.add_argument("--reason", required=True)
    s = sub.add_parser("check"); s.add_argument("slug", nargs="?"); s.add_argument("--fix", action="store_true")
    s = sub.add_parser("migrate"); s.add_argument("slug", nargs="?"); s.add_argument("--all", action="store_true")
    s.add_argument("--dry-run", action="store_true"); s.add_argument("--undo", action="store_true")
    a = ap.parse_args()
    {"issue": cmd_issue, "ready": cmd_ready, "issued": cmd_issued, "file": cmd_file, "archive": cmd_archive, "restore": cmd_restore, "find": cmd_find,
     "match": cmd_match, "hold": cmd_hold, "check": cmd_check, "migrate": cmd_migrate}[a.cmd](a)


if __name__ == "__main__":
    main()
