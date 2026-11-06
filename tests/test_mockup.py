"""The mock-up tool: the build, the spec checks (status colours, typos, buttons that move a record to another
status), the server that saves comments, and (where Node and Microsoft Edge are installed) the mock-up
itself, clicked through in the browser."""
import io
import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

import support
import mockup

BROWSER_SCRIPT = support.ROOT / "tests" / "mockup_browser.mjs"

# Statuses for the colour tests. The first three have no colour and are guessed from their wording; the
# guess used to read "active", "approved" and "available" inside them and show them green.
GUESSED = {"LV-T-1": "Inactive", "LV-T-2": "Not Approved", "LV-T-3": "Unavailable"}
# These two take their colour from the spec, against what the wording would suggest.
COLOURED = {"LV-T-4": ("On Hold", "amber"), "LV-T-5": ("Active Review", "red")}


def mockup_spec():
    """The sample spec with extra statuses and records for the colour tests, a dialog whose confirm button
    goes nowhere, and a dialog with no confirm button of its own."""
    spec = support.load_spec(support.EXAMPLE)
    row = spec["data"]["applications"][0]
    for record, status in {**GUESSED, **{k: v[0] for k, v in COLOURED.items()}}.items():
        spec["data"]["applications"].append({**row, "id": record, "status": status})
    for name, color in COLOURED.values():
        spec["statuses"].append({"id": name.lower().replace(" ", "-"), "name": name, "meaning": "Made up for the tests.", "color": color})
    dialogs = {d["id"]: d for d in spec["dialogs"]}
    del dialogs["approve-dialog"]["confirm"]["to"]
    spec["dialogs"].append({"id": "info-dialog", "title": "Information", "message": "Nothing to confirm."})
    # A second step on the form, and a search box on a list, for the tests of kept input and of searching.
    new_application = next(s for s in spec["screens"] if s["id"] == "new-application")
    new_application["sections"].append({"title": "More", "page": 2, "page_title": "More", "fields": [{"id": "note", "label": "Note", "type": "text"}]})
    next(s for s in spec["screens"] if s["id"] == "approvals")["list"]["search"] = ["employee"]
    # For the tests of status moves: an employee role without a named person, and an action that moves its row.
    del next(r for r in spec["roles"] if r["id"] == "employee")["user"]
    next(s for s in spec["screens"] if s["id"] == "approvals")["list"]["actions"].append(
        {"label": "Approve now", "set_status": "approved", "toast": "Application approved"})
    return spec


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The mock-up of that spec, built once in a temp folder."""
    project = tmp_path_factory.mktemp("mockup") / "leave-request"
    support.write_spec(project, mockup_spec())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "stdout", io.StringIO())
        mockup.build(project)
    return project


@pytest.fixture
def served(built, tmp_path):
    """The built mock-up on a free port, with a feedback file of the test's own."""
    server = serve_in_thread(built / "mockup", tmp_path / "feedback" / "feedback.json")
    yield server
    server.shutdown()
    server.server_close()


def serve_in_thread(mock, fb_file):
    server = mockup.make_server(mock, fb_file, "127.0.0.1", 0)
    server.fb_file = fb_file
    server.url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def post(server, body):
    """POST raw bytes to the feedback address. Returns (status, parsed answer)."""
    request = urllib.request.Request(server.url + "api/feedback", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def saved(server):
    return json.loads(server.fb_file.read_text(encoding="utf-8")) if server.fb_file.exists() else []


# ---------------------------------------------------------------------- build
def test_build_writes_a_mockup_that_opens_on_its_own(built):
    mock = built / "mockup"
    for name in ("index.html", "spec.js", "assets/app.js", "assets/base.css", "assets/theme.css"):
        assert (mock / name).is_file(), name
    assert (mock / "spec.js").read_text(encoding="utf-8").startswith("window.SPEC = ")
    assert (mock / "versions" / "v0.1" / "index.html").is_file()  # this version is kept


# ---------------------------------------------------------------------- status colours in the spec
@pytest.mark.parametrize("color", ["green", "amber", "red", "grey", "gray", "Red"])
def test_a_status_may_name_its_colour(color):
    spec = mockup_spec()
    spec["statuses"][0]["color"] = color
    assert mockup.validate(spec) == []


def test_an_unknown_status_colour_is_a_spec_error():
    spec = mockup_spec()
    spec["statuses"][0]["color"] = "purple"
    errors = mockup.validate(spec)
    assert len(errors) == 1
    assert "status draft" in errors[0] and "purple" in errors[0] and "green, amber, red, grey" in errors[0]


def test_the_status_colours_reach_the_mockup(built):
    spec = json.loads((built / "mockup" / "spec.js").read_text(encoding="utf-8").removeprefix("window.SPEC = ").rstrip().rstrip(";"))
    colours = {s["name"]: s.get("color") for s in spec["statuses"]}
    assert colours["On Hold"] == "amber" and colours["Active Review"] == "red" and colours["Draft"] == "grey"


# ---------------------------------------------------------------------- the server that saves comments
def test_a_comment_is_saved_with_an_id(served):
    status, answer = post(served, json.dumps({"screen": "approvals", "element": "column:Status", "text": "Add a column"}).encode())
    assert status == 200 and answer["id"] == "FB-001" and answer["received"]
    post(served, json.dumps({"screen": "approvals", "text": "Second"}).encode())
    assert [(c["id"], c["text"]) for c in saved(served)] == [("FB-001", "Add a column"), ("FB-002", "Second")]
    with urllib.request.urlopen(served.url + "api/feedback", timeout=10) as answer:
        assert [c["id"] for c in json.loads(answer.read())] == ["FB-001", "FB-002"]


@pytest.mark.parametrize("body", [b"{oops", b"[1, 2]", b'"text"', b"{}", b'{"text": "   "}', b"\xff\xfe"])
def test_what_is_not_a_comment_is_refused_with_an_answer(served, body):
    """The mock-up keeps a comment in the browser when the server says no, so it must say no, not hang up."""
    status, answer = post(served, body)
    assert status == 400 and "error" in answer
    assert saved(served) == []


def test_a_comment_is_saved_even_when_the_console_cannot_show_it(served, monkeypatch):
    """A console that cannot print the characters used to turn a saved comment into a failed request."""
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="ascii"))
    status, answer = post(served, json.dumps({"screen": "approvals", "text": "批准后通知 ✓"}).encode())
    assert status == 200 and answer["id"] == "FB-001"
    assert saved(served)[0]["text"] == "批准后通知 ✓"


