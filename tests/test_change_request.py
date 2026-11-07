"""tools/change_request.py: a request checked against the version the client signed, the CR log, sizing in
building blocks, the client's change request note and an Ambiguous request turned into a register question.

Every project is a temp copy of the made-up sample (the temp_workspace fixture points the tools at it), issued
with project.py itself. The knowledge base is the starter one in templates/ or a copy the test changes, never
knowledge/ in the app folder, which is a link into the workspace.
"""
import json
import os
import shutil
import stat
import sys

import openpyxl
import pytest
from docx import Document

import support

import change_request as cr_tool
import project as project_tool

STARTER = support.ROOT / "templates" / "knowledge"
DOC = "Leave Request System – System Requirement Specifications v0.1"

REGISTER = {"project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "items": [
    {"id": "R-001", "type": "question", "audience": "client", "severity": "medium", "category": "GP-01", "stage": "workshop-2",
     "source": "Roles", "finding": "HR Admin's access to applications is not stated.",
     "question": "Can HR Admin see every leave application?", "status": "resolved",
     "answer": "Yes, every application, read-only.", "raised": "2026-10-20", "resolved_in": "Workshop 2"},
    {"id": "R-002", "type": "question", "audience": "client", "severity": "high", "category": "GP-08", "stage": "workshop-2",
     "source": "FR-APP-002", "finding": "No stand-in approver is defined.",
     "question": "Who approves when the line manager is on leave?", "status": "open", "raised": "2026-10-20"}]}

NEW = {"title": "Export all applications to Excel", "request": "HR wants to export every leave application to Excel.",
       "asked_by": "HR manager, during UAT", "raised": "2026-12-03", "stage": "uat", "verdict": "new", "basis_version": "0.1",
       "cited": [{"ref": "screen my-applications", "section": "section 4.2",
                  "quote": "My Leave Applications. Lists the employee's own applications."}],
       "reasoning": "No export anywhere in v0.1; the list is the employee's own.",
       "why": "The signed document has no export: each employee sees their own applications on screen only.",
       "changes": ["An Export to Excel button for HR Admin", "A new list of every application, with filters"],
       "gap_pattern": "GP-04",
       "lines": [{"id": "L01", "item": "Excel export of all applications", "block": "BB-13", "count": 1, "note": "one export, 8 columns"},
                 {"id": "L02", "item": "List of every application", "block": "BB-06", "count": 1}],
       "assumptions": ["Same columns as the list", "Up to 5,000 rows"], "status": "raised"}
IN_SCOPE = {"title": "Cancel an approved application", "request": "Employees want to cancel leave that is already approved.",
            "asked_by": "Employee, during UAT", "raised": "2026-12-04", "stage": "uat", "verdict": "in-scope", "basis_version": "0.1",
            "cited": [{"ref": "FR-APP-003.1", "section": "section 3",
                       "quote": "System shall allow the employee to cancel a Pending or Approved application before the leave starts."}],
            "reasoning": "Signed in FR-APP-003.1.", "status": "raised"}
AMBIGUOUS = {"title": "Half-day leave", "request": "Can employees apply for half a day?", "asked_by": "HR manager",
             "raised": "2026-12-05", "verdict": "ambiguous", "basis_version": "0.1",
             "cited": [{"ref": "FR-APP-001.3", "quote": "System shall calculate Number of Days as the working days between From Date and To Date."}],
             "question": "Should an employee be able to apply for half a day of leave?", "gap_pattern": "GP-13",
             "severity": "high", "effort_impact": "medium", "status": "raised"}


@pytest.fixture(autouse=True)
def starter_knowledge(monkeypatch):
    """A test that does not name a knowledge folder gets the starter one, never the workspace's."""
    monkeypatch.setattr(cr_tool, "knowledge_dir", lambda: STARTER)


@pytest.fixture
def run(monkeypatch, capsys):
    def call(tool, *args):
        monkeypatch.setattr(sys, "argv", [f"{tool.__name__}.py", *map(str, args)])
        tool.main()
        return capsys.readouterr().out
    return call


