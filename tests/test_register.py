"""tools/register.py: adding, finding and updating items, validating a register and rendering the Excel file."""
import copy
import io
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
    shown = [ws.title for ws in workbook.worksheets if ws.sheet_state == "visible"]
    assert shown == ["For client", "Internal fixes", "All items", "Summary"]
    assert workbook[register.RENDERED].sheet_state == "veryHidden", "the note of what was written is out of sight"


def test_internal_items_never_reach_the_client_sheet(workbook):
    client = sheet_rows(workbook["For client"])
    assert [r[0] for r in client[1:]] == ["R-001", "R-002", "R-003"]
    flat = " ".join(str(cell) for row in client for cell in row)
    assert "R-004" not in flat and INTERNAL_TEXT not in flat
    for internal_only in ("Type", "Category", "Fix / recommendation", "Effort impact", "Audience", "Stage"):
        assert internal_only not in client[0], f"the client sheet must not have a '{internal_only}' column"


def test_client_sheet_is_what_the_ba_sends(workbook):
    client = sheet_rows(workbook["For client"])
    assert client[0] == ["ID", "Severity", "Document", "Where", "Observation", "Question for client",
                         "Our recommendation", "Client response", "Status", "Raised"]
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


# ====================================================================== what was typed into the Excel file
def type_into(project, sheet, item_id, column, value):
    """Change one cell of register.xlsx, as the BA does in Excel."""
    path = project / "register.xlsx"
    wb = load_workbook(path)
    ws = wb[sheet]
    head = [c.value for c in ws[1]]
    row = next(r for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=head.index("ID") + 1).value == item_id)
    ws.cell(row=row, column=head.index(column) + 1, value=value)
    wb.save(path)


def item(project, item_id):
    return next(it for it in json.loads((project / "register.json").read_text(encoding="utf-8"))["items"] if it["id"] == item_id)


def cell(project, sheet, item_id, column):
    ws = load_workbook(project / "register.xlsx")[sheet]
    head = [c.value for c in ws[1]]
    row = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[head.index("ID")] == item_id)
    return row[head.index(column)] or ""


@pytest.fixture
def rendered(tmp_path, monkeypatch, capsys):
    project = write_register(tmp_path / "typed", GOOD)
    run(monkeypatch, "render", project)
    capsys.readouterr()
    return project


OPEN_CLIENT = next(it["id"] for it in GOOD["items"] if it["audience"] == "client" and it["status"] == "open" and not it.get("answer"))


def test_an_answer_typed_into_excel_is_kept_when_the_file_is_written_again(rendered, monkeypatch, capsys):
    """The BA types the client's answers into register.xlsx. The next render used to write the file afresh
    from register.json and the answers were gone, without a word."""
    type_into(rendered, "For client", OPEN_CLIENT, "Client response", "Only the requester, before approval.")
    run(monkeypatch, "render", rendered)
    out = capsys.readouterr().out
    assert "Taken from register.xlsx into register.json:" in out and f"{OPEN_CLIENT} answer: Only the requester, before approval." in out
    assert item(rendered, OPEN_CLIENT)["answer"] == "Only the requester, before approval."
    assert item(rendered, OPEN_CLIENT)["status"] == "answered", "an answer moves an open question to answered"
    assert cell(rendered, "For client", OPEN_CLIENT, "Client response") == "Only the requester, before approval."
    assert cell(rendered, "All items", OPEN_CLIENT, "Answer / decision") == "Only the requester, before approval."


def test_a_status_changed_in_excel_is_kept(rendered, monkeypatch, capsys):
    type_into(rendered, "For client", OPEN_CLIENT, "Status", "asked")
    type_into(rendered, "Internal fixes", "R-004", "Status", "resolved")
    run(monkeypatch, "render", rendered)
    assert item(rendered, OPEN_CLIENT)["status"] == "asked" and item(rendered, "R-004")["status"] == "resolved"


def test_an_answer_with_its_own_status_keeps_that_status(rendered, monkeypatch, capsys):
    type_into(rendered, "For client", OPEN_CLIENT, "Client response", "Agreed.")
    type_into(rendered, "For client", OPEN_CLIENT, "Status", "resolved")
    run(monkeypatch, "render", rendered)
    assert (item(rendered, OPEN_CLIENT)["answer"], item(rendered, OPEN_CLIENT)["status"]) == ("Agreed.", "resolved")