def test_only_the_mockup_folder_is_served(served):
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(served.url + "../spec/app.yaml", timeout=10)
    assert e.value.code == 404


# ---------------------------------------------------------------------- one mock-up per port
def test_a_second_server_cannot_take_the_same_port(served, built, tmp_path):
    """On Windows a second server used to start on the same port without an error."""
    port = served.server_address[1]
    with pytest.raises(OSError):
        mockup.make_server(built / "mockup", tmp_path / "other" / "feedback.json", "127.0.0.1", port)


def test_serve_stops_with_the_reason_when_the_port_is_taken(served, built, monkeypatch, capsys):
    port = served.server_address[1]
    opened = []
    monkeypatch.setattr(mockup.webbrowser, "open", opened.append)
    with pytest.raises(SystemExit) as e:
        mockup.serve(built, port, lan=False)
    message = str(e.value)
    assert f"port {port}" in message and "already in use" in message and f"--port {port + 1}" in message
    assert opened == []  # no browser window for a mock-up that did not start


def test_the_port_is_free_again_after_the_server_stops(built, tmp_path):
    first = serve_in_thread(built / "mockup", tmp_path / "a.json")
    port = first.server_address[1]
    first.shutdown()
    first.server_close()
    second = mockup.make_server(built / "mockup", tmp_path / "b.json", "127.0.0.1", port)
    second.server_close()


# ---------------------------------------------------------------------- do the screenshots still show the spec?
def form(spec):
    return next(s for s in spec["screens"] if s["type"] == "form")


@pytest.mark.parametrize("change", [
    lambda s: form(s)["sections"][0]["fields"].append({"id": "phone", "label": "Contact Number", "type": "text"}),
    lambda s: form(s)["sections"][0]["fields"][0].update(label="Staff Name"),
    lambda s: s["screens"][1].update(title="My Leave"),
    lambda s: s["data"]["applications"][0].update(status="Approved"),
    lambda s: s["data"]["applications"].__setitem__(0, dict(reversed(list(s["data"]["applications"][0].items())))),
    lambda s: s["roles"][0].update(name="Staff"),
    lambda s: s["statuses"][0].update(color="amber"),
    lambda s: s["dialogs"][0].update(title="Approve Leave"),
    lambda s: s["project"].update(primary_color="#aa0000"),
    lambda s: s["project"].update(theme="modern"),
    lambda s: next(x for x in s["screens"] if x.get("list") and x["list"].get("where"))["list"].update(where={"status": "Approved"}),
], ids=["new-field", "field-label", "screen-title", "sample-data", "data-key-order", "role-name", "status-colour",
        "dialog-title", "colour", "theme", "list-filter"])
def test_what_the_mockup_draws_changes_the_fingerprint(change):
    spec = mockup_spec()
    before = mockup.fingerprint(spec)
    change(spec)
    assert mockup.fingerprint(spec) != before


