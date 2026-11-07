"""Where everything is in a project folder: the one place that knows the folder layout.

Usage:
    python -I tools/layout.py <project_dir>          which layout the project is in, and where each part is

A project folder is in one of two layouts. Every tool asks this module where a part of the project is, so
both work, and a teammate on an older or newer Blueprint is not stopped by a project moved to the other.

The **new layout** (a project with a `_blueprint` folder) puts what people open at the top, numbered in the
order of the process, and Blueprint's working files out of the way:

    Project overview.html, Open the mock-up.cmd / .command
    Questions and fixes register.xlsx    the register for the BA (internal sheets too)
    Questions for the client.xlsx        the client's questions alone: the file to send
    1 Client documents/          the client's documents, never changed
    2 Reviews/                   each review as a Word file, and the mock-up's change notes
    3 Workshops/                 the agenda for the client and the facilitator notes (internal)
    4 Mock-up screenshots/       the pictures of the mock-up
    5 Requirements document/     each version's Word file and PDF
    6 UAT/                       the testers' workbook and the client's document
    7 Change requests/           the client's change request notes
    Internal – estimates and change requests/    the estimates and the CR log: never sent to the client
    _blueprint/                  everything Blueprint works from (spec, register, comments, the mock-up's
                                 build and versions, the .json sources, review extracts, issued versions)

The **old layout** (no `_blueprint` folder) keeps them in docs/, reviews/, spec/, mockup/, feedback/,
output/, workshops/, estimates/, uat/, changes/ and register.json / register.xlsx at the top.

Folders appear only when the project has something for them. `python -I tools/project.py migrate <slug>`
moves a project from the old layout to the new one (and back with --undo); `plan_migration`, `migrate` and
`undo` here do the work.
"""
import datetime as dt
import json
import os
import re
import socket
import sys
from pathlib import Path

MACHINE = "_blueprint"
README = "README.txt"
README_TEXT = ("Blueprint's working files. Leave them as they are; ask Claude instead.\n\n"
               "The files to open are one folder up: start with Project overview.html.\n")
MIGRATION_LOG = "migration.json"

DOCS = "1 Client documents"
REVIEWS = "2 Reviews"
WORKSHOPS = "3 Workshops"
SCREENSHOTS = "4 Mock-up screenshots"
REQUIREMENTS = "5 Requirements document"
UAT = "6 UAT"
CHANGES = "7 Change requests"
INTERNAL = "Internal – estimates and change requests"  # an en dash, as in the generated documents' names
REGISTER_XLSX = "Questions and fixes register.xlsx"
CLIENT_REGISTER_XLSX = "Questions for the client.xlsx"  # the client's items only: the file to send; same place in both layouts
OVERVIEW = "Project overview.html"
SHORTCUTS = ("Open the mock-up.cmd", "Open the mock-up.command")
CR_LOG = "CR log (internal).xlsx"
SCREENSHOT_RECORD = "taken-from.json"
SERVER_MARK = ".server.json"
# The folders for people, in the order the overview and the documentation name them.
PEOPLE_FOLDERS = (DOCS, REVIEWS, WORKSHOPS, SCREENSHOTS, REQUIREMENTS, UAT, CHANGES, INTERNAL)
# The old layout's parts: the folders and files the migration moves.
OLD_PARTS = ("register.xlsx", "register.json", "docs", "reviews", "workshops", "mockup", "feedback", "spec", "output",
             "estimates", "uat", "changes")
OFFICE = {".docx", ".doc", ".xlsx", ".xls", ".xlsm", ".pptx", ".ppt"}


# ------------------------------------------------------------------ which layout
def is_new(project):
    """True when the project is in the new layout (it has a _blueprint folder)."""
    return (Path(project) / MACHINE).is_dir()


def name(project):
    return "new" if is_new(project) else "old"


