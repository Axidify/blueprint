"""tools/workshop.py: what a workshop has to settle, the checks on an agenda, and the two documents.

Projects are made in temp folders from the made-up sample; the gap patterns come from the starter knowledge
base in templates/ or from a file the test writes. None reads knowledge/ in the app folder, which is a link
into the workspace.
"""
import copy
import json
import sys

import pytest
from docx import Document

import support

import workshop

STARTER = support.ROOT / "templates" / "knowledge"

REGISTER = {"project": "Leave Request System", "items": [
    {"id": "R-001", "type": "question", "audience": "client", "severity": "high", "status": "open",
     "question": "Who approves when the line manager is on leave?", "raised": "2026-01-05"},
    {"id": "R-002", "type": "question", "audience": "client", "severity": "medium", "status": "asked",
     "question": "Which columns does HR need in the export?", "raised": "2026-01-05"},
    {"id": "R-003", "type": "question", "audience": "client", "severity": "high", "status": "open",
     "question": "How long are applications kept?", "raised": "2026-01-06"},
    {"id": "R-004", "type": "question", "audience": "client", "severity": "low", "status": "resolved",
     "question": "Is medical leave a leave type?", "raised": "2026-01-06"},
    {"id": "R-005", "type": "fix", "audience": "internal", "severity": "high", "status": "open",
     "finding": "The access matrix misses HR Admin.", "raised": "2026-01-06"}]}

AGENDA = {
    "project": "Leave Request System",
    "workshop": "Workshop 2: mock-up review",
    "date": "2026-02-10",
    "duration_minutes": 60,
    "goal": "Agree the approval rules so the requirements document can go for sign-off.",
    "attendees": [{"role": "Business owner", "name": "", "needed_for": "the approval rules"}],
    "bring": ["A sample of the current leave form"],
    "sections": [
        {"title": "Approval", "minutes": 30, "show": ["review-application"], "items": [
            {"ref": "R-001", "question": "Who approves when the line manager is on leave?",
             "options": ["The manager's manager", "A named delegate"],
             "why": "Without a stand-in, applications wait until the manager is back.",
             "recommendation": "A named delegate, set by the manager.", "gap_pattern": "GP-08", "effort_impact": "medium"}]},
        {"title": "Reports", "minutes": 20, "items": [
            {"ref": "R-002", "question": "Which columns does HR need in the export?", "why": "Each column is a rule to build."}]}],
    "parked": [{"ref": "R-003", "question": "How long are applications kept?", "reason": "Needs the records manager, who is not attending."}],
    "after": ["We update the mock-up and send the requirements document within five working days."],
}


@pytest.fixture(autouse=True)
def starter_knowledge(monkeypatch):
    """A test that does not name a knowledge folder gets the starter one, never the workspace's."""
    monkeypatch.setattr(workshop, "knowledge_dir", lambda: STARTER)


@pytest.fixture
def project(tmp_path):
    folder = support.make_project(tmp_path / "leave-request")
    (folder / "register.json").write_text(json.dumps(REGISTER), encoding="utf-8")
    return folder


def write_agenda(project, agenda=AGENDA, name="2026-02-10 workshop 2.json"):
    (project / "workshops").mkdir(exist_ok=True)
    path = project / "workshops" / name
    path.write_text(json.dumps(agenda), encoding="utf-8")
    return path


def agenda_with(**keys):
    out = copy.deepcopy(AGENDA)
    out.update(keys)
    return out


@pytest.fixture
def run(monkeypatch, capsys):
    def call(*args):
        monkeypatch.setattr(sys, "argv", ["workshop.py", *map(str, args)])
        workshop.main()
        return capsys.readouterr().out

    return call


# ====================================================================== what is still open
def test_open_client_questions_come_high_first_and_leave_out_closed_and_internal_ones():
    assert [it["id"] for it in workshop.open_client_items(REGISTER["items"])] == ["R-001", "R-003", "R-002"]


def test_a_project_without_a_spec_has_no_spec_gaps():
    assert workshop.spec_gaps(None) == []


def test_the_sample_spec_only_lacks_its_notifications():
    assert workshop.spec_gaps(support.load_spec(support.EXAMPLE)) == [("Notifications", "no e-mail or notification is listed", "GP-14")]


def without_rule(spec):
    del spec["statuses"][1]["cancel"]


def without_failure(spec):
    spec["integrations"][0]["on_failure"] = ""


def without_formula(spec):
    del spec["screens"][1]["stats"][3]["formula"]


