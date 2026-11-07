"""tools/layout.py and `project.py migrate`: the two folder layouts of a project, moving a project from the old one
to the new one and back, what stops a move, and every tool a skill uses working on a migrated project.

Every project is a temp copy of the made-up sample (the temp_workspace fixture points the tools at a temp
workspace). The knowledge base is the starter one in templates/, never the workspace's.
"""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import threading
from urllib.parse import unquote

import pytest
from openpyxl import load_workbook

import support

import change_request
import estimate
import layout
import mockup
import overview
import platform_fit
import project as project_tool
import register
import review_doc
import status
import uat
import workshop

STARTER = support.ROOT / "templates" / "knowledge"
SAMPLE_DOC = "Leave Request System – System Requirement Specifications v0.1"
REVIEW_MD = "# Review: Leave Request System SRS v1.0\n\n## Verdict\n\n**Not ready for sign-off.**\n"
AGENDA = {"project": "Leave Request System", "workshop": "Workshop 2: mock-up review", "date": "2026-02-10",
          "duration_minutes": 60, "goal": "Agree the approval rules.",
          "sections": [{"title": "Approval", "minutes": 30, "show": ["review-application"],
                        "items": [{"ref": "R-001", "question": "Who approves when the line manager is on leave?",
                                   "why": "Applications wait otherwise."}]}]}
ITEMS = [{"type": "question", "audience": "client", "severity": "high", "category": "GP-08", "stage": "workshop-2",
          "source": "FR-APP-002", "finding": "No stand-in approver is defined.",
          "question": "Who approves when the line manager is on leave?"}]
CR = {"title": "Export all applications to Excel", "request": "HR wants to export every leave application to Excel.",
      "asked_by": "HR manager, during UAT", "raised": "2026-12-03", "stage": "uat", "verdict": "new", "basis_version": "0.1",
      "cited": [{"ref": "screen my-applications", "section": "section 4.2", "quote": "My Leave Applications."}],
      "reasoning": "No export anywhere in v0.1.", "why": "The signed document has no export.",
      "changes": ["An Export to Excel button for HR Admin"], "gap_pattern": "GP-04",
      "lines": [{"id": "L01", "item": "Excel export", "block": "BB-13", "count": 1}],
      "assumptions": ["Same columns as the list"], "status": "raised"}


# ---------------------------------------------------------------------- helpers
def quiet(fn, *args, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kw)


@pytest.fixture
def projects(temp_workspace, monkeypatch):
    monkeypatch.setattr(status, "ROOT", temp_workspace)
    monkeypatch.setattr(change_request, "knowledge_dir", lambda: STARTER)
    monkeypatch.setattr(workshop, "knowledge_dir", lambda: STARTER)
    return temp_workspace / "projects"


@pytest.fixture
def run(monkeypatch, capsys):
    """Run a tool's main() with arguments and return what it printed."""
    def call(tool, *args):
        monkeypatch.setattr(sys, "argv", [f"{tool.__name__}.py", *map(str, args)])
        tool.main()
        return capsys.readouterr().out
    return call


