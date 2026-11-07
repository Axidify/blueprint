"""contradictions.py: the review pack of everything a spec says about each subject, the clashes found mechanically
and the pairs left to judgement. Every contradiction here is planted in a copy of the made-up sample."""
import copy
import sys

import pytest

import support  # noqa: F401  (puts tools/ on the import path)
import contradictions
import layout

BASE = support.load_spec(support.EXAMPLE)


def spec():
    return copy.deepcopy(BASE)


def group(s, gid):
    return next(g for g in s["requirements"] if g["id"] == gid)


def screen(s, sid):
    return next(x for x in s["screens"] if x["id"] == sid)


def status(s, sid):
    return next(x for x in s["statuses"] if x["id"] == sid)


def pairs(items, rule=None):
    return {(c["a"]["loc"], c["b"]["loc"]) for c in items if rule is None or c["rule"] == rule}


def test_the_sample_has_no_contradictions_and_a_pack_by_subject():
    result = contradictions.build(spec())
    assert result["clashes"] == []
    assert result["look_here"] == []
    titles = {s["title"] for s in result["subjects"]}
    assert {"Status: Approved", "Screen: New Leave Application", "Field: Supporting Document",
            "Integration: SMTP", "Theme: Cancelling and withdrawing"} <= titles
    approved = next(s for s in result["subjects"] if s["title"] == "Status: Approved")
    locs = {d["loc"] for d in approved["statements"]}
    # the rules, the button that moves records there and the requirement naming it, side by side
    assert {"Status Approved: rules", "FR-APP-003.1", "Screen Leave Application Details: button Cancel Application"} <= locs


def test_a_requirement_against_the_status_rules():
    s = spec()
    group(s, "FR-APP-003")["items"].append("System shall allow the line manager to cancel an Approved application.")
    result = contradictions.build(s)
    assert ("FR-APP-003.3", "Status Approved: rules") in pairs(result["clashes"], "status-rule")
    clash = next(c for c in result["clashes"] if c["a"]["loc"] == "FR-APP-003.3")
    assert "Line Manager" in clash["why"] and "Employee" in clash["why"]
    assert clash["a"]["text"].startswith("System shall allow the line manager")


def test_a_sentence_forbidding_what_the_rules_allow():
    s = spec()
    group(s, "FR-APP-003")["items"].append("The employee cannot cancel an Approved application.")
    assert ("FR-APP-003.3", "Status Approved: rules") in pairs(contradictions.build(s)["clashes"], "status-rule")


def test_a_condition_makes_it_a_question_not_a_clash():
    s = spec()
    group(s, "FR-APP-003")["items"].append("The employee cannot cancel an Approved application after the leave starts.")
    result = contradictions.build(s)
    assert ("FR-APP-003.3", "Status Approved: rules") not in pairs(result["clashes"])
    assert ("FR-APP-003.3", "Status Approved: rules") in pairs(result["look_here"])


def test_a_status_meaning_against_its_own_rules():
    s = spec()
    status(s, "rejected")["meaning"] = "Rejected by the line manager; the employee may delete it."
    assert ("Status Rejected: meaning", "Status Rejected: rules") in pairs(contradictions.build(s)["clashes"], "status-rule")


def test_a_cancel_button_shown_to_a_role_the_rules_leave_out():
    s = spec()
    button = next(b for b in screen(s, "application-details")["buttons"] if b["label"] == "Cancel Application")
    button["roles"] = ["employee", "manager"]
    clashes = [c for c in contradictions.build(s)["clashes"] if c["rule"] == "button-rule"]
    assert {c["b"]["loc"] for c in clashes} == {"Status Pending Approval: rules", "Status Approved: rules"}
    assert all("Line Manager sees 'Cancel Application'" in c["why"] for c in clashes)


def test_a_cancel_rule_with_nowhere_to_go():
    s = spec()
    status(s, "approved")["next"] = []
    clash = [c for c in contradictions.build(s)["clashes"] if c["rule"] == "rule-move"]
    assert clash and "may cancel in Approved, but it cannot move to Cancelled" in clash[0]["why"]


def test_an_integration_named_as_out_of_scope_is_left_to_judgement():
    s = spec()
    s["integrations"].append({"system": "Attendance System", "purpose": "Leave days sent for attendance records",
                              "direction": "Outbound"})
    result = contradictions.build(s)
    assert not [c for c in result["clashes"] if c["rule"] == "out-of-scope"]  # "out of scope" may name only one part of it
    clash = [c for c in result["look_here"] if c["rule"] == "out-of-scope"]
    assert [(c["a"]["loc"], c["b"]["loc"]) for c in clash] == [("Scope: out of scope 2", "Integration Attendance System: purpose")]


