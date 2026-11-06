"""The tour: a guided first run of Blueprint on a scratch copy of the made-up sample project.

Usage:
    python -I tools/tour.py start      a fresh copy of examples/leave-request in .tour/leave-request
    python -I tools/tour.py comment    add a sample comment to the copy's mock-up, as if typed in the room
    python -I tools/tour.py end        remove the copy

start    copies the made-up sample (its spec and the other files kept in git; not what was built from it)
         into .tour/leave-request in the app folder, in the folder layout a new project has (tools/layout.py),
         gives it an empty register, and puts a short draft requirements document in its "1 Client documents"
         with a few gaps planted in it, for the tour's review. Run it
         again to start over: the old copy is replaced. The copy is ignored by git, is not one of the
         projects (status.py and the page that lists every mock-up never show it), and every Blueprint tool
         works on it: give them .tour/leave-request where they ask for projects/<slug>.
comment  saves one sample comment on the copy's mock-up, the way the mock-up's Feedback does, for someone
         who would rather not type one. An open mock-up shows it within a few seconds.
end      removes the copy and nothing else. It refuses any other folder, and a folder it did not make.

Nothing here reads or writes the workspace: no client documents, no knowledge base, no projects.
"""
import datetime as dt
import os
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "leave-request"
SLUG = "leave-request"
MARKER = ".blueprint-tour"  # in the copy: says the tour made this folder, so `end` may remove it
# What is built from the sample, not part of it: never copied, so the tour builds it afresh.
GENERATED = {"mockup", "feedback", "output", "reviews", "register.xlsx", "Project overview.html",
             "Open the mock-up.cmd", "Open the mock-up.command", "__pycache__", MARKER}
DRAFT_NAME = "draft requirements v0.1 (sample).docx"

# The planted draft. Each gap is written so that a review finds it, and the tests check it is there.
DRAFT_TITLE = "Leave Request System - Requirements (draft v0.1)"
DRAFT_NOTE = "A made-up sample for the Blueprint tour. Not a client document."
DRAFT_SECTIONS = [
    ("1 Purpose", ["Employees apply for leave online and their line manager decides on each application. "
                   "HR Admin maintains the leave types."]),
    ("2 Roles", "ROLES"),
    ("3 Applying for leave", [
        "FR-01 The employee selects the leave type, the dates and a reason, and submits the application.",
        "FR-02 The system sends the application to the employee's line manager.",
        "FR-03 The line manager approves the application. Once approved, the employee receives an e-mail "
        "and the leave appears in the team calendar."]),
    ("4 Team calendar", ["FR-04 The Supervisor can see the team calendar with everyone's approved leave."]),
    ("5 Dashboard", ["FR-05 The HR dashboard shows the Approval Rate for each department."]),
    ("6 Supporting documents", ["FR-06 Medical Leave needs a supporting document. The maximum file size is TBC."]),
    ("7 Integrations", ["FR-07 Approved leave is sent to the payroll system, if applicable."]),
]
DRAFT_ROLES = [("Role", "What they do"),
               ("Employee", "Applies for leave and tracks their applications."),
               ("Line Manager", "Approves leave applications from their direct reports."),
               ("HR Admin", "Maintains leave types and views reports.")]
# The gaps, for the tests (and for whoever changes the draft): where each is and what gives it away.
PLANTED = [
    {"where": "FR-03", "gap": "no reject path: only approval is described", "sign": "approves the application"},
    {"where": "FR-04", "gap": "a role the roles table does not have", "sign": "Supervisor"},
    {"where": "FR-05", "gap": "a KPI without a formula", "sign": "Approval Rate"},
    {"where": "FR-06", "gap": "an open item", "sign": "TBC"},
    {"where": "FR-07", "gap": "an integration in scope only 'if applicable'", "sign": "if applicable"},
]
SAMPLE_COMMENT = {"screen": "new-application", "role": "employee", "element": "field:days",
                  "text": "Could this form show how many leave days I have left, before I submit?",
                  "author": "Sample comment (tour)"}


def tour_dir(root=ROOT):
    return Path(root) / ".tour"


def tour_copy(root=ROOT):
    return tour_dir(root) / SLUG


def shown(path, root=ROOT):
    """A path as the user would type it: relative to the app folder when it is inside it."""
    path = Path(path)
    try:
        return path.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(path)


def real(path):
    return Path(os.path.realpath(path))


def is_the_copy(target, root=ROOT):
    """True only for the tour's own copy: the right place, reached without a link, and marked by the tour."""
    target, copy = Path(target), tour_copy(root)
    if Path(os.path.abspath(target)) != Path(os.path.abspath(copy)):
        return False
    if real(tour_dir(root)) != real(root) / ".tour" or real(target) != real(tour_dir(root)) / SLUG:
        return False  # .tour or the copy is a link to somewhere else: never remove what it points to
    return (target / MARKER).is_file()