def old_project(projects, slug="leave-request"):
    """The sample in the old layout with something in every folder: client documents, a review with its Word file
    and extraction, change notes, a workshop with its two documents, comments with ids, a live session that
    ended, two mock-up versions and screenshots, a generated and issued document, an estimate, UAT scripts and a
    CR log with its Excel file and client note."""
    p = projects / slug
    shutil.copytree(support.EXAMPLE, p, ignore=shutil.ignore_patterns("mockup", "feedback", "output", "*.xlsx"))
    quiet(mockup.build, p)
    support.fake_screenshots(p)
    (p / "docs").mkdir()
    (p / "docs" / "2026-10-22 SRS v1.0.pdf").write_bytes(b"%PDF-1.4 sample")
    (p / "docs" / "2026-10-30 brief.docx").write_bytes(b"brief")
    (p / "register.json").write_text(json.dumps({"project": "Leave Request System", "client": "Sample", "items": []}), encoding="utf-8")
    reg = register.load(p)
    new, _, errors = register.prepare(reg, ITEMS)
    assert not errors
    reg["items"] += new
    register.save(p, reg)
    quiet(register.render, p, register.load(p))
    review = p / "reviews" / "srs-v1.0"
    (review / "extract" / "images").mkdir(parents=True)
    (review / "extract" / "text.md").write_text("text", encoding="utf-8")
    (review / "review.md").write_text(REVIEW_MD, encoding="utf-8")
    review_doc.render(p, review)
    (p / "reviews" / "mockup-v0.1-changes.md").write_text("# Mock-up v0.1 changes\n\n- Wider list\n", encoding="utf-8")
    (p / "workshops").mkdir()
    agenda = p / "workshops" / "2026-02-10 workshop 2.json"
    agenda.write_text(json.dumps(AGENDA), encoding="utf-8")
    workshop.render(AGENDA, p, agenda)
    (p / "feedback").mkdir(exist_ok=True)
    (p / "feedback" / "feedback.json").write_text(json.dumps([{"id": "FB-001", "screen": "login", "text": "Wider", "status": "applied"},
                                                              {"id": "FB-007", "screen": "login", "text": "Later"}]), encoding="utf-8")
    (p / "feedback" / "live.json").write_text(json.dumps({"started": "2026-11-06T20:52:13", "ended": "2026-11-06T20:55:05"}), encoding="utf-8")
    shutil.copytree(p / "mockup" / "versions" / "v0.1", p / "mockup" / "versions" / "v0.1-presented-20261106-2052")
    (p / "output").mkdir()
    (p / "output" / f"{SAMPLE_DOC}.docx").write_bytes(b"docx")
    (p / "output" / f"{SAMPLE_DOC}.pdf").write_bytes(b"%PDF-1.4 sample")
    shutil.copy(p / "spec" / "app.yaml", p / "output" / "spec-v0.1.yaml")
    (p / "uat").mkdir()
    (p / "uat" / "2026-11-06 uat scripts v0.1.json").write_text(json.dumps({"spec": "output/spec-v0.1.yaml"}), encoding="utf-8")
    (p / "uat" / "2026-11-06 uat scripts v0.1.xlsx").write_bytes(b"xlsx")
    (p / "uat" / "2026-11-06 uat scripts v0.1.docx").write_bytes(b"docx")
    (p / "changes").mkdir()
    (p / "changes" / "crs.json").write_text(json.dumps({"project": "Leave Request System", "crs": []}), encoding="utf-8")
    (p / "changes" / "CR log (internal).xlsx").write_bytes(b"xlsx")
    (p / "changes" / "CR-001 Export - change request note.docx").write_bytes(b"docx")
    return p


def issue(p, run):
    run(project_tool, "issue", p.name, "--date", "2026-11-10", "--without-pdf", "--anyway", "test fixture")  # the PDF needs Word, not here


def tree(folder):
    """Every file under a folder with a hash of its content and whether it is read-only, and every folder."""
    files = {f.relative_to(folder).as_posix(): (hashlib.sha256(f.read_bytes()).hexdigest(), os.access(f, os.W_OK))
             for f in sorted(folder.rglob("*")) if f.is_file()}
    folders = {d.relative_to(folder).as_posix() for d in folder.rglob("*") if d.is_dir()}
    return files, folders


def writable(path):
    return bool(os.stat(path).st_mode & stat.S_IWRITE)


def links(project):
    html = (project / overview.PAGE).read_text(encoding="utf-8")
    return [unquote(h) for h in re.findall(r'href="([^"]+)"', html)]