def new_project(projects, issued=True, run=None):
    """The sample project with a register and a stand-in for its generated document, issued as v0.1 with project.py."""
    p = projects / "leave-request"
    for folder in ("docs", "reviews", "spec", "feedback", "output"):
        (p / folder).mkdir(parents=True)
    shutil.copy(support.EXAMPLE / "spec" / "app.yaml", p / "spec" / "app.yaml")
    (p / "register.json").write_text(json.dumps(REGISTER), encoding="utf-8")
    (p / "output" / f"{DOC}.docx").write_bytes(b"generated")
    (p / "output" / f"{DOC}.pdf").write_bytes(b"%PDF-1.4 generated")
    shutil.copy(p / "spec" / "app.yaml", p / "output" / "spec-v0.1.yaml")  # as the generator leaves it
    if issued:
        run(project_tool, "issue", "leave-request", "--date", "2026-11-10")
    return p


@pytest.fixture
def issued(temp_workspace, run):
    return new_project(temp_workspace / "projects", run=run)


@pytest.fixture
def unissued(temp_workspace):
    return new_project(temp_workspace / "projects", issued=False)


def refs(found):
    return [e["ref"] for _, e in found]


def write_log(project, *crs, platform="Joget DX"):
    log = {"project": "Leave Request System", "platform": platform,
           "crs": [{"id": f"CR-{n:03d}", **cr} for n, cr in enumerate(crs, 1)]}
    (project / "changes").mkdir(exist_ok=True)
    (project / "changes" / "crs.json").write_text(json.dumps(log), encoding="utf-8")
    return log


def knowledge_with(tmp_path, rates=None, calibration=None):
    """A copy of the starter knowledge base with some rates and calibration notes set."""
    kdir = tmp_path / "knowledge"
    shutil.copytree(STARTER, kdir)
    path = kdir / "building-blocks.md"
    text = path.read_text(encoding="utf-8")
    for block, rate in (rates or {}).items():
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if line.startswith(f"| {block} |"):
                cells = line.split("|")
                cells[4], cells[5] = f" {rate} ", " medium "
                lines[i] = "|".join(cells)
        text = "\n".join(lines) + "\n"
    if calibration is not None:
        text = text.replace("## Calibration notes\n\nNone yet.", "## Calibration notes\n\n" + calibration)
    path.write_text(text, encoding="utf-8")
    return kdir


# ====================================================================== what the client signed
def test_the_issued_version_is_the_basis(issued):
    basis = cr_tool.signed_basis(issued)
    assert basis["version"] == "0.1" and basis["issued"]["date"] == "2026-11-10"
    assert basis["source"] == "output/spec-v0.1.yaml" and basis["warnings"] == []


def test_a_request_finds_the_signed_requirement_that_covers_it(issued):
    basis, found = cr_tool.lookup(issued, "Can an employee cancel leave that was already approved, before it starts?")
    assert refs(found)[0] == "FR-APP-003.1", refs(found)
    best = found[0][1]
    assert best["kind"] == "requirement" and "cancel a Pending or Approved application" in best["text"]
    assert "FR-APP-003 Cancel Application" in best["where"]


@pytest.mark.parametrize("request_, kind, ref", [
    ("Link leave to the attendance system", "scope", "Scope: out of scope 2"),
    ("HR Admin should see every application", "decision", "R-001"),
    ("A stand-in approver while the line manager is on leave", "open item", "R-002"),
    ("Who may edit a rejected application and resubmit it?", "status rule", "status Rejected"),
])
def test_scope_lines_decisions_open_items_and_status_rules_are_found_too(issued, request_, kind, ref):
    _, found = cr_tool.lookup(issued, request_)
    assert any(e["kind"] == kind and e["ref"] == ref for _, e in found[:3]), [(s, e["kind"], e["ref"]) for s, e in found]


def test_a_screen_carries_its_section_number(issued):
    _, found = cr_tool.lookup(issued, "Leave Types maintenance screen entitlement")
    screens = [e for _, e in found if e["kind"] == "screen"]
    assert screens and screens[0]["ref"] == "screen leave-types" and screens[0]["where"].startswith("section ")


def test_later_changes_to_the_spec_are_not_what_was_signed(issued):
    spec = support.load_spec(issued)
    spec["project"]["version"] = "0.2"
    spec["requirements"].append({"id": "FR-APP-004", "title": "Export", "items": ["System shall export every application to Excel."]})
    support.write_spec(issued, spec)
    basis, found = cr_tool.lookup(issued, "Export every application to Excel")
    assert not any(r.startswith("FR-APP-004") for r in refs(found)), "v0.2 was never issued"
    assert basis["version"] == "0.1" and any("current spec is v0.2" in n for n in basis["notes"])


