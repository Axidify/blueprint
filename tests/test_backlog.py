"""tools/backlog.py: the backlog draft from the spec, its checks, story points from the estimate, and the files
made from it (the team's workbook, the client's traceability sheet, the Project Desk, Jira and Azure DevOps imports).

Projects are made in temp folders from the made-up sample; the knowledge base is a temp copy of the app's
starter one with a few rates filled in. Nothing here reads or writes the workspace.
"""
import csv
import json
import shutil
import sys

import pytest
from openpyxl import load_workbook

import support
import layout  # noqa: E402

import backlog
import overview

SCALE_ROWS = {1: "0.5", 2: "1", 3: "2", 5: "3", 8: "5", 13: "8"}


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "leave-request"
    (folder / "spec").mkdir(parents=True)
    shutil.copy(support.EXAMPLE / "spec" / "app.yaml", folder / "spec" / "app.yaml")
    shutil.copytree(support.EXAMPLE / "estimates", folder / "estimates")
    return folder


def knowledge(tmp_path, rates=True, scale=SCALE_ROWS):
    """A copy of the starter knowledge base: BB-01 at 3–5 and BB-03 at 2–4 mandays, and the given scale."""
    k = tmp_path / "knowledge"
    shutil.copytree(support.ROOT / "templates" / "knowledge", k)
    path = k / "building-blocks.md"
    text = path.read_text(encoding="utf-8")
    if rates:
        text = text.replace("| Fields, validations, lookups | TBD | – |", "| Fields, validations, lookups | 3–5 | medium |")
        text = text.replace("| Routing rule, reject path, notifications | TBD | – |", "| Routing rule, reject path, notifications | 2–4 | medium |")
    if scale is None:
        text = text[:text.index("## Story points")] + text[text.index("## Calibration notes"):]
    else:
        for points, md in scale.items():
            text = text.replace(f"| {points} | TBD |", f"| {points} | {md} |")
    path.write_text(text, encoding="utf-8")
    return k


@pytest.fixture
def run(monkeypatch, capsys):
    def call(*args, fail=False):
        monkeypatch.setattr(sys, "argv", ["backlog.py", *map(str, args)])
        if fail:
            with pytest.raises(SystemExit) as stop:
                backlog.main()
            return capsys.readouterr().out + str(stop.value.code or "")
        backlog.main()
        return capsys.readouterr().out

    return call


def drafted(project, run, *extra):
    run("draft", project, "--date", "2026-11-07", *extra)
    path = project / "backlog" / "2026-11-07 backlog v0.1.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def refined(project, run, *extra):
    """The draft as Claude leaves it: every story with 'so that', the draft notes worked in."""
    path, data = drafted(project, run, *extra)
    for s in data["stories"]:
        s["so_that"] = "the application is complete"
        s.pop("todo", None)
        if not s["acceptance"]:
            s["acceptance"] = ["It happens as the requirement says"]
    data.pop("unplaced", None)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path, data


def story(data, sid):
    return next(s for s in data["stories"] if s["id"] == sid)


# ====================================================================== the draft
def test_the_draft_has_an_epic_per_requirement_group_and_a_story_per_item(project, run):
    path, data = drafted(project, run)
    assert path.name == "2026-11-07 backlog v0.1.json"
    assert data["spec"] == "spec/app.yaml" and "not yet issued" in data["based_on"]
    assert [(e["id"], e["group"]) for e in data["epics"]] == [("EP-01", "FR-APP-001"), ("EP-02", "FR-APP-002"), ("EP-03", "FR-APP-003")]
    assert [s["id"] for s in data["stories"]] == [f"US-{n:03d}" for n in range(1, 11)]
    assert [s["requirements"] for s in data["stories"]][:2] == [["FR-APP-001.1"], ["FR-APP-001.2"]]
    assert all(s["todo"] and s["type"] == "Story" for s in data["stories"])


def test_the_draft_writes_the_story_as_the_user_would_and_guesses_the_role(project, run):
    _, data = drafted(project, run)
    cancel = story(data, "US-009")
    assert cancel["role"] == "employee" and cancel["want"].startswith("to cancel a Pending or Approved application")
    assert cancel["title"].startswith("Cancel a Pending or Approved application")