@pytest.mark.parametrize("change", [
    lambda s: s["requirements"][0]["items"].append("A new requirement."),
    lambda s: s["project"].update(version="0.2", date="2026-12-01", status="Final", prepared_by="Someone"),
    lambda s: s["screens"][1].update(description="Reworded.", caption="Reworded caption"),
    lambda s: form(s)["sections"][0]["fields"][0].update(validation="Reworded", source="Reworded", length=250),
    lambda s: s["roles"][0].update(description="Reworded.", scope="Reworded"),
    lambda s: s["statuses"][0].update(meaning="Reworded."),
    lambda s: s.update(overview=["Reworded."], signoff=[{"name": "A. Person", "organisation": "Client"}], glossary=[{"term": "LM", "meaning": "Line manager"}]),
    lambda s: next(x for x in s["screens"] if x.get("stats"))["stats"][-1].update(formula="Reworded: what it counts."),
    lambda s: s["statuses"][0].update(edit="all", cancel="none", next=[]),
    lambda s: s["integrations"][0].update(trigger="Reworded.", on_failure="Reworded."),
    lambda s: s["dialogs"][0]["confirm"].pop("set_status"),
], ids=["requirement", "version-and-cover", "screen-description", "field-rule", "role-text", "status-meaning", "document-chapters",
        "figure-formula", "status-rules", "integration-details", "status-move"])
def test_what_only_the_document_prints_leaves_the_fingerprint(change):
    spec = mockup_spec()
    before = mockup.fingerprint(spec)
    change(spec)
    assert mockup.fingerprint(spec) == before


def test_a_condition_on_a_data_field_named_like_a_document_key_still_counts():
    """`where: {source: Online}` filters the list on a data field called source: it changes the screen."""
    spec = mockup_spec()
    listing = next(x for x in spec["screens"] if x.get("list"))["list"]
    listing["where"] = {"source": "Online"}
    before = mockup.fingerprint(spec)
    listing["where"] = {"source": "Counter"}
    assert mockup.fingerprint(spec) != before


def test_taking_screenshots_notes_the_screens_they_show(tmp_path, monkeypatch, capsys):
    """The screenshot command with the browser step faked: it leaves the note the document generator reads,
    in the folder and in the kept copy of this mock-up version."""
    project = tmp_path / "leave-request"
    support.write_spec(project, mockup_spec())
    called = []
    monkeypatch.setattr(mockup.subprocess, "run", lambda command, **kw: called.append(command) or subprocess.CompletedProcess(command, 0))
    mockup.screenshots(project)
    assert called and called[0][0] == "node"
    note = json.loads((project / "mockup" / "screenshots" / mockup.RECORD).read_text(encoding="utf-8"))
    assert note["screens"] == mockup.fingerprint(mockup.load_spec(project)) and note["taken"]
    assert (project / "mockup" / "versions" / "v0.1" / "screenshots" / mockup.RECORD).is_file()


def test_screenshot_problems_names_what_is_wrong(tmp_path):
    project = support.make_project(tmp_path / "leave-request", spec=mockup_spec())
    spec = mockup.load_spec(project)
    assert mockup.screenshot_problems(project, spec) == []

    (project / "mockup" / "screenshots" / "approvals.png").unlink()
    (project / "mockup" / "screenshots" / "leave-types.png").unlink()
    problems = mockup.screenshot_problems(project, spec)
    assert len(problems) == 1 and problems[0].startswith("no picture for approvals, leave-types: ")

    form(spec)["sections"][0]["fields"][0]["label"] = "Staff Name"
    problems = mockup.screenshot_problems(project, spec)
    assert len(problems) == 2 and problems[0].startswith("the screens in the spec changed after the screenshots were taken")
    assert all(f"python -I tools/mockup.py screenshots {project}" in p for p in problems)


def test_screenshot_problems_copes_with_a_damaged_note_or_list(tmp_path):
    project = support.make_project(tmp_path / "leave-request", spec=mockup_spec())
    spec = mockup.load_spec(project)
    (project / "mockup" / "screenshots" / mockup.RECORD).write_text("not json", encoding="utf-8")
    assert mockup.screenshot_problems(project, spec) == []  # no note to compare with: the list of shots still matches
    (project / "mockup" / "shots.json").write_text("not json", encoding="utf-8")
    assert len(mockup.screenshot_problems(project, spec)) == 1


# ---------------------------------------------------------------------- spec typos that used to build without error
def listing(spec, screen_id="approvals"):
    return next(s for s in spec["screens"] if s["id"] == screen_id)["list"]