def without_out_of_scope(spec):
    spec["scope"]["out_of_scope"] = []


def without_data_scope(spec):
    del spec["roles"][0]["scope"]


@pytest.mark.parametrize("change, topic, detail, pattern", [
    (without_rule, "Status rules", "is not set for: Pending Approval", "GP-02"),
    (without_failure, "Integrations", "is not set for: Active Directory", "GP-10"),
    (without_formula, "Figures", "no formula for: Leave balance (days) (", "GP-03"),
    (lambda spec: spec.pop("scope"), "Scope", "nothing says what is in scope", ""),
    (without_out_of_scope, "Scope", "nothing listed as out of scope", ""),
    (lambda spec: spec.pop("nfr"), "Non-functional requirements", "none recorded", "GP-12"),
    (without_data_scope, "Roles", "no data scope (what they see) for: Employee", "GP-01"),
])
def test_each_thing_a_spec_leaves_open_is_named_with_its_gap_pattern(change, topic, detail, pattern):
    spec = support.load_spec(support.EXAMPLE)
    change(spec)
    found = [g for g in workshop.spec_gaps(spec) if g[0] == topic]
    assert len(found) == 1 and detail in found[0][1] and found[0][2] == pattern


def test_notification_wording_still_to_confirm_and_screens_without_a_requirement_are_named():
    gaps = workshop.spec_gaps(support.load_spec(support.WIDE))
    assert ("Notifications", "the wording is to be confirmed for: Booking approved or rejected", "GP-14") in gaps
    loose = [g for g in gaps if g[0] == "Requirements"]
    assert len(loose) == 1 and loose[0][1].startswith("no requirement refers to: ")
    assert "Approvals" not in loose[0][1], "a screen a requirement group lists is not reported"


# ====================================================================== gap patterns
def test_the_starter_gap_patterns_are_read_with_their_questions():
    patterns = workshop.gap_patterns(STARTER)
    assert [p["id"] for p in patterns][:3] == ["GP-01", "GP-02", "GP-03"] and len(patterns) >= 10
    first = patterns[0]
    assert first["title"] == "Unidentified viewers and read-only stakeholders"
    assert first["evidence"] == "none" and first["questions"] == 4, "a question on two lines counts once"


def test_gap_patterns_are_read_whichever_way_they_are_written(tmp_path):
    (tmp_path / "gap-patterns.md").write_text("""# Gap patterns
Is this a question? It is before the first pattern, so it is not counted.

## GP-01 Viewers
**What goes wrong:** Who else needs to see it? Nobody asked.
**Evidence:** Cost: two projects, a new role after go-live.
**Workshop questions:**
- Who needs to see the data?
- Does anyone need a
  different scope?
**Document check:** Is every role in the access matrix?

## GP-02 Corrections
**Evidence:** Review: found in one document review.
**Workshop questions:** Who can change it after approval? Can it be withdrawn? What stays for audit?

## GP-03 Calculations
**Evidence:** Came back as a CR of 6 MD on one project.
**Workshop questions:**
- What is the formula?

## GP-04 Reports
**Evidence:** Seen in two requirement reviews.

## GP-05 Columns
**Evidence:** none yet.
""", encoding="utf-8")
    assert workshop.gap_patterns(tmp_path) == [
        {"id": "GP-01", "title": "Viewers", "evidence": "cost", "questions": 2},
        {"id": "GP-02", "title": "Corrections", "evidence": "review", "questions": 3},
        {"id": "GP-03", "title": "Calculations", "evidence": "cost", "questions": 1},
        {"id": "GP-04", "title": "Reports", "evidence": "review", "questions": 0},
        {"id": "GP-05", "title": "Columns", "evidence": "none", "questions": 0}]


def test_no_gap_patterns_file_is_not_an_error(tmp_path):
    assert workshop.gap_patterns(tmp_path) == []


# ====================================================================== checking an agenda
def test_a_sound_agenda_has_no_mistakes(project):
    assert workshop.check(AGENDA, project) == []


def section(ref="R-001", minutes=30, show=None, question="Who approves?"):
    return {"title": "Approval", "minutes": minutes, "show": show or [], "items": [{"ref": ref, "question": question}]}


PARKED = [{"ref": "R-003", "reason": "Needs the records manager."}]