def test_acceptance_criteria_from_the_screens_land_on_the_story_they_read_like(project, run):
    _, data = drafted(project, run)
    assert "Reject cannot be confirmed without Reason for rejection" in story(data, "US-007")["acceptance"]
    assert story(data, "US-007")["screens"] == ["review-application"]
    assert any("presses Cancel Application, it moves to Cancelled" in a for a in story(data, "US-009")["acceptance"])
    assert any("Number of Days is filled in by the system" in a for a in story(data, "US-003")["acceptance"])
    assert any(u["criterion"] == "Reason is required" for u in data["unplaced"]), "the form's reason is not the rejection reason"


def test_the_draft_links_the_estimate_lines_to_the_epic_whose_name_they_share(project, run):
    _, data = drafted(project, run)
    assert data["estimate"] == "estimates/2026-11-06 estimate from spec v0.1.json"
    assert {tuple(s["lines"]) for s in data["stories"] if s["epic"] == "EP-01"} == {("L01",)}
    assert {tuple(s["lines"]) for s in data["stories"] if s["epic"] == "EP-03"} == {("L03",)}


def test_the_draft_is_never_replaced_without_force(project, run):
    drafted(project, run)
    out = run("draft", project, "--date", "2026-11-07", fail=True)
    assert "exists already" in out
    drafted(project, run, "--force")


def test_without_an_estimate_the_draft_says_there_will_be_no_points(project, run):
    shutil.rmtree(project / "estimates")
    out = run("draft", project, "--date", "2026-11-07")
    data = json.loads((project / "backlog" / "2026-11-07 backlog v0.1.json").read_text(encoding="utf-8"))
    assert "no story points" in out and "estimate" not in data and not any(s.get("lines") for s in data["stories"])


# ====================================================================== checks
def problems(project, data, k):
    spec = support.load_spec(project)
    lines, problem = backlog.estimate_lines(project, data.get("estimate"), k)
    return backlog.check(data, spec, project, lines, problem)


def test_a_refined_backlog_passes_and_lists_the_gaps(project, run, tmp_path):
    _, data = refined(project, run)
    errors, refine, gaps = problems(project, data, knowledge(tmp_path))
    assert errors == [] and refine == []
    assert any("L06" in g and "Leave Types maintenance" in g for g in gaps), "estimated work no requirement asks for"
    assert any("'Leave Types' is in no story" in g for g in gaps)


def test_every_requirement_must_end_in_a_story_or_be_excluded_with_a_reason(project, run, tmp_path):
    _, data = refined(project, run)
    k = knowledge(tmp_path)
    data["stories"] = [s for s in data["stories"] if s["id"] != "US-010"]
    errors, _, _ = problems(project, data, k)
    assert "FR-APP-003.2 is in no story: add one, or exclude it with a reason" in errors
    data["excluded"] = [{"requirement": "FR-APP-003.2", "reason": ""}]
    assert "excluded: FR-APP-003.2 needs a reason" in problems(project, data, k)[0]
    data["excluded"][0]["reason"] = "Covered by the e-mail settings of the platform"
    assert problems(project, data, k)[0] == []


@pytest.mark.parametrize("change, expected", [
    (lambda s: s.update(role="director"), "role 'director' is not a role of the spec"),
    (lambda s: s.update(screens=["nowhere"]), "screen 'nowhere' is not in the spec"),
    (lambda s: s.update(requirements=["FR-XXX-009.1"]), "FR-XXX-009.1 is not a requirement of the spec"),
    (lambda s: s.update(lines=["L99"]), "L99 is not a building-block or manday line of the estimate"),
    (lambda s: s.update(lines=["L12"]), "L12 is not a building-block or manday line of the estimate"),
    (lambda s: s.update(lines=[{"line": "L01", "share": 1.5}]), "the share of L01 must be a number above 0 and up to 1"),
    (lambda s: s.update(type="Spike"), "type 'Spike' is not one of Story, Task"),
    (lambda s: s.update(priority="High"), "priority 'High' is not one of Must, Should, Could"),
    (lambda s: s.update(title="Leave form (3 mandays)"), "keep mandays, rates and building blocks out of it"),
    (lambda s: s.update(register=["R-404"]), "R-404 is not in the register"),
])
def test_check_names_each_mistake(project, run, tmp_path, change, expected):
    _, data = refined(project, run)
    change(data["stories"][0])
    errors, _, _ = problems(project, data, knowledge(tmp_path))
    assert any(expected in e for e in errors), errors