@pytest.mark.parametrize("change, said", [
    (lambda s: listing(s)["columns"][0].update(field="idd"), "screen approvals: column 'idd' is not a field of the 'applications' data (did you mean 'id'?)"),
    (lambda s: listing(s, "my-applications").update(filters=["statuz"]), "filter field 'statuz' is not a field of the 'applications' data (did you mean 'status'?)"),
    (lambda s: listing(s).update(search=["nobody"]), "search field 'nobody' is not a field of the 'applications' data (it has "),
    (lambda s: listing(s).update(where={"state": "Pending Approval"}), "'where' 'state' is not a field of the 'applications' data"),
    (lambda s: listing(s)["actions"][0].update(when={"stage": "Draft"}), "action Review: 'when' 'stage' is not a field"),
    (lambda s: next(x for x in s["screens"] if x["id"] == "my-applications")["stats"][0].update(count={"statuss": ["Approved"]}), "'count' 'statuss' is not a field"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from="leave_types.title"), "options_from 'title' is not a field of the 'leave_types' data"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from="leavetypes.name"), "options_from 'leavetypes.name' must be <data list>.<field>"),
    (lambda s: form(s)["sections"][0]["fields"][0].update(type="texarea"), "type 'texarea' is not one of"),
    (lambda s: listing(s).update(colums=listing(s).pop("columns")), "'colums' is not a list setting (did you mean 'columns'?)"),
    (lambda s: s["screens"][1].update(tittle="My Leave"), "'tittle' is not a screen setting (did you mean 'title'?)"),
    (lambda s: form(s)["sections"][0]["fields"][0].update(requierd=True), "'requierd' is not a field setting (did you mean 'required'?)"),
    (lambda s: next(x for x in s["screens"] if x["id"] == "application-details").update(record="LV-0000"), "record 'LV-0000' is not in the 'applications' data"),
    (lambda s: s["screenshots"][0].update(record="LV-0000"), "record 'LV-0000' is not in the 'applications' data"),
    (lambda s: s["screenshots"][0].update(role="boss"), "unknown role 'boss'"),
    (lambda s: s["screens"][1].update(screenshot_role="boss"), "screenshot_role 'boss' is not a role"),
    (lambda s: s["roles"].append(dict(s["roles"][0])), "role id 'employee' is used more than once"),
    (lambda s: s["dialogs"].append(dict(s["dialogs"][0])), "dialog id 'approve-dialog' is used more than once"),
], ids=["column", "filter", "search", "where", "action-when", "stat-count", "options-field", "options-list", "field-type",
        "misspelt-list-key", "misspelt-screen-key", "misspelt-field-key", "screen-record", "screenshot-record", "screenshot-role",
        "screenshot_role", "duplicate-role", "duplicate-dialog"])
def test_a_typo_in_the_spec_is_reported_instead_of_showing_blanks(change, said):
    """Each of these used to build: the mock-up showed an empty column, an empty drop-down, the first
    record in place of the one asked for, or simply ignored the setting."""
    spec = json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))
    assert mockup.validate(spec) == []
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


def test_the_sample_specs_pass_the_check():
    for source in (support.EXAMPLE, support.WIDE):
        spec = json.loads(json.dumps(support.load_spec(source), default=str))
        assert mockup.validate(spec) == [], source.name


def test_keys_the_format_does_not_know_are_left_alone_unless_they_look_like_a_typo():
    spec = json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))
    spec["screens"][1]["ba_note"] = "ask about the balance"
    form(spec)["sections"][0]["fields"][0]["ticket"] = "JIRA-12"
    assert mockup.validate(spec) == []


def test_a_column_called_no_is_not_mistaken_for_a_typo():
    """YAML reads an unquoted `no` as false, as a record's key and as a column's field alike, and the
    mock-up shows the column all the same."""
    spec = support.load_spec(support.EXAMPLE)
    spec["data"]["leave_types"] = [{False: 1, "name": "Annual Leave"}, {False: 2, "name": "Medical Leave"}]
    listing(spec, "leave-types")["columns"] = [{"field": False, "label": "No"}, {"field": "name", "label": "Leave Type"}]
    assert mockup.validate(json.loads(json.dumps(spec, default=str))) == []


# ---------------------------------------------------------------------- buttons that move a record to another status
def sample():
    return json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))


def screen(spec, screen_id):
    return next(s for s in spec["screens"] if s["id"] == screen_id)


def confirm(spec, dialog_id):
    return next(d for d in spec["dialogs"] if d["id"] == dialog_id)["confirm"]


