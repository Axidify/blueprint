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
    # every move the status rules allow has a case; a rejected application the employee may change is sent again
    # with the form's own button, since the form's records start in Pending Approval
    titles = [c["title"] for c in cases_of(scripts, "status change")]
    assert any("Pending Approval to Cancelled" in t for t in titles) and any("Approved to Cancelled" in t for t in titles)
    resubmit = next(c for c in scripts["cases"] if c["title"] == "Submit: from Rejected to Pending Approval")
    assert "todo" not in resubmit and resubmit["roles"] == ["employee"]
    assert [s["action"] for s in resubmit["steps"]][-2:] == ["Open LV-2026-009 to change it", "Press Submit"]
    assert resubmit["steps"][-1]["expected"] == "The status is now Pending Approval"


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
    note = next(c for c in cases_of(scripts, "notification") if c["title"].startswith("Notification:"))
    assert note["steps"][0]["expected"] == "Employee receives the notification as specified (Approval e-mail)"


def test_every_requirement_is_covered_and_the_draft_passes_the_check(project, run):
    _, scripts, _ = drafted(project, run)
    covered = {r for c in scripts["cases"] for r in c["requirements"]}
    assert covered == set(uat.requirement_ids(support.load_spec(support.EXAMPLE)))
    assert not cases_of(scripts, "requirement")  # every requirement of the sample is tied to a scenario that tests it
    assert "OK:" in run("check", project)


def test_a_requirement_the_draft_cannot_tie_is_a_case_to_refine(project, run):
    spec = support.load_spec(support.EXAMPLE)
    spec["requirements"][0]["items"].append("System shall keep each application for seven years.")
    support.write_spec(project, spec)
    _, scripts, out = drafted(project, run)
    (stub,) = cases_of(scripts, "requirement")
    assert stub["requirements"] == ["FR-APP-001.6"] and "write real steps" in stub["todo"]
    assert "Cases still to refine: 1" in out


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


def test_render_never_writes_over_the_testers_results(rendered, project, run):
    """Writing the scripts again replaced the workbook the testers fill in, and every result was gone."""
    path, _, _ = rendered
    book = path.with_suffix(".xlsx")
    wb = load_workbook(book)
    ws = wb[uat.STEPS_SHEET]
    head = [c.value for c in ws[1]]
    ws.cell(2, head.index("Pass/Fail") + 1, "Fail")
    ws.cell(2, head.index("Actual result") + 1, "The button did nothing")
    wb.save(book)
    with pytest.raises(SystemExit, match="filled in 1 step"):
        run("render", project)
    assert uat.filled_in(book) == 1, "the workbook is untouched"
    out = run("render", project, "--force")
    kept = [f for f in book.parent.glob("* - results kept *.xlsx")]
    assert len(kept) == 1 and uat.filled_in(kept[0]) == 1 and kept[0].name in out
    assert uat.filled_in(book) == 0, "a fresh workbook beside the kept one"



def test_render_stops_before_writing_anything_when_a_file_is_open(rendered, project, run, monkeypatch):
    """The workbook was written, then the document: with the document open in Word, only half was replaced."""
    path, _, _ = rendered
    book, doc = path.with_suffix(".xlsx"), path.with_suffix(".docx")
    before = book.read_bytes()
    real_open = open

    def word_has_it(file, *args, **kwargs):
        if str(file) == str(doc) and args and "+" in args[0]:
            raise PermissionError(13, "in use")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", word_has_it)
    with pytest.raises(SystemExit, match="Nothing was written"):
        run("render", project)
    assert book.read_bytes() == before


def test_an_item_whose_audience_is_not_client_counts_as_internal(project, run):
    """Only an exact "internal" was taken as internal: a missing or misspelt audience let its id into the scripts."""
    register = {"project": "Leave Request System", "items": [
        {"id": "R-009", "type": "fix", "severity": "low", "status": "open", "finding": "x"}]}
    (project / "register.json").write_text(json.dumps(register), encoding="utf-8")
    path, scripts, _ = drafted(project, run)
    scripts["cases"][0]["requirements"] = list(scripts["cases"][0].get("requirements") or []) + ["R-009"]
    scripts["cases"][0]["steps"][0]["expected"] += " (see R-009)"
    path.write_text(json.dumps(scripts), encoding="utf-8")
    errors, _ = uat.check(scripts, project)
    assert any("R-009" in e for e in errors), errors