def test_with_nothing_issued_it_compares_with_the_current_spec_and_warns(unissued):
    basis, found = cr_tool.lookup(unissued, "Can an employee cancel leave that was already approved, before it starts?")
    assert basis["issued"] is None and basis["source"] == "spec/app.yaml"
    assert "Nothing has been issued to the client yet" in basis["warnings"][0]
    assert refs(found)[0] == "FR-APP-003.1"


def test_an_issued_version_without_its_snapshot_falls_back_with_a_warning(unissued):
    (unissued / "output" / "spec-v0.1.yaml").unlink()
    (unissued / "output" / "issued.json").write_text(json.dumps([{"version": "0.1", "date": "2026-11-10", "to": "SAMPLE", "files": []}]))
    basis = cr_tool.signed_basis(unissued)
    assert basis["source"] == "spec/app.yaml" and "snapshot of the issued v0.1" in basis["warnings"][0]


def test_a_version_never_issued_is_refused(issued):
    with pytest.raises(SystemExit, match="v0.9 was never issued"):
        cr_tool.signed_basis(issued, "0.9")


def test_scope_takes_a_list_of_requests_and_says_the_score_decides_nothing(issued, run, tmp_path):
    requests = tmp_path / "requests.txt"
    requests.write_text("- Cancel approved leave before it starts\n\n- Link leave to the attendance system\n", encoding="utf-8")
    out = run(cr_tool, "scope", issued, "--file", requests)
    assert "Checked against v0.1, issued to SAMPLE on 2026-11-10 (output/spec-v0.1.yaml)" in out
    assert "Request 1: Cancel approved leave before it starts" in out and "Request 2: Link leave to the attendance system" in out
    assert "FR-APP-003.1" in out and "Scope: out of scope 2" in out
    assert "it does not decide scope" in out


def test_scope_on_an_unissued_project_says_so_first(unissued, run):
    out = run(cr_tool, "scope", unissued, "Cancel approved leave")
    assert "not issued" in out.splitlines()[0] and "Warning: Nothing has been issued" in out


# ====================================================================== the CR log
def test_a_sound_log_checks_and_renders_an_internal_excel_file(issued, run):
    write_log(issued, NEW, IN_SCOPE, {**AMBIGUOUS, "register": ["R-002"]})
    out = run(cr_tool, "render", issued)
    assert "3 requests (1 new, 1 ambiguous, 1 in scope)" in out
    assert "CR-001  new       raised   Export all applications to Excel" in out
    assert "counted, not priced (2 lines)" in out, "the starter knowledge base has no rates"
    assert "no calibration note about change requests" in out
    path = issued / "changes" / "CR log (internal).xlsx"
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ["CR log", "Sizing", "Summary"]
    for ws in wb.worksheets:
        assert ws.oddHeader.center.text == cr_tool.INTERNAL_MARK
    log = list(wb["CR log"].iter_rows(values_only=True))
    assert [r[0] for r in log[1:]] == ["CR-001", "CR-002", "CR-003"]
    assert log[1][5] == "New" and "FR-APP-003.1" in log[2][6] and log[3][17] == "R-002"
    assert "Internal: not for the client" in out


@pytest.mark.parametrize("change, said", [
    ({"cited": []}, "new needs what the signed document says"),
    ({"why": ""}, "needs why"),
    ({"gap_pattern": "GP-99"}, "GP-99 is not in knowledge/gap-patterns.md"),
    ({"gap_pattern": "new"}, "needs gap_note"),
    ({"status": "quoted"}, "a quoted CR needs sold_md and sold_by"),
    ({"sold_md": 4}, "sold_md needs sold_by"),
    ({"register": ["R-404"]}, "R-404 is not in the register"),
    ({"verdict": "maybe"}, "verdict 'maybe'"),
    ({"why": "About 4 MD of work."}, "why mentions 'MD'"),
    ({"changes": ["Two BB-06 lists"]}, "changes mentions 'BB-06'"),
    ({"weeks": [3, 1]}, "weeks is a number or [low, high]"),
    ({"assumptions": []}, "assumptions are needed with lines"),
    ({"lines": [{"id": "L01", "item": "x", "block": "BB-77", "count": 1}]}, "BB-77 is not a building block"),
    ({"colour": "red"}, "unknown field colour"),
])
def test_each_mistake_in_the_log_is_named(issued, change, said):
    log = write_log(issued, {**NEW, **change})
    errors, _, _ = cr_tool.check_log(log, issued)
    assert any(said in e for e in errors), errors