def test_one_field_with_two_limits():
    s = spec()
    form = screen(s, "new-application")["sections"][0]["fields"]
    next(f for f in form if f["id"] == "attachment")["validation"] = "File size must be less than 10 MB"
    group(s, "FR-APP-001")["items"].append("Reason may be up to 1,000 characters.")
    clashes = [c for c in contradictions.build(s)["clashes"] if c["rule"] == "field-limit"]
    whys = " ".join(c["why"] for c in clashes)
    assert "Supporting Document is given two limits: 5 and 10 MB" in whys
    assert "Reason is given two limits: 500 and 1,000 characters" in whys


def test_a_required_field_called_optional():
    s = spec()
    group(s, "FR-APP-001")["items"].append("Reason is optional for Emergency Leave.")
    assert ("FR-APP-001.6", "Screen New Leave Application: field Reason (settings)") in \
        pairs(contradictions.build(s)["clashes"], "field-optional")


def test_all_or_nothing_against_partial_import_is_left_to_judgement():
    """The case that started it: one part said a bad upload imports nothing, a requirement said import the good
    rows and skip the bad ones. Nothing in the structure links them, so it is a look-here pair, not a clash."""
    s = spec()
    screen(s, "leave-types")["description"] = ("HR Admin maintains the leave types, or uploads them from a spreadsheet: "
                                               "if any row is invalid, the upload is rejected and nothing is imported.")
    s["requirements"].append({"id": "FR-TYP-001", "title": "Upload Leave Types", "screens": ["leave-types"], "items": [
        "System shall check each row of the uploaded file.",
        "System shall import the valid rows and skip the rows with errors, listing them for HR Admin."]})
    result = contradictions.build(s)
    assert not [c for c in result["clashes"] if "FR-TYP-001" in c["a"]["loc"] + c["b"]["loc"]]
    hit = [c for c in result["look_here"] if {c["a"]["loc"], c["b"]["loc"]} == {"Screen Leave Types: description", "FR-TYP-001.2"}]
    assert hit and hit[0]["why"] == "One reads all-or-nothing, the other partial."
    theme = next(x for x in result["subjects"] if x["title"] == "Theme: Uploads and imports")
    assert {"Screen Leave Types: description", "FR-TYP-001.2"} <= {d["loc"] for d in theme["statements"]}


TEXT = """# Planning Upload System

## 3.2 Upload

=== PAGE 2 ===
If the uploaded file has any invalid row, the whole file is rejected and nothing is imported.

=== PAGE 3 ===
## 4.1 Functional requirements
| ID | Requirement |
|---|---|
| FR-PLN-001.4 | The system shall import the valid rows and skip the invalid ones, with an error report. |
| FR-PLN-001.5 | The system shall e-mail the planner when an upload finishes. |
"""


def test_a_document_gets_themes_and_look_here_pairs_with_locations():
    result = contradictions.build_text(TEXT)
    assert result["clashes"] == []
    assert ("§3.2 Upload (p2)", "FR-PLN-001.4 (p3)") in pairs(result["look_here"])
    assert any(s["title"] == "Theme: Uploads and imports" for s in result["subjects"])


def test_the_pack_is_written_to_the_project(tmp_path, monkeypatch, capsys):
    project = tmp_path / "sample"
    layout.create_new(project)
    s = spec()
    group(s, "FR-APP-003")["items"].append("System shall allow the line manager to cancel an Approved application.")
    support.write_spec(project, s)
    monkeypatch.setattr(sys, "argv", ["contradictions.py", str(project), "--strict"])
    assert contradictions.main() == 1
    out = capsys.readouterr().out
    assert "Clashes (mechanical): 1" in out
    pack = layout.reviews_dir(project) / "spec-v0.1-contradictions" / "pack.md"
    text = pack.read_text(encoding="utf-8")
    assert "## 1. Clashes (found mechanically)" in text and "**FR-APP-003.3**" in text
    assert "## 2. Look here" in text and "### Status: Approved" in text
    assert (pack.parent / "pack.json").exists()


@pytest.mark.parametrize("text", ["System shall allow the employee to cancel a Pending application.",
                                  "System shall inform the line manager when the employee cancels an Approved application.",
                                  "System shall allow the line manager to cancel an application until it is Approved."])
def test_sentences_that_agree_or_do_not_say_who_are_not_clashes(text):
    s = spec()
    group(s, "FR-APP-003")["items"].append(text)
    assert contradictions.build(s)["clashes"] == []