def is_old_project(project):
    """An old-layout project that has something to move (a register, a spec or documents)."""
    p = Path(project)
    return not is_new(p) and any((p / part).exists() for part in ("register.json", "spec", "docs", "mockup", "output"))


def machine(project):
    """Where Blueprint's working files are: _blueprint/ in the new layout, the project folder in the old one."""
    p = Path(project)
    return p / MACHINE if is_new(p) else p


def _people(project, new_name, old):
    p = Path(project)
    return p / new_name if is_new(p) else p / old


# ------------------------------------------------------------------ every location
def spec_dir(project):
    return machine(project) / "spec"


def spec_file(project):
    return spec_dir(project) / "app.yaml"


def register_json(project):
    return machine(project) / "register.json"


def register_xlsx(project):
    return _people(project, REGISTER_XLSX, "register.xlsx")


def client_register_xlsx(project):
    """The register's client items alone, the file that goes to the client (written with register.xlsx)."""
    return Path(project) / CLIENT_REGISTER_XLSX


def docs_dir(project):
    """The client's documents, kept as received."""
    return _people(project, DOCS, "docs")


def reviews_dir(project):
    """The review sources: one folder per review (its extraction and review.md), and the mock-up's change notes."""
    return machine(project) / "reviews"


def review_reports_dir(project, review_dir):
    """Where a review's Word file goes: 2 Reviews/ in the new layout, beside its review.md in the old one."""
    return Path(project) / REVIEWS if is_new(project) else Path(review_dir)


def review_notes(project):
    """The notes kept beside the reviews (the mock-up's change notes, mockup-v<version>-changes.md, and any
    other notes from a review), oldest first."""
    folder = reviews_dir(project)
    return sorted((f for f in folder.glob("*.md") if f.is_file()), key=lambda f: f.stat().st_mtime) if folder.is_dir() else []


def note_docx(project, note):
    """The Word file of a note, for people: in 2 Reviews/ in the new layout; None in the old layout, where the
    note itself is linked. "mockup-v0.2-changes.md" is "Mock-up v0.2 changes.docx"."""
    if not is_new(project):
        return None
    stem = Path(note).stem
    hit = re.match(r"mockup-(v.+)-changes$", stem)
    words = f"Mock-up {hit.group(1)} changes" if hit else (stem.replace("-", " ").replace("_", " ").strip() or stem)
    return Path(project) / REVIEWS / f"{words[:1].upper() + words[1:]}.docx"


def comments_xlsx(project):
    """The mock-up's comments as one internal workbook: in 2 Reviews/ in the new layout, beside the comments
    in the old one."""
    return Path(project) / REVIEWS / "Mock-up comments.xlsx" if is_new(project) else feedback_dir(project) / "comments.xlsx"


def workshops_source(project):
    return machine(project) / "workshops"


def workshops_output(project):
    return _people(project, WORKSHOPS, "workshops")


def workshop_documents(project, source):
    """(agenda for the client, facilitator notes) for a workshop's .json source."""
    out, stem = workshops_output(project), Path(source).stem
    return out / f"{stem} - agenda.docx", out / f"{stem} - facilitator notes (internal).docx"


def mockup_dir(project):
    """The built mock-up (index.html, assets/, shots.json)."""
    return machine(project) / "mockup"


def versions_dir(project):
    return mockup_dir(project) / "versions"


def screenshots_dir(project):
    return Path(project) / SCREENSHOTS if is_new(project) else mockup_dir(project) / "screenshots"


def screenshots_record(project):
    """The note of which screens the screenshots show (a working file: in _blueprint/ in the new layout)."""
    return mockup_dir(project) / "screenshots" / SCREENSHOT_RECORD


def shots_plan(project):
    return mockup_dir(project) / "shots.json"


def feedback_dir(project):
    return machine(project) / "feedback"


def feedback_file(project):
    return feedback_dir(project) / "feedback.json"


def live_file(project):
    return feedback_dir(project) / "live.json"