def test_an_ambiguous_cr_waits_for_the_client_and_is_never_quoted(issued):
    errors, warnings, _ = cr_tool.check_log(write_log(issued, {**AMBIGUOUS, "status": "quoted"}), issued)
    assert any("stays raised until the client answers" in e for e in errors)
    _, warnings, _ = cr_tool.check_log(write_log(issued, AMBIGUOUS), issued)
    assert any("not in the register yet" in w for w in warnings)


def test_a_cr_is_sized_with_the_knowledge_bases_rates_and_its_calibration_note(issued, run, monkeypatch, tmp_path):
    note = "- Small CRs under 5 MD took 1.5 times the building-block rate: regression testing and deployment."
    kdir = knowledge_with(tmp_path, {"BB-13": "1–2", "BB-06": "2–3"}, note)
    monkeypatch.setattr(cr_tool, "knowledge_dir", lambda: kdir)
    write_log(issued, NEW)
    out = run(cr_tool, "check", issued)
    assert "3 – 5 MD, low confidence" in out
    assert "Small CRs under 5 MD took 1.5 times" in out


def test_a_partly_priced_cr_is_never_given_a_total(issued, monkeypatch, tmp_path):
    kdir = knowledge_with(tmp_path, {"BB-13": "1–2"})
    monkeypatch.setattr(cr_tool, "knowledge_dir", lambda: kdir)
    _, _, sizing = cr_tool.check_log(write_log(issued, NEW), issued)
    assert cr_tool.sized_text(sizing["CR-001"]).startswith("priced so far 1 – 2 MD, 1 of 2 lines not priced")


