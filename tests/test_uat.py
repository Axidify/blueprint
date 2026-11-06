"""tools/uat.py: the UAT draft from the spec, its checks, the workbook and document, and reading results back.

Projects are made in temp folders from the made-up sample; nothing here reads or writes the workspace.
"""
import json
import shutil
import sys

import pytest
from docx import Document
from openpyxl import load_workbook

import support

import uat


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "leave-request"
    (folder / "spec").mkdir(parents=True)
    shutil.copy(support.EXAMPLE / "spec" / "app.yaml", folder / "spec" / "app.yaml")
    return folder


@pytest.fixture
def run(monkeypatch, capsys):
    def call(*args):
        monkeypatch.setattr(sys, "argv", ["uat.py", *map(str, args)])
        uat.main()
        return capsys.readouterr().out

    return call


def drafted(project, run, *extra):
    out = run("draft", project, "--date", "2026-11-06", *extra)
    path = next((project / "uat").glob("*.json"))
    return path, json.loads(path.read_text(encoding="utf-8")), out


def cases_of(scripts, kind):
    return [c for c in scripts["cases"] if c["type"] == kind]


def all_text(case):
    return " ".join([case["title"], *case["preconditions"]] + [f"{s['action']} {s['expected']}" for s in case["steps"]])


# ====================================================================== the draft
def test_the_draft_is_dated_named_after_the_spec_version_and_says_what_it_was_written_from(project, run):
    path, scripts, out = drafted(project, run)
    assert path.name == "2026-11-06 uat scripts v0.1.json"
    assert scripts["spec"] == "spec/app.yaml" and scripts["spec_version"] == "0.1"
    assert "not yet issued" in scripts["based_on"] and "not yet issued" in out
    assert [c["id"] for c in scripts["cases"]] == [f"UAT-{n:03d}" for n in range(1, len(scripts["cases"]) + 1)]
    assert len({c["title"].lower() for c in scripts["cases"]}) == len(scripts["cases"])


def test_the_main_process_runs_from_submit_to_approval_as_each_role_in_turn(project, run):
    _, scripts, _ = drafted(project, run)
    (main,) = cases_of(scripts, "main process")
    assert main["priority"] == "High" and main["roles"] == ["employee", "manager"]
    actions = [s["action"] for s in main["steps"]]
    assert actions[0] == "Sign in as Employee" and "Press Submit" in actions
    assert actions.index("Sign in as Line Manager") < actions.index("Press Approve") < actions.index("Press Confirm Approve")
    assert "The status is now Approved" in next(s["expected"] for s in main["steps"] if s["action"] == "Press Confirm Approve")
    assert "Approved" in main["steps"][-1]["expected"] and main["steps"][-1]["screen"] == "application-details"
    assert all(s.get("screen") in (None, "login", "new-application", "approvals", "review-application", "my-applications",
                                   "application-details") for s in main["steps"])


def test_rejecting_is_a_case_of_its_own_through_the_dialog(project, run):
    _, scripts, _ = drafted(project, run)
    reject = next(c for c in cases_of(scripts, "status change") if c["title"].startswith("Reject:"))
    assert reject["priority"] == "High" and reject["roles"] == ["manager"]
    assert reject["preconditions"] == ["A record in Pending Approval, for example LV-2026-014"]
    assert [s["action"] for s in reject["steps"]][-3:] == ["Press Reject", "Fill in Reason for rejection", "Press Confirm Reject"]
    assert "The status is now Rejected" in reject["steps"][-1]["expected"]
    # every move the status rules allow has a case; one no button makes is left for Claude to write
    titles = [c["title"] for c in cases_of(scripts, "status change")]
    assert any("Pending Approval to Cancelled" in t for t in titles) and any("Approved to Cancelled" in t for t in titles)
    resubmit = next(c for c in scripts["cases"] if c["title"] == "From Rejected to Pending Approval")
    assert "no button" in resubmit["todo"]


def test_what_a_role_may_not_do_in_a_status_is_tested(project, run):
    _, scripts, _ = drafted(project, run)
    pending = next(c for c in cases_of(scripts, "not allowed") if c["title"].startswith("Pending Approval"))
    assert pending["priority"] == "High"
    manager = next(s for s in pending["steps"] if s["role"] == "manager")
    assert "no way to change, cancel or delete it" in manager["expected"]
    employee = next(s for s in pending["steps"] if s["role"] == "employee")
    assert "change or delete" in employee["expected"] and "cancel" not in employee["expected"]  # the employee may cancel