@pytest.mark.parametrize("change, said", [
    (lambda s: confirm(s, "approve-dialog").update(set_status="aproved"),
     "dialog approve-dialog, button Confirm Approve: set_status 'aproved' is not a status (did you mean 'approved'?)"),
    (lambda s: confirm(s, "approve-dialog").update(set_status="draft"),
     "dialog approve-dialog, button Confirm Approve: moves a record from Pending Approval to Draft, but in the status rules "
     "Pending Approval may only move to Approved, Rejected, Cancelled. Change the button, or the status's 'next'"),
    (lambda s: listing(s, "my-applications")["actions"].append({"label": "Reopen", "set_status": "Pending Approval", "when": {"status": "Cancelled"}}),
     "screen my-applications, button Reopen: moves a record from Cancelled to Pending Approval, but in the status rules "
     "Cancelled is a final status (next: [])"),
    (lambda s: listing(s)["actions"].append({"label": "Send back", "set_status": "draft"}),
     "screen approvals, button Send back: moves a record from Pending Approval to Draft"),  # the list's `where` says where it is
    (lambda s: screen(s, "my-applications").update(buttons=[{"label": "Approve all", "set_status": "approved"}]),
     "screen my-applications, button Approve all: set_status has no record to move here"),
    (lambda s: listing(s).update(toolbar=[{"label": "Approve all", "set_status": "approved"}]),
     "screen approvals, button Approve all: set_status has no record to move here"),
    (lambda s: listing(s, "leave-types")["actions"].append({"label": "Retire", "set_status": "cancelled"}),
     "screen leave-types, button Retire: set_status changes a record's 'status' field, and the 'leave_types' data has none"),
    (lambda s: screen(s, "review-application")["buttons"][1].update(set_statuss="rejected"),
     "'set_statuss' is not a button setting (did you mean 'set_status'?)"),
    (lambda s: confirm(s, "cancel-dialog").update(label=True),
     "dialog cancel-dialog: a button's label reads as true, not as text. YAML takes an unquoted Yes, No, On or Off for true or false"),
], ids=["unknown-status", "against-the-rules", "from-a-final-status", "source-from-the-list", "no-record-on-a-dashboard", "no-record-on-a-toolbar",
        "data-without-status", "misspelt", "label-read-as-true"])
def test_a_status_move_that_cannot_work_or_breaks_the_status_rules_is_refused(change, said):
    spec = sample()
    assert mockup.validate(spec) == []
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


def test_a_status_without_rules_lets_a_button_move_it_anywhere():
    """The rules are optional: a status that has none set is not checked."""
    spec = sample()
    for status in spec["statuses"]:
        status.pop("next")
    confirm(spec, "approve-dialog")["set_status"] = "Draft"   # by name, in any letter case, works as the id does
    assert mockup.validate(spec) == []


def test_the_moves_of_the_sample_are_made_by_its_three_dialogs():
    spec = sample()
    moves = {(m["where"], m["label"]): m for m in mockup.status_moves(spec)}
    assert set(moves) == {("dialog approve-dialog", "Confirm Approve"), ("dialog reject-dialog", "Confirm Reject"),
                          ("dialog cancel-dialog", "Yes, cancel it")}
    cancel = moves[("dialog cancel-dialog", "Yes, cancel it")]
    assert [s["id"] for s in cancel["sources"]] == ["pending", "approved"], "where the button that opens the dialog shows"
    assert cancel["record"] and cancel["data"] == "applications"


def test_the_moves_the_rules_allow_but_no_button_makes_are_listed():
    spec = sample()
    assert mockup.moves_not_shown(spec) == ["Draft to Pending Approval", "Rejected to Pending Approval"]
    for dialog in spec["dialogs"]:
        dialog["confirm"].pop("set_status", None)
    assert mockup.moves_not_shown(spec) == [], "a mock-up that moves nothing is not told what it leaves out"


def test_build_says_how_many_buttons_move_a_record_and_what_is_left_out(tmp_path, capsys):
    project = tmp_path / "leave-request"
    support.write_spec(project, sample())
    mockup.build(project)
    out = capsys.readouterr().out
    assert "3 buttons move a record to another status when clicked (until the page is reloaded)." in out
    assert "which no button of the mock-up makes: Draft to Pending Approval; Rejected to Pending Approval." in out


# ---------------------------------------------------------------------- the fingerprint does not move with an update
def test_the_fingerprint_of_an_unchanged_spec_is_what_0_7_0_computed():
    """The document generator compares this value with the one noted when the screenshots were taken. If a
    change to Blueprint alters it, every project's screenshots look out of date after the update, for no
    reason. If this test fails, undo the change to `drawn`; if the change is truly needed, say in the
    changelog that screenshots must be taken again."""
    spec = json.loads(json.dumps(support.load_spec(support.WIDE), default=str))
    assert mockup.fingerprint(spec) == "7438bfca2a36857e159f1129994b38f59f8bbb11ea8db8a75d342ae96820faf5"


# ---------------------------------------------------------------------- an issued version keeps its mock-up
def test_the_saved_mockup_of_an_issued_version_is_not_replaced(tmp_path, capsys):
    """Rebuilding used to overwrite mockup/versions/v<version>/ every time, also after that version had
    gone to the client: showing "what the client saw" then showed something else."""
    project = tmp_path / "leave-request"
    spec = mockup_spec()
    support.write_spec(project, spec)
    mockup.build(project)
    kept = project / "mockup" / "versions" / "v0.1" / "spec.js"
    as_issued = kept.read_text(encoding="utf-8")
    (project / "output").mkdir()
    (project / "output" / "issued.json").write_text(json.dumps([{"version": "0.1", "date": "2026-11-10", "to": "SAMPLE", "files": []}]), encoding="utf-8")

    spec["screens"][1]["title"] = "Changed after it was issued"
    support.write_spec(project, spec)
    capsys.readouterr()
    mockup.build(project)
    out = capsys.readouterr().out
    assert kept.read_text(encoding="utf-8") == as_issued, "the client's version is untouched"
    assert "Changed after it was issued" in (project / "mockup" / "spec.js").read_text(encoding="utf-8"), "the working mock-up is rebuilt"
    assert "v0.1 was issued to SAMPLE on 2026-11-10" in out and "bump project.version" in out

    spec["project"]["version"] = "0.2"
    support.write_spec(project, spec)
    mockup.build(project)
    assert "Changed after it was issued" in (project / "mockup" / "versions" / "v0.2" / "spec.js").read_text(encoding="utf-8")
    assert kept.read_text(encoding="utf-8") == as_issued


