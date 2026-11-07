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
    p = new_project(projects)
    run("issue", "leave-request")
    record = project_tool.load_issues(p)[0]
    assert record["to"] == "SAMPLE"
    assert record["date"] == dt.date.today().isoformat()
    assert record["files"] == [f"{DOC}.docx", f"{DOC}.pdf"] and record["note"] == ""


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
    for ext in ("docx", "pdf"):
        (p / "output" / f"{DOC.replace('v0.1', 'v0.2')}.{ext}").write_bytes(b"generated")
    run("issue", "leave-request", "--date", "2026-11-20")
    assert [i["version"] for i in project_tool.load_issues(p)] == ["0.1", "0.2"]
    assert project_tool.load_issues(p)[1]["files"] == [f"{DOC.replace('v0.1', 'v0.2')}.{e}" for e in ("docx", "pdf")], "only that version's files"
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
    ("E-PASS", "epass", "same"),
    ("Acme E-PASS System", "Zeta EPASS", "similar"),
    ("Zeta EPASS System", "e pass", "similar"),
    ("Purchase Request System", "Leave Request System", None),
    ("Room Booking", "Courier Booking System", None),
    ("User Location Summary", "Asset Details Location", None),
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


def test_find_sees_a_distinctive_word_through_hyphens_and_extra_words(temp_workspace, projects, run):
    """A made-up archived "Acme E-PASS System" was not found for "Zeta EPASS" or "Zeta EPASS System": the
    hyphen split the word, and the extra words around it made the names neither the same nor a subset."""
    p = new_project(projects, slug="e-pass")
    reg = json.loads((p / "register.json").read_text(encoding="utf-8"))
    reg.update(project="Acme E-PASS System", client="Made-up Motors Sdn. Bhd.")
    (p / "register.json").write_text(json.dumps(reg), encoding="utf-8")
    spec = support.load_spec(p)
    spec["project"].update(name="Acme E-PASS System", client="Made-up Motors Sdn. Bhd.")
    support.write_spec(p, spec)
    run("archive", "e-pass")
    for name in ("EPASS", "Zeta EPASS", "Zeta EPASS System"):
        assert "archived project Acme E-PASS System (projects/_archive/e-pass" in run("find", name), name
    out = run("find", "Zeta EPASS System", "--client", "Made-up Motors Sdn. Bhd.")
    assert "similar name, same client" in out
    assert "No earlier project" in run("find", "Zeta Request System")


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


def test_archive_moves_the_whole_folder_or_nothing(projects, run, monkeypatch):
    """When something in the folder was open, the move fell back to copying and deleting: half the project
    stayed, client documents went missing from it, and both archive and restore then refused."""
    p = new_project(projects)
    before = sorted(str(f.relative_to(p)) for f in p.rglob("*"))

    def in_use(src, dest):
        raise PermissionError(32, "The process cannot access the file because it is being used by another process")

    with monkeypatch.context() as m:
        m.setattr(project_tool.os, "rename", in_use)
        with pytest.raises(SystemExit, match="Nothing was archived.*close its files"):
            run("archive", "leave-request")
    assert sorted(str(f.relative_to(p)) for f in p.rglob("*")) == before
    assert not (projects / "_archive" / "leave-request").exists()
    run("archive", "leave-request")
    with monkeypatch.context() as m:
        m.setattr(project_tool.os, "rename", in_use)
        with pytest.raises(SystemExit, match="Nothing was restored"):
            run("restore", "leave-request")
    assert (projects / "_archive" / "leave-request").exists() and not p.exists()


# ====================================================================== ready for sign-off
ITEM = {"type": "question", "audience": "client", "severity": "medium", "category": "GP-01", "stage": "workshop-1",
        "source": "Minutes", "finding": "Not said.", "raised": "2026-11-01"}


def with_items(p, items, spec_change=None):
    """The register (and the spec) as given, with the generated document made after them, as after generating."""
    spec = support.load_spec(p)
    if spec_change:
        spec_change(spec)
        support.write_spec(p, spec)
    (p / "register.json").write_text(json.dumps({"project": "Leave Request System", "items": [{**ITEM, **it} for it in items]}),
                                     encoding="utf-8")
    later = (p / "register.json").stat().st_mtime + 60
    for f in (p / "output").iterdir():
        os.utime(f, (later, later))


def test_a_version_with_a_question_blocking_sign_off_is_not_issued_without_a_reason(projects, run):
    """A version went out for signature with a question still marked "Blocks sign-off" in it."""
    p = new_project(projects)
    with_items(p, [{"id": "R-001", "severity": "high", "status": "answered", "question": "Which export do you use?",
                    "answer": "The daily one."}])
    with pytest.raises(SystemExit, match="Nothing was issued"):
        run("issue", "leave-request")
    assert not project_tool.load_issues(p)
    out = run("issue", "leave-request", "--anyway", "client signs with R-001 open")
    assert "R-001 still blocks sign-off: Which export do you use? It has an answer" in out
    assert project_tool.load_issues(p)[0]["note"] == "Issued with 1 point(s) open: client signs with R-001 open"