def server_file(project):
    """Written by a running mock-up server of this project (tools/mockup.py serve), removed when it stops."""
    return feedback_dir(project) / SERVER_MARK


def output_dir(project):
    """The generated requirements documents (Word and PDF)."""
    return _people(project, REQUIREMENTS, "output")


def snapshots_dir(project):
    """The spec of each generated version, the record of issued versions and the format preview."""
    return machine(project) / "output"


def snapshot(project, version):
    return snapshots_dir(project) / f"spec-v{version}.yaml"


def issued_file(project):
    return snapshots_dir(project) / "issued.json"


def preview_dir(project):
    return snapshots_dir(project) / "preview"


def estimates_source(project):
    return machine(project) / "estimates"


def estimates_output(project):
    return _people(project, INTERNAL, "estimates")


def estimate_xlsx(project, source):
    return estimates_output(project) / Path(source).with_suffix(".xlsx").name


def uat_source(project):
    return machine(project) / "uat"


def uat_output(project):
    return _people(project, UAT, "uat")


def changes_source(project):
    return machine(project) / "changes"


def cr_log(project):
    return changes_source(project) / "crs.json"


def cr_notes_dir(project):
    return _people(project, CHANGES, "changes")


def cr_log_xlsx(project):
    return _people(project, INTERNAL, "changes") / CR_LOG


def overview(project):
    return Path(project) / OVERVIEW


def shortcuts(project):
    return [Path(project) / s for s in SHORTCUTS]


def has_spec(project):
    return spec_file(project).exists()


def shown(project, path):
    """A path inside the project as people read it ("_blueprint/spec/app.yaml"), else the path as it is."""
    try:
        return Path(path).relative_to(Path(project)).as_posix()
    except ValueError:
        return Path(path).as_posix()


def resolve(project, old_rel):
    """A project-relative path written the old way ("output/spec-v0.1.yaml", "spec/app.yaml") as it is in this
    project's layout. Files that record a path inside the project keep the old way of writing it, which reads
    the same in both layouts."""
    rel = Path(str(old_rel).replace("\\", "/")).as_posix()
    if not is_new(project):
        return Path(project) / rel
    new = new_place(rel, is_file=bool(Path(rel).suffix), review_docx=_review_docx_names(project))
    return Path(project) / (new if new is not None else rel)


def create_new(project):
    """Start a project in the new layout: _blueprint/ with its spec/ and feedback/ folders and README, and the
    folder for the client's documents."""
    p = Path(project)
    for folder in (p / MACHINE / "spec", p / MACHINE / "feedback", p / DOCS):
        folder.mkdir(parents=True, exist_ok=True)
    write_readme(p)
    return p


def write_readme(project):
    f = Path(project) / MACHINE / README
    if not f.exists() or f.read_text(encoding="utf-8", errors="replace") != README_TEXT:
        f.write_text(README_TEXT, encoding="utf-8")
    return f


# ------------------------------------------------------------------ old place <-> new place
def _readable(folder_name):
    import review_doc  # one place names a review's Word file

    return review_doc.docx_name(folder_name)