def test_a_version_not_yet_issued_is_replaced_on_every_build(tmp_path):
    project = tmp_path / "leave-request"
    spec = mockup_spec()
    support.write_spec(project, spec)
    mockup.build(project)
    spec["screens"][1]["title"] = "Second draft"
    support.write_spec(project, spec)
    mockup.build(project)
    assert "Second draft" in (project / "mockup" / "versions" / "v0.1" / "spec.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- real screenshots
WIDE_LIST = {"id": "wide-list", "type": "list", "title": "Every Column", "menu": "Every Column", "roles": ["hr"],
             "list": {"data": "applications",
                      "columns": [{"field": f, "label": f"{f.replace('_', ' ').title()} of the application"}
                                  for f in ("id", "employee", "leave_type", "from", "to", "days", "reason", "status", "submitted")] * 2}}
FLOW = {"title": "Leave process", "steps": [{"name": "Apply", "role": "Employee", "status": "Pending Approval"},
                                           {"name": "Approve", "role": "Line Manager", "status": "Approved"}]}


@pytest.fixture(scope="module")
def pictures(tmp_path_factory):
    """The screenshot command for real, in Microsoft Edge: {shot name: (width, height) in pixels} and what
    it printed. Skipped where Node, the Node packages or Edge are missing, as on GitHub."""
    from PIL import Image

    if not shutil.which("node") or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or `npm install`)")
    project = tmp_path_factory.mktemp("pictures") / "leave-request"
    spec = mockup_spec()
    spec["screens"].append(WIDE_LIST)
    spec["process_flow"] = FLOW
    support.write_spec(project, spec)
    run = subprocess.run([sys.executable, "-I", str(support.ROOT / "tools" / "mockup.py"), "screenshots", str(project)],
                         cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stdout + run.stderr
    sizes = {p.stem: Image.open(p).size for p in (project / "mockup" / "screenshots").glob("*.png")}
    return {"sizes": sizes, "log": run.stdout, "planned": [s["name"] for s in mockup.shot_list(mockup.load_spec(project))]}


def test_every_planned_screenshot_is_taken(pictures):
    assert sorted(pictures["sizes"]) == sorted(pictures["planned"])


def test_screens_are_taken_narrow_so_their_text_is_readable_in_the_document(pictures):
    """1000 px wide at twice the pixels. At the old 1440 px the mock-up's text printed at about 4 pt."""
    narrow = {name: size for name, size in pictures["sizes"].items() if name != "wide-list"}
    assert {size[0] for size in narrow.values()} == {2000}, narrow


def test_a_screen_that_does_not_fit_is_taken_wider_and_says_so(pictures):
    assert pictures["sizes"]["wide-list"][0] in (2400, 2880)
    assert "wide-list.png (taken" in pictures["log"] and "it does not fit in 1000" in pictures["log"]


def test_screenshots_are_cropped_to_the_content(pictures):
    """No minimum height: a list with two rows and the process flow are short pictures, not half-empty ones."""
    sizes = pictures["sizes"]
    assert sizes["approvals"][1] < 800 and sizes["process-flow"][1] < 700
    assert sizes["new-application-p1"][1] > sizes["approvals"][1] + 300, "a form is as tall as its fields"
    assert 800 < sizes["login"][1] < 1400, "the login card with space around it"
    assert sizes["review-application-reject"][1] >= sizes["review-application"][1], "a dialog never shortens its screen"


# ---------------------------------------------------------------------- in the browser
@pytest.fixture(scope="module")
def browser(built, tmp_path_factory):
    """The mock-up clicked through in Microsoft Edge by tests/mockup_browser.mjs. Skipped where Node, the
    Node packages (`npm install`) or Edge are missing, as on GitHub."""
    node = shutil.which("node")
    if not node or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or `npm install`)")
    server = serve_in_thread(built / "mockup", tmp_path_factory.mktemp("browser-feedback") / "feedback.json")
    try:
        run = subprocess.run([node, str(BROWSER_SCRIPT), server.url, *GUESSED, *COLOURED],
                             cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=180)
    finally:
        server.shutdown()
        server.server_close()
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    seen["saved"]["file"] = seen["afterRetry"]["file"] = saved(server)
    return seen


def test_the_mockup_runs_without_script_errors(browser):
    assert browser["errors"] == []