# ---------------------------------------------------------------------- both layouts
def test_both_layouts_resolve(tmp_path):
    old = support.EXAMPLE
    assert not layout.is_new(old) and layout.name(old) == "old"
    assert layout.spec_file(old) == old / "spec" / "app.yaml" and layout.spec_file(old).exists()
    assert layout.register_xlsx(old) == old / "register.xlsx" and layout.docs_dir(old) == old / "docs"
    assert layout.screenshots_dir(old) == old / "mockup" / "screenshots" and layout.output_dir(old) == old / "output"
    assert layout.estimate_xlsx(old, old / "estimates" / "a.json") == old / "estimates" / "a.xlsx"

    new = support.migrated_copy(tmp_path / "leave-request")
    assert layout.is_new(new) and layout.name(new) == "new"
    expected = {
        layout.spec_file(new): "_blueprint/spec/app.yaml", layout.register_json(new): "_blueprint/register.json",
        layout.register_xlsx(new): "Questions and fixes register.xlsx", layout.docs_dir(new): "1 Client documents",
        layout.reviews_dir(new): "_blueprint/reviews", layout.review_reports_dir(new, layout.reviews_dir(new) / "x"): "2 Reviews",
        layout.workshops_source(new): "_blueprint/workshops", layout.workshops_output(new): "3 Workshops",
        layout.mockup_dir(new): "_blueprint/mockup", layout.screenshots_dir(new): "4 Mock-up screenshots",
        layout.screenshots_record(new): "_blueprint/mockup/screenshots/taken-from.json",
        layout.versions_dir(new): "_blueprint/mockup/versions", layout.feedback_file(new): "_blueprint/feedback/feedback.json",
        layout.output_dir(new): "5 Requirements document", layout.issued_file(new): "_blueprint/output/issued.json",
        layout.snapshot(new, "0.1"): "_blueprint/output/spec-v0.1.yaml", layout.estimates_source(new): "_blueprint/estimates",
        layout.estimates_output(new): "Internal – estimates and change requests", layout.uat_source(new): "_blueprint/uat",
        layout.uat_output(new): "6 UAT", layout.cr_log(new): "_blueprint/changes/crs.json", layout.cr_notes_dir(new): "7 Change requests",
        layout.cr_log_xlsx(new): "Internal – estimates and change requests/CR log (internal).xlsx",
        layout.defect_log(new): "_blueprint/uat/defects/defects.json", layout.defect_log_xlsx(new): "6 UAT/Defect log.xlsx",
    }
    for path, rel in expected.items():
        assert layout.shown(new, path) == rel
    assert layout.spec_file(new).exists() and (new / "_blueprint" / "README.txt").read_text(encoding="utf-8").startswith(
        "Blueprint's working files. Leave them as they are; ask Claude instead.")
    assert layout.resolve(new, "spec/app.yaml") == layout.spec_file(new)
    assert layout.resolve(new, "output/spec-v0.1.yaml") == layout.snapshot(new, "0.1")
    assert layout.resolve(old, "output/spec-v0.1.yaml") == old / "output" / "spec-v0.1.yaml"


def test_a_new_project_starts_in_the_new_layout(projects, run):
    import new_project

    out = run(new_project, "courier-booking", "Courier Booking System", "Sample Client")
    p = projects / "courier-booking"
    assert layout.is_new(p) and "1 Client documents/" in out
    assert sorted(x.name for x in p.iterdir()) == ["1 Client documents", "Project overview.html", "_blueprint"]
    assert json.loads(layout.register_json(p).read_text(encoding="utf-8"))["project"] == "Courier Booking System"
    assert "Blueprint's working files are in" in (p / overview.PAGE).read_text(encoding="utf-8")


def test_a_teammates_project_in_the_other_layout_is_read_by_every_tool_that_reads(projects, run):
    """Both layouts side by side in one projects folder, as a shared folder has them during the change."""
    support.migrated_copy(projects / "moved")
    shutil.copytree(support.EXAMPLE, projects / "not-moved", ignore=shutil.ignore_patterns("mockup", "feedback", "output", "*.xlsx"))
    names = [m["slug"] for m in mockup.mockups(projects)]
    assert sorted(names) == ["moved", "not-moved"], "the page that lists every mock-up finds both"
    for slug in ("moved", "not-moved"):
        s = status.project_status(projects / slug)
        assert s["spec_version"] == "0.1" and not s["problems"]
    assert {p["slug"] for p in [project_tool.profile(projects / "moved"), project_tool.profile(projects / "not-moved")]} == {"moved", "not-moved"}
    assert project_tool.profile(projects / "moved")["screens"] == project_tool.profile(projects / "not-moved")["screens"] != set()