def test_a_change_in_the_register_since_the_file_was_written_is_not_an_edit_in_excel(rendered, monkeypatch, capsys):
    """Blueprint updates register.json and then renders: the Excel file is simply behind, nothing was typed."""
    reg = json.loads((rendered / "register.json").read_text(encoding="utf-8"))
    next(it for it in reg["items"] if it["id"] == OPEN_CLIENT).update(status="resolved", answer="Decided in workshop 2.")
    write_register(rendered, reg)
    run(monkeypatch, "render", rendered)
    assert "Taken from register.xlsx" not in capsys.readouterr().out
    assert item(rendered, OPEN_CLIENT)["answer"] == "Decided in workshop 2."
    assert cell(rendered, "For client", OPEN_CLIENT, "Client response") == "Decided in workshop 2."


def test_rendering_twice_changes_nothing(rendered, monkeypatch, capsys):
    before = (rendered / "register.json").read_bytes()
    run(monkeypatch, "render", rendered)
    assert (rendered / "register.json").read_bytes() == before and "Taken from" not in capsys.readouterr().out


def test_excel_and_the_register_both_changed_stops_and_writes_nothing(rendered, monkeypatch, capsys):
    type_into(rendered, "For client", OPEN_CLIENT, "Client response", "The client says A.")
    reg = json.loads((rendered / "register.json").read_text(encoding="utf-8"))
    next(it for it in reg["items"] if it["id"] == OPEN_CLIENT)["answer"] = "Blueprint recorded B."
    write_register(rendered, reg)
    with pytest.raises(SystemExit) as stop:
        run(monkeypatch, "render", rendered)
    out = capsys.readouterr().out
    assert stop.value.code == 1 and "disagree. Nothing was written" in out
    assert f"{OPEN_CLIENT} answer: Excel has 'The client says A.', register.json has 'Blueprint recorded B.'" in out
    assert cell(rendered, "For client", OPEN_CLIENT, "Client response") == "The client says A.", "the Excel file is untouched"
    assert item(rendered, OPEN_CLIENT)["answer"] == "Blueprint recorded B."

    monkeypatch.setattr(sys, "argv", ["register.py", "render", str(rendered), "--overwrite"])
    register.main()
    assert cell(rendered, "For client", OPEN_CLIENT, "Client response") == "Blueprint recorded B.", "--overwrite takes the register"


def test_two_sheets_edited_differently_is_a_conflict(rendered, monkeypatch, capsys):
    type_into(rendered, "For client", OPEN_CLIENT, "Client response", "Yes.")
    type_into(rendered, "All items", OPEN_CLIENT, "Answer / decision", "No.")
    with pytest.raises(SystemExit):
        run(monkeypatch, "render", rendered)
    assert "the sheets of the Excel file disagree" in capsys.readouterr().out


def test_a_status_excel_does_not_know_is_refused(rendered, monkeypatch, capsys):
    type_into(rendered, "For client", OPEN_CLIENT, "Status", "done")
    with pytest.raises(SystemExit):
        run(monkeypatch, "render", rendered)
    assert f"{OPEN_CLIENT} status: 'done' in Excel is not one of" in capsys.readouterr().out
    assert item(rendered, OPEN_CLIENT)["status"] == "open"


def test_a_file_from_an_older_blueprint_still_gives_up_its_answers(rendered, monkeypatch, capsys):
    """It has no hidden sheet. An answer in Excel where the register has none is taken; anything else in it
    is left, because it cannot be told from the file simply being behind."""
    path = rendered / "register.xlsx"
    wb = load_workbook(path)
    del wb[register.RENDERED]
    wb.save(path)
    type_into(rendered, "For client", OPEN_CLIENT, "Client response", "Typed into the old file.")
    type_into(rendered, "Internal fixes", "R-004", "Status", "resolved")
    run(monkeypatch, "render", rendered)
    assert item(rendered, OPEN_CLIENT)["answer"] == "Typed into the old file."
    assert item(rendered, "R-004")["status"] == "open", "a status alone is not taken from a file without the note"