def test_ready_asks_for_the_agreed_decision_and_passes_once_it_is_written(projects, run, capsys):
    """The client's raw answers were printed as the decisions they sign."""
    p = new_project(projects)
    settled = {"id": "R-002", "status": "resolved", "question": "Keep closed requests how long?", "answer": "TEST ANSWER: 7y, IT says 10"}
    with_items(p, [settled])
    with pytest.raises(SystemExit):
        run("ready", "leave-request")
    assert "R-002 is settled with no agreed decision, so the document prints the client's own answer as what is signed." \
        in capsys.readouterr().out
    with_items(p, [{**settled, "decision": "Closed requests are kept for ten years."}])
    out = run("ready", "leave-request")
    assert "Not ready" not in out and "agreed decision" not in out


def test_ready_stops_when_the_document_is_older_than_the_register(projects, run):
    p = new_project(projects)
    with_items(p, [])
    later = (p / "output" / f"{DOC}.docx").stat().st_mtime + 60
    os.utime(p / "register.json", (later, later))
    with pytest.raises(SystemExit):
        run("ready", "leave-request")


def test_ready_points_at_what_to_check_before_it_goes_out(projects, run, capsys):
    """Answered questions still open, the same question twice, choices that differ from the client's list,
    "the agreed time" with no time agreed, nobody to sign."""
    p = new_project(projects)

    def change(spec):
        spec["dialogs"] = [{"id": "cancel-dialog", "title": "Cancel request", "fields": [
            {"id": "reason", "label": "Reason", "type": "select", "options": ["Plans changed", "Illness", "Work", "Other"]}]}]
        spec["requirements"][0]["items"].append("System shall remind the approver after the agreed time.")
        spec["requirements"][0]["items"].append({"text": "System shall keep files for the agreed period.", "tbc": "R-004"})
    with_items(p, [
        {"id": "R-003", "status": "answered", "question": "Which reasons may an employee give when cancelling a request?",
         "answer": "Plans changed, Illness, Family or travel, Other (with remarks)"},
        {"id": "R-004", "status": "open", "question": "Which reasons may an employee give when cancelling a leave request?"},
    ], change)
    out = run("ready", "leave-request")
    assert "R-003 has an answer but is still open" in out
    assert "R-003 and R-004 look like the same question" in out
    assert ("dialog 'Cancel request', field 'Reason': its choices differ from R-003's answer "
            "(it leaves out family or travel and adds Work)") in out
    assert 'FR-APP-001.6 says "the agreed time" with nothing tracking it' in out
    assert "FR-APP-001.7" not in out, "a placeholder linked to its register item is tracked"
    assert "The spec names nobody to sign" in out
    assert "Not ready" not in out, "none of these stops the issue"


def sow(spec, deferred=None):
    """The scope of work sold a leave application, its approval and a leave balance report; the spec specifies the
    first two."""
    spec["sow"] = {"source": "1 Client documents/2026-01-05 Scope of work.pdf", "items": [
        {"ref": "1", "item": "Leave application"}, {"ref": "2", "item": "Approval"},
        {"ref": "3", "item": "Leave balance report", **({"deferred": deferred} if deferred else {})}]}
    spec["requirements"][0]["sow"] = "1"
    spec["requirements"][1]["sow"] = ["2"]


def test_ready_stops_when_something_the_scope_of_work_sold_is_not_specified(projects, run, capsys):
    """An end-to-end test signed off a requirements document that covered six of the fourteen modules sold."""
    p = new_project(projects)
    with_items(p, [], sow)
    with pytest.raises(SystemExit):
        run("ready", "leave-request")
    out = capsys.readouterr().out
    assert 'Scope of work item 3 "Leave balance report" has no requirement.' in out
    assert "FR-APP-003 names no scope of work item" in out, "a requirement nothing sold may be a change request"
    with_items(p, [], lambda spec: sow(spec, deferred="Phase 2, agreed in workshop 2"))
    out = run("ready", "leave-request")
    assert "Scope of work item" not in out, "an item left out with the client's agreement is accounted for"


def test_ready_asks_for_the_scope_of_work_when_the_spec_has_none(projects, run):
    p = new_project(projects)
    with_items(p, [])
    assert "The spec lists no scope of work items (sow)" in run("ready", "leave-request")