def test_shares_of_one_line_may_not_add_up_to_more_than_the_line(project, run, tmp_path):
    _, data = refined(project, run)
    story(data, "US-001")["lines"] = [{"line": "L01", "share": 0.7}]
    story(data, "US-002")["lines"] = [{"line": "L01", "share": 0.5}]
    errors, _, _ = problems(project, data, knowledge(tmp_path))
    assert "the shares of L01 add up to 120%: more than the whole line" in errors


def test_a_task_needs_no_role_or_requirement(project, run, tmp_path):
    _, data = refined(project, run)
    data["stories"].append({"id": "US-011", "epic": "EP-01", "type": "Task", "title": "Move to production",
                            "want": "Migrate the application to production", "acceptance": ["It runs in production"], "lines": ["L11"]})
    errors, _, gaps = problems(project, data, knowledge(tmp_path))
    assert errors == [] and not any("L11" in g for g in gaps)


def test_a_story_waiting_on_an_open_client_question_is_not_ready(project, run, tmp_path):
    _, data = refined(project, run)
    (project / "register.json").write_text(json.dumps({"items": [{"id": "R-001", "status": "open"}]}), encoding="utf-8")
    story(data, "US-003")["register"] = ["R-001"]
    _, _, gaps = problems(project, data, knowledge(tmp_path))
    assert "US-003 waits on R-001, still open: not ready to build until the client answers" in gaps


# ====================================================================== story points
def test_points_come_from_the_estimate_lines_shared_among_their_stories_and_the_scale(project, run, tmp_path):
    _, data = refined(project, run)
    k = knowledge(tmp_path)
    lines, _ = backlog.estimate_lines(project, data["estimate"], k)
    scale, issues = backlog.read_scale(k)
    pts = backlog.work_out_points(data, lines, scale, issues)
    assert issues == []
    assert round(pts["US-001"]["low"], 2) == 0.6 and round(pts["US-001"]["high"], 2) == 1.0  # L01 3–5 MD, five stories
    assert pts["US-001"]["points"] == 2
    assert pts["US-009"]["points"] == 3  # L03 2–4 MD, two stories: 1.5 MD


def test_a_given_share_takes_its_part_and_the_rest_is_split(project, run, tmp_path):
    _, data = refined(project, run)
    story(data, "US-009")["lines"] = [{"line": "L03", "share": 0.75}]
    k = knowledge(tmp_path)
    lines, _ = backlog.estimate_lines(project, data["estimate"], k)
    pts = backlog.work_out_points(data, lines, *backlog.read_scale(k))
    assert (pts["US-009"]["low"], pts["US-009"]["high"]) == (1.5, 3.0)
    assert (pts["US-010"]["low"], pts["US-010"]["high"]) == (0.5, 1.0)


@pytest.mark.parametrize("rates, scale, why", [
    (False, SCALE_ROWS, "L01 has no rate in the knowledge base yet"),
    (True, None, "no story-point scale in the knowledge base yet"),
    (True, {1: "0.5", 2: "1"}, "not set yet for 3, 5, 8, 13 points"),
    (True, {1: "2", 2: "1", 3: "3", 5: "4", 8: "5", 13: "6"}, "the mandays must grow with the points"),
])
def test_without_a_rate_or_a_whole_scale_there_are_no_points_and_the_reason_is_shown(project, run, tmp_path, rates, scale, why):
    _, data = refined(project, run)
    k = knowledge(tmp_path, rates=rates, scale=scale)
    lines, _ = backlog.estimate_lines(project, data["estimate"], k)
    pts = backlog.work_out_points(data, lines, *backlog.read_scale(k))
    assert pts["US-001"]["points"] is None and why in pts["US-001"]["why"]


def test_a_story_above_the_scale_gets_the_largest_value_and_is_marked_to_split():
    points, note = backlog.to_points(9.5, {p: float(md) for p, md in SCALE_ROWS.items()})
    assert points == 13 and "split the story" in note
    assert backlog.to_points(0.5, {p: float(md) for p, md in SCALE_ROWS.items()}) == (1, "")