def test_negative_statuses_are_not_shown_green(browser):
    for record, status in GUESSED.items():
        assert browser["chips"][record] == "chip bad", status


def test_a_status_colour_from_the_spec_wins_over_the_guess(browser):
    assert browser["chips"]["LV-T-4"] == "chip warn"   # On Hold: amber in the spec, grey by its wording
    assert browser["chips"]["LV-T-5"] == "chip bad"    # Active Review: red in the spec, green by its wording


def test_a_confirm_button_that_goes_nowhere_closes_its_dialog(browser):
    after = browser["confirmWithoutTarget"]
    assert not after["dialog"] and after["screen"] == "review-application" and "dialog=" not in after["hash"]
    assert after["toasts"] == ["Application approved"]


def test_the_default_ok_button_closes_its_dialog(browser):
    after = browser["defaultOk"]
    assert not after["dialog"] and after["screen"] == "review-application"


def test_a_confirm_button_still_goes_to_its_screen(browser):
    after = browser["confirmWithTarget"]
    assert not after["dialog"] and after["screen"] == "approvals" and after["toasts"] == ["Application rejected"]


def test_cancel_closes_a_dialog_and_stays_on_the_screen(browser):
    after = browser["cancel"]
    assert not after["dialog"] and after["screen"] == "review-application" and after["toasts"] == []


# Status moves. The record is Daniel Tan's pending application, LV-2026-011; the manager is Ahmad Faiz.
def test_a_dialog_only_moves_the_record_when_it_is_confirmed(browser):
    before, opened = browser["moveBefore"], browser["moveDialogOpen"]
    assert before["status"] == opened["status"] == "Pending Approval"
    assert before["buttons"] == ["Back", "Reject", "Approve"]


def test_approving_moves_the_record_and_the_screen_follows(browser):
    """It used to show a message and leave the record as it was."""
    after = browser["moveApproved"]
    assert after["screen"] == "review-application" and after["toasts"] == ["Application approved"]
    assert after["status"] == "Approved" and after["chip"] == "chip ok"
    assert after["buttons"] == ["Back"], "Approve and Reject are for a pending application only"


def test_the_step_that_was_waiting_is_recorded_with_who_when_and_the_comment(browser):
    done, handled = browser["moveApproved"]["timeline"]
    assert done == ["Submitted", "Nur Aisyah", "2026-11-05 09:12", "Done", "-"]
    assert handled[:2] == ["Line Manager Approval", "Ahmad Faiz"] and handled[3:] == ["Approved", "Enjoy the break"]
    assert len(handled[2]) == 16 and handled[2][:2] == "20", "the time it was clicked, written like the sample data"


def test_a_moved_record_leaves_the_list_it_no_longer_belongs_to(browser):
    assert browser["moveApprovalsAfter"] == ["LV-2026-014"]
    assert browser["moveRejectedList"] == ["LV-2026-014"]


def test_every_screen_shows_the_moved_record_the_same_way(browser):
    elsewhere = browser["moveSeenElsewhere"]
    assert elsewhere["screen"] == "application-details" and elsewhere["status"] == "Approved"
    assert elsewhere["timeline"][1][3:] == ["Approved", "Enjoy the break"]
    rejected = browser["moveRejected"]
    assert rejected["status"] == "Rejected" and rejected["chip"] == "chip bad"
    assert rejected["timeline"][1][3:] == ["Rejected", "Year-end freeze"]


def test_a_reload_puts_the_sample_data_back(browser):
    again = browser["moveAfterReload"]
    assert again["status"] == "Pending Approval" and again["buttons"] == ["Back", "Reject", "Approve"]


def test_counts_follow_a_moved_record(browser):
    before, after = browser["moveFiguresBefore"], browser["moveFiguresAfter"]
    assert int(after["Pending"]) == int(before["Pending"]) - 1
    assert after["Approved"] == before["Approved"] and after["Rejected"] == before["Rejected"]
    assert browser["moveCancelledRow"].startswith("LV-2026-014 ") and " Cancelled " in browser["moveCancelledRow"]


def test_after_a_final_status_nothing_is_left_waiting(browser):
    cancelled = browser["moveCancelled"]
    assert cancelled["status"] == "Cancelled" and cancelled["buttons"] == ["Back"]
    assert [row[3] for row in cancelled["timeline"]] == ["Done", "Cancelled"]
    assert cancelled["timeline"][1][1] == "Employee", "handled by whoever is signed in: a role without a name shows its own"


def test_an_action_on_a_row_moves_that_row_and_stays_on_the_page(browser):
    after = browser["moveRowAction"]
    assert len(after["rows"]) == 1 and after["rows"][0].startswith("LV-2026-011 "), "the first row was approved and left the list"
    assert after["pager"] == "Showing 1 of 1 records" and after["toasts"] == ["Application approved"]