def sent_to_client(project, tmp_path):
    """The register.xlsx the BA sent to the client: a copy, kept apart from the project's own file."""
    copy_path = tmp_path / "returned" / "Register with our answers.xlsx"
    copy_path.parent.mkdir(exist_ok=True)
    copy_path.write_bytes((project / "register.xlsx").read_bytes())
    return copy_path


def type_into_copy(path, sheet, item_id, column, value):
    folder = path.parent
    (folder / "register.xlsx").unlink(missing_ok=True)
    path.rename(folder / "register.xlsx")
    type_into(folder, sheet, item_id, column, value)
    (folder / "register.xlsx").rename(path)


def render_from(monkeypatch, project, returned, *flags):
    monkeypatch.setattr(sys, "argv", ["register.py", "render", str(project), "--from", str(returned), *flags])
    register.main()


def test_a_register_returned_by_the_client_gives_up_its_answers(rendered, tmp_path, monkeypatch, capsys):
    """The client answers in the copy they were sent. --from takes those answers in, reads the copy only,
    and writes the project's own register.xlsx with them."""
    returned = sent_to_client(rendered, tmp_path)
    type_into_copy(returned, "For client", OPEN_CLIENT, "Client response", "Only HR may cancel.")
    before = returned.read_bytes()
    render_from(monkeypatch, rendered, returned)
    out = capsys.readouterr().out
    assert f"Taken from {returned.name} into register.json:" in out and f"{OPEN_CLIENT} answer: Only HR may cancel." in out
    assert (item(rendered, OPEN_CLIENT)["answer"], item(rendered, OPEN_CLIENT)["status"]) == ("Only HR may cancel.", "answered")
    assert cell(rendered, "For client", OPEN_CLIENT, "Client response") == "Only HR may cancel."
    assert returned.read_bytes() == before, "the returned file is only read"
    render_from(monkeypatch, rendered, returned)
    assert "Nothing new in" in capsys.readouterr().out, "taking the same copy twice changes nothing"


def test_the_bas_own_typing_is_taken_before_the_returned_copy(rendered, tmp_path, monkeypatch, capsys):
    returned = sent_to_client(rendered, tmp_path)
    type_into(rendered, "Internal fixes", "R-004", "Status", "resolved")
    type_into_copy(returned, "For client", OPEN_CLIENT, "Client response", "Yes, both.")
    render_from(monkeypatch, rendered, returned)
    assert item(rendered, "R-004")["status"] == "resolved" and item(rendered, OPEN_CLIENT)["answer"] == "Yes, both."


def test_a_returned_answer_to_an_item_changed_here_since_stops(rendered, tmp_path, monkeypatch, capsys):
    returned = sent_to_client(rendered, tmp_path)
    type_into_copy(returned, "For client", OPEN_CLIENT, "Client response", "The client says A.")
    monkeypatch.setattr(sys, "argv", ["register.py", "update", str(rendered), OPEN_CLIENT, "--set", "answer=Decided B in the call."])
    register.main()
    run(monkeypatch, "render", rendered)
    capsys.readouterr()
    with pytest.raises(SystemExit) as stop:
        render_from(monkeypatch, rendered, returned)
    out = capsys.readouterr().out
    assert stop.value.code == 1 and "register.xlsx was not written" in out
    assert f"{OPEN_CLIENT} answer: the returned file has 'The client says A.', register.json has 'Decided B in the call.'" in out
    assert item(rendered, OPEN_CLIENT)["answer"] == "Decided B in the call."