@pytest.mark.parametrize("keys, said", [
    ({"goal": ""}, "missing goal"),
    ({"date": None}, "missing date"),
    ({"sections": []}, "missing sections"),
    ({"duration_minutes": "two hours"}, "duration_minutes must be a number of minutes, for example 120"),
    ({"sections": [section(ref="R-004")], "parked": PARKED + [{"ref": "R-001", "reason": "Later."}]}, "R-004 is already resolved"),
    ({"sections": [section(ref="R-005")], "parked": PARKED + [{"ref": "R-001", "reason": "Later."}]},
     "R-005 is an internal item: it is your team's to fix, not a question for the client"),
    ({"sections": [section(ref="R-099"), section()]}, "R-099 is not in the register: add the question there first"),
    ({"sections": [section(show=["no-such-screen"])]}, "'no-such-screen' is not a screen of the mock-up"),
    ({"sections": [section(minutes=45), section(ref="R-002", minutes=40)]},
     "the sections add up to 85 minutes, the workshop is 60: move items to parked or shorten sections"),
    ({"sections": [section(minutes=0)]}, "minutes must be a number above 0"),
    ({"sections": [section(question=" ")]}, "section 1 (Approval), item 1: needs a question"),
    ({"sections": [{"title": "Empty", "minutes": 10, "items": []}, section()]}, "section 1 (Empty): needs a title and at least one item"),
    ({"sections": [section(), section()]}, "R-001 is already in section 1 (Approval)"),
    ({"parked": []}, "R-003 (high) is open and not on the agenda: add it to a section, or to parked with the reason it waits"),
    ({"parked": [{"ref": "R-003"}]}, "parked item 1: needs a ref or a question, and the reason it waits"),
    ({"parked": PARKED + [{"ref": "R-001", "reason": "Later."}]}, "R-001 is both on the agenda and parked"),
])
def test_each_mistake_in_an_agenda_is_named(project, keys, said):
    errors = workshop.check(agenda_with(**keys), project)
    assert any(said in e for e in errors), errors


def test_a_project_without_a_spec_or_register_can_still_have_an_agenda(tmp_path):
    """Workshop 1 often comes before either exists: questions then have no reference and screens are not checked."""
    agenda = agenda_with(sections=[{"title": "Roles", "minutes": 20, "show": ["a-sketch"],
                                    "items": [{"question": "Besides daily users, who needs to see the data?"}]}], parked=[])
    assert workshop.check(agenda, tmp_path) == []


# ====================================================================== the two documents
@pytest.fixture
def pack(project):
    path = write_agenda(project)
    client, notes = workshop.render(AGENDA, project, path)
    return client, notes, support.all_text(Document(str(client))), support.all_text(Document(str(notes)))


def test_the_pack_is_two_documents_next_to_the_agenda(project, pack):
    client, notes, _, _ = pack
    assert client == project / "workshops" / "2026-02-10 workshop 2 - agenda.docx" and client.exists()
    assert notes == project / "workshops" / "2026-02-10 workshop 2 - facilitator notes (internal).docx" and notes.exists()


def test_the_clients_agenda_has_the_questions_and_room_for_each_decision(pack):
    client, _, text, _ = pack
    for said in ("Workshop agenda", "Workshop 2: mock-up review", "Leave Request System", AGENDA["goal"], "Business owner",
                 "A sample of the current leave form", "1  Approval", "2  Reports", "Who approves when the line manager is on leave?",
                 "Options: The manager's manager  /  A named delegate", "Which columns does HR need in the export?",
                 "30 minutes", "On screen: ", "After the session", AGENDA["after"][0]):
        assert said in text, said
    questions = [t for t in Document(str(client)).tables if [c.text for c in t.rows[0].cells] == ["No", "Question", "Decision"]]
    assert len(questions) == 2
    assert [c.text for c in questions[0].rows[1].cells][0::2] == ["1.1", ""], "the decision is left empty to write in"


def test_nothing_internal_reaches_the_clients_agenda(pack):
    _, _, text, _ = pack
    for internal in ("Without a stand-in", "A named delegate, set by the manager", "We recommend", "Why:", "GP-08", "effort impact",
                     "severity", "R-001", "R-003", "How long are applications kept?", "records manager", "Left for later",
                     "Notes for you", workshop.INTERNAL_MARK, "Facilitator notes", "0:00", "spare"):
        assert internal not in text, internal


