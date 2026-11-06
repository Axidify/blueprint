"""tools/project.py: issuing and locking versions, filing documents, archiving, and the layout check.

Every test runs on a temp workspace (the temp_workspace fixture points the tool at it).
"""
import datetime as dt
import json
import os
import stat
import sys

import pytest

import support

import project as project_tool

DOC = "Leave Request System – Requirements Specification v0.1"


@pytest.fixture
def projects(temp_workspace):
    return temp_workspace / "projects"


@pytest.fixture
def run(monkeypatch, capsys):
    """Run `project.py <args>` and return what it printed."""
    def call(*args):
        monkeypatch.setattr(sys, "argv", ["project.py", *map(str, args)])
        project_tool.main()
        return capsys.readouterr().out
    return call


def new_project(projects, slug="leave-request", generated=("docx", "pdf"), version="0.1"):
    """A project folder with the sample spec and stand-ins for a generated document."""
    p = projects / slug
    for folder in ("docs", "reviews", "spec", "feedback", "output"):
        (p / folder).mkdir(parents=True)
    spec = support.load_spec(support.EXAMPLE)
    spec["project"]["version"] = version
    support.write_spec(p, spec)
    (p / "register.json").write_text(json.dumps({"project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "items": []}), encoding="utf-8")
    name = DOC.replace("v0.1", f"v{version}")
    for ext in generated:
        (p / "output" / f"{name}.{ext}").write_bytes(b"generated")
    if generated:
        (p / "output" / f"spec-v{version}.yaml").write_text("snapshot", encoding="utf-8")
    return p


def writable(path):
    return bool(os.stat(path).st_mode & stat.S_IWRITE)


def at_noon(path, date):
    """Set a file's modified time to noon on a date (local time, like the tool reads it)."""
    stamp = dt.datetime.combine(dt.date.fromisoformat(date), dt.time(12)).timestamp()
    os.utime(path, (stamp, stamp))


# ====================================================================== issue and lock
def test_issue_records_the_version_and_locks_its_files(projects, run):
    p = new_project(projects)
    out = run("issue", "leave-request", "--to", "Sample Client IT", "--date", "2026-11-10", "--note", "for workshop 2")
    assert f"Issued v0.1 to Sample Client IT on 2026-11-10: {DOC}.docx, {DOC}.pdf" in out
    assert json.loads((p / "output" / "issued.json").read_text(encoding="utf-8")) == [{
        "version": "0.1", "date": "2026-11-10", "to": "Sample Client IT", "files": [f"{DOC}.docx", f"{DOC}.pdf"],
        "note": "for workshop 2"}]
    for name in (f"{DOC}.docx", f"{DOC}.pdf", "spec-v0.1.yaml"):
        assert not writable(p / "output" / name), f"{name} should be read-only once issued"
    assert writable(p / "spec" / "app.yaml"), "the spec itself stays editable"


def test_issue_defaults_to_the_client_and_today(projects, run):
    p = new_project(projects, generated=("docx",))
    run("issue", "leave-request")
    record = project_tool.load_issues(p)[0]
    assert record["to"] == "SAMPLE"
    assert record["date"] == dt.date.today().isoformat()
    assert record["files"] == [f"{DOC}.docx"] and record["note"] == ""


def test_is_issued_is_what_the_generator_asks(projects, run):
    p = new_project(projects)
    assert project_tool.is_issued(p, "0.1") is None
    run("issue", "leave-request", "--date", "2026-11-10")
    assert project_tool.is_issued(p, "0.1")["date"] == "2026-11-10"
    assert project_tool.is_issued(p, "0.2") is None


def test_a_version_cannot_be_issued_twice(projects, run):
    p = new_project(projects)
    run("issue", "leave-request")
    with pytest.raises(SystemExit, match="v0.1 was already issued"):
        run("issue", "leave-request")
    assert len(project_tool.load_issues(p)) == 1


def test_the_next_version_is_issued_alongside(projects, run):
    p = new_project(projects)
    run("issue", "leave-request", "--date", "2026-11-10")
    spec = support.load_spec(p)
    spec["project"]["version"] = "0.2"
    support.write_spec(p, spec)
    (p / "output" / f"{DOC.replace('v0.1', 'v0.2')}.docx").write_bytes(b"generated")
    run("issue", "leave-request", "--date", "2026-11-20")
    assert [i["version"] for i in project_tool.load_issues(p)] == ["0.1", "0.2"]
    assert project_tool.load_issues(p)[1]["files"] == [f"{DOC.replace('v0.1', 'v0.2')}.docx"], "only that version's files"
    listing = run("issued", "leave-request")
    assert "v0.1  2026-11-10  to SAMPLE" in listing and "v0.2  2026-11-20  to SAMPLE" in listing


def test_nothing_to_issue_without_a_generated_document(projects, run):
    p = new_project(projects, generated=())
    with pytest.raises(SystemExit, match="No generated requirements document for v0.1"):
        run("issue", "leave-request")
    assert not (p / "output" / "issued.json").exists()


def test_nothing_to_issue_without_a_spec_version(projects, run):
    p = projects / "bare"
    (p / "output").mkdir(parents=True)
    with pytest.raises(SystemExit, match="no spec version"):
        run("issue", "bare")


def test_issued_lists_nothing_at_first(projects, run):
    new_project(projects)
    assert run("issued", "leave-request").strip() == "Nothing issued yet."


def test_unknown_project_names_the_ones_that_exist(projects, run):
    new_project(projects)
    with pytest.raises(SystemExit, match="No project 'nope'. Projects: leave-request"):
        run("issue", "nope")


# ====================================================================== file
def test_file_moves_a_document_in_under_a_dated_name(projects, run, tmp_path):
    p = new_project(projects)
    src = tmp_path / "Comments FINAL.DOCX"
    src.write_bytes(b"comments")
    out = run("file", "leave-request", src, "--kind", "client comments", "--responds-to", "v1.3", "--date", "2026-11-12")
    assert "Filed Comments FINAL.DOCX as docs/2026-11-12 client comments on v1.3.docx" in out
    assert (p / "docs" / "2026-11-12 client comments on v1.3.docx").read_bytes() == b"comments"
    assert not src.exists(), "the original is moved"


def test_file_dates_from_the_file_when_no_date_is_given(projects, run, tmp_path):
    p = new_project(projects)
    src = tmp_path / "notes.txt"
    src.write_text("workshop notes", encoding="utf-8")
    at_noon(src, "2026-03-04")
    run("file", "leave-request", src, "--kind", "workshop 1 notes")
    assert [f.name for f in (p / "docs").iterdir()] == ["2026-03-04 workshop 1 notes.txt"]


def test_file_copy_keeps_the_original(projects, run, tmp_path):
    p = new_project(projects)
    src = tmp_path / "brief.pdf"
    src.write_bytes(b"brief")
    run("file", "leave-request", src, "--kind", "brief", "--date", "2026-01-05", "--copy")
    assert src.exists() and (p / "docs" / "2026-01-05 brief.pdf").read_bytes() == b"brief"


def test_file_never_overwrites(projects, run, tmp_path):
    p = new_project(projects)
    for content in (b"first", b"second", b"third"):
        src = tmp_path / "brief.pdf"
        src.write_bytes(content)
        run("file", "leave-request", src, "--kind", "brief", "--date", "2026-01-05")
    assert {f.name: f.read_bytes() for f in (p / "docs").iterdir()} == {
        "2026-01-05 brief.pdf": b"first", "2026-01-05 brief (2).pdf": b"second", "2026-01-05 brief (3).pdf": b"third"}


def test_file_cleans_characters_windows_cannot_store(projects, run, tmp_path):
    p = new_project(projects)
    src = tmp_path / "x.txt"
    src.write_text("x", encoding="utf-8")
    run("file", "leave-request", src, "--kind", ' SOW: draft/final? ', "--date", "2026-01-05")
    assert [f.name for f in (p / "docs").iterdir()] == ["2026-01-05 SOW- draft-final-.txt"]


@pytest.mark.parametrize("text, name", [
    ("Leave Request System", "Leave Request System"),
    ("Import/Export Permit System", "Import-Export Permit System"),
    ("Phase 2: Claims System", "Phase 2- Claims System"),
    ('What? "Draft" <v1>|*', "What- -Draft- -v1-"),
    ("  Ends with dots... ", "Ends with dots"),
])
def test_safe_name_is_a_name_windows_can_store(text, name):
    """Shared with the document generator, which names the requirements document after the system."""
    assert project_tool.safe_name(text) == name


def test_file_needs_an_existing_file(projects, run, tmp_path):
    new_project(projects)
    with pytest.raises(SystemExit, match="No such file"):
        run("file", "leave-request", tmp_path / "missing.docx", "--kind", "brief")


# ====================================================================== archive and restore
def test_archive_then_restore(projects, run):
    p = new_project(projects)
    new_project(projects, slug="other")
    run("issue", "leave-request", "--date", "2026-11-10")

    out = run("archive", "leave-request")
    assert "Archived leave-request to projects/_archive/" in out
    assert not p.exists() and (projects / "_archive" / "leave-request" / "spec" / "app.yaml").exists()
    assert project_tool.active_slugs() == ["other"], "archived projects leave the active list"
    assert "v0.1  2026-11-10" in run("issued", "leave-request"), "an archived project's history can still be read"
    with pytest.raises(SystemExit, match="No project 'leave-request'"):
        run("archive", "leave-request")

    assert "Restored leave-request to projects/." in run("restore", "leave-request")
    assert project_tool.active_slugs() == ["leave-request", "other"]
    assert not (projects / "_archive" / "leave-request").exists()
    assert project_tool.is_issued(p, "0.1"), "the issue record comes back with it"


def test_restore_refuses_what_it_cannot_do(projects, run):
    new_project(projects)
    with pytest.raises(SystemExit, match="No archived project 'leave-request'"):
        run("restore", "leave-request")
    run("archive", "leave-request")
    new_project(projects)  # a new project took the name meanwhile
    with pytest.raises(SystemExit, match="already exists"):
        run("restore", "leave-request")
    assert (projects / "_archive" / "leave-request").exists()


# ====================================================================== check
def test_check_passes_a_standard_project(projects, run):
    new_project(projects, generated=())
    out = run("check")
    assert out.splitlines()[0] == "leave-request: OK"
    assert "in the old folder layout" in out and "python -I tools/project.py migrate leave-request --dry-run" in out,         "an old-layout project is fine, with a hint to migrate"


def test_check_passes_a_project_in_the_new_layout(projects, run, new_project_tool):
    new_project_tool("courier-booking", "Courier Booking System", "Sample Client")
    assert run("check").strip() == "courier-booking: OK"


def test_check_reports_then_fixes_a_bare_project(projects, run):
    p = projects / "bare"
    (p / "spec").mkdir(parents=True)
    support.write_spec(p, support.load_spec(support.EXAMPLE))
    out = run("check", "bare")
    assert "bare: needs fixing" in out
    for missing in ("no docs/ folder", "no reviews/ folder", "no feedback/ folder", "no register.json"):
        assert missing in out
    assert "Run with --fix" in out and not (p / "docs").exists(), "check alone changes nothing"

    out = run("check", "bare", "--fix")
    assert "bare: fixed" in out
    assert all((p / d).is_dir() for d in project_tool.LAYOUT)
    assert json.loads((p / "register.json").read_text(encoding="utf-8")) == {
        "project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "items": []}
    assert run("check", "bare").splitlines()[0] == "bare: OK"


def test_check_notes_issued_and_unissued_versions(projects, run):
    new_project(projects)
    assert "document versions generated (v0.1) but none recorded as issued" in run("check")
    run("issue", "leave-request")
    assert "v0.1 is issued: bump project.version before changing the spec" in run("check")


def test_check_skips_the_archive(projects, run):
    new_project(projects)
    run("archive", "leave-request")
    assert run("check").strip() == "No projects."


def test_archive_never_moves_a_project_into_an_archived_one_of_the_same_name(projects, run):
    """It used to move the project inside projects/_archive/<slug>/ when that folder existed."""
    new_project(projects)
    run("archive", "leave-request")
    p = new_project(projects)
    with pytest.raises(SystemExit, match="An archived project called 'leave-request' already exists"):
        run("archive", "leave-request")
    assert (p / "spec" / "app.yaml").exists(), "nothing was moved"
    assert not (projects / "_archive" / "leave-request" / "leave-request").exists()


# ====================================================================== earlier work on the same system
@pytest.mark.parametrize("a, b, how", [
    ("Leave Request System", "leave request", "same"),
    ("Leave Request System", "Leave Request System Phase 2", "same"),
    ("Equipment Booking", "Equipment Booking and Return System", "similar"),
    ("Leave Requests", "Leave Request", "similar"),
    ("Leave Request System", "Courier Booking System", None),
    ("System", "Leave Request System", None),
])
def test_system_names_are_compared_without_filler_words(a, b, how):
    assert project_tool.likeness(a, b) == how


def earlier_work(temp_workspace, projects):
    new_project(projects, slug="leave-request")
    new_project(projects, slug="leave-old")
    project_tool.cmd_archive(type("A", (), {"slug": "leave-old"}))
    knowledge = temp_workspace / "knowledge"
    (knowledge / "actuals").mkdir(parents=True)
    (knowledge / "actuals" / "leave-old.md").write_text("# Leave Request System – actuals\n", encoding="utf-8")
    (knowledge / "projects-log.md").write_text(
        "| Project | Platform | Phase |\n|---|---|---|\n| Leave Request System | Joget DX | 1 |\n| Courier Booking | Joget DX | 1 |\n",
        encoding="utf-8")


def test_find_lists_active_archived_and_delivered_work_on_the_same_system(temp_workspace, projects, run):
    earlier_work(temp_workspace, projects)
    out = run("find", "Leave request")
    assert "active project Leave Request System (projects/leave-request, same name)" in out
    assert "archived project Leave Request System (projects/_archive/leave-old, same name): bring it back with python -I tools/project.py restore leave-old" in out
    assert "delivered before: Leave Request System (knowledge/actuals/leave-old.md, same name)" in out
    assert "change requests" in out
    assert "projects log row: Leave Request System | Joget DX | 1" in out and "Courier" not in out
    assert "No earlier project" in run("find", "Asset Tracking")


@pytest.fixture
def new_project_tool(monkeypatch, capsys):
    import new_project as tool

    def call(*args):
        monkeypatch.setattr(sys, "argv", ["new_project.py", *args])
        tool.main()
        return capsys.readouterr().out
    return call


def test_new_project_prints_a_short_path_and_the_next_step(projects, new_project_tool):
    out = new_project_tool("courier-booking", "Courier Booking System", "Sample Client")
    assert out.startswith("Created projects/courier-booking\n")
    assert str(projects) not in out and "Warning" not in out
    assert "Next: " in out and "'process my inbox'" in out
    p = projects / "courier-booking"
    assert json.loads((p / "_blueprint" / "register.json").read_text(encoding="utf-8"))["project"] == "Courier Booking System"
    assert (p / "1 Client documents").is_dir() and (p / "_blueprint" / "README.txt").is_file(), "a new project starts in the new layout"
    assert not (p / "docs").exists() and not (p / "register.json").exists()


def test_new_project_refuses_the_name_of_an_archived_project(temp_workspace, projects, new_project_tool):
    earlier_work(temp_workspace, projects)
    with pytest.raises(SystemExit, match=r"python -I tools/project.py restore leave-old"):
        new_project_tool("leave-old", "Leave Request System", "Sample Client")
    assert not (projects / "leave-old").exists()


def test_new_project_warns_about_earlier_work_on_the_same_system(temp_workspace, projects, new_project_tool):
    earlier_work(temp_workspace, projects)
    out = new_project_tool("leave-request-phase-2", "Leave Request System", "Sample Client")
    assert "Warning: earlier work on a system like 'Leave Request System':" in out
    assert "projects/_archive/leave-old" in out and "knowledge/actuals/leave-old.md" in out
    assert (projects / "leave-request-phase-2" / "_blueprint" / "register.json").exists(), "a warning, not a refusal"