# ====================================================================== two kinds of record
# tests/fixtures/two-records: a made-up batch of leave applications, approved on the batch's screen, whose
# applications then move on their own screens. The spec has one list of statuses for both.
TWO = support.ROOT / "tests" / "fixtures" / "two-records"


@pytest.fixture
def two(tmp_path):
    folder = tmp_path / "leave-batch"
    (folder / "spec").mkdir(parents=True)
    shutil.copy(TWO / "spec" / "app.yaml", folder / "spec" / "app.yaml")
    return folder


def steps_on(case):
    return [(s.get("role"), s["action"], s.get("screen")) for s in case["steps"]]


def test_each_kind_of_record_has_its_own_main_process_on_its_own_screens(two, run):
    _, scripts, _ = drafted(two, run)
    batch, application = cases_of(scripts, "main process")
    assert batch["title"] == "Main process: the batch, from Open to Closed"
    assert application["title"] == "Main process: the application, from Waiting to Archived"
    # the batch never goes to an application's screen, nor an application to the batch's
    assert {s.get("screen") for s in batch["steps"]} <= {"login", "batches", "new-batch", "batch"}
    assert {s.get("screen") for s in application["steps"]} <= {"login", "applications", "application"}
    # every move is made with the button that makes it, nothing is left for Claude to find
    assert "todo" not in batch
    assert batch["source"] == "status rules: Open > Submitted > Approved > Closed"
    actions = [a for _, a, _ in steps_on(batch)]
    assert actions.index("Press Save batch") < actions.index("Press Submit to HR") < actions.index("Press Approve") \
        < actions.index("Press Confirm approval") < actions.index("Press Close batch")


def test_the_role_allowed_to_press_each_button_makes_the_move(two, run):
    _, scripts, _ = drafted(two, run)
    batch, application = cases_of(scripts, "main process")
    assert batch["roles"] == ["officer", "manager"]  # the HR Manager approves: the process flow names roles by name
    actions = [a for _, a, _ in steps_on(batch)]
    assert actions.index("Sign in as HR Manager") < actions.index("Press Approve")
    assert actions.index("Press Submit to HR") < actions.index("Sign in as HR Manager")
    assert application["roles"] == ["clerk"]


def test_a_record_that_exists_already_is_opened_from_its_list_not_made_again(two, run):
    _, scripts, _ = drafted(two, run)
    batch = cases_of(scripts, "main process")[0]
    actions = [a for _, a, _ in steps_on(batch)]
    # made once with New batch; submitted, approved and closed from the batch opened in its list
    assert actions.count("Press New batch") == 1
    submit = actions.index("Press Submit to HR")
    assert actions[submit - 2:submit] == ["Open Batches from the side menu", "Find the batch and press Open"]
    resubmit = next(c for c in cases_of(scripts, "status change") if c["title"] == "Submit to HR: from Returned to Submitted")
    assert "Press New batch" not in [s["action"] for s in resubmit["steps"]]
    assert "Find the batch and press Open" in [s["action"] for s in resubmit["steps"]]


def test_a_later_kind_of_record_starts_from_a_sample_record_and_a_row_action_moves_it(two, run):
    _, scripts, _ = drafted(two, run)
    application = cases_of(scripts, "main process")[1]
    assert application["preconditions"] == ["An application in Waiting, for example LV-101"]
    assert "apart from the batch" in application["todo"]  # Claude says what the batch must be in
    actions = [a for _, a, _ in steps_on(application)]
    assert "Press Record in payroll" in actions and "Find LV-101 and press Archive" in actions


def test_a_button_shown_in_a_status_wins_over_a_form_that_adds_a_record(two, run):
    """A status move is made by the button shown in that status (in a dialog or a row too), never by the main
    button of the form that adds a new record in the same status."""
    _, scripts, _ = drafted(two, run)
    titles = [c["title"] for c in cases_of(scripts, "status change")]
    assert "Return: from Submitted to Returned" in titles  # confirmed in a dialog
    late = next(c for c in cases_of(scripts, "status change") if c["title"] == "Accept late: from Late to Waiting")
    assert late["roles"] == ["manager"] and "Add application" not in all_text(late)
    assert [s["action"] for s in late["steps"]][-2:] == ["Find LV-104 and press View", "Press Accept late"]
    assert not [c for c in scripts["cases"] if "no button" in str(c.get("todo"))]
    assert "OK:" in run("check", two)