def test_scale_prints_the_table_to_add_when_the_knowledge_base_has_none(run, tmp_path):
    out = run("scale", "--knowledge", knowledge(tmp_path, scale=None))
    assert "## Story points" in out and "| 13 | TBD |" in out
    assert "1: 0.5, 2: 1, 3: 2, 5: 3, 8: 5, 13: 8" in run("scale", "--knowledge", knowledge(tmp_path / "set"))


def test_the_starter_knowledge_base_has_the_scale_and_the_estimate_still_reads_it():
    import estimate

    k = support.ROOT / "templates" / "knowledge"
    scale, issues = backlog.read_scale(k)
    assert scale == {} and issues == ["not set yet for 1, 2, 3, 5, 8, 13 points"]
    assert "BB-18" in estimate.read_blocks("Joget DX", k)[0] and "OW-06" in estimate.read_other_work(k)


# ====================================================================== the files
@pytest.fixture
def rendered(project, run, tmp_path):
    path, data = refined(project, run)
    (project / "uat").mkdir()
    (project / "uat" / "2026-11-07 uat scripts v0.1.json").write_text(json.dumps(
        {"cases": [{"id": "UAT-004", "requirements": ["FR-APP-002.2"]}]}), encoding="utf-8")
    (project / "changes").mkdir()
    (project / "changes" / "crs.json").write_text(json.dumps(
        {"crs": [{"id": "CR-001", "title": "Export to Excel", "cited": [{"ref": "FR-APP-003.1"}]}]}), encoding="utf-8")
    out = run("render", project, "--knowledge", knowledge(tmp_path))
    return path, data, out


def test_render_writes_the_five_files_next_to_the_backlog(rendered):
    path, _, out = rendered
    base = path.with_suffix("")
    for suffix in (".xlsx", " - traceability.xlsx", " - Project Desk import.xlsx", " - Jira import.csv", " - Azure DevOps import.csv"):
        assert (base.parent / f"{base.name}{suffix}").exists(), suffix
    assert "story points on 10" in out


def test_in_the_folder_layout_the_files_go_where_people_look_and_the_sources_in_blueprint(tmp_path, run):
    """The backlog came before the project folder layout and read and wrote the old folders only."""
    p = tmp_path / "laid-out"
    support.make_project(p, new=True)
    shutil.copytree(support.EXAMPLE / "estimates", layout.estimates_source(p))
    run("draft", p, "--date", "2026-11-07")
    source = layout.backlog_source(p) / "2026-11-07 backlog v0.1.json"
    assert source.exists() and source.parent.parent.name == "_blueprint"
    data = json.loads(source.read_text(encoding="utf-8"))
    assert data["estimate"] and (p / data["estimate"]).exists(), "the estimate is found in _blueprint/estimates"
    for s in data["stories"]:
        s["so_that"] = "the application is complete"
        s.pop("todo", None)
        s["acceptance"] = s["acceptance"] or ["It happens as the requirement says"]
    data.pop("unplaced", None)
    source.write_text(json.dumps(data, indent=2), encoding="utf-8")
    run("render", p, "--knowledge", knowledge(tmp_path))
    internal, client = p / layout.INTERNAL, p / layout.REQUIREMENTS
    assert (internal / "2026-11-07 backlog v0.1.xlsx").exists() and (internal / "2026-11-07 backlog v0.1 - Jira import.csv").exists()
    assert (client / "2026-11-07 backlog v0.1 - traceability.xlsx").exists(), "the client's sheet beside the requirements document"
    assert not list(layout.backlog_source(p).glob("*.xlsx")), "nothing for people inside _blueprint"


def test_the_team_workbook_shows_the_backlog_and_how_each_story_was_sized(rendered):
    path, _, _ = rendered
    wb = load_workbook(path.with_suffix(".xlsx"))
    assert wb.sheetnames == ["Summary", "Backlog", "Points"]
    rows = list(wb["Backlog"].values)
    assert rows[1][:4] == ("1", "Epic", "EP-01", "Apply for Leave") and rows[2][:3] == ("1.1", "Story", "US-001")
    assert rows[2][4].startswith("As an Employee, I want") and rows[2][7] == 2
    points = list(wb["Points"].values)
    assert points[1][2] == "L01 New Leave Application form: 20%" and points[1][3] == "0.6 – 1 MD"