@pytest.mark.parametrize("name, message", [("missing.xlsx", "No file at"), ("not-excel.xlsx", "Cannot read")])
def test_a_returned_file_that_cannot_be_read_is_refused(rendered, tmp_path, monkeypatch, name, message):
    (tmp_path / "not-excel.xlsx").write_text("plain text", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        render_from(monkeypatch, rendered, tmp_path / name)
    assert message in str(stop.value) and "Nothing was written" in str(stop.value)


def test_an_excel_file_that_is_open_gives_a_plain_message(rendered, monkeypatch, capsys):
    from openpyxl import Workbook

    def locked(self, path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Workbook, "save", locked)
    with pytest.raises(SystemExit) as stop:
        run(monkeypatch, "render", rendered)
    assert "close it in Excel and run this again" in str(stop.value)


def test_an_unknown_option_shows_the_usage(tmp_path, monkeypatch):
    project = write_register(tmp_path / "usage", GOOD)
    monkeypatch.setattr(sys, "argv", ["register.py", "render", str(project), "--force"])
    with pytest.raises(SystemExit) as stop:
        register.main()
    assert "--overwrite" in str(stop.value)


# ====================================================================== add, similar and update
NEW = {"type": "gap", "audience": "client", "severity": "medium", "category": "GP-05", "stage": "workshop-2",
       "source": "v1.1 screen booking-list", "finding": "The booking list has no filter by department.",
       "question": "Should managers filter the booking list by department?"}
INTERNAL = {"type": "fix", "audience": "internal", "severity": "low", "category": "hygiene", "stage": "requirements-draft",
            "source": "v1.1 cover page", "finding": "The cover page still names a café from another template."}


def run_args(monkeypatch, *args, stdin=None):
    monkeypatch.setattr(sys, "argv", ["register.py", *map(str, args)])
    if stdin is not None:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(stdin.encode("utf-8")), encoding="utf-8"))
    register.main()