# ---------------------------------------------------------------------- the migration
def test_the_dry_run_lists_every_move_and_moves_nothing(projects, run):
    p = old_project(projects)
    issue(p, run)
    before = tree(p)
    out = run(project_tool, "migrate", p.name, "--dry-run")
    assert tree(p) == before, "a dry run moves nothing"
    assert "would move to the new layout (dry run: nothing moved)" in out
    for line in ("docs  ->  1 Client documents", "register.xlsx  ->  Questions and fixes register.xlsx",
                 "register.json  ->  _blueprint/register.json", "spec  ->  _blueprint/spec", "feedback  ->  _blueprint/feedback",
                 "reviews/srs-v1.0/SRS v1.0 review.docx  ->  2 Reviews/SRS v1.0 review.docx", "reviews  ->  _blueprint/reviews",
                 "workshops/2026-02-10 workshop 2 - agenda.docx  ->  3 Workshops/2026-02-10 workshop 2 - agenda.docx",
                 "mockup/screenshots/login.png  ->  4 Mock-up screenshots/login.png", "mockup  ->  _blueprint/mockup",
                 f"output/{SAMPLE_DOC}.pdf  ->  5 Requirements document/{SAMPLE_DOC}.pdf", "output  ->  _blueprint/output",
                 "uat/2026-11-06 uat scripts v0.1.xlsx  ->  6 UAT/2026-11-06 uat scripts v0.1.xlsx",
                 "changes/CR-001 Export - change request note.docx  ->  7 Change requests/CR-001 Export - change request note.docx",
                 "changes/CR log (internal).xlsx  ->  Internal – estimates and change requests/CR log (internal).xlsx",
                 "estimates  ->  _blueprint/estimates"):
        assert line in out, line
    moves = len(layout.plan_migration(p)[0])
    assert out.count("  ->  ") == moves


def test_migrate_moves_everything_to_its_place_and_undo_puts_it_back_byte_for_byte(projects, run):
    p = old_project(projects)
    issue(p, run)
    overview.build(p)  # the page as it was, so that it is the same after undo
    before = tree(p)
    out = run(project_tool, "migrate", p.name)
    assert "moved to the new layout" in out and "Issued files are still read-only" in out
    top = sorted(x.name for x in p.iterdir())
    assert top == ["1 Client documents", "2 Reviews", "3 Workshops", "4 Mock-up screenshots", "5 Requirements document",
                   "6 UAT", "7 Change requests", "Internal – estimates and change requests", "Open the mock-up.cmd",
                   "Open the mock-up.command", "Project overview.html", "Questions and fixes register.xlsx",
                   "Questions for the client.xlsx", "_blueprint"]
    assert sorted(x.name for x in (p / "2 Reviews").iterdir()) == ["Mock-up comments.xlsx", "Mock-up v0.1 changes.docx", "SRS v1.0 review.docx"]
    assert sorted(x.name for x in (p / "3 Workshops").iterdir()) == [
        "2026-02-10 workshop 2 - agenda.docx", "2026-02-10 workshop 2 - facilitator notes (internal).docx"]
    assert all(f.suffix == ".png" for f in (p / "4 Mock-up screenshots").iterdir()) and (p / "4 Mock-up screenshots" / "login.png").exists()
    assert sorted(x.name for x in (p / "5 Requirements document").iterdir()) == [f"{SAMPLE_DOC}.docx", f"{SAMPLE_DOC}.pdf"]
    assert sorted(x.name for x in (p / "Internal – estimates and change requests").iterdir()) == ["CR log (internal).xlsx"]
    assert sorted(x.name for x in (p / "_blueprint").iterdir()) == [
        "README.txt", "changes", "estimates", "feedback", "migration.json", "mockup", "output", "register.json", "reviews", "spec",
        "uat", "workshops"]
    assert (p / "_blueprint" / "reviews" / "srs-v1.0" / "extract" / "text.md").exists()
    assert (p / "_blueprint" / "mockup" / "screenshots" / "taken-from.json").exists() and not mockup.screenshot_problems(p, mockup.load_spec(p))
    assert [c["id"] for c in json.loads(layout.feedback_file(p).read_text(encoding="utf-8"))] == ["FB-001", "FB-007"]
    for f in (p / "5 Requirements document").iterdir():
        assert not writable(f), f"{f.name} was issued: it stays read-only"
    assert not writable(layout.snapshot(p, "0.1"))
    assert project_tool.is_issued(p, "0.1"), "the record of what was issued moved with it"
    log = json.loads((p / "_blueprint" / "migration.json").read_text(encoding="utf-8"))
    assert ["docs", "1 Client documents"] in log["moves"] and "2 Reviews/Mock-up v0.1 changes.docx" in log["made"]

    out = run(project_tool, "migrate", p.name, "--undo")
    assert "moved to the old layout" in out
    assert tree(p) == before, "undo puts every file back where it was, byte for byte and read-only where it was"