def test_fields_are_checked_for_required_rules_length_and_choices(project, run):
    _, scripts, _ = drafted(project, run)
    checks = {c["title"]: all_text(c) for c in cases_of(scripts, "field checks")}
    assert "Reason is pointed out as required" in checks["New Leave Application: required fields"]
    rules = checks["New Leave Application: field rules"]
    assert "To Date must be on or after From Date" in rules and "more than 500 characters" in rules
    assert "Annual Leave" in rules and "cannot be changed" in rules
    assert "Reason for rejection is pointed out as required" in checks["Reject Application: required fields"]


def test_each_role_is_refused_the_screens_it_may_not_open(project, run):
    _, scripts, _ = drafted(project, run)
    employee = next(c for c in cases_of(scripts, "access") if c["roles"] == ["employee"])
    refused = [s["screen"] for s in employee["steps"] if s["expected"] == "Access is refused"]
    assert refused == ["approvals", "review-application", "leave-types"]
    assert "own applications only" in employee["steps"][-1]["expected"]


def test_integrations_and_figures_say_what_is_specified(project, run):
    _, scripts, _ = drafted(project, run)
    ad = next(c for c in cases_of(scripts, "integration") if "Active Directory" in c["title"])
    assert "Sign-in, and submitting an application" in ad["steps"][0]["action"]
    assert ad["steps"][1]["expected"].startswith("As specified: Sign-in is refused")
    figures = all_text(cases_of(scripts, "figures")[0])
    assert "entitlement for the year" in figures and "status Pending Approval" in figures


def test_notifications_become_cases(project, run):
    spec = support.load_spec(support.EXAMPLE)
    spec["notifications"] = [{"event": "Application approved", "recipient": "Employee", "template": "Approval e-mail"}]
    support.write_spec(project, spec)
    _, scripts, _ = drafted(project, run)
    (note,) = cases_of(scripts, "notification")
    assert note["steps"][0]["expected"] == "Employee receives the notification as specified (Approval e-mail)"


def test_every_requirement_is_covered_and_the_draft_passes_the_check(project, run):
    _, scripts, _ = drafted(project, run)
    covered = {r for c in scripts["cases"] for r in c["requirements"]}
    assert covered == set(uat.requirement_ids(support.load_spec(support.EXAMPLE)))
    stub = next(c for c in cases_of(scripts, "requirement") if c["requirements"] == ["FR-APP-002.2"])
    assert "todo" in stub and stub["related"]  # Claude merges it into the scenario that already tests it
    assert "OK:" in run("check", project)


def test_a_second_draft_of_the_same_day_is_refused_unless_forced(project, run):
    drafted(project, run)
    with pytest.raises(SystemExit, match="exists already"):
        run("draft", project, "--date", "2026-11-06")
    assert "UAT draft" in run("draft", project, "--date", "2026-11-06", "--force")


def test_the_issued_version_is_preferred_to_the_current_spec(project, run):
    spec = support.load_spec(support.EXAMPLE)
    (project / "output").mkdir()
    support.write_spec(project, spec)
    shutil.copy(project / "spec" / "app.yaml", project / "output" / "spec-v0.1.yaml")
    (project / "output" / "issued.json").write_text(json.dumps([{"version": "0.1", "date": "2026-11-20", "to": "SAMPLE", "files": []}]),
                                                    encoding="utf-8")
    spec["project"]["version"] = "0.2"
    spec["requirements"].append({"id": "FR-APP-004", "title": "Reports", "items": ["System shall export applications."]})
    support.write_spec(project, spec)
    _, scripts, out = drafted(project, run)
    assert scripts["spec"] == "output/spec-v0.1.yaml" and scripts["spec_version"] == "0.1"
    assert scripts["based_on"] == "the requirements document v0.1, issued on 20 November 2026"
    assert "moved on to v0.2" in out
    assert not any("FR-APP-004" in c["requirements"] for c in scripts["cases"])
    run("draft", project, "--date", "2026-11-07", "--current")
    current = json.loads((project / "uat" / "2026-11-07 uat scripts v0.2.json").read_text(encoding="utf-8"))
    assert current["spec"] == "spec/app.yaml" and any("FR-APP-004.1" in c["requirements"] for c in current["cases"])


# ====================================================================== the check
def checked(project, scripts):
    return uat.check(scripts, project)