def test_a_filter_is_applied_by_search_and_removed_by_clear_filters(browser):
    """Filters, search boxes and their two buttons used to do nothing when clicked."""
    before, picked, filtered, cleared = (browser[k] for k in ("listBefore", "listPickedNotApplied", "listFiltered", "listCleared"))
    total = len(before["rows"])
    assert total >= 2 and before["pager"] == f"Showing {total} of {total} records"
    assert picked["rows"] == before["rows"], "choosing a value does nothing until Search is pressed, as in the real system"
    assert filtered["rows"] and all(" Approved " in f" {row} " for row in filtered["rows"]) and len(filtered["rows"]) < total
    assert filtered["pager"] == f"Showing {len(filtered['rows'])} of {total} records"
    assert cleared["rows"] == before["rows"] and browser["filterAfterClear"] == "All"


def test_a_search_box_matches_part_of_the_text_in_any_letter_case(browser):
    found = browser["searched"]
    assert len(found["rows"]) == 1 and "Daniel Tan" in found["rows"][0] and found["pager"] == "Showing 1 of 2 records"


def test_a_search_that_finds_nothing_says_so(browser):
    nothing = browser["searchedNone"]
    assert nothing["rows"] == [] and nothing["noneShown"] and nothing["pager"] == "Showing 0 of 2 records"


def test_what_was_typed_survives_moving_between_the_steps_of_a_form(browser):
    """The page is drawn again on every move, which used to empty every field already filled in."""
    assert browser["typedBack"] == {"reason": "Family trip", "typeKept": True}
    assert browser["typedStep2"] == "Back on Monday"


def test_a_form_starts_clean_when_it_is_opened_again(browser):
    assert browser["typedAfterLeaving"] == ""


def test_a_comment_the_server_takes_is_shown_as_saved(browser):
    state = browser["saved"]
    assert state["pins"] == 1 and state["unsentPins"] == 0 and state["kept"] == [] and state["errorToasts"] == []
    assert "Saved to the project folder." in state["panel"] and "not saved" not in state["toggle"]


def test_a_comment_the_server_does_not_take_is_kept_and_flagged(browser):
    state = browser["failed"]
    assert state["kept"] == ["typed while the server is down"]
    assert len(state["errorToasts"]) == 1 and "NOT saved" in state["errorToasts"][0]
    assert "1 not saved" in state["toggle"]
    assert state["pins"] == 2 and state["unsentPins"] == 1
    assert "1 comment not saved to the project yet." in state["panel"] and "Saved to the project folder." not in state["panel"]


def test_an_unsaved_comment_survives_a_reload(browser):
    state = browser["afterReload"]
    assert state["kept"] == ["typed while the server is down"] and state["unsentPins"] == 1 and "1 not saved" in state["toggle"]


def test_try_again_saves_the_kept_comment_once(browser):
    state = browser["afterRetry"]
    assert state["kept"] == [] and state["unsentPins"] == 0 and state["pins"] == 2
    assert "Saved to the project folder." in state["panel"] and "not saved" not in state["toggle"]
    assert [c["text"] for c in state["file"]] == ["saved while the server is up", "typed while the server is down", "from another laptop"]


def test_a_comment_saved_by_someone_else_appears_without_a_reload(browser):
    """Each page used to show only the comments that were there when it loaded, so people in the room did
    not see each other's comments, and the same comment had a different number on every laptop."""
    state = browser["afterOthers"]
    assert state["pins"] == browser["afterRetry"]["pins"] + 1 and "from another laptop" in state["panel"]
    assert browser["numbersShown"] == ["1", "2"], "a pin shows the number the comment was saved under (FB-001 is 1)"
    assert browser["numbersAfterOthers"] == ["1", "2", "3"]


def test_lan_addresses_are_this_machines_and_never_the_loopback(monkeypatch):
    for address in mockup.lan_addresses():
        assert address.count(".") == 3 and not address.startswith("127.")

    class NoNetwork:
        def __init__(self, *a, **k):
            raise OSError("no network")

    monkeypatch.setattr(mockup.socket, "socket", NoNetwork)
    monkeypatch.setattr(mockup.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 0)), (None, None, None, None, ("192.168.1.20", 0))])
    assert mockup.lan_addresses() == ["192.168.1.20"]


def test_serving_for_the_room_prints_the_address_to_share(built, monkeypatch, capsys):
    class Stop(Exception):
        pass

    class Server:
        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(mockup, "make_server", lambda *a, **k: Server())
    monkeypatch.setattr(mockup.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(mockup, "lan_addresses", lambda: ["192.168.1.20"])
    mockup.serve(built, 8765, lan=True)
    out = capsys.readouterr().out
    assert "Others on the same network open: http://192.168.1.20:8765/" in out
    monkeypatch.setattr(mockup, "lan_addresses", lambda: [])
    mockup.serve(built, 8765, lan=True)
    assert "the address could not be worked out" in capsys.readouterr().out
    mockup.serve(built, 8765, lan=False)
    assert "Others on the same network" not in capsys.readouterr().out