def new_place(rel, is_file=True, review_docx=None):
    """Where an old-layout path (relative, with /) goes in the new layout, or None when it stays where it is.
    `review_docx` is {review folder name: its Word file's name} (worked out from the folder name when left out)."""
    parts = Path(rel).parts
    if not parts:
        return None
    top, rest = parts[0], parts[1:]
    m = f"{MACHINE}/"
    if rel == "register.xlsx":
        return REGISTER_XLSX
    if rel == "register.json":
        return m + "register.json"
    if top == "docs":
        return "/".join((DOCS,) + rest)
    if top in ("spec", "feedback"):
        return m + rel
    loose = len(rest) == 1 and is_file  # a file right in the folder, not in a folder of its own
    if top == "reviews":
        if len(rest) == 2:
            word = (review_docx or {}).get(rest[0]) or _readable(rest[0])
            if rest[1] == word:
                return f"{REVIEWS}/{rest[1]}"
        return m + rel
    if top == "workshops":
        return f"{WORKSHOPS}/{rest[0]}" if loose and not rest[0].lower().endswith(".json") else m + rel
    if top == "mockup":
        if len(rest) == 2 and rest[0] == "screenshots" and is_file and rest[1] != SCREENSHOT_RECORD:
            return f"{SCREENSHOTS}/{rest[1]}"
        return m + rel
    if top == "output":
        return f"{REQUIREMENTS}/{rest[0]}" if loose and Path(rest[0]).suffix.lower() in (".docx", ".pdf") else m + rel
    if top == "estimates":
        return f"{INTERNAL}/{rest[0]}" if loose and not rest[0].lower().endswith(".json") else m + rel
    if top == "uat":
        return f"{UAT}/{rest[0]}" if loose and not rest[0].lower().endswith(".json") else m + rel
    if top == "changes":
        if loose and rest[0] == CR_LOG:
            return f"{INTERNAL}/{CR_LOG}"
        return f"{CHANGES}/{rest[0]}" if loose and not rest[0].lower().endswith(".json") else m + rel
    return None


def old_place(project, rel, review_dirs=None):
    """Where a new-layout path (relative, with /) goes back to in the old layout, or None when it stays."""
    parts = Path(rel).parts
    if not parts:
        return None
    top, rest = parts[0], parts[1:]
    if rel == REGISTER_XLSX:
        return "register.xlsx"
    if top == MACHINE:
        if not rest or rest[0] in (README, MIGRATION_LOG):
            return None
        return "/".join(rest)
    if not rest:
        return None
    name_ = rest[0]
    if top == DOCS:
        return "/".join(("docs",) + rest)
    if top == REVIEWS:
        folder = (review_dirs or {}).get(name_)
        return f"reviews/{folder}/{name_}" if folder else f"reviews/{name_}"
    if top == WORKSHOPS:
        return "/".join(("workshops",) + rest)
    if top == SCREENSHOTS:
        return "/".join(("mockup", "screenshots") + rest)
    if top == REQUIREMENTS:
        return "/".join(("output",) + rest)
    if top == UAT:
        return "/".join(("uat",) + rest)
    if top == CHANGES:
        return "/".join(("changes",) + rest)
    if top == INTERNAL:
        return f"changes/{name_}" if name_ == CR_LOG and len(rest) == 1 else "/".join(("estimates",) + rest)
    return None


def _review_docx_names(project):
    """{review folder name: its Word file's name} for the reviews of a project."""
    folder = reviews_dir(project)
    return {d.name: _readable(d.name) for d in folder.iterdir() if d.is_dir()} if folder.is_dir() else {}


