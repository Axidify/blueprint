"""tools/register.py: validating a register and rendering the Excel file for the BA."""
import copy
import json
import sys

import pytest
from openpyxl import load_workbook

import support

import register

GOOD = json.loads((support.WIDE / "register.json").read_text(encoding="utf-8"))
INTERNAL_TEXT = "INTERNAL-ONLY-MARKER"  # in the finding of the fixture's one internal item, R-004


def with_item(**changes):
    """The good register with fields of its first item changed; None removes a field."""
    reg = copy.deepcopy(GOOD)
    for key, value in changes.items():
        if value is None:
            reg["items"][0].pop(key, None)
        else:
            reg["items"][0][key] = value
    return reg


def write_register(folder, reg):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "register.json").write_text(json.dumps(reg), encoding="utf-8")
    return folder


def run(monkeypatch, command, project):
    monkeypatch.setattr(sys, "argv", ["register.py", command, str(project)])
    register.main()


def sheet_rows(ws):
    return [[cell if cell is not None else "" for cell in row] for row in ws.iter_rows(values_only=True)]


# ====================================================================== validation
def test_good_register_is_accepted():
    assert register.validate(GOOD) == []
    assert register.validate({"project": "Empty", "client": "Sample", "items": []}) == []


@pytest.mark.parametrize("field", register.REQUIRED)
def test_missing_required_field_is_rejected(field):
    where = "item #1" if field == "id" else "R-001"  # without an id, the item is named by its position
    assert f"{where}: missing {field}" in register.validate(with_item(**{field: None}))


def test_empty_required_field_is_rejected():
    assert register.validate(with_item(finding="")) == ["R-001: missing finding"]


def test_unknown_stage_is_rejected():
    errors = register.validate(with_item(stage="kickoff"))
    assert len(errors) == 1 and errors[0].startswith("R-001: stage 'kickoff' not in [")


@pytest.mark.parametrize("stage", ["sow", "workshop-1", "mockup", "workshop-2", "requirements-draft", "requirements-final",
                                   "development", "uat", "srs-draft", "srs-final"])
def test_every_documented_stage_is_accepted(stage):
    assert register.validate(with_item(stage=stage)) == []


@pytest.mark.parametrize("field, value", [("type", "bug"), ("audience", "everyone"), ("severity", "critical"), ("status", "closed")])
def test_unknown_values_are_rejected(field, value):
    errors = register.validate(with_item(**{field: value}))
    assert len(errors) == 1 and errors[0].startswith(f"R-001: {field} '{value}' not in [")


def test_client_item_needs_a_question():
    assert register.validate(with_item(question=None)) == ["R-001: client items need a question"]
    internal_without_question = [it for it in GOOD["items"] if it["audience"] == "internal" and "question" not in it]
    assert internal_without_question, "the fixture has an internal item without a question, and it is valid"


def test_duplicate_id_is_rejected():
    reg = copy.deepcopy(GOOD)
    reg["items"][1]["id"] = "R-001"
    assert register.validate(reg) == ["R-001: duplicate id"]


def test_every_problem_is_reported_at_once():
    reg = with_item(stage="kickoff", severity=None)
    reg["items"][3]["status"] = "closed"
    assert register.validate(reg) == ["R-001: missing severity", "R-001: stage 'kickoff' not in " + str(sorted(register.STAGES)),
                                      "R-004: status 'closed' not in " + str(sorted(register.STATUSES))]


def test_next_id_follows_the_highest():
    assert register.next_id(GOOD) == "R-005"
    assert register.next_id({"items": []}) == "R-001"
    gap = copy.deepcopy(GOOD)
    gap["items"] = [it for it in gap["items"] if it["id"] in ("R-001", "R-004")]
    assert register.next_id(gap) == "R-005", "ids are never reused, even after a gap"


# ====================================================================== the command line
def test_validate_command_passes_a_good_register(tmp_path, monkeypatch, capsys):
    run(monkeypatch, "validate", write_register(tmp_path / "good", GOOD))
    assert capsys.readouterr().out.strip() == "OK: 4 items"


@pytest.mark.parametrize("command", ["validate", "render"])
def test_bad_register_stops_the_command(tmp_path, monkeypatch, capsys, command):
    project = write_register(tmp_path / "bad", with_item(stage="kickoff"))
    with pytest.raises(SystemExit) as stop:
        run(monkeypatch, command, project)
    assert stop.value.code == 1
    assert "R-001: stage 'kickoff'" in capsys.readouterr().out
    assert not (project / "register.xlsx").exists(), "nothing is rendered from a register that fails validation"


def test_missing_register_is_reported(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="No register at"):
        run(monkeypatch, "validate", tmp_path)


def test_next_id_command(tmp_path, monkeypatch, capsys):
    run(monkeypatch, "next-id", write_register(tmp_path / "good", GOOD))
    assert capsys.readouterr().out.strip() == "R-005"


# ====================================================================== the Excel file
@pytest.fixture
def workbook(tmp_path, monkeypatch, capsys):
    project = write_register(tmp_path / "render", GOOD)
    run(monkeypatch, "render", project)
    assert "3 client items, 1 internal fixes" in capsys.readouterr().out
    return load_workbook(project / "register.xlsx")


def test_workbook_has_the_four_sheets(workbook):
    assert workbook.sheetnames == ["For client", "Internal fixes", "All items", "Summary"]


def test_internal_items_never_reach_the_client_sheet(workbook):
    client = sheet_rows(workbook["For client"])
    assert [r[0] for r in client[1:]] == ["R-001", "R-002", "R-003"]
    flat = " ".join(str(cell) for row in client for cell in row)
    assert "R-004" not in flat and INTERNAL_TEXT not in flat
    for internal_only in ("Type", "Category", "Fix / recommendation", "Effort impact", "Audience", "Stage"):
        assert internal_only not in client[0], f"the client sheet must not have a '{internal_only}' column"


def test_client_sheet_is_what_the_ba_sends(workbook):
    client = sheet_rows(workbook["For client"])
    assert client[0] == ["ID", "Severity", "Reference", "Observation", "Question for client", "Our recommendation",
                         "Client response", "Status", "Raised"]
    first = dict(zip(client[0], client[1]))
    assert first["Severity"] == "High"
    assert first["Question for client"] == "May two people book the same equipment for overlapping dates?"
    assert first["Status"] == "open"


def test_internal_sheet_has_only_internal_items(workbook):
    internal = sheet_rows(workbook["Internal fixes"])
    assert [r[0] for r in internal[1:]] == ["R-004"]
    assert INTERNAL_TEXT in internal[1][internal[0].index("Finding")]


def test_all_items_sheet_puts_closed_items_last(workbook):
    everything = sheet_rows(workbook["All items"])
    assert [r[0] for r in everything[1:]] == ["R-001", "R-002", "R-004", "R-003"], "open by severity, then resolved"
    audience = everything[0].index("Audience")
    assert [r[audience] for r in everything[1:]] == ["client", "client", "internal", "client"]


def test_summary_counts(workbook):
    summary = {r[0]: r[1] for r in sheet_rows(workbook["Summary"]) if r[0]}
    assert summary["Total items"] == 4
    assert (summary["client"], summary["internal"]) == (3, 1)
    assert (summary["high"], summary["medium"], summary["low"]) == (1, 2, 1)