def test_files_added_after_the_migration_go_back_with_undo(projects, run):
    p = old_project(projects)
    run(project_tool, "migrate", p.name)
    (p / "1 Client documents" / "2026-11-12 client comments.docx").write_bytes(b"later")
    (p / "5 Requirements document" / "Later v0.2.docx").write_bytes(b"later")
    (p / "6 UAT" / "results.xlsx").write_bytes(b"later")
    run(project_tool, "migrate", p.name, "--undo")
    assert (p / "docs" / "2026-11-12 client comments.docx").exists() and (p / "output" / "Later v0.2.docx").exists()
    assert (p / "uat" / "results.xlsx").exists() and not (p / "_blueprint").exists() and not (p / "6 UAT").exists()


def test_migrate_all_reports_each_project(projects, run):
    old_project(projects, "first")
    old_project(projects, "second")
    support.migrated_copy(projects / "already")
    out = run(project_tool, "migrate", "--all", "--dry-run")
    assert "first: would move" in out and "second: would move" in out and "already" not in out
    out = run(project_tool, "migrate", "--all")
    assert "first: moved" in out and "second: moved" in out
    assert all(layout.is_new(projects / s) for s in ("first", "second", "already"))
    assert "every one is in the new layout already" in run(project_tool, "migrate", "--all")


def test_check_says_an_old_project_can_be_migrated(projects, run):
    old_project(projects)
    assert "say 'migrate the folders'" in run(project_tool, "check")
    run(project_tool, "migrate", "leave-request")
    assert "migrate" not in run(project_tool, "check")


# ---------------------------------------------------------------------- what stops it
def refused(run, p, *args):
    before = tree(p)
    with pytest.raises(SystemExit):
        run(project_tool, "migrate", p.name, *args)
    assert tree(p) == before, "nothing was moved"