def test_the_check_names_an_uncovered_requirement_and_accepts_one_excluded_with_a_reason(project, run):
    _, scripts, _ = drafted(project, run)
    scripts["cases"] = [c for c in scripts["cases"] if c["requirements"] != ["FR-APP-003.2"]]
    errors, _ = checked(project, scripts)
    assert errors == ["FR-APP-003.2 is not covered: add it to a case that tests it, or to excluded with the reason"]
    scripts["excluded"] = [{"requirement": "FR-APP-003.2", "reason": ""}]
    assert any("needs its id and the reason" in e for e in checked(project, scripts)[0])
    scripts["excluded"] = [{"requirement": "FR-APP-003.2", "reason": "Tested with the e-mail system in the integration test."}]
    assert checked(project, scripts)[0] == []


def test_the_check_names_a_step_without_an_expected_result_and_other_mistakes(project, run):
    _, scripts, _ = drafted(project, run)
    scripts["cases"][0]["steps"][1]["expected"] = " "
    scripts["cases"][1]["id"] = scripts["cases"][0]["id"]
    scripts["cases"][2]["roles"] = ["auditor"]
    scripts["cases"][2]["steps"][0]["screen"] = "reports"
    scripts["cases"][3]["steps"] = []
    scripts["cases"][4]["priority"] = "Urgent"
    scripts["cases"][5]["requirements"] = ["FR-XYZ-001.1"]
    errors, _ = checked(project, scripts)
    assert "UAT-001, step 2: needs an expected result" in errors
    assert "UAT-001 is used twice" in errors
    assert "UAT-003: 'auditor' is not a role of the spec" in errors
    assert "UAT-003, step 1: 'reports' is not a screen of the mock-up" in errors
    assert "UAT-004: needs steps" in errors
    assert "UAT-005: priority must be High, Medium or Low" in errors
    assert "UAT-006: FR-XYZ-001.1 is not a requirement of spec v0.1" in errors


def test_the_check_refuses_internal_content(project, run):
    (project / "register.json").write_text(json.dumps({"items": [
        {"id": "R-007", "audience": "internal", "type": "fix", "status": "open"}]}), encoding="utf-8")
    _, scripts, _ = drafted(project, run)
    scripts["cases"][0]["steps"][0]["expected"] = "Takes 2 mandays to build"
    scripts["cases"][1]["preconditions"] = ["R-007 is fixed"]
    errors, _ = checked(project, scripts)
    assert any("'mandays' is internal" in e for e in errors) and "UAT-002: R-007 is an internal register item" in errors


# ====================================================================== the workbook and the document
@pytest.fixture
def rendered(project, run):
    spec = support.load_spec(support.EXAMPLE)
    spec["requirements"][0]["items"][0] = {"text": spec["requirements"][0]["items"][0], "note": "SECRET-NOTE ask the lead dev"}
    spec["platform_fit"] = [{"feature": "screen:list", "support": "custom", "takes": "SECRET-FIT a plugin"}]
    support.write_spec(project, spec)
    path, scripts, _ = drafted(project, run)
    out = run("render", project)
    return path, scripts, out


def test_render_writes_the_workbook_and_the_document_next_to_the_scripts(rendered):
    path, scripts, out = rendered
    assert path.with_suffix(".xlsx").exists() and path.with_suffix(".docx").exists()
    assert "Workbook for the testers" in out and "requirements covered 10 of 10" in out


def test_the_workbook_has_a_row_per_step_with_result_columns_and_a_pass_fail_list(rendered):
    path, scripts, _ = rendered
    wb = load_workbook(path.with_suffix(".xlsx"))
    ws = wb[uat.STEPS_SHEET]
    header = [c.value for c in ws[1]]
    for column in ("Actual result", "Pass/Fail", "Tester", "Date", "Defect ref", "Expected result", "Requirements"):
        assert column in header
    assert ws.max_row - 1 == sum(len(c["steps"]) for c in scripts["cases"])
    pass_fail = "ABCDEFGHIJKLMNO"[header.index("Pass/Fail")]
    lists = [dv for dv in ws.data_validations.dataValidation if dv.type == "list"]
    assert lists and lists[0].formula1 == '"Pass,Fail,Blocked,Not run"' and str(lists[0].sqref) == f"{pass_fail}2:{pass_fail}{ws.max_row}"
    summary = [row for row in wb["Summary"].iter_rows(values_only=True)]
    assert ("FR-APP-002", "Approve or Reject", 3, 3, 0) == next(r for r in summary if r[0] == "FR-APP-002")[:5]
    assert any(r[0] == "Steps failed" and str(r[1]).startswith("=COUNTIF") for r in summary)
    assert "6 November 2026" in summary[1][0]


