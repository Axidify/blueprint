"""tools/close.py: the close-out drafted from the project's own records, change requests held against the signed
version, and the knowledge base written only on apply. Also the TEST marker of the projects log
(estimate.logged_projects) and the warning when a CR marked New reads like the signed version.

Every project is a temp copy of the made-up sample, issued with project.py (test_change_request's fixtures);
the knowledge base is a temp copy of the starter one, never the workspace's.
"""
import json
import shutil
import sys

import pytest

import support

import change_request as cr_tool
import close
import estimate
from test_change_request import IN_SCOPE, NEW, STARTER, new_project, write_log


@pytest.fixture(autouse=True)
def starter_knowledge(monkeypatch):
    monkeypatch.setattr(cr_tool, "knowledge_dir", lambda: STARTER)


@pytest.fixture
def run(monkeypatch, capsys):
    def call(tool, *args):
        monkeypatch.setattr(sys, "argv", [f"{tool.__name__}.py", *map(str, args)])
        tool.main()
        return capsys.readouterr().out
    return call


@pytest.fixture
def issued(temp_workspace, run):
    return new_project(temp_workspace / "projects", run=run)


@pytest.fixture
def kdir(tmp_path):
    k = tmp_path / "knowledge"
    shutil.copytree(STARTER, k)
    return k


ACTUALS = {"phase": "Phase 1", "team": "1 developer", "test": True, "sold_md": 20,
           "actual": [{"area": "Forms and workflow", "md": 18}, {"area": "Reports", "md": 6}, {"area": "UAT support", "md": 3, "kind": "testing"}],
           "crs": [{"title": "Cancel leave that is already approved, before it starts", "md": 2},
                   {"title": "Export all applications to Excel", "md": 3, "cr": "CR-001"}],
           "lessons": ["The approval rules took longer than counted"]}


def actuals(project, **changes):
    (project / "close").mkdir(exist_ok=True)
    (project / "close" / "actuals.json").write_text(json.dumps({**ACTUALS, **changes}), encoding="utf-8")


def test_change_requests_in_the_signed_version_are_flagged(issued, run):
    """At close-out the lead developer listed as CRs items that were in the signed version, and nothing noticed."""
    write_log(issued, {**NEW, "status": "built", "sold_md": 3}, IN_SCOPE)
    actuals(issued)
    out = run(close, "check", issued)
    assert "Change requests held against v0.1" in out
    assert "Cancel leave that is already approved, before it starts: probably in v0.1: FR-APP-003.1" in out
    assert "CR-002 Cancel an approved application: in scope of v0.1 (its CR log verdict)" in out
    assert "Export all applications to Excel: no close match" in out, "a New CR the signed version does not have stays a CR"
    assert "2 of 3 look like part of the signed version" in out


def test_a_verdict_given_at_close_out_is_kept(issued, run):
    write_log(issued, {**NEW, "status": "built", "sold_md": 3})
    actuals(issued, crs=[{"title": "Cancel leave that is already approved, before it starts", "md": 2, "verdict": "new"}])
    assert "no close match" in run(close, "check", issued)


def test_the_draft_is_a_proposal_and_leaves_the_knowledge_base_alone(issued, run, kdir):
    write_log(issued, {**NEW, "status": "built", "sold_md": 3}, IN_SCOPE)
    actuals(issued)
    before = {f.name: f.read_text(encoding="utf-8") for f in kdir.rglob("*.md")}
    out = run(close, "draft", issued)
    assert "Nothing was written to the knowledge base" in out
    assert {f.name: f.read_text(encoding="utf-8") for f in kdir.rglob("*.md")} == before
    draft = (issued / "close" / close.DRAFT).read_text(encoding="utf-8")
    assert draft.startswith("# Leave Request System – actuals (TEST DATA)")
    assert "| Development sold | 20 |" in draft and "| CRs billed | 3 |" in draft and "| Total billed for development | 23 |" in draft
    assert "| Actual development | 24 (Forms and workflow 18, Reports 6) |" in draft
    assert "| Actual testing and UAT support | 3 (UAT support 3) |" in draft
    assert "| Variance | +1 MD (+4%) |" in draft
    crs_table = draft.split("## Change requests", 1)[1].split("##", 1)[0]
    assert "CR-001 Export all applications to Excel | new | 3 | 3 | GP-04 |" in crs_table
    assert "Cancel" not in crs_table, "what was in the signed version is not a change request"
    signed = draft.split("## Listed as change requests, but in the signed v0.1", 1)[1]
    assert "Cancel leave that is already approved, before it starts (2 MD): probably in v0.1: FR-APP-003.1" in signed
    assert "CR-002 Cancel an approved application: in scope of v0.1" in signed
    proposal = (issued / "close" / close.PROPOSAL).read_text(encoding="utf-8")
    assert "| leave-request (TEST) | Joget DX | Phase 1 | 1 developer | 20 | 3 | 24 | +1 MD (+4%) | 1 (1 billed) | TEST DATA." in proposal
    assert "GP-04: Cost evidence – leave-request CR-001 (new, 3 MD spent)" in proposal
    assert "FR-APP-003" not in proposal.split("## 3.", 1)[1].split("## 4.", 1)[0], "no gap evidence from an in-scope item"