def test_add_gives_the_ids_and_refuses_a_bad_cr(issued, run, tmp_path):
    batch = tmp_path / "crs.json"
    batch.write_text(json.dumps([{**IN_SCOPE, "id": "CR-042"}, NEW]), encoding="utf-8")
    out = run(cr_tool, "add", issued, "--file", batch)
    assert "CR-001 (in-scope)" in out and "CR-002 (new)" in out
    batch.write_text(json.dumps({**NEW, "cited": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        run(cr_tool, "add", issued, "--file", batch)
    assert len(json.loads((issued / "changes" / "crs.json").read_text(encoding="utf-8"))["crs"]) == 2


def test_the_sold_figure_is_only_what_the_project_lead_enters(issued, run):
    write_log(issued, NEW)
    with pytest.raises(SystemExit):
        run(cr_tool, "update", issued, "CR-001", "--set", "status=quoted")
    with pytest.raises(SystemExit):
        run(cr_tool, "update", issued, "CR-001", "--set", "sold_md=4")
    out = run(cr_tool, "update", issued, "CR-001", "--set", "sold_md=4", "--set", "sold_by=Project lead", "--set", "status=quoted",
              "--set", "weeks=1-2")
    assert "CR-001 sold_md: (empty) -> 4" in out
    cr = json.loads((issued / "changes" / "crs.json").read_text(encoding="utf-8"))["crs"][0]
    assert (cr["status"], cr["sold_md"], cr["sold_by"], cr["weeks"]) == ("quoted", 4, "Project lead", [1.0, 2.0])


# ====================================================================== the client's note
@pytest.fixture
def note_text(issued, run, monkeypatch, tmp_path):
    """The client's note for a New CR that was sized with real rates, as text."""
    def make(**change):
        kdir = knowledge_with(tmp_path / f"k{len(list((tmp_path).glob('k*')))}", {"BB-13": "1–2", "BB-06": "2–3"})
        monkeypatch.setattr(cr_tool, "knowledge_dir", lambda: kdir)
        write_log(issued, {**NEW, **change})
        out = run(cr_tool, "note", issued, "CR-001")
        path = issued / "changes" / "CR-001 Export all applications to Excel - change request note.docx"
        assert path.exists() and str(path) in out
        doc = Document(str(path))
        headers = " ".join(p.text for s in doc.sections for p in s.header.paragraphs)
        return support.all_text(doc) + "\n" + headers, out
    return make


def test_the_client_note_says_what_was_asked_why_it_is_a_change_and_what_it_changes(note_text):
    text, out = note_text()
    for said in ("Change request", "Export all applications to Excel", "CR-001", "HR wants to export every leave application to Excel.",
                 "HR manager, during UAT", "3 December 2026", "Why this is a change", NEW["why"],
                 "The requirements document v0.1, issued on 10 November 2026, says:", "screen my-applications",
                 "My Leave Applications. Lists the employee's own applications.", "What it would change",
                 "An Export to Excel button for HR Admin", "Your decision", "Quotation to follow"):
        assert said in text, said
    assert "Quotation to follow" in out and "has not entered the sold figure" in out


def test_the_client_note_holds_nothing_internal(note_text):
    text, _ = note_text(confidence="low", confidence_reason="First export on this platform", notes="Watch the row limit")
    for internal in ("BB-", "OW-", "GP-04", "MD", "manday", "confidence", "Confidence", "1 – 2", "2 – 3", "3 – 5",
                     NEW["reasoning"], "Same columns as the list", "one export, 8 columns", "Watch the row limit",
                     "First export", "Internal", "uat", "L01"):
        assert internal not in text, internal


def test_the_price_shows_once_the_project_lead_has_entered_it(note_text):
    text, _ = note_text(status="quoted", sold_md=4, sold_by="Project lead", price="SGD 4,000", weeks=[1, 2])
    assert "SGD 4,000" in text and "Quotation to follow" not in text and "1 – 2 weeks" in text
    text, _ = note_text(status="quoted", sold_md=3, sold_by="Project lead")
    assert "3 mandays" in text and "Quotation to follow" not in text


def test_an_in_scope_request_gets_a_short_internal_note_and_no_document(issued, run):
    write_log(issued, IN_SCOPE)
    out = run(cr_tool, "note", issued, "CR-001")
    assert "in scope (internal: not for the client)" in out and "FR-APP-003.1" in out and "No client note" in out
    assert not list((issued / "changes").glob("*.docx"))


# ====================================================================== an ambiguous request
def test_an_ambiguous_request_becomes_a_client_question_in_the_register(issued, run):
    write_log(issued, AMBIGUOUS)
    out = run(cr_tool, "ask", issued, "CR-001", "--check")
    assert "would be added to the register as R-003" in out
    assert len(json.loads((issued / "register.json").read_text(encoding="utf-8"))["items"]) == 2
    out = run(cr_tool, "ask", issued, "CR-001")
    assert "as R-003, and linked it to CR-001" in out
    item = json.loads((issued / "register.json").read_text(encoding="utf-8"))["items"][-1]
    assert (item["id"], item["type"], item["audience"], item["severity"], item["category"], item["stage"], item["status"]) == (
        "R-003", "question", "client", "high", "GP-13", "development", "open")
    assert item["question"] == AMBIGUOUS["question"] and item["source"].startswith("CR-001")
    assert json.loads((issued / "changes" / "crs.json").read_text(encoding="utf-8"))["crs"][0]["register"] == ["R-003"]
    with pytest.raises(SystemExit, match="already in the register as R-003"):
        run(cr_tool, "ask", issued, "CR-001")
    with pytest.raises(SystemExit, match="is Ambiguous"):
        run(cr_tool, "note", issued, "CR-001")


def test_only_an_ambiguous_request_is_asked(issued, run):
    write_log(issued, NEW)
    with pytest.raises(SystemExit, match="only an Ambiguous CR"):
        run(cr_tool, "ask", issued, "CR-001")



def test_ask_writes_the_register_and_the_log_together_or_neither(issued, run, monkeypatch):
    """The register was written, then the log: when the log could not be written, the question was in the
    register with no link from the CR, and asking again added it twice."""
    write_log(issued, AMBIGUOUS)
    before = (issued / "register.json").read_bytes()

    def locked(project, log):
        sys.exit("Cannot write crs.json: close it")

    monkeypatch.setattr(cr_tool, "save_log", locked)
    with pytest.raises(SystemExit, match="Cannot write crs.json"):
        run(cr_tool, "ask", issued, "CR-001")
    assert (issued / "register.json").read_bytes() == before, "the register put back"


def test_the_request_in_the_client_note_is_checked_for_internal_words(issued):
    cr = {**NEW, "request": "HR wants an export, about 4 mandays"}
    write_log(issued, cr)
    errors = cr_tool.check_log(cr_tool.load_log(issued), issued)[0]
    assert any("request mentions 'mandays'" in e for e in errors), errors