def test_the_facilitator_notes_add_the_reasons_and_what_waits(pack):
    _, notes, _, text = pack
    for said in ("Facilitator notes", workshop.INTERNAL_MARK, "Who approves when the line manager is on leave?",
                 "Why: Without a stand-in, applications wait until the manager is back.",
                 "We recommend: A named delegate, set by the manager.", "R-001 · GP-08 · high severity · medium effort impact",
                 "R-002 · medium severity", "30 minutes  ·  0:00 to 0:30", "20 minutes  ·  0:30 to 0:50",
                 "Planned: 50 of 60 minutes, 10 spare", "Left for later", "How long are applications kept?",
                 "Needs the records manager, who is not attending."):
        assert said in text, said
    headers = "".join(p.text for s in Document(str(notes)).sections for p in s.header.paragraphs) + "".join(
        c.text for s in Document(str(notes)).sections for t in s.header.tables for r in t.rows for c in r.cells)
    assert workshop.INTERNAL_MARK in headers, "every page of the notes says they are internal"


def test_neither_document_holds_mandays_or_cost(pack):
    _, _, client, notes = pack
    for text in (client, notes):
        assert "manday" not in text.lower() and " MD" not in text and "RM" not in text


# ====================================================================== the commands
def test_gaps_lists_what_the_workshop_has_to_settle(project, run):
    write_agenda(project)
    out = run("gaps", project)
    assert "Open questions for the client: 3 (2 high, 1 medium, 0 low)" in out
    assert out.index("R-001 [high") < out.index("R-003 [high") < out.index("R-002 [medium")
    assert "R-004" not in out and "R-005" not in out
    assert "Internal items still open: 1" in out
    assert "What the spec does not say yet: 1" in out and "Notifications: no e-mail or notification is listed  [GP-14]" in out
    assert "GP-01 Unidentified viewers and read-only stakeholders [no evidence yet; 4 workshop questions]" in out
    assert "Earlier agendas: 2026-02-10 workshop 2.json" in out


def test_gaps_says_so_when_there_is_no_spec(tmp_path, run):
    (tmp_path / "register.json").write_text(json.dumps(REGISTER), encoding="utf-8")
    assert "No spec yet: the workshop works from the brief and the gap patterns below." in run("gaps", tmp_path)


def test_check_takes_the_newest_agenda_and_sums_it_up(project, run):
    write_agenda(project, agenda_with(workshop="Workshop 1"), "2026-01-20 workshop 1.json")
    write_agenda(project)
    assert run("check", project) == "OK: 2026-02-10 workshop 2.json: 2 sections, 2 questions, 50 of 60 minutes, 1 left for later\n"
    assert run("check", project, "2026-01-20 workshop 1.json").startswith("OK: 2026-01-20 workshop 1.json")


def test_render_refuses_an_agenda_with_mistakes_and_writes_nothing(project, run, capsys):
    write_agenda(project, agenda_with(parked=[]))
    with pytest.raises(SystemExit) as stop:
        run("render", project)
    assert stop.value.code == 1
    out = capsys.readouterr().out
    assert "2026-02-10 workshop 2.json needs fixing:" in out and "R-003 (high) is open and not on the agenda" in out
    assert not list((project / "workshops").glob("*.docx"))


def test_render_says_where_the_two_documents_are_and_which_is_internal(project, run):
    write_agenda(project)
    out = run("render", project)
    assert "Workshop pack for Leave Request System: 2 sections, 2 questions, 50 of 60 minutes, 1 left for later" in out
    assert "For the client:" in out and "- agenda.docx" in out
    assert "For you only:" in out and "- facilitator notes (internal).docx" in out
    assert "The facilitator notes are internal: send the agenda, keep the notes." in out


@pytest.mark.parametrize("content, said", [
    ("{ not json", "is not valid JSON"),
    (None, "No agenda in"),
])
def test_a_missing_or_unreadable_agenda_is_explained(project, run, content, said):
    if content is not None:
        (project / "workshops").mkdir()
        (project / "workshops" / "2026-02-10 workshop 2.json").write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run("check", project)
    assert said in str(stop.value.code)



def test_the_agendas_own_words_are_checked_for_the_teams(project):
    """Only a ref was checked: a question pasted without one, or effort in the goal, reached the client's agenda."""
    agenda = json.loads(json.dumps(AGENDA))
    agenda["goal"] = "Settle the approval rules: 6 mandays at stake."
    agenda["sections"][1]["items"].append({"question": "Is BB-07 the right building block?"})
    errors = workshop.check(agenda, project)
    assert any(e.startswith("goal: 'mandays'") for e in errors), errors
    assert any("section 2, item 2: 'BB-07'" in e for e in errors), errors