def test_figures_not_given_stay_not_given(issued, run):
    actuals(issued, sold_md=None, crs=[], test=False)
    out = run(close, "draft", issued)
    assert "Development sold is not given" in out
    draft = (issued / "close" / close.DRAFT).read_text(encoding="utf-8")
    assert "| Development sold | not given |" in draft and "cannot be worked out: nothing sold to compare with" in draft
    assert "TEST" not in draft
    assert "**Not given yet:** development sold" in (issued / "close" / close.PROPOSAL).read_text(encoding="utf-8")


def test_apply_writes_only_after_a_draft_and_keeps_an_existing_record(issued, run, kdir):
    with pytest.raises(SystemExit, match="Nothing drafted"):
        run(close, "apply", issued, "--knowledge", kdir)
    actuals(issued)
    run(close, "draft", issued)
    out = run(close, "apply", issued, "--knowledge", kdir)
    assert "knowledge/actuals/leave-request.md" in out and "row added" in out
    assert (kdir / "actuals" / "leave-request.md").read_text(encoding="utf-8").startswith("# Leave Request System – actuals (TEST DATA)")
    log = (kdir / "projects-log.md").read_text(encoding="utf-8")
    assert log.count("| leave-request (TEST) |") == 1
    with pytest.raises(SystemExit, match="exists: nothing was written"):
        run(close, "apply", issued, "--knowledge", kdir)
    actuals(issued, test=False, team="2 developers")
    run(close, "draft", issued)
    assert "row replaced" in run(close, "apply", issued, "--knowledge", kdir, "--only", "log")
    log = (kdir / "projects-log.md").read_text(encoding="utf-8")
    assert "| leave-request (TEST) |" not in log and log.count("| leave-request |") == 1 and "2 developers" in log


def test_test_rows_of_the_projects_log_are_not_delivered_projects(issued, run, kdir):
    """A TEST row in projects-log.md would make later estimates on the platform look calibrated."""
    actuals(issued)
    run(close, "draft", issued)
    run(close, "apply", issued, "--knowledge", kdir, "--only", "log")
    assert estimate.logged_projects("Joget DX", kdir) == (set(), set())
    actuals(issued, test=False)
    run(close, "draft", issued)
    run(close, "apply", issued, "--knowledge", kdir, "--only", "log")
    assert estimate.logged_projects("Joget DX", kdir) == ({"leave-request"}, {"leave-request"})


@pytest.mark.parametrize("header, row, test", [
    (["project", "notes"], ["courtesy-car", "First project."], False),
    (["project", "notes"], ["lps", "TEST DATA. No SOW figures."], True),
    (["project", "notes"], ["lps (TEST)", ""], True),
    (["project", "notes"], ["lps", "Tested in UAT; contest won"], False),
    (["project", "test", "notes"], ["lps", "yes", ""], True),
    (["project", "test", "notes"], ["lps", "no", ""], False),
])
def test_the_test_marker(header, row, test):
    assert estimate.is_test_row(header, row) is test


def test_a_new_cr_that_reads_like_the_signed_version_is_questioned_when_logged(issued, run, tmp_path):
    f = tmp_path / "cr.json"
    f.write_text(json.dumps({**NEW, "title": "Cancel approved leave", "lines": [], "assumptions": [],
                             "request": "Employees want to cancel an approved application before the leave starts."}), encoding="utf-8")
    out = run(cr_tool, "add", issued, "--file", f)
    assert "Check: CR-001 is marked New, but v0.1 has FR-APP-003.1" in out
    f.write_text(json.dumps(NEW), encoding="utf-8")
    assert "Check:" not in run(cr_tool, "add", issued, "--file", f)