def test_a_flow_step_no_button_makes_is_named_with_the_button_that_moves_it_elsewhere(two, run):
    spec = support.load_spec(two)
    batch_screen = next(s for s in spec["screens"] if s["id"] == "batch")
    close = next(b for b in batch_screen["buttons"] if b["label"] == "Close batch")
    close["when"] = {"status": "Submitted"}  # wrongly shown, so nothing closes an approved batch
    support.write_spec(two, spec)
    _, scripts, _ = drafted(two, run)
    batch = cases_of(scripts, "main process")[0]
    assert "no button in the mock-up moves a batch from Approved to Closed (Close batch on Leave Batch does it from Submitted)" \
        in batch["todo"]
    assert batch["steps"][-1]["expected"].endswith("Its status is Closed.")


def test_the_batch_and_the_application_requirements_go_to_the_process_that_makes_their_moves(two, run):
    _, scripts, out = drafted(two, run)
    batch, application = cases_of(scripts, "main process")
    ret = next(c for c in scripts["cases"] if c["title"] == "Return: from Submitted to Returned")
    # "approves or returns a batch": the batch's process (Approve) and the Return case; "an approved batch" is a status
    assert "FR-BAT-001.1" in batch["requirements"] and "FR-BAT-001.1" in ret["requirements"]
    assert application["requirements"] == ["FR-BAT-001.2"] and "FR-BAT-001.2" not in batch["requirements"]
    assert not cases_of(scripts, "requirement")


# ====================================================================== requirements tied to their scenarios
def test_each_requirement_of_the_sample_goes_to_the_scenario_that_tests_it(project, run):
    _, scripts, out = drafted(project, run)
    by_req = {}
    for c in scripts["cases"]:
        for r in c["requirements"]:
            by_req.setdefault(r, []).append(c)
    titles = {r: [c["title"] for c in cases] for r, cases in by_req.items()}
    assert titles["FR-APP-001.1"] == titles["FR-APP-001.2"] == titles["FR-APP-001.3"] == ["New Leave Application: field rules"]
    assert titles["FR-APP-002.2"] == ["Reject Application: required fields"]  # the dialog's reason, not the form's
    required = by_req["FR-APP-001.4"][0]
    assert required["title"] == "New Leave Application: required fields"
    assert required["steps"][-1]["action"] == "Choose Medical Leave in Leave Type, leave Supporting Document empty and press Submit"
    main = by_req["FR-APP-002.1"][0]
    assert main["type"] == "main process"
    assert any("sent to them as the Line Manager" in s["expected"] and s["action"].startswith("Find") for s in main["steps"])
    assert titles["FR-APP-003.1"] == ["Cancel Application: from Pending Approval to Cancelled", "Cancel Application: from Approved to Cancelled"]
    assert titles["FR-APP-002.3"] == ["E-mail to the Employee: Approved", "E-mail to the Employee: Rejected"]
    mail = by_req["FR-APP-003.2"][0]
    assert mail["title"] == "E-mail to the Line Manager: Cancelled" and mail["type"] == "notification"
    assert [s["action"] for s in mail["steps"]][-3:] == ["Press Cancel Application", "Press Yes, cancel it",
                                                         "Open the mailbox of the Line Manager test account"]
    draft = by_req["FR-APP-001.5"][0]
    assert "leave the required fields empty and press Save as Draft" in draft["steps"][-1]["action"]
    assert "saved with status Draft" in draft["steps"][-1]["expected"]
    assert "Cases still to refine: 0" in out


def test_a_requirement_waiting_for_a_decision_is_never_tied(project, run):
    spec = support.load_spec(support.EXAMPLE)
    spec["requirements"][1]["items"][1] = {"text": "System shall require a reason when rejecting.", "tbc": "R-004"}
    support.write_spec(project, spec)
    _, scripts, _ = drafted(project, run)
    (stub,) = cases_of(scripts, "requirement")
    assert stub["requirements"] == ["FR-APP-002.2"] and stub["preconditions"] == ["The open decision R-004 has been made"]
    assert "FR-APP-002.2" not in next(c for c in scripts["cases"] if c["title"] == "Reject Application: required fields")["requirements"]