def items_file(tmp_path, data, name="items.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path):
    return write_register(tmp_path / "add", GOOD)


def saved(project):
    return json.loads((project / "register.json").read_text(encoding="utf-8"))


def test_add_gives_the_next_ids_and_fills_the_defaults(project, tmp_path, monkeypatch, capsys):
    run_args(monkeypatch, "add", project, "--file", items_file(tmp_path, [NEW, INTERNAL]))
    out = capsys.readouterr().out
    assert "Added 2 items to register.json: R-005 to R-006" in out and "Next: python -I tools/register.py render" in out
    reg = saved(project)
    assert [it["id"] for it in reg["items"]] == ["R-001", "R-002", "R-003", "R-004", "R-005", "R-006"]
    added = reg["items"][4]
    assert added["status"] == "open" and added["raised"] == register.date.today().isoformat()
    assert list(added) == [f for f in register.FIELDS if f in added], "fields are written in the documented order"
    assert reg["items"][5]["finding"] == INTERNAL["finding"]
    assert register.validate(reg) == []
    raw = (project / "register.json").read_text(encoding="utf-8")
    assert raw == json.dumps(reg, indent=2, ensure_ascii=False) + "\n" and "café" in raw, "same formatting, text kept as written"
    assert not list(project.glob(".register-*")), "no temporary file is left behind"


def test_add_ignores_an_id_it_was_given_and_keeps_raised_and_status(project, tmp_path, monkeypatch, capsys):
    item = dict(NEW, id="R-001", status="asked", raised="2026-10-30")
    run_args(monkeypatch, "add", project, "--file", items_file(tmp_path, item))
    assert "the id R-001 it carried is not used; it is R-005" in capsys.readouterr().out
    added = saved(project)["items"][-1]
    assert (added["id"], added["status"], added["raised"]) == ("R-005", "asked", "2026-10-30")
    assert [it["id"] for it in saved(project)["items"]].count("R-001") == 1


def test_add_after_a_gap_never_reuses_an_id(tmp_path, monkeypatch, capsys):
    reg = copy.deepcopy(GOOD)
    reg["items"] = [it for it in reg["items"] if it["id"] != "R-002"]
    folder = write_register(tmp_path / "gap", reg)
    run_args(monkeypatch, "add", folder, "--file", items_file(tmp_path, NEW))
    assert saved(folder)["items"][-1]["id"] == "R-005"


def test_one_bad_item_refuses_the_whole_batch_and_writes_nothing(project, tmp_path, monkeypatch, capsys):
    before = (project / "register.json").read_bytes()
    no_question = {k: v for k, v in NEW.items() if k != "question"}
    bad = [NEW, dict(INTERNAL, severity="critical"), no_question, dict(NEW, colour="red", effort_impact="huge")]
    with pytest.raises(SystemExit) as stop:
        run_args(monkeypatch, "add", project, "--file", items_file(tmp_path, bad))
    out = capsys.readouterr().out
    assert stop.value.code == 1 and "Nothing was added" in out
    assert "item 2 (R-006): severity 'critical' not in ['high', 'low', 'medium']" in out, "the same rule and message as validate"
    assert "item 3 (R-007): client items need a question" in out
    assert "item 4 (R-008): unknown field 'colour'" in out and "item 4 (R-008): effort_impact 'huge' not in" in out
    assert (project / "register.json").read_bytes() == before


@pytest.mark.parametrize("content, message", [("", "is empty"), ("{not json", "is not valid JSON"), ("[]", "Give one item"),
                                              ('["text"]', "item 1: not an item")])
def test_add_refuses_input_that_is_not_items(project, tmp_path, monkeypatch, capsys, content, message):
    path = tmp_path / "items.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        run_args(monkeypatch, "add", project, "--file", path)
    assert message in str(stop.value.code) + capsys.readouterr().out
    assert saved(project) == GOOD


def test_add_reads_standard_input_and_a_file_with_a_bom(project, tmp_path, monkeypatch, capsys):
    run_args(monkeypatch, "add", project, stdin=json.dumps({"items": [NEW]}))
    assert "Added 1 item to register.json: R-005" in capsys.readouterr().out
    bom = tmp_path / "bom.json"
    bom.write_text(json.dumps(INTERNAL, ensure_ascii=False), encoding="utf-8-sig")  # as Windows PowerShell saves it
    run_args(monkeypatch, "add", project, "--file", bom)
    assert saved(project)["items"][-1]["finding"] == INTERNAL["finding"]
    run_args(monkeypatch, "add", project, "--file", "-", stdin=json.dumps(NEW))
    assert [it["id"] for it in saved(project)["items"][-3:]] == ["R-005", "R-006", "R-007"]


def test_add_names_likely_duplicates_and_still_writes(project, tmp_path, monkeypatch, capsys):
    again = dict(NEW, finding="Two bookings of the same equipment may overlap; the brief is silent.",
                 question="Can two people book the same equipment for overlapping dates?")
    run_args(monkeypatch, "add", project, "--file", items_file(tmp_path, [again, NEW, NEW]))
    out = capsys.readouterr().out
    assert "R-005 may be a duplicate of R-001 (similarity" in out
    assert "R-007 may be a duplicate of R-006 (similarity 1.00" in out, "items of the same batch are compared too"
    assert "R-006 may be a duplicate" not in out, "a new subject is not flagged"
    assert len(saved(project)["items"]) == 7


def test_add_check_writes_nothing(project, tmp_path, monkeypatch, capsys):
    before = (project / "register.json").read_bytes()
    same = dict(NEW, question="May two people book the same equipment for overlapping dates?")
    run_args(monkeypatch, "add", project, "--file", items_file(tmp_path, same), "--check")
    out = capsys.readouterr().out
    assert "Checked, nothing written: 1 item would be added as R-005." in out and "may be a duplicate of R-001" in out
    assert (project / "register.json").read_bytes() == before


def test_similarity_reads_past_wording():
    assert register.similarity({"question": "Should the Storekeeper receive an email when bookings are approved?"},
                               GOOD["items"][1]) >= register.DUPLICATE
    assert register.similarity({"question": "Which currencies does the invoice support?"}, GOOD["items"][1]) < 0.2
    assert register.words("The e-mails were approved") == {"email", "approv"}


def test_similar_lists_the_closest_items(project, monkeypatch, capsys):
    run_args(monkeypatch, "similar", project, "Does the storekeeper get an e-mail when a booking is approved?")
    lines = capsys.readouterr().out.splitlines()
    assert lines[1].split()[0] == "R-002" and "asked" in lines[1]
    run_args(monkeypatch, "similar", project, "currency", "of", "invoices")
    assert "No existing item reads like it" in capsys.readouterr().out


def test_update_answers_and_resolves(project, monkeypatch, capsys):
    run_args(monkeypatch, "update", project, "R-001", "--set", "status=resolved", "--set", "answer=No, never.",
             "--set", "resolved_in=Workshop 2", "--set", "owner=")
    out = capsys.readouterr().out
    assert "R-001 status: open -> resolved" in out and "R-001 owner: Operations -> (removed)" in out
    it = saved(project)["items"][0]
    assert (it["status"], it["answer"], it["resolved_in"]) == ("resolved", "No, never.", "Workshop 2") and "owner" not in it
    assert list(it) == [f for f in register.FIELDS if f in it], "new fields go in their documented place"


def test_update_an_answer_alone_moves_the_item_to_answered(project, monkeypatch, capsys):
    run_args(monkeypatch, "update", project, "R-001", "R-002", "--set", "answer=Yes.")
    assert [it["status"] for it in saved(project)["items"][:2]] == ["answered", "answered"]


@pytest.mark.parametrize("sets, message", [
    (["colour=red"], "unknown field 'colour'"), (["id=R-009"], "id cannot be changed"),
    (["status=done"], "R-001: status 'done' not in"), (["finding="], "R-001: missing finding"),
    (["effort_impact=huge"], "effort_impact 'huge' not in"), (["due=soon"], "due 'soon' is not a date"),
    (["status"], "write it as field=value")])
def test_update_refuses_and_writes_nothing(project, monkeypatch, capsys, sets, message):
    before = (project / "register.json").read_bytes()
    with pytest.raises(SystemExit) as stop:
        run_args(monkeypatch, "update", project, "R-001", *[a for s in sets for a in ("--set", s)])
    out = capsys.readouterr().out
    assert stop.value.code == 1 and "Nothing was changed" in out and message in out
    assert (project / "register.json").read_bytes() == before


def test_update_an_unknown_item_is_refused(project, monkeypatch, capsys):
    with pytest.raises(SystemExit):
        run_args(monkeypatch, "update", project, "R-001", "R-099", "--set", "status=asked")
    assert "R-099: no such item in the register" in capsys.readouterr().out
    assert saved(project)["items"][0]["status"] == "open", "nothing changed, not even the item that exists"


@pytest.mark.parametrize("args", [["update", "R-001"], ["similar"], ["add", "--file"], ["add", "--set", "x=y"]])
def test_new_commands_show_the_usage_when_misused(project, monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["register.py", args[0], str(project), *args[1:]])
    with pytest.raises(SystemExit) as stop:
        register.main()
    assert "register.py add" in str(stop.value)


# ---------------------------------------------------------------- readable references
@pytest.mark.parametrize("source, document, where", [
    ("SRS v1.0 Appendix A item 4 (p82); Figure 5 (p30); Figure 8 T&Cs (p36)",
     "SRS v1.0", "Appendix A item 4 · page 82\nFigure 5 · page 30\nFigure 8 T&Cs · page 36"),
    ("SRS v1.0 §2.1/§2.2 Loan Request Form; FR-LR-001",
     "SRS v1.0", "Section 2.1, Section 2.2 Loan Request Form\nFR-LR-001"),
    ("SRS v1.0 §1.5.1 row 2 (p9-10); 4.3.1 (p31)",
     "SRS v1.0", "Section 1.5.1 row 2 · pages 9–10\nSection 4.3.1 · page 31"),
    ("SRS v1.0 Figure 8 (4.6 T&Cs, p36)", "SRS v1.0", "Figure 8 (4.6 T&Cs) · page 36"),
    ("URS draft v0.3 section 4 (pp. 12-14)", "URS draft v0.3", "Section 4 · pages 12–14"),
    ("Mock-up v0.1 FB-001, New Loan Request, Estimated Repair Days",
     "Mock-up v0.1", "comment FB-001, New Loan Request, Estimated Repair Days"),
    ("v1.0 §3.2 FR-REQ-003.1", "v1.0", "Section 3.2 FR-REQ-003.1"),
    ("Figure 2", "", "Figure 2"),
    ("Word draft, heading 'Approvals'", "", "Word draft, heading 'Approvals'"),
])
def test_a_reference_reads_as_the_document_and_each_place_on_its_own_line(source, document, where):
    """The Excel file shows where an item was found as the document, said once, and each place on a line of
    its own in plain words; a note in a style the rules do not know is shown as it is."""
    assert register.readable_reference(source) == (document, where)


def test_a_long_quote_in_a_reference_is_shortened_and_the_columns_replace_the_old_one(workbook):
    _, where = register.readable_reference("SRS v1.0 §2.1 'Customer Information to be retrieved from 3 In 1'; Figure 5 (p30)")
    assert where.split("\n")[0] == "Section 2.1 'Customer Information to be ret…'"
    for name in ("For client", "Internal fixes", "All items"):
        header = sheet_rows(workbook[name])[0]
        assert "Reference" not in header and header.index("Where") == header.index("Document") + 1


def test_the_workbook_follows_the_design_language(rendered):
    """docs/design-language.md, Spreadsheets: a quiet header, no gridlines, severity and status as a dot and a
    coloured word, the client's response as a field to fill in, and the internal sheets marked."""
    import sheets

    wb = load_workbook(register.layout.register_xlsx(rendered))
    ws = wb["For client"]
    header = [c.value for c in ws[1]]
    head = ws.cell(row=1, column=1)
    assert head.fill.fgColor.rgb.endswith(sheets.HEAD_FILL) and head.font.color.rgb.endswith(sheets.GREY) and head.font.bold
    assert not ws.sheet_view.showGridLines
    response = header.index("Client response") + 1
    assert ws.cell(row=1, column=response).font.color.rgb.endswith(sheets.ACCENT), "the column to fill in, in the accent"
    assert ws.cell(row=2, column=response).fill.fgColor.rgb.endswith(sheets.INPUT_FILL)
    for name in ("Severity", "Status"):
        cell = ws.cell(row=2, column=header.index(name) + 1)
        assert cell.number_format == sheets.DOT_FORMAT and cell.value.lower() == cell.value.lower().lstrip("● "), "the value is the word alone"
    rules = {rule.formula[0] for rng in ws.conditional_formatting for rule in rng.rules}
    assert {'"High"', '"asked"', '"resolved"'} <= rules
    assert "Internal" in wb["Internal fixes"].oddHeader.center.text and not ws.oddHeader.center.text


def test_the_file_for_the_client_holds_the_client_items_alone_in_every_sheet(rendered, monkeypatch, capsys):
    """The register's own file has internal sheets and a hidden one with every item's answer, so cutting it by
    hand still sent internal work. The file to send is written apart, with nothing of an internal item in it."""
    import zipfile

    out = rendered / "Questions for the client.xlsx"
    assert out.exists()
    wb = load_workbook(out)
    assert wb.sheetnames == ["For client", register.RENDERED] and wb["For client"].sheet_state == "visible"
    ids = {row[0] for ws in wb.worksheets for row in sheet_rows(ws)[1:] if row and row[0]}
    assert ids == {it["id"] for it in GOOD["items"] if it["audience"] == "client"}
    raw = b"".join(zipfile.ZipFile(out).read(n) for n in zipfile.ZipFile(out).namelist())
    assert b"R-004" not in raw and INTERNAL_TEXT.encode() not in raw, "not in any sheet, hidden or not"
    # The client fills it in and sends it back: their answer is taken in like one typed into the register.
    ws = wb["For client"]
    header = [c.value for c in ws[1]]
    row = next(r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == OPEN_CLIENT)
    ws.cell(row, header.index("Client response") + 1, "Answered by the client")
    returned = rendered / "returned.xlsx"
    wb.save(returned)
    monkeypatch.setattr(sys, "argv", ["register.py", "render", str(rendered), "--from", str(returned)])
    register.main()
    assert "Send this one to the client" in capsys.readouterr().out
    reg = json.loads((rendered / "register.json").read_text(encoding="utf-8"))
    assert next(it for it in reg["items"] if it["id"] == OPEN_CLIENT)["answer"] == "Answered by the client"



def test_render_warns_when_a_client_item_speaks_of_effort(tmp_path, monkeypatch, capsys):
    reg = copy.deepcopy(GOOD)
    item = next(it for it in reg["items"] if it["audience"] == "client")
    item["recommendation"] = "Drop it: saves 4 mandays"
    project = write_register(tmp_path / "words", reg)
    run(monkeypatch, "render", project)
    assert f"Check {item['id']} before sending: its recommendation says 'mandays'" in capsys.readouterr().out
