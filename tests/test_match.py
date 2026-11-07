"""tools/project.py match and hold: which project a file in the inbox belongs to, and the note of a file left there.

Two made-up projects for the same made-up client, both from the sample spec: the sample itself, and a copy
turned into an expense claims system (other name, roles and screens; the same statuses and some of the same
field labels, as two projects of one client often have). Every test runs on a temp workspace.
"""
import json
import sys

import pytest
from docx import Document

import support

import project as project_tool

LEAVE_BUILD = "a" * 64
CLAIMS_BUILD = "b" * 64


def leave_register():
    items = [{"id": f"R-{n:03d}", "question": f"Placeholder question number {n} about public holidays"} for n in range(1, 41)]
    items[30]["question"] = "Should a rejected application go back to the employee for editing and resubmission?"
    items[34]["question"] = "How many days ahead must annual leave be applied for?"
    items[2]["question"] = "Who maintains the list of leave types?"
    return {"project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "items": items}


def claims_spec():
    spec = support.load_spec(support.EXAMPLE)
    spec["project"].update(name="Expense Claims System", short_name="ECS")
    for role, name in zip(spec["roles"], ["Claimant", "Finance Officer", "Finance Approver"]):
        role["name"] = name
        role["user"] = {"Claimant": "Siti Rahman", "Finance Officer": "Kumar Rajan"}.get(name, "")
    for screen in spec["screens"]:
        screen["id"] = "claim-" + screen["id"]
        for key in ("title", "menu"):
            if screen.get(key):
                screen[key] = screen[key].replace("Leave Applications", "Expense Claims").replace("Leave Application", "Expense Claim").replace("Leave", "Claim")
    spec["requirements"] = [{"id": "FR-CLM-001", "title": "Submit a Claim", "items": ["System shall require a receipt for every claim."]}]
    return spec


def make(projects, slug, spec, register, build, folder=None):
    p = (folder or projects) / slug
    support.write_spec(p, spec)
    (p / "register.json").write_text(json.dumps(register), encoding="utf-8")
    if build:
        (p / "mockup" / "versions" / "v0.1").mkdir(parents=True)
        (p / "mockup" / "versions" / "v0.1" / ".built-from").write_text(build[::-1], encoding="utf-8")
        (p / "mockup" / ".built-from").write_text(build, encoding="utf-8")
    return p


@pytest.fixture
def two(temp_workspace):
    """Two active projects of one client, an inbox, and nothing else."""
    projects = temp_workspace / "projects"
    leave_spec = support.load_spec(support.EXAMPLE)
    leave_spec["project"]["version"] = "0.2"
    leave = make(projects, "leave-request", leave_spec, leave_register(), LEAVE_BUILD)
    claims = make(projects, "expense-claims", claims_spec(), {"project": "Expense Claims System", "client": "Sample Client Sdn. Bhd.", "items": [
        {"id": "R-001", "question": "Is a receipt required for claims under 50?"},
        {"id": "R-003", "question": "Can a finance officer return a claim to the claimant for a missing receipt?"},
    ]}, CLAIMS_BUILD)
    (claims / "uat").mkdir()
    (claims / "uat" / "2026-11-06 uat scripts v0.1.json").write_text(json.dumps({"cases": [
        {"id": "UAT-001", "title": "Submit a claim with its receipt"}, {"id": "UAT-002", "title": "Finance officer returns a claim"}]}), encoding="utf-8")
    (leave / "uat").mkdir()
    (leave / "uat" / "2026-11-06 uat scripts v0.1.json").write_text(json.dumps({"cases": [
        {"id": "UAT-001", "title": "Apply for annual leave and see it pending"}]}), encoding="utf-8")
    inbox = temp_workspace / "inbox"
    inbox.mkdir()
    return inbox


@pytest.fixture
def run(monkeypatch, capsys):
    def call(*args):
        monkeypatch.setattr(sys, "argv", ["project.py", *map(str, args)])
        project_tool.main()
        return capsys.readouterr().out
    return call


def drop(inbox, name, content):
    f = inbox / name
    if isinstance(content, (list, dict)):
        content = json.dumps(content)
    f.write_text(content, encoding="utf-8")
    return f


def scores(m):
    return {r["slug"]: r["score"] for r in m["projects"]}


def test_a_comments_export_matches_the_mockup_it_was_made_on(two, run):
    f = drop(two, "feedback-2026-11-05.json", [
        {"screen": "my-applications", "element": "list", "text": "Add a column for the approver", "version": "0.2", "build": LEAVE_BUILD},
        {"screen": "new-application", "element": "field:reason", "text": "Make the reason optional", "version": "0.2"}])
    m = project_tool.match_file(f)
    assert m["verdict"] == "clear" and m["best"] == "leave-request"
    assert m["kind"] == "mock-up comments export"
    assert m["summary"] == "comments export from Leave Request System mock-up v0.2 → leave-request"
    assert scores(m)["leave-request"] >= 100 and scores(m).get("expense-claims", 0) <= 0
    out = run("match", f)
    assert "Verdict: clear: it belongs to leave-request" in out and "comments made on this project's mock-up (v0.2)" in out


def test_an_earlier_mockup_version_is_recognised_too(two):
    f = drop(two, "feedback-old.json", [{"screen": "claim-my-applications", "text": "Rename the menu", "version": "0.1", "build": CLAIMS_BUILD[::-1]}])
    m = project_tool.match_file(f)
    assert (m["verdict"], m["best"]) == ("clear", "expense-claims")
    assert "(v0.1)" in m["projects"][0]["evidence"][0]["what"]


def test_screens_of_the_other_project_count_against_it(two):
    f = drop(two, "feedback-x.json", [{"screen": "claim-my-applications", "text": "x"}, {"screen": "claim-new-application", "text": "y"}])
    m = project_tool.match_file(f)
    assert m["best"] == "expense-claims" and m["verdict"] in ("clear", "likely")
    assert scores(m).get("leave-request", 0) < 0


def test_notes_naming_one_projects_roles_and_screens_point_to_it(two):
    f = drop(two, "workshop notes.txt", "Workshop with Sample Client Sdn. Bhd.\nThe Line Manager and HR Admin walked "
             "through My Leave Applications and the Leave Application Details screen.\nAgreed: Number of Days stays read-only.")
    m = project_tool.match_file(f)
    assert m["best"] == "leave-request" and m["verdict"] in ("clear", "likely")
    what = " ".join(e["what"] for e in m["projects"][0]["evidence"])
    assert '"Line Manager"' in what and '"My Leave Applications"' in what
    assert "client" in what  # listed, though it says nothing about which project


def test_the_client_name_alone_never_decides(two, run):
    f = drop(two, "minutes.txt", "Meeting with Sample Client Sdn. Bhd. (SAMPLE) about the next steps and the invoice.")
    m = project_tool.match_file(f)
    assert m["verdict"] == "unknown" and m["best"] is None and m["summary"] == ""
    assert scores(m) == {"expense-claims": 5, "leave-request": 5}
    assert "on its own it does not say which" in m["projects"][0]["evidence"][0]["what"]
    assert "Verdict: unknown" in run("match", f)


def test_register_ids_with_their_topic_weigh_heavily(two):
    f = drop(two, "answers.txt", "Answers from the client\nR-031: yes, a rejected application goes back to the employee for editing.\n"
             "R-035: annual leave must be applied for 3 days ahead.")
    m = project_tool.match_file(f)
    assert (m["verdict"], m["best"]) == ("clear", "leave-request")
    assert scores(m)["leave-request"] >= 50 and scores(m).get("expense-claims", 0) == 0
    assert m["projects"][0]["evidence"][0]["what"].startswith("R-031 (register item) with its topic")


def test_an_id_both_projects_have_goes_to_the_one_whose_topic_matches(two):
    f = drop(two, "reply.txt", "R-003 - a finance officer may return a claim when the receipt is missing.")
    m = project_tool.match_file(f)
    assert m["best"] == "expense-claims" and scores(m).get("leave-request", 0) == 0
    assert "other projects have that id too" in m["projects"][0]["evidence"][0]["what"]


def test_an_id_without_its_topic_counts_for_little(two):
    f = drop(two, "list.txt", "R-038 R-039 R-040 see the attached spreadsheet")
    m = project_tool.match_file(f)
    assert scores(m)["leave-request"] == 15 and m["verdict"] == "likely"


def test_uat_ids_match_the_project_whose_scripts_they_are(two):
    f = drop(two, "UAT results.csv", "Case,Title,Result\nUAT-001,Submit a claim with its receipt,Fail\nUAT-002,Finance officer returns a claim,Pass\n")
    m = project_tool.match_file(f)
    assert (m["verdict"], m["best"]) == ("clear", "expense-claims")


def test_a_word_document_is_read_and_text_from_an_earlier_extraction_is_used(two, tmp_path):
    doc = Document()
    doc.add_paragraph("Expense Claims System (ECS): comments on the Finance Approver screens")
    doc.save(two / "comments.docx")
    m = project_tool.match_file(two / "comments.docx")
    assert m["best"] == "expense-claims" and m["verdict"] == "clear"
    text = tmp_path / "text.md"
    text.write_text("The Leave Request System and the LRS short name", encoding="utf-8")
    m = project_tool.match_file(two / "comments.docx", text)
    assert m["best"] == "leave-request"


def test_the_file_name_can_name_the_project(two):
    f = drop(two, "ECS kick-off.txt", "nothing inside says which")
    m = project_tool.match_file(f)
    assert m["best"] == "expense-claims" and m["verdict"] == "likely"


def test_archived_projects_are_listed_apart_and_never_a_target(two, temp_workspace, run):
    spec = support.load_spec(support.EXAMPLE)
    spec["project"].update(name="Attendance Tracking System", short_name="ATS")
    for role, name in zip(spec["roles"], ["Shift Supervisor", "Plant Manager", "Timekeeper"]):
        role["name"] = name
    make(None, "attendance", spec, {"project": "Attendance Tracking System", "items": []}, None, temp_workspace / "projects" / "_archive")
    f = drop(two, "attendance notes.txt", "Attendance Tracking System: the Shift Supervisor and the Plant Manager want a new report.")
    m = project_tool.match_file(f)
    assert m["verdict"] == "unknown" and m["best"] is None
    assert "attendance" not in scores(m)
    assert [r["slug"] for r in m["archived"]] == ["attendance"]
    out = run("match", f)
    assert "Archived, not a place to file it unless restored first: attendance" in out
    assert json.loads(run("match", f, "--json"))["archived"][0]["where"] == "projects/_archive/attendance"


def test_a_project_close_to_an_archived_one_is_not_clear(two, temp_workspace):
    archive = temp_workspace / "projects" / "_archive"
    make(None, "leave-request-phase-1", support.load_spec(support.EXAMPLE), {"project": "Leave Request System", "items": []}, None, archive)
    f = drop(two, "notes.txt", "Leave Request System: the Line Manager and HR Admin on My Leave Applications.")
    m = project_tool.match_file(f)
    assert m["best"] == "leave-request" and m["verdict"] == "likely" and m["archived"]


def test_hold_writes_a_note_and_filing_removes_it(two, run):
    f = drop(two, "minutes.txt", "Meeting with Sample Client.")
    other = drop(two, "other.txt", "x")
    out = run("hold", f, "--reason", "not sure which project: leave-request or expense-claims")
    assert "Left minutes.txt where it is" in out
    run("hold", other, "--reason", "waiting for the BA")
    notes = json.loads((two / ".notes.json").read_text(encoding="utf-8"))
    assert notes["minutes.txt"]["reason"] == "not sure which project: leave-request or expense-claims" and notes["minutes.txt"]["date"]
    assert project_tool.match_file(f)["note"]["reason"].startswith("not sure")
    run("file", "leave-request", f, "--kind", "client meeting minutes", "--date", "2026-11-05")
    assert list(json.loads((two / ".notes.json").read_text(encoding="utf-8"))) == ["other.txt"]
    other.unlink()  # handled some other way (a comments export merged into feedback/): its note goes with the next write
    project_tool.drop_note(other)
    assert not (two / ".notes.json").exists()


def test_no_active_project_means_unknown(temp_workspace):
    (temp_workspace / "inbox").mkdir()
    f = drop(temp_workspace / "inbox", "brief.txt", "A new system for a new client")
    m = project_tool.match_file(f)
    assert (m["verdict"], m["best"], m["projects"]) == ("unknown", None, [])


def test_words_on_every_mockup_never_make_a_guess(two):
    """Notes with "User", "Location", "Summary" and "Details" in them made an unrelated project the best guess:
    single words that common say nothing about which project a file is for."""
    spec = support.load_spec(support.EXAMPLE)
    spec["project"].update(name="Fleet Inspection System", short_name="FIS", client="Another Client Bhd.")
    spec["screens"][0]["title"] = "User"
    spec["screens"][1]["title"] = "Summary"
    spec["screens"][0].setdefault("fields", []).extend([{"id": "loc", "label": "Location"}, {"id": "det", "label": "Details"}])
    make(two.parent / "projects", "fleet-inspection", spec, {"project": "Fleet Inspection System", "items": []}, None)
    f = drop(two, "minutes.txt", "The user opens the Location screen and sees the Summary and the Details.")
    m = project_tool.match_file(f)
    assert m["verdict"] == "unknown" and m["best"] is None
    assert "fleet-inspection" not in scores(m)


def test_a_distinctive_word_of_an_archived_name_is_found_through_hyphens(two, temp_workspace):
    """An inbox file "Zeta EPASS" did not find the archived "Acme E-PASS System": the file name had to hold every
    word of the name, and the hyphen split "E-PASS" in two."""
    spec = support.load_spec(support.EXAMPLE)
    spec["project"].update(name="Acme E-PASS System", short_name="", client="Made-up Motors Sdn. Bhd.")
    make(None, "e-pass", spec, {"project": "Acme E-PASS System", "items": []}, None, temp_workspace / "projects" / "_archive")
    f = drop(two, "Zeta EPASS.txt", "Minutes of the kick-off meeting.")
    m = project_tool.match_file(f)
    assert [r["slug"] for r in m["archived"]] == ["e-pass"]
    assert "the file name has a word of its system name: epass" in m["archived"][0]["evidence"][0]["what"]
    assert m["verdict"] == "unknown"
    m = project_tool.match_file(drop(two, "notes.txt", "Notes on the leave rollout: who signs off."))
    assert "a word of its system name: leave" in " ".join(e["what"] for e in m["projects"][0]["evidence"])