def test_a_flow_step_is_made_with_the_button_named_after_it(tmp_path, run):
    folder = tmp_path / "equipment"
    shutil.copytree(support.WIDE / "spec", folder / "spec")
    _, scripts, _ = drafted(folder, run)
    (main,) = cases_of(scripts, "main process")
    actions = [s["action"] for s in main["steps"]]
    assert "Press Approve" in actions and "Press Confirm Approve" in actions and "Press Issue Equipment" in actions
    assert main["todo"] == "no button in the mock-up does 'Record return': write how it is done"
    shows = next(c for c in scripts["cases"] if c["title"] == "Booking Details: what it shows")
    assert shows["requirements"] == ["FR-BKG-001.3"] and "It shows" in shows["steps"][-1]["expected"]
    kept = next(c for c in scripts["cases"] if c["title"] == "Equipment: add and edit")
    assert kept["requirements"] == ["FR-EQP-001.1"] and kept["roles"] == ["admin"]


# ====================================================================== test data
def test_each_scenario_lists_the_test_data_it_needs(project, run):
    spec = project / "spec" / "app.yaml"
    text = spec.read_text(encoding="utf-8").replace(
        "    delete: none\n    next: [cancelled]\n", "    delete: none\n    next: [cancelled]\n    auto: [cancelled]\n", 1)
    spec.write_text(text, encoding="utf-8")
    _, scripts, _ = drafted(project, run)
    case = {c["title"]: c for c in scripts["cases"]}
    data = {c: {d["need"]: d for d in case[c]["test_data"]} for c in case}
    reject = next(t for t in case if t.startswith("Reject:"))
    assert set(data[reject]) == {
        "A test account for Line Manager (what it sees: applications from their direct reports; set it up so the test records are among them)",
        "A record in Pending Approval"}
    assert data[reject]["A record in Pending Approval"]["how"] == "Fill in New Leave Application and press Submit"
    rejected = data["Submit: from Rejected to Pending Approval"]["A record in Rejected"]
    assert rejected["kind"] == "record" and rejected["how"] == "Fill in New Leave Application and press Submit, then Reject (as Line Manager)"
    auto = data["Automatic: from Approved to Cancelled"]
    assert any("will meet the condition for Cancelled during UAT" in n and auto[n]["kind"] == "record" for n in auto)
    files = data["New Leave Application: field rules"]
    assert "A file for Supporting Document that breaks its rule: File size must be less than 5 MB" in files
    assert "A mailbox the testers can read for the Employee test account" in data["E-mail to the Employee: Approved"]
    assert all(d["kind"] in uat.DATA_KINDS for c in scripts["cases"] for d in c["test_data"])


def test_the_check_asks_for_test_data_and_refuses_a_malformed_entry(project, run):
    path, scripts, _ = drafted(project, run)
    del scripts["cases"][0]["test_data"]
    scripts["cases"][1]["test_data"] = [{"kind": "person", "need": "Someone"}]
    errors, warnings = checked(project, scripts)
    assert any(w.startswith("UAT-001: no test data listed") for w in warnings)
    assert any(e.startswith("UAT-002: each test_data entry needs a kind") for e in errors)


def test_the_workbook_and_the_document_carry_the_test_data_list(rendered):
    path, scripts, _ = rendered
    wb = load_workbook(path.with_suffix(".xlsx"))
    assert wb.sheetnames[:3] == ["Summary", uat.DATA_SHEET, uat.STEPS_SHEET] and wb.active.title == uat.STEPS_SHEET
    rows = list(wb[uat.DATA_SHEET].iter_rows(values_only=True))
    assert rows[0] == ("Ref", "Kind", "What is needed", "How to get it", "Scenarios", "Prepared by", "Ready", "Notes")
    listed = {r[2]: r for r in rows[1:]}
    assert listed["A record in Draft"][3] == "Fill in New Leave Application and press Save as Draft"
    assert rows[1][0] == "TD-01" and rows[1][1] == "Test account"
    steps = wb[uat.STEPS_SHEET]
    header = [c.value for c in steps[1]]
    first = [r for r in steps.iter_rows(min_row=2, values_only=True) if r[header.index("Step")] == 1]
    assert all(r[header.index("Test data")].startswith("TD-") for r in first)
    doc = Document(str(path.with_suffix(".docx")))
    text = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    assert "Test data to prepare before UAT" in text and "A record in Draft" in text and "Test data: TD-" in text