def test_a_running_mock_up_server_stops_the_move(projects, run, capsys):
    p = old_project(projects)
    server = mockup.make_server(layout.mockup_dir(p), layout.feedback_file(p), "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with mockup.server_mark(p, server.server_address[1]):
            refused(run, p)
            assert "its mock-up is open" in capsys.readouterr().out
    finally:
        server.shutdown()
        server.server_close()
    assert not layout.server_file(p).exists(), "the mark goes when the server stops"
    layout.server_file(p).write_text(json.dumps({"port": server.server_address[1]}), encoding="utf-8")
    assert layout.server_running(p) is None, "a mark left by a server that stopped is ignored"


def test_an_open_live_session_stops_the_move(projects, run, capsys):
    p = old_project(projects)
    (p / "feedback" / "live.json").write_text(json.dumps({"started": "2026-11-06T20:52:13"}), encoding="utf-8")
    refused(run, p)
    assert "a live session is open (started 2026-11-06T20:52:13)" in capsys.readouterr().out


def test_a_file_open_in_word_or_excel_stops_the_move(projects, run, capsys):
    p = old_project(projects)
    owner = p / "docs" / "~$26-10-30 brief.docx"  # Word's lock file beside the open document
    owner.write_bytes(b"someone")
    refused(run, p)
    out = capsys.readouterr().out
    assert "docs/2026-10-30 brief.docx is open in Word or Excel" in out and "Close them and try again" in out
    owner.unlink()
    if os.name == "nt":  # Windows also refuses to move a file another program holds open
        with open(layout.register_xlsx(p), "rb"):
            refused(run, p)
        assert "register.xlsx is open in another program" in capsys.readouterr().out


def test_a_target_that_exists_stops_the_move(projects, run, capsys):
    p = old_project(projects)
    (p / "1 Client documents").mkdir()
    refused(run, p)
    out = capsys.readouterr().out
    assert "these already exist, so nothing was moved" in out and "1 Client documents" in out
    shutil.rmtree(p / "1 Client documents")
    run(project_tool, "migrate", p.name)
    (p / "docs").mkdir()
    capsys.readouterr()
    refused(run, p, "--undo")
    assert "already exist in the old layout's places" in capsys.readouterr().out


def test_a_failed_move_puts_back_what_was_moved(projects, monkeypatch):
    p = old_project(projects)
    before = tree(p)
    real = layout._move

    def failing(project, src, dst):
        if src == "output":
            raise PermissionError("locked")
        real(project, src, dst)
    monkeypatch.setattr(layout, "_move", failing)
    with pytest.raises(RuntimeError, match="output could not be moved"):
        layout.migrate(p)
    assert tree(p) == before


# ---------------------------------------------------------------------- what keeps working
def test_the_registers_excel_take_over_finds_the_renamed_file(projects, run):
    p = old_project(projects)
    run(project_tool, "migrate", p.name)
    path = layout.register_xlsx(p)
    wb = load_workbook(path)
    ws = wb["For client"]
    head = [c.value for c in ws[1]]
    ws.cell(row=2, column=head.index("Client response") + 1, value="The manager's manager.")
    wb.save(path)
    out = run(register, "render", p)
    assert "Taken from Questions and fixes register.xlsx into register.json:" in out
    assert register.load(p)["items"][0]["answer"] == "The manager's manager."
    assert not (p / "register.xlsx").exists() and not (p / "register.json").exists()


def test_the_overview_links_resolve_after_the_migration(projects, run):
    p = old_project(projects)
    issue(p, run)
    run(project_tool, "migrate", p.name)
    found = links(p)
    assert len(found) >= 10
    for href in found:
        assert (p / href).exists(), href
    for folder in ("1 Client documents/", "2 Reviews/", "3 Workshops/", "4 Mock-up screenshots/", "5 Requirements document/",
                   "Questions and fixes register.xlsx", "_blueprint/mockup/index.html"):
        assert any(h.startswith(folder) for h in found), folder
    assert not any(h.startswith(("docs/", "reviews/", "output/", "mockup/")) for h in found)


def test_every_tool_the_skills_use_works_on_a_migrated_sample(projects, run, monkeypatch, tmp_path):
    p = support.migrated_copy(projects / "leave-request")
    quiet(mockup.build, p)
    assert (p / "_blueprint" / "mockup" / "index.html").exists() and (p / "_blueprint" / "mockup" / "versions" / "v0.1").is_dir()
    support.fake_screenshots(p)  # the screenshot step without a browser
    assert (p / "4 Mock-up screenshots" / "login.png").exists() and not mockup.screenshot_problems(p, mockup.load_spec(p))

    built = support.generate(p)
    assert built.path.parent == p / "5 Requirements document" and layout.snapshot(p, "0.1").exists()
    issue(p, run)
    assert not writable(built.path)

    layout.register_json(p).write_text(json.dumps({"project": "Leave Request System", "client": "Sample", "items": []}), encoding="utf-8")
    items = tmp_path / "items.json"
    items.write_text(json.dumps(ITEMS), encoding="utf-8")
    assert "R-001" in run(register, "add", p, "--file", items)
    run(register, "render", p)
    assert layout.register_xlsx(p).exists()

    agenda = layout.workshops_source(p) / "2026-02-10 workshop 2.json"
    agenda.parent.mkdir(parents=True)
    agenda.write_text(json.dumps(AGENDA), encoding="utf-8")
    run(workshop, "render", p)
    assert (p / "3 Workshops" / "2026-02-10 workshop 2 - agenda.docx").exists()
    assert (p / "3 Workshops" / "2026-02-10 workshop 2 - facilitator notes (internal).docx").exists()

    run(estimate, "--knowledge", STARTER, "render", p)
    assert (p / "Internal – estimates and change requests" / "2026-11-06 estimate from spec v0.1.xlsx").exists()

    out = run(uat, "draft", p, "--date", "2026-11-06")
    assert "issued on" in out
    scripts = next(layout.uat_source(p).glob("*.json"))
    assert json.loads(scripts.read_text(encoding="utf-8"))["spec"] == "output/spec-v0.1.yaml", "written the way both layouts read"
    run(uat, "render", p)
    assert sorted(f.suffix for f in (p / "6 UAT").iterdir()) == [".docx", ".xlsx"]

    cr = tmp_path / "cr.json"
    cr.write_text(json.dumps(CR), encoding="utf-8")
    assert "_blueprint/changes/crs.json" in run(change_request, "add", p, "--file", cr)
    run(change_request, "render", p)
    run(change_request, "note", p, "CR-001")
    assert (p / "Internal – estimates and change requests" / "CR log (internal).xlsx").exists()
    assert len(list((p / "7 Change requests").glob("CR-001 *.docx"))) == 1
    assert "_blueprint/output/spec-v0.1.yaml" in change_request.signed_basis(p)["source"]

    run(platform_fit, "apply", p, "--knowledge", STARTER)
    assert "platform_fit:" in layout.spec_file(p).read_text(encoding="utf-8")

    brief = tmp_path / "brief.docx"
    brief.write_bytes(b"brief")
    run(project_tool, "file", p.name, brief, "--kind", "brief", "--date", "2026-11-01")
    assert (p / "1 Client documents" / "2026-11-01 brief.docx").exists()

    review = layout.reviews_dir(p) / "srs-v1.0"
    review.mkdir(parents=True)
    (review / "review.md").write_text(REVIEW_MD, encoding="utf-8")
    run(review_doc, p)
    assert (p / "2 Reviews" / "SRS v1.0 review.docx").exists()

    mockup.save_comment(layout.feedback_file(p), {"screen": "login", "text": "Bigger logo"})
    s = status.project_status(p)
    assert s["layout"] == "new" and s["feedback_unprocessed"] == 1 and s["last_issued"]["version"] == "0.1" and not s["problems"]
    run(overview, "build", p)
    for href in links(p):
        assert (p / href).exists(), href
    leftovers = [name for name in layout.OLD_PARTS if (p / name).exists()]
    assert not leftovers, f"a tool wrote into the old layout's places: {leftovers}"


def test_status_shows_an_old_project_with_the_offer_to_migrate(projects, temp_workspace, run, monkeypatch):
    old_project(projects, "old-one")
    support.migrated_copy(projects / "new-one")
    out = run(status)
    assert "(old-one): " in out and "old folder layout" in out.split("(old-one)")[1].split("\n- ")[0]
    assert "migrate the folders" in out
    assert "old folder layout" not in out.split("(new-one)")[1].split("\n- ")[0]



def test_a_failed_move_says_what_could_not_be_put_back(projects, monkeypatch):
    """It said "Everything moved so far was put back" even when putting back failed."""
    p = old_project(projects)
    real = layout._move

    def failing(project, src, dst):
        if src == "output":
            raise PermissionError("locked")
        real(project, src, dst)

    monkeypatch.setattr(layout, "_move", failing)
    monkeypatch.setattr(layout.os, "rename", lambda a, b: (_ for _ in ()).throw(PermissionError("still open"))
                        if os.path.basename(b) == "docs" else os.replace(a, b))
    with pytest.raises(RuntimeError, match="could NOT be put back"):
        layout.migrate(p)