# ------------------------------------------------------------------ what stops a move
def server_running(project):
    """A mock-up server of this project is running (tools/mockup.py serve writes its mark while it runs):
    {port, pid, started} or None. A mark left by a server that stopped without removing it is ignored."""
    mark = server_file(project)
    try:
        info = json.loads(mark.read_text(encoding="utf-8"))
        port = int(info.get("port"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return info
    except OSError:
        return None


def live_open(project):
    """The start of the project's live session when one is open (not ended), else None."""
    try:
        data = json.loads(live_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and data and not data.get("ended"):
        return str(data.get("started") or "earlier")
    return None


def office_lock(path):
    """Why a file cannot be moved now ("open in Word or Excel ..."), or "" when nothing holds it."""
    path = Path(path)
    owners = [path.with_name("~$" + path.name), path.with_name("~$" + path.name[2:])]
    if path.suffix.lower() in OFFICE and any(o.exists() for o in owners if o != path):
        return "open in Word or Excel (here or on a teammate's computer: its ~$ lock file is beside it)"
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateFileW.restype = wintypes.HANDLE
            k.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.HANDLE)
            handle = k.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)  # read, shared with nobody
            if handle in (None, wintypes.HANDLE(-1).value):
                if ctypes.get_last_error() in (32, 33):  # in use by another program
                    return "open in another program"
                return ""
            k.CloseHandle(handle)
        except Exception:  # noqa: BLE001  (the move itself will still say so)
            return ""
    return ""


def _files(path):
    path = Path(path)
    if path.is_file():
        return [path]
    return [f for f in path.rglob("*") if f.is_file()] if path.is_dir() else []


def _busy(project, moves):
    """Refusals that hold for both directions: a server, a live session, a file in use."""
    p = Path(project)
    reasons = []
    server = server_running(p)
    if server:
        reasons.append(f"its mock-up is open (served on port {server.get('port')}): close the mock-up's window, "
                       "or press Ctrl+C where it runs, then try again")
    started = live_open(p)
    if started:
        reasons.append(f"a live session is open (started {started}): end it first (say 'end the live session')")
    locked = []
    for src, _ in moves:
        for f in _files(p / src):
            if f.suffix.lower() not in OFFICE | {".pdf"}:
                continue  # only documents people open are checked: opening every file would download a synced folder
            why = office_lock(f)
            if why:
                locked.append(f"{shown(p, f)} is {why}")
    if locked:
        reasons.append("files are in use, and a file in use cannot be moved. Close them and try again:\n    "
                       + "\n    ".join(locked[:12]) + ("\n    …" if len(locked) > 12 else ""))
    return reasons


# ------------------------------------------------------------------ the migration
def plan_migration(project):
    """(moves, stays, refusals) to bring an old-layout project to the new layout. `moves` are (from, to) paths
    relative to the project, in the order they are made; `stays` the items left where they are."""
    p = Path(project)
    refusals = []
    if is_new(p):
        return [], [], [f"{p.name} is already in the new layout (it has a {MACHINE} folder)."]
    reviews = {d.name: _readable(d.name) for d in (p / "reviews").iterdir() if d.is_dir()} if (p / "reviews").is_dir() else {}
    moves = []

    def add(src):
        new = new_place(src, is_file=(p / src).is_file(), review_docx=reviews)
        if new is not None:
            moves.append((src, new))

    for part in OLD_PARTS:
        if not (p / part).exists():
            continue
        if part == "register.xlsx" or part == "register.json" or part in ("docs", "spec", "feedback"):
            add(part)
            continue
        folder = p / part
        if folder.is_file():
            continue
        # Files for people come out of the folder first; the folder, with the rest, then goes to _blueprint/.
        if part == "reviews":
            for d in sorted(x for x in folder.iterdir() if x.is_dir()):
                word = d / reviews[d.name]
                if word.is_file():
                    add(f"reviews/{d.name}/{word.name}")
        elif part == "mockup":
            shots = folder / "screenshots"
            for f in sorted(shots.iterdir()) if shots.is_dir() else []:
                if f.is_file() and f.name != SCREENSHOT_RECORD:
                    add(f"mockup/screenshots/{f.name}")
        else:
            for f in sorted(folder.iterdir()):
                rel = f"{part}/{f.name}"
                if f.is_file() and new_place(rel, True, reviews) != MACHINE + "/" + rel:
                    add(rel)
        moves.append((part, f"{MACHINE}/{part}"))
    known = set(OLD_PARTS) | {OVERVIEW, *SHORTCUTS}
    stays = sorted(x.name for x in p.iterdir() if x.name not in known) if p.is_dir() else []
    taken = _taken(p, moves)
    for folder in (MACHINE,) + PEOPLE_FOLDERS:
        if (p / folder).exists() and folder not in taken:
            taken.append(folder)
    if taken:
        refusals.append("these already exist, so nothing was moved (move or rename them first): "
                        + ", ".join(sorted(set(taken))))
    if not moves:
        refusals.append(f"{p.name} has nothing in the old layout to move.")
    refusals += _busy(p, moves)
    return moves, stays, refusals


def _move(p, src, dst):
    target = p / dst
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(dst)
    os.rename(p / src, target)  # keeps a read-only (issued) file read-only


def _run(p, moves, done):
    """Make the moves; on a failure put back what was moved and raise with a plain reason."""
    try:
        for src, dst in moves:
            _move(p, src, dst)
            done.append((src, dst))
    except OSError as e:
        failed = (src, dst)
        stuck = []
        for s, d in reversed(done):
            try:
                os.rename(p / d, p / s)
            except OSError:
                stuck.append(f"{d} (should be back at {s})")
        _tidy(p)
        what = "a file in it is open in another program, or read-only and locked" if isinstance(e, PermissionError) else str(e)
        back = ("Everything moved so far was put back; close what holds it and try again." if not stuck else
                "These could NOT be put back, so the project is half moved: " + "; ".join(stuck)
                + ". Close what holds them and move them back by hand (or ask Claude), then try again.")
        raise RuntimeError(f"{failed[0]} could not be moved to {failed[1]} ({what}). {back}") from e


def _tidy(p):
    """Remove the new layout's folders that the move left empty."""
    for folder in PEOPLE_FOLDERS + (MACHINE,):
        f = p / folder
        if f.is_dir() and not any(f.iterdir()):
            f.rmdir()


def migrate(project, dry_run=False, rebuild_page=True):
    """Move an old-layout project to the new layout. Returns {moves, stays, refusals, made}; nothing moves when
    there is a refusal or on a dry run. `rebuild_page` makes the overview page and the shortcuts again."""
    p = Path(project)
    moves, stays, refusals = plan_migration(p)
    result = {"moves": moves, "stays": stays, "refusals": refusals, "made": []}
    if refusals or dry_run:
        return result
    done = []
    _run(p, moves, done)
    write_readme(p)
    made = [f"{MACHINE}/{README}"]
    before = {f for f in (p / REVIEWS).glob("*")} if (p / REVIEWS).is_dir() else set()
    log = {"migrated": dt.datetime.now().isoformat(timespec="seconds"), "from": "old", "to": "new",
           "moves": [list(m) for m in moves], "made": made, "left": stays}
    (p / MACHINE / MIGRATION_LOG).write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    if rebuild_page:
        rebuild(p)
    made += [shown(p, f) for f in sorted((p / REVIEWS).glob("*")) if f not in before] if (p / REVIEWS).is_dir() else []
    log["made"] = made
    (p / MACHINE / MIGRATION_LOG).write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    result["made"] = made
    return result


def plan_undo(project):
    """(moves, removes, refusals) to bring a new-layout project back to the old layout."""
    p = Path(project)
    if not is_new(p):
        return [], [], [f"{p.name} is in the old layout already: there is nothing to move back."]
    m = p / MACHINE
    review_dirs = {}
    for d in (m / "reviews").iterdir() if (m / "reviews").is_dir() else []:
        if d.is_dir():
            review_dirs[_readable(d.name)] = d.name
    notes = {note_docx(p, n).name for n in review_notes(p)}
    moves, removes = [], [f"{MACHINE}/{README}", f"{MACHINE}/{MIGRATION_LOG}"]
    # The folders of _blueprint/ go back first, then the files for people go back into them.
    for x in sorted(m.iterdir()):
        if x.name in (README, MIGRATION_LOG):
            continue
        moves.append((f"{MACHINE}/{x.name}", x.name))
    if (p / REGISTER_XLSX).exists():
        moves.append((REGISTER_XLSX, "register.xlsx"))
    for folder in PEOPLE_FOLDERS:
        f = p / folder
        if not f.is_dir():
            continue
        if folder == DOCS:
            moves.append((DOCS, "docs"))
            continue
        for x in sorted(f.iterdir()):
            rel = f"{folder}/{x.name}"
            if folder == REVIEWS and (x.name in notes or x.name == comments_xlsx(p).name) and x.is_file():
                removes.append(rel)  # made from a note or from the comments, which stay the source
                continue
            back = old_place(p, rel, review_dirs)
            if back:
                moves.append((rel, back))
    refusals = []
    taken = _taken(p, moves)
    if taken:
        refusals.append("these already exist in the old layout's places, so nothing was moved (move or rename them first): "
                        + ", ".join(taken))
    refusals += _busy(p, moves)
    return moves, removes, refusals


def _taken(p, moves):
    """The targets of `moves` that would already be there when their turn comes: there now, or brought there by
    an earlier move of the folder they are in, or named twice."""
    taken, seen = [], set()
    for i, (src, dst) in enumerate(moves):
        there = (p / dst).exists()
        for s, t in moves[:i]:
            if dst.startswith(t + "/"):
                there = there or (p / (s + dst[len(t):])).exists()
        if there or dst in seen:
            taken.append(dst)
        seen.add(dst)
    return sorted(set(taken))


def undo(project, dry_run=False):
    """Move a new-layout project back to the old layout. Returns {moves, removes, refusals}."""
    p = Path(project)
    moves, removes, refusals = plan_undo(p)
    result = {"moves": moves, "removes": removes, "refusals": refusals}
    if refusals or dry_run:
        return result
    kept = {}
    for rel in removes:  # put back if the moves fail
        f = p / rel
        if f.is_file():
            kept[rel] = f.read_bytes()
    for rel in kept:
        _writable_unlink(p / rel)
    done = []
    try:
        _run(p, moves, done)
    except RuntimeError:
        (p / MACHINE).mkdir(exist_ok=True)
        for rel, data in kept.items():
            (p / rel).parent.mkdir(parents=True, exist_ok=True)
            (p / rel).write_bytes(data)
        raise
    _tidy(p)
    rebuild(p)
    return result


def _writable_unlink(f):
    try:
        f.unlink()
    except PermissionError:
        os.chmod(f, 0o666)
        f.unlink()


def rebuild(project):
    """The overview page and the Open the mock-up shortcuts, after a move."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import overview

        overview.build(Path(project))
    except Exception as e:  # noqa: BLE001  (the move is done; the page can be built again by hand)
        print(f"(The project overview page was not rebuilt: {type(e).__name__}: {e}. "
              f"To see why: python -I tools/overview.py build {Path(project).as_posix()})")


# ------------------------------------------------------------------ command line
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if len(args) != 1 or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    p = Path(args[0])
    if not p.is_dir():
        sys.exit(f"No project folder {p}")
    print(f"{p.name}: {name(p)} layout")
    for label, where in (("spec", spec_file(p)), ("register", register_json(p)), ("register for the BA", register_xlsx(p)),
                         ("register for the client", client_register_xlsx(p)),
                         ("client documents", docs_dir(p)), ("reviews (sources)", reviews_dir(p)), ("workshops (sources)", workshops_source(p)),
                         ("workshop documents", workshops_output(p)), ("mock-up", mockup_dir(p)), ("screenshots", screenshots_dir(p)),
                         ("comments", feedback_file(p)), ("requirements documents", output_dir(p)), ("issued versions", issued_file(p)),
                         ("estimates (sources)", estimates_source(p)), ("estimates (Excel)", estimates_output(p)),
                         ("UAT (sources)", uat_source(p)), ("UAT documents", uat_output(p)), ("CR log", cr_log(p)),
                         ("CR notes", cr_notes_dir(p)), ("CR log (Excel)", cr_log_xlsx(p))):
        print(f"  {label:24} {shown(p, where)}{'' if where.exists() else '  (not yet)'}")


if __name__ == "__main__":
    main()