# ====================================================================== the defect log
def filled(path, marks, name="filled in.xlsx"):
    """A copy of the testers' workbook with {row: (result, actual, defect ref)} filled in."""
    wb = load_workbook(path.with_suffix(".xlsx"))
    ws = wb[uat.STEPS_SHEET]
    header = [c.value for c in ws[1]]
    col = {n: header.index(n) + 1 for n in header}
    for row, (result, actual, ref) in marks.items():
        ws.cell(row=row, column=col["Pass/Fail"], value=result)
        ws.cell(row=row, column=col["Actual result"], value=actual)
        ws.cell(row=row, column=col["Defect ref"], value=ref)
        ws.cell(row=row, column=col["Tester"], value="Tester A")
    out = path.with_name(name)
    wb.save(out)
    return (out, [ws.cell(row=row, column=col["Case"]).value for row in marks],
            [ws.cell(row=row, column=col["Requirements"]).value for row in marks])


def test_failed_steps_become_defects_linked_to_their_case_and_requirements(rendered, run):
    import layout

    path, scripts, _ = rendered
    project = path.parent.parent
    workbook, (case,), (reqs,) = filled(path, {3: ("Fail", "The side menu also shows Leave Types", "T-1")})
    out = run("results", project, workbook)
    assert "1 new: D-001" in out
    log = json.loads(layout.defect_log(project).read_text(encoding="utf-8"))
    (d,) = log["defects"]
    assert d["id"] == "D-001" and d["status"] == "open" and d["case"] == case and d["step"] == 2
    assert d["actual"] == "The side menu also shows Leave Types" and d["client_ref"] == "T-1" and d["tester"] == "Tester A"
    assert d["requirements"] == ([r.strip() for r in reqs.split(",")] if reqs else [])
    assert d["priority"] == next(c["priority"] for c in scripts["cases"] if c["id"] == case)
    assert layout.defect_log_xlsx(project).exists()
    # reading the same workbook again changes nothing
    assert "nothing new from this workbook" in run("results", project, workbook)
    assert len(json.loads(layout.defect_log(project).read_text(encoding="utf-8"))["defects"]) == 1


def test_a_defect_goes_through_its_statuses_and_a_retest_closes_or_reopens_it(rendered, run):
    import layout

    path, _, _ = rendered
    project = path.parent.parent
    first, _, _ = filled(path, {3: ("Fail", "Wrong menu", ""), 5: ("Fail", "No message", "")}, "round 1.xlsx")
    run("results", project, first)
    assert "D-001, D-002: retest" in run("defect", project, "D-001", "D-002", "retest", "--note", "fixed in build 14")
    second, _, _ = filled(path, {3: ("Pass", "", ""), 5: ("Fail", "Still no message", "")}, "round 2.xlsx")
    out = run("results", project, second)
    assert "1 open again: D-002" in out and "1 closed: D-001" in out
    log = {d["id"]: d for d in json.loads(layout.defect_log(project).read_text(encoding="utf-8"))["defects"]}
    assert log["D-001"]["status"] == "closed" and log["D-002"]["status"] == "open" and log["D-002"]["actual"] == "Still no message"
    assert [h["status"] for h in log["D-002"]["history"]] == ["open", "retest", "open"]
    assert log["D-002"]["history"][1]["note"] == "fixed in build 14"
    with pytest.raises(SystemExit, match="Say why it is not a defect"):
        run("defect", project, "D-002", "not a defect")
    with pytest.raises(SystemExit, match="not a defect status"):
        run("defect", project, "D-002", "parked")
    with pytest.raises(SystemExit, match="Not in the defect log: D-009"):
        run("defect", project, "D-009", "fixed")
    out = run("defect", project, "D-002", "change request")
    assert "change-request skill" in out and "change_request.py scope" in out
    run("defect", project, "D-002", "change request", "--cr", "CR-004")
    log = {d["id"]: d for d in json.loads(layout.defect_log(project).read_text(encoding="utf-8"))["defects"]}
    assert log["D-002"]["status"] == "change request" and log["D-002"]["cr"] == "CR-004"
    out = run("defects", project)
    assert "2 defects: 1 closed, 1 change request" in out and "-> CR-004" in out
    rows = list(load_workbook(layout.defect_log_xlsx(project))["Defects"].iter_rows(values_only=True))
    assert rows[0][:4] == ("Defect", "Status", "Priority", "Case") and [r[1] for r in rows[1:]] == ["closed", "change request"]


def test_results_never_takes_the_defect_log_for_the_testers_workbook(rendered, run):
    import layout

    path, _, _ = rendered
    project = path.parent.parent
    workbook, _, _ = filled(path, {3: ("Fail", "Wrong", "")})
    run("results", project, workbook)
    workbook.unlink()
    assert layout.defect_log_xlsx(project).exists()
    out = run("results", project)
    assert "UAT results in 2026-11-06 uat scripts v0.1.xlsx" in out