def test_ready_stops_on_a_required_section_still_empty_unless_an_open_register_item_tracks_it(projects, run, capsys):
    p = new_project(projects)

    def without_reports(spec):
        spec["extra_sections"] = [e for e in spec["extra_sections"] if e["title"] != "Reports"]
        spec["nfr"] = [x for x in spec["nfr"] if x["area"] != "Backup"] + [{"area": "Backup", "tbc": "R-005"}]
    with_items(p, [{"id": "R-005", "status": "open", "question": "How long are backups kept?"}], without_reports)
    with pytest.raises(SystemExit):
        run("ready", "leave-request")
    out = capsys.readouterr().out
    assert ("The document prints the section Reports as To be confirmed: write it in the spec, or open a register item "
            "for it and link it there (tbc: R-…).") in out
    assert "Backup" not in out, "an open register item tracks it"

    def tracked(spec):
        without_reports(spec)
        spec["extra_sections"].append({"title": "Reports", "tbc": "R-006"})
    with_items(p, [{"id": "R-005", "status": "resolved", "question": "How long are backups kept?", "decision": "30 days."},
                   {"id": "R-006", "status": "open", "question": "Which reports does HR need?"}], tracked)
    with pytest.raises(SystemExit):
        run("ready", "leave-request")
    out = capsys.readouterr().out
    assert ("The document still prints the non-functional requirement Backup as To be confirmed, but R-005 is settled: "
            "write what was agreed into the spec.") in out
    assert "section Reports" not in out


def test_a_list_of_choices_keeps_an_or_inside_it():
    assert project_tool.answer_list("TEST ANSWER: Vehicle problem, Road or weather, Other (with remarks).") == \
        {"vehicle problem", "road or weather", "other"}
    assert project_tool.answer_list("Email, SMS or push") == {"email", "sms", "push"}


# ====================================================================== QC pass 1: medium findings
def test_issue_takes_this_version_only_and_needs_its_pdf(projects, run):
    """`* v1.*` also matched v1.0 and v1.1, Word's ~$ lock file and leftovers of the PDF step, and a version with
    no PDF (the Word step failed) was locked for good."""
    p = new_project(projects, version="1", generated=("docx",))
    for extra in ("Leave Request System – Requirements Specification v1.0.docx", "~$ave Request System – Requirements Specification v1.docx",
                  "Leave Request System – Requirements Specification v1.sharp.pdf"):
        (p / "output" / extra).write_bytes(b"other")
    with pytest.raises(SystemExit, match="has no PDF"):
        run("issue", "leave-request")
    assert not project_tool.load_issues(p), "nothing issued"
    run("issue", "leave-request", "--without-pdf")
    assert project_tool.load_issues(p)[0]["files"] == [DOC.replace("v0.1", "v1") + ".docx"]
    assert writable(p / "output" / "Leave Request System – Requirements Specification v1.0.docx"), "another version stays editable"


def test_a_version_written_without_quotes_is_refused(projects, run):
    """YAML reads 1.10 as the number 1.1: the version would be named, locked and overwritten as v1.1."""
    p = new_project(projects)
    spec = support.load_spec(p)
    spec["project"]["version"] = 1.10  # as YAML reads `version: 1.10`
    support.write_spec(p, spec)
    assert "version: 1.1\n" in (p / "spec" / "app.yaml").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="without quotes"):
        run("issue", "leave-request")


def test_a_version_issued_on_another_computer_stays_locked(projects, run):
    """Two people issuing at once: OneDrive keeps both records, one under another name. Both count."""
    p = new_project(projects)
    run("issue", "leave-request", "--date", "2026-11-10")
    (p / "output" / "issued-LAPTOP-2.json").write_text(json.dumps([{"version": "0.0", "date": "2026-11-01", "to": "SAMPLE", "files": [], "note": ""}]),
                                                         encoding="utf-8")
    assert project_tool.is_issued(p, "0.0") and project_tool.is_issued(p, "0.1")
    assert not list((p / "output").glob(".issued-*.tmp")), "written in one step"


def test_file_never_leaves_a_document_in_both_places(projects, run, tmp_path, monkeypatch):
    """A file open in Word or Excel was copied, then could not be removed: it ended up in the inbox and the
    project both, with a raw error."""
    p = new_project(projects)
    src = tmp_path / "comments.docx"
    src.write_bytes(b"comments")

    def in_use(a, b):
        raise PermissionError(32, "in use")

    with monkeypatch.context() as m:
        m.setattr(project_tool.os, "rename", in_use)
        with pytest.raises(SystemExit, match="Nothing was filed"):
            run("file", "leave-request", str(src), "--kind", "client comments", "--date", "2026-11-12")
    assert src.exists() and not list((p / "docs").glob("*comments*"))
    with pytest.raises(SystemExit, match="not a date"):
        run("file", "leave-request", str(src), "--kind", "client comments", "--date", "2026/11/12")
    run("file", "leave-request", str(src), "--kind", "client comments", "--responds-to", "1:3", "--date", "2026-11-12")
    assert (p / "docs" / "2026-11-12 client comments on v1-3.docx").exists() and not src.exists()