def test_the_traceability_sheet_for_the_client_links_each_requirement_and_holds_no_estimate(rendered):
    path, _, _ = rendered
    ws = load_workbook(path.parent / f"{path.stem} - traceability.xlsx").active
    rows = list(ws.values)
    assert rows[3] == ("Requirement", "What it says", "Priority", "Screens", "User stories", "UAT scenarios", "Change requests")
    by = {r[0]: r for r in rows[4:]}
    assert len(by) == 10
    assert by["FR-APP-002.2"][4].startswith("US-007 ") and by["FR-APP-002.2"][5] == "UAT-004"
    assert by["FR-APP-003.1"][6] == "CR-001 Export to Excel"
    text = " ".join(str(c) for r in rows for c in r if c)
    assert not backlog.INTERNAL_WORDS.search(text) and "Points" not in text and "L01" not in text


def test_the_project_desk_file_has_its_tasks_sheet_with_epics_and_stories_nested_by_number(rendered):
    path, _, _ = rendered
    ws = load_workbook(path.parent / f"{path.stem} - Project Desk import.xlsx")["Tasks"]
    rows = list(ws.values)
    assert rows[0] == ("#", "Title", "Type", "Status", "Priority", "Story Points", "Description", "Acceptance Criteria")
    assert rows[1][:4] == ("1", "Apply for Leave", "Epic", "To do") and rows[2][:3] == ("1.1", rows[2][1], "Story")
    assert rows[2][5] == 2 and rows[2][4] == "P3 · Medium", "no priority agreed in the spec: Project Desk's default"
    assert rows[4][7] == "Number of Days is filled in by the system (Calculated: working days between From and To) and " \
        "cannot be changed\nFrom Date is required\nTo Date is required\nTo Date must be on or after From Date", \
        "one criterion a line, without numbers"
    assert "Story id in Blueprint: US-001" in rows[2][6]


def test_the_jira_file_makes_stories_children_of_their_epic(rendered):
    path, _, _ = rendered
    with open(path.parent / f"{path.stem} - Jira import.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Issue ID", "Parent", "Issue Type", "Summary", "Description", "Priority", "Story Points", "Labels"]
    assert rows[1][:3] == ["1", "", "Epic"] and rows[2][:3] == ["2", "1", "Story"]
    assert "Acceptance criteria:\n1. " in rows[2][4] and rows[2][6] == "2" and rows[2][7] == "LRS"


def test_the_azure_devops_file_nests_stories_under_a_feature_and_follows_the_process(rendered, project, run, tmp_path):
    path, _, _ = rendered
    name = path.parent / f"{path.stem} - Azure DevOps import.csv"
    with open(name, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Work Item Type", "Title 1", "Title 2", "Description", "Story Points", "Priority", "Tags"]
    assert rows[1][:3] == ["Feature", "Apply for Leave", ""] and rows[2][:2] == ["User Story", ""]
    assert rows[2][3].startswith("<p>As an Employee") and "<ol><li>" in rows[2][3]
    run("render", project, "--ado-process", "scrum", "--knowledge", tmp_path / "knowledge")
    with open(name, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Work Item Type", "Title 1", "Title 2", "Description", "Acceptance Criteria", "Effort", "Priority", "Tags"]
    assert rows[2][0] == "Product Backlog Item" and rows[2][4].startswith("<ol><li>") and "<ol>" not in rows[2][3]


def test_render_writes_nothing_while_there_are_mistakes(project, run, tmp_path):
    path, data = refined(project, run)
    data["stories"][0]["role"] = "director"
    path.write_text(json.dumps(data), encoding="utf-8")
    out = run("render", project, "--knowledge", knowledge(tmp_path), fail=True)
    assert "Nothing was written" in out and not path.with_suffix(".xlsx").exists()


def test_the_overview_lists_the_backlog_files_and_who_each_is_for(rendered, project):
    page = overview.build(project).read_text(encoding="utf-8")
    card = page[page.index("Development backlog"):]
    assert "Backlog v0.1</span>" in card and "Backlog v0.1 - traceability" in card and "For the client" in card
    assert "Backlog v0.1 - Project Desk import" in card and card.count('class="row"') == 5


def test_the_overview_has_no_backlog_card_before_there_is_a_backlog(project):
    assert "Development backlog" not in overview.build(project).read_text(encoding="utf-8")