def test_nothing_internal_reaches_the_workbook_or_the_document(rendered):
    path, scripts, _ = rendered
    text = "\n".join(p.text for p in Document(str(path.with_suffix(".docx"))).paragraphs)
    doc = Document(str(path.with_suffix(".docx")))
    text += "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    wb = load_workbook(path.with_suffix(".xlsx"))
    text += "\n".join(str(v) for ws in wb for row in ws.iter_rows(values_only=True) for v in row if v)
    for leak in ("SECRET", "status rules:", "still to do", "write real steps", "manday", "platform"):
        assert leak not in text
    assert scripts["cases"][0]["title"] in text and "How to record results" in text


def test_results_lists_the_failed_and_blocked_steps(rendered, run):
    path, _, _ = rendered
    wb = load_workbook(path.with_suffix(".xlsx"))
    ws = wb[uat.STEPS_SHEET]
    header = [c.value for c in ws[1]]
    col = {name: header.index(name) + 1 for name in header}
    ws.cell(row=2, column=col["Pass/Fail"], value="Pass")
    ws.cell(row=3, column=col["Pass/Fail"], value="fail")
    ws.cell(row=3, column=col["Actual result"], value="The menu also shows Leave Types")
    ws.cell(row=3, column=col["Defect ref"], value="D-12")
    ws.cell(row=4, column=col["Pass/Fail"], value="Blocked")
    filled = path.with_name("filled in.xlsx")
    wb.save(filled)
    out = run("results", path.parent.parent, filled)
    assert "1 pass, 1 fail, 1 blocked" in out
    assert "UAT-001 step 2" in out and "defect D-12" in out and "The menu also shows Leave Types" in out


def test_dates_are_written_for_people():
    assert uat.readable("2026-11-06") == "6 November 2026" and uat.readable("soon") == "soon"


def test_a_filtered_drop_down_is_tested_with_only_the_records_it_offers(project, run):
    spec = project / "spec" / "app.yaml"
    text = spec.read_text(encoding="utf-8").replace(
        "options_from: leave_types.name,",
        "options_from: {list: leave_types, field: name, where: {requires_attachment: \"No\"}},", 1)
    spec.write_text(text, encoding="utf-8")
    _, scripts, _ = drafted(project, run)
    choices = [s["expected"] for c in scripts["cases"] for s in c["steps"] if s["action"] == "Open the choices of Leave Type"]
    assert choices, "the filtered drop-down has a step"
    assert "only, requires attachment No" in choices[0]
    assert "Annual Leave" in choices[0] and "Medical Leave" not in choices[0]


def test_a_move_the_system_makes_on_its_own_is_a_case_without_a_button(project, run):
    spec = project / "spec" / "app.yaml"
    text = spec.read_text(encoding="utf-8").replace(
        "    delete: none\n    next: [cancelled]\n", "    delete: none\n    next: [cancelled]\n    auto: [cancelled]\n", 1)
    spec.write_text(text, encoding="utf-8")
    _, scripts, _ = drafted(project, run)
    auto = [c for c in scripts["cases"] if c["title"].startswith("Automatic: from Approved to Cancelled")]
    assert len(auto) == 1
    assert "on its own" in all_text(auto[0]) and auto[0]["todo"]
    assert not [c for c in scripts["cases"] if c["title"] == "From Approved to Cancelled"]


def test_the_workbook_follows_the_design_language(rendered):
    """docs/design-language.md, Spreadsheets: the testers' columns as fields to fill in, results as a dot and a word."""
    import sheets

    path, _, _ = rendered
    ws = load_workbook(path.with_suffix(".xlsx"))[uat.STEPS_SHEET]
    header = [c.value for c in ws[1]]
    for name, by_tester in ((n, t) for n, _, t in uat.STEP_COLUMNS):
        cell = ws.cell(row=2, column=header.index(name) + 1)
        assert cell.fill.fgColor.rgb.endswith(sheets.INPUT_FILL) == by_tester, name
    result = ws.cell(row=2, column=header.index("Pass/Fail") + 1)
    assert result.number_format == sheets.DOT_FORMAT
    assert {'"Pass"', '"Fail"', '"Blocked"', '"Not run"'} <= {rule.formula[0] for rng in ws.conditional_formatting for rule in rng.rules}