def _writable(func, path, _exc):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def remove_copy(target=None, root=ROOT):
    """Remove the tour's copy. Anything else is refused, with nothing touched. Returns True when removed."""
    copy = tour_copy(root)
    target = Path(target) if target else copy
    if not target.exists():
        if Path(os.path.abspath(target)) != Path(os.path.abspath(copy)):
            sys.exit(f"{target} is not the tour's copy. The tour only ever removes {shown(copy, root)}.")
        return False
    if not is_the_copy(target, root):
        sys.exit(f"{target} is not the tour's copy, so it was left alone. The tour only ever removes "
                 f"{shown(copy, root)}, and only when the tour made it.")
    try:
        shutil.rmtree(target, onerror=_writable)
    except PermissionError as e:
        sys.exit(f"Could not remove everything in {shown(copy, root)}: a file is still open ({e.filename}). Close it "
                 "(Excel, Word, or the mock-up's window) and run this again.")
    try:
        tour_dir(root).rmdir()  # only when nothing else is in it
    except OSError:
        pass
    return True


def write_draft(path):
    """The short draft requirements document with the planted gaps."""
    from docx import Document

    doc = Document()
    doc.core_properties.title = DRAFT_TITLE
    doc.core_properties.author = "Blueprint tour"
    doc.core_properties.comments = ""
    doc.core_properties.created = doc.core_properties.modified = dt.datetime.now().replace(microsecond=0)
    doc.add_heading(DRAFT_TITLE, level=0)
    doc.add_paragraph(DRAFT_NOTE)
    for heading, body in DRAFT_SECTIONS:
        doc.add_heading(heading, level=1)
        if body == "ROLES":
            table = doc.add_table(rows=0, cols=2)
            table.style = "Table Grid"
            for row in DRAFT_ROLES:
                cells = table.add_row().cells
                cells[0].text, cells[1].text = row
            continue
        for text in body:
            doc.add_paragraph(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path


def start(root=ROOT, today=None):
    """A fresh copy of the sample for the tour; an earlier copy is replaced. Returns the copy's path."""
    import json

    import yaml

    copy = tour_copy(root)
    if copy.exists():
        remove_copy(copy, root)
    shutil.copytree(EXAMPLE, copy, ignore=lambda folder, names: [n for n in names if n in GENERATED or n.endswith(".xlsx")])
    (copy / MARKER).write_text("Made by tools/tour.py for the Blueprint tour. Removed by: python -I tools/tour.py end\n",
                               encoding="utf-8")
    sys.path.insert(0, str(ROOT / "tools"))
    import layout

    if not layout.is_new(copy):  # the sample is kept in the old layout; the tour shows the one a new project has
        moved = layout.migrate(copy, rebuild_page=False)
        if moved["refusals"]:
            sys.exit("The tour copy could not be laid out: " + "; ".join(moved["refusals"]))
    layout.create_new(copy)
    spec = yaml.safe_load(layout.spec_file(copy).read_text(encoding="utf-8")) or {}
    about = spec.get("project") or {}
    if not layout.register_json(copy).exists():
        layout.register_json(copy).write_text(json.dumps(
            {"project": about.get("name", "Leave Request System"), "client": about.get("client", "Sample client"),
             "platform": about.get("platform", ""), "items": []}, indent=2) + "\n", encoding="utf-8")
    day = (today or dt.date.today()).isoformat()
    write_draft(layout.docs_dir(copy) / f"{day} {DRAFT_NAME}")
    return copy


def draft_of(copy):
    sys.path.insert(0, str(ROOT / "tools"))
    import layout

    found = sorted(layout.docs_dir(copy).glob(f"* {DRAFT_NAME}"))
    return found[-1] if found else None


def add_comment(root=ROOT):
    """Save the sample comment to the copy's feedback file, as the mock-up would. Returns it as saved."""
    import yaml

    copy = tour_copy(root)
    if not is_the_copy(copy, root):
        sys.exit("There is no tour copy yet. Start the tour first: python -I tools/tour.py start")
    sys.path.insert(0, str(ROOT / "tools"))
    import layout
    import mockup

    spec = yaml.safe_load(layout.spec_file(copy).read_text(encoding="utf-8")) or {}
    item = {**SAMPLE_COMMENT, "x": 0, "y": 0, "time": dt.datetime.now().isoformat(timespec="seconds"),
            "version": str((spec.get("project") or {}).get("version", ""))}
    return mockup.save_comment(layout.feedback_file(copy), item)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else ""
    if command == "start":
        copy = start()
        print(f"Tour copy ready: {shown(copy)}")
        print("  A made-up sample copied from examples/leave-request. No client data; the workspace is not touched.")
        print(f"  Draft to review: {shown(draft_of(copy))}")
        print("  Give the tools this folder where they ask for projects/<slug>.")
        print("  Remove it at the end: python -I tools/tour.py end")
    elif command == "comment":
        item = add_comment()
        print(f"Sample comment {item['id']} saved on the New Leave Application screen: \"{item['text']}\"")
    elif command == "end":
        if remove_copy(args[1] if len(args) > 1 else None):
            print("The tour copy is removed. Nothing else was changed.")
        else:
            print("There was no tour copy to remove.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
