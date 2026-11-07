"""The mock-up tool: the build, the spec checks (status colours, typos, buttons that move a record to another
status), the server that saves comments, and (where Node and Microsoft Edge are installed) the mock-up
itself, clicked through in the browser."""
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

import support
import layout
import mockup

BROWSER_SCRIPT = support.ROOT / "tests" / "mockup_browser.mjs"

# Statuses for the colour tests. The first three have no colour and are guessed from their wording; the
# guess used to read "active", "approved" and "available" inside them and show them green.
GUESSED = {"LV-T-1": "Inactive", "LV-T-2": "Not Approved", "LV-T-3": "Unavailable"}
# These two take their colour from the spec, against what the wording would suggest.
COLOURED = {"LV-T-4": ("On Hold", "amber"), "LV-T-5": ("Active Review", "red")}


OWN_JS = """Mockup.onRender(function (view) {
  var mark = document.createElement("div");
  mark.id = "own-code";
  mark.textContent = "own code on " + view.screen + " as " + view.role;
  view.root.appendChild(mark);
});
"""


PLATFORM_FIT = {"checked": "2026-11-06", "stack": ["Joget DX"], "standard": 12, "features": [
    {"what": "Figures with a calculation of their own", "support": "custom", "row": "Joget DX PF-17", "takes": "Calculated in a script, an SQL query or a plugin",
     "block": "BB-08", "source": "https://docs.example.test/figures", "features": ["stat:formula"], "used_in": ["screen my-applications"],
     "elements": [{"screen": "my-applications", "element": "stat:Leave balance (days)"}]},
    {"what": "Signing on screen", "support": "not supported", "row": "Joget DX PF-40", "takes": "A signature plugin from the marketplace",
     "source": "not yet checked against the documentation", "features": ["field:signature"], "used_in": ["screen new-application"]},
    {"what": "Choosing a user", "support": "configuration", "row": "Joget DX PF-07", "takes": "A select bound to the directory", "features": ["field:user"],
     "used_in": ["screen new-application"]}]}


def with_cars(spec):
    """A second list whose records the applications name (made up for the tests of `also_move`): approving
    LV-2026-011 puts its courtesy car on loan, to whoever applied."""
    spec["statuses"] += [
        {"id": "available", "name": "Available", "meaning": "Made up for the tests.", "color": "green", "next": ["loaned-out"]},
        {"id": "loaned-out", "name": "Loaned Out", "meaning": "Made up for the tests.", "color": "amber", "next": ["available"]},
        {"id": "in-service", "name": "In Service", "meaning": "Made up for the tests.", "color": "grey", "next": ["available"]}]
    spec["data"]["cars"] = [{"reg_no": "WXY 1234", "model": "Myvi", "status": "Available", "holder": ""},
                            {"reg_no": "VBN 5678", "model": "Axia", "status": "In Service", "holder": ""}]
    next(r for r in spec["data"]["applications"] if r["id"] == "LV-2026-011")["car"] = "WXY 1234"
    confirm(spec, "approve-dialog")["also_move"] = {"data": "cars", "link": "car", "key": "reg_no", "set_status": "loaned-out",
                                                    "copy": {"holder": "employee"}}
    return spec


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
    # One button that serves two steps, and a record whose progress has a step that was skipped.
    next(s for s in spec["screens"] if s["id"] == "application-details")["buttons"].append(
        {"label": "Resume", "roles": ["hr"], "set_status": {"On Hold": "pending", "Active Review": "Approved"}})
    # A list two roles open, each seeing rows of its own, with an action for one of them only.
    spec["screens"].append({
        "id": "all-applications", "type": "list", "title": "All Applications", "menu": "All Applications", "roles": ["manager", "hr"],
        "list": {"data": "applications", "where": {"status": "Approved"}, "where_by_role": {"hr": {"status": ["Rejected", "Cancelled"]}},
                 "columns": [{"field": "id", "label": "Ref No"}, {"field": "status", "label": "Status", "chip": True}],
                 "actions": [{"label": "View", "to": "application-details"}, {"label": "Reopen", "toast": "Reopened", "roles": ["hr"]}]}})
    # What waits for whoever is signed in, read from each record's progress; and a button that goes by the step.
    spec["screens"].append({
        "id": "my-tasks", "type": "list", "title": "My Tasks", "menu": "My Tasks", "roles": ["manager", "hr"],
        "list": {"data": "applications", "where": {"waiting_for_me": True}, "empty": "Nothing is waiting for you",
                 "columns": [{"field": "id", "label": "Ref No"}, {"field": "status", "label": "Status", "chip": True}],
                 "actions": [{"label": "View", "to": "application-details"}]}})
    next(s for s in spec["screens"] if s["id"] == "application-details")["buttons"].append(
        {"label": "Sign off", "roles": ["manager"], "when": {"waiting_for_me": True},
         "set_status": {"Line Manager Approval": "approved", "On Hold": "rejected"}})
    new_application["sections"][-1]["fields"].append({"id": "sign", "label": "Signature", "type": "signature"})
    next(r for r in spec["data"]["applications"] if r["id"] == "LV-T-4")["timeline"] = [
        {"step": "Submitted", "by": "Nur Aisyah", "at": "2026-11-05 09:12", "status": "Done"},
        {"step": "HR Check", "by": "", "at": "", "status": "Skipped"},
        {"step": "Line Manager Approval", "by": "Ahmad Faiz", "at": "", "status": "Pending"}]
    # A second role that starts on the same screen as the manager, for switching role with "View as".
    spec["roles"].append({"id": "deputy", "name": "Deputy Manager", "user": "Lim Wei", "description": "Made up for the tests."})
    next(s for s in spec["screens"] if s["id"] == "approvals")["roles"].append("deputy")
    # A form on a record: its own default record, buttons that follow the record's status, and a single tick box.
    spec["screens"].append({
        "id": "edit-application", "type": "form", "title": "Edit Application", "roles": ["employee"], "data": "applications", "record": "LV-2026-014",
        "sections": [{"title": "Application", "fields": [{"id": "reason", "label": "Reason", "type": "textarea"},
                                                         {"id": "urgent", "label": "Urgent", "type": "checkbox"}]}],
        "buttons": [{"label": "Withdraw", "when": {"status": "Pending Approval"}, "set_status": "cancelled", "toast": "Withdrawn"},
                    {"label": "Resubmit", "when": {"status": "Rejected"}, "set_status": "pending"}]})
    # A form opened on a record whose Save keeps what was typed in that record.
    spec["screens"].append({
        "id": "change-reason", "type": "form", "title": "Change Reason", "roles": ["employee"], "data": "applications",
        "sections": [{"title": "Application", "fields": [{"id": "reason", "label": "Reason", "type": "textarea"},
                                                         {"id": "note", "label": "Note to the manager", "type": "text"}]}],
        "buttons": [{"label": "Save", "style": "primary", "toast": "Saved", "to": "my-applications"}]})
    # What the platform check found to be custom work, for the tags shown while presenting: one at a named part,
    # one (written before platform_fit named the parts) at the heading of its screen, and one that is only configuration.
    spec["platform_fit"] = PLATFORM_FIT
    # A list of the cars the applications name, moved along when an application is approved.
    with_cars(spec)
    spec["screens"].append({
        "id": "cars", "type": "list", "title": "Cars", "menu": "Cars", "roles": ["manager"],
        "list": {"data": "cars", "columns": [{"field": "reg_no", "label": "Reg No"}, {"field": "status", "label": "Status", "chip": True},
                                             {"field": "holder", "label": "Holder"}]}})
    # A car's own screen with the applications that name it (a related list), and a drop-down of the cars free to lend.
    spec["screens"].append(car_screen())
    new_application["sections"][0]["fields"].append(
        {"id": "car", "label": "Courtesy car", "type": "select", "options_from": {"list": "cars", "field": "reg_no", "where": {"status": "Available"}}})
    # A step still to come that the spec gives no word for: the mock-up says Waiting.
    next(r for r in spec["data"]["applications"] if r["id"] == "LV-T-1")["timeline"] = [
        {"step": "Submitted", "by": "Nur Aisyah", "at": "2026-11-05 09:12", "status": "Done"}, {"step": "Second check", "by": "Somebody Else", "at": ""}]
    return spec


def car_screen():
    return {"id": "car", "type": "detail", "title": "Car", "roles": ["manager"], "data": "cars", "record": "WXY 1234",
            "sections": [{"title": "Car", "fields": [{"id": "reg_no", "label": "Reg No"}, {"id": "model", "label": "Model"}]}],
            "list": {"data": "applications", "title": "Applications for this car", "where_record": {"car": "reg_no"}, "empty": "Never lent",
                     "columns": [{"field": "id", "label": "Ref No"}, {"field": "employee", "label": "Employee"}]}}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The mock-up of that spec, built once in a temp folder."""
    project = tmp_path_factory.mktemp("mockup") / "leave-request"
    support.write_spec(project, mockup_spec())
    (project / "spec" / "mockup.js").write_text(OWN_JS, encoding="utf-8")   # the project's own code, for the browser tests
    (project / "spec" / "mockup.css").write_text("#own-code { color: rgb(1, 2, 3); }\n", encoding="utf-8")
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
    lambda s: listing(s, "all-applications")["where_by_role"].update(hr={"source": "Counter"}),
], ids=["new-field", "field-label", "screen-title", "sample-data", "data-key-order", "role-name", "status-colour",
        "dialog-title", "colour", "theme", "list-filter", "list-filter-of-a-role"])
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
    monkeypatch.setattr(mockup, "run_shots", lambda command: called.append(command) or (0, "", []))
    mockup.screenshots(project)
    assert called and called[0][0] == "node"
    note = json.loads((project / "mockup" / "screenshots" / mockup.RECORD).read_text(encoding="utf-8"))
    assert note["screens"] == mockup.fingerprint(mockup.load_spec(project)) and note["taken"]
    assert (project / "mockup" / "versions" / "v0.1" / "screenshots" / mockup.RECORD).is_file()


def test_screenshots_that_stop_at_a_screen_say_which_and_why(tmp_path, monkeypatch, capsys):
    """They used to stop with only the browser library's message: a timeout waiting for '#app > *'."""
    project = tmp_path / "leave-request"
    support.write_spec(project, mockup_spec())
    said = "page.waitForSelector: Timeout 30000ms exceeded.\nCall log:\n  - waiting for locator('#app > *')"
    monkeypatch.setattr(mockup, "run_shots", lambda command: (1, said, ["login", "my-applications"]))
    monkeypatch.setattr(mockup, "browser_errors", lambda address: ["TypeError: f.notes.map is not a function"])
    with pytest.raises(SystemExit) as stop:
        mockup.screenshots(project)
    err = capsys.readouterr().err
    assert stop.value.code == 1
    assert "Screenshots stopped at new-application-p1 (screen new-application, as employee): the mock-up drew nothing there" in err
    assert "The browser reported:\n  TypeError: f.notes.map is not a function" in err
    assert "spec/mockup.js" in err and "#/new-application?role=employee&clean=1&menu=0&page=1" in err
    assert not (project / "mockup" / "screenshots" / mockup.RECORD).exists(), "no note that the pictures show the spec"


def test_when_the_browser_cannot_start_the_screenshots_say_so_as_before(tmp_path, monkeypatch, capsys):
    project = tmp_path / "leave-request"
    support.write_spec(project, sample())
    monkeypatch.setattr(mockup, "run_shots", lambda command: (77, "Neither Microsoft Edge nor Google Chrome could be started", []))
    with pytest.raises(SystemExit) as stop:
        mockup.screenshots(project)
    assert stop.value.code == 77 and "Neither Microsoft Edge" in capsys.readouterr().err


@pytest.mark.parametrize("new", [False, True], ids=["old layout", "new layout"])
@pytest.mark.parametrize("stopped", [(77, "Neither Microsoft Edge nor Google Chrome could be started", 0),
                                     (1, "page.screenshot: Target crashed", 1)], ids=["no browser", "stopped half-way"])
def test_screenshots_that_fail_keep_the_last_ones_that_worked(tmp_path, monkeypatch, capsys, new, stopped):
    """They used to be deleted before the browser was started, so a run without a browser left none, and the
    next requirements document had no figures."""
    code, said, done = stopped
    project = tmp_path / "leave-request"
    if new:
        layout.create_new(project)
    support.write_spec(project, mockup_spec())
    monkeypatch.setattr(mockup, "run_shots", fake_shots)
    mockup.screenshots(project)
    pictures = layout.screenshots_dir(project)
    before = {p.name: p.read_bytes() for p in pictures.glob("*.png")}
    note = layout.screenshots_record(project).read_text(encoding="utf-8")
    assert before and note

    def failing(command, quiet=False):
        plan, out = Path(command[3]), Path(command[4])
        names = [s["name"] for s in json.loads(plan.read_text(encoding="utf-8"))][:done]
        for name in names:  # what was taken before it stopped
            (out / f"{name}.png").write_bytes(b"half a run")
        return code, said, names

    monkeypatch.setattr(mockup, "run_shots", failing)
    with pytest.raises(SystemExit) as stop:
        mockup.screenshots(project)
    assert stop.value.code == code
    assert {p.name: p.read_bytes() for p in pictures.glob("*.png")} == before
    assert layout.screenshots_record(project).read_text(encoding="utf-8") == note
    assert "The screenshots of the last run that worked are kept" in capsys.readouterr().err
    assert not list(layout.mockup_dir(project).glob(".screenshots-*")), "the scratch folder is removed"


def test_the_errors_a_page_reports_in_the_browser_are_found(tmp_path):
    if not shutil.which("node") or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    page = tmp_path / "index.html"
    page.write_text("<!doctype html><body><script>throw new Error('the spec broke it')</script></body>", encoding="utf-8")
    found = mockup.browser_errors(page.as_uri())
    if not found and os.name != "nt":
        pytest.skip("no browser to open the page")
    assert any("the spec broke it" in e for e in found), found


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
    (lambda s: listing(s).update(where_by_role={"manger": {"status": "Approved"}}), "screen approvals: where_by_role names 'manger', which is not a role (did you mean 'manager'?)"),
    (lambda s: listing(s).update(where_by_role={"manager": {"statuz": "Approved"}}), "'where_by_role' for manager: 'statuz' is not a field of the 'applications' data (did you mean 'status'?)"),
    (lambda s: listing(s).update(where_by_role={"manager": "Approved"}), "screen approvals: where_by_role must give a filter for each role it names"),
    (lambda s: s["roles"].append(dict(s["roles"][0])), "role id 'employee' is used more than once"),
    (lambda s: s["dialogs"].append(dict(s["dialogs"][0])), "dialog id 'approve-dialog' is used more than once"),
], ids=["column", "filter", "search", "where", "action-when", "stat-count", "options-field", "options-list", "field-type",
        "misspelt-list-key", "misspelt-screen-key", "misspelt-field-key", "screen-record", "screenshot-record", "screenshot-role",
        "screenshot_role", "role-filter-role", "role-filter-field", "role-filter-shape", "duplicate-role", "duplicate-dialog"])
def test_a_typo_in_the_spec_is_reported_instead_of_showing_blanks(change, said):
    """Each of these used to build: the mock-up showed an empty column, an empty drop-down, the first
    record in place of the one asked for, or simply ignored the setting."""
    spec = json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))
    assert mockup.validate(spec) == []
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


@pytest.mark.parametrize("change, said", [
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from={"list": "leave_types", "field": "title"}),
     "options_from field 'title' is not a field of the 'leave_types' data"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from={"list": "leavetypes", "field": "name"}), "options_from needs 'list'"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from={"list": "leave_types", "field": "name", "where": {"kind": "x"}}),
     "options_from 'where' 'kind' is not a field of the 'leave_types' data"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options_from={"list": "leave_types", "feild": "name"}), "(did you mean 'field'?)"),
    (lambda s: listing(s).update(where_record={"id": "id"}), "where_record shows the rows that name the record a detail screen shows"),
    (lambda s: next(x for x in s["screens"] if x["id"] == "application-details").update(
        list={"data": "leave_types", "where_record": {"title": "leave_type"}, "columns": [{"field": "name", "label": "Name"}]}),
     "where_record 'title' is not a field of the 'leave_types' data"),
    (lambda s: next(x for x in s["screens"] if x["id"] == "application-details").update(
        list={"data": "leave_types", "where_record": {"name": "kind"}, "columns": [{"field": "name", "label": "Name"}]}),
     "where_record (a field of the record shown) 'kind' is not a field of the 'applications' data"),
    (lambda s: s["statuses"][1].update(auto=["expired"]), "status pending: auto 'expired' is not a status"),
    (lambda s: s["statuses"][1].update(auto=["draft"]), "status pending: auto 'draft' is a move the system makes on its own, so it must also be in"),
    (lambda s: s["statuses"][1].update(auto="cancelled"), "'auto' must be a list"),
], ids=["options-from-field", "options-from-list", "options-from-where", "options-from-key", "where-record-not-on-detail",
        "where-record-row-field", "where-record-shown-field", "auto-unknown", "auto-not-in-next", "auto-not-a-list"])
def test_a_filtered_drop_down_a_related_list_and_automatic_moves_are_checked(change, said):
    spec = json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


def test_a_filtered_drop_down_a_related_list_and_automatic_moves_build(tmp_path, capsys):
    spec = sample()
    form(spec)["sections"][0]["fields"][1].update(options_from={"list": "leave_types", "field": "name", "where": {"requires_attachment": "No"}})
    next(x for x in spec["screens"] if x["id"] == "application-details")["list"] = {
        "data": "leave_types", "title": "Its leave type", "where_record": {"name": "leave_type"}, "columns": [{"field": "name", "label": "Name"}]}
    spec["statuses"][3]["auto"] = ["pending"]
    plain = mockup.fingerprint(sample())
    assert mockup.validate(spec) == [] and mockup.spec_warnings(spec) == []
    project = tmp_path / "leave-request"
    support.write_spec(project, spec)
    mockup.build(project)
    out = capsys.readouterr().out
    assert "Made by the system on its own (auto), so no button makes them: Rejected to Pending Approval." in out
    only_auto = sample()
    only_auto["statuses"][3]["auto"] = ["pending"]
    assert mockup.fingerprint(only_auto) == plain, "auto is a status rule: the screenshots are not out of date"


@pytest.mark.parametrize("platform, theme", [("Joget DX", "joget"), ("joget dx 8", "joget"), ("Microsoft Power Apps", "desk"), ("", "desk"), (None, "desk")])
def test_a_new_project_starts_with_desk_unless_its_platform_is_joget(platform, theme):
    assert mockup.default_theme(platform) == theme


def test_a_spec_without_a_theme_keeps_joget_and_desk_is_built_when_asked(tmp_path, capsys):
    """Existing projects never change look by themselves; desk is the design language's theme."""
    spec = sample()
    del spec["project"]["theme"]
    project = tmp_path / "plain"
    support.write_spec(project, spec)
    mockup.build(project)
    assert "theme joget: the spec sets no theme, so it keeps joget" in capsys.readouterr().out
    assert '"theme": "joget"' in (project / "mockup" / "build.js").read_text(encoding="utf-8")
    assert (project / "mockup" / "assets" / "theme.css").read_text(encoding="utf-8") == (mockup.ENGINE / "themes" / "joget.css").read_text(encoding="utf-8")
    spec["project"]["theme"] = "desk"
    support.write_spec(project, spec)
    mockup.build(project)
    assert '"theme": "desk"' in (project / "mockup" / "build.js").read_text(encoding="utf-8")
    css = (project / "mockup" / "assets" / "theme.css").read_text(encoding="utf-8")
    for token in ("#F5F5F7", "#1D1D1F", "#6E6E73", "#E5E5EA", "#D2D2D7", "#E9E9EE", "Geist", "Geist Mono", "16px", "20px", "prefers-reduced-transparency"):
        assert token in css, token


def test_the_sample_specs_pass_the_check():
    for source in (support.EXAMPLE, support.WIDE):
        spec = json.loads(json.dumps(support.load_spec(source), default=str))
        assert mockup.validate(spec) == [], source.name


def test_keys_the_format_does_not_know_are_warned_about_but_do_not_stop_the_build():
    """They used to be ignored without a word, as the mock-up ignores them."""
    spec = json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))
    spec["screens"][1]["ba_note"] = "ask about the balance"
    form(spec)["sections"][0]["fields"][0]["ticket"] = "JIRA-12"
    spec["process_flow"] = {"steps": [{"name": "Submit", "role": "Employee", "owner": "HR"}]}
    assert mockup.validate(spec) == []
    warnings = mockup.spec_warnings(spec)
    assert "screen my-applications: 'ba_note' is not a screen setting, so the mock-up ignores it. Start it with _ if it is a note of your own" in warnings
    assert any("'ticket' is not a field setting" in w for w in warnings) and any("process_flow, step" in w and "'owner'" in w for w in warnings)
    assert len(warnings) == 3


def test_a_note_of_ones_own_starts_with_an_underscore_and_is_not_warned_about():
    spec = sample()
    spec["screens"][1]["_note"] = "ask about the balance"
    assert mockup.validate(spec) == [] and mockup.spec_warnings(spec) == []


def test_a_stray_key_from_a_comma_in_unquoted_text_is_pointed_out(tmp_path, capsys):
    """`{label: Approve, toast: Done, approved}` reads as a button with a key `approved` and no value."""
    spec = sample()
    screen(spec, "review-application")["buttons"].append(yaml.safe_load("{label: Approve, toast: Done, approved}"))
    assert mockup.validate(spec) == []
    assert mockup.spec_warnings(spec) == ["screen review-application, button Approve: 'approved' is not a button setting, so the mock-up "
                                          "ignores it. It has no value: often a comma inside an unquoted text between { }, which splits it in two. "
                                          "Put that text in quotes"]
    support.write_spec(tmp_path / "leave-request", spec)
    mockup.build(tmp_path / "leave-request")
    assert "Settings the mock-up ignores" in capsys.readouterr().out, "the build says so, and goes on"


@pytest.mark.parametrize("change, said", [
    (lambda s: s.update(process_flow={"steps": [{"name": "Submit"}], "notes": "Rejected applications go back to the employee."}),
     "process_flow: 'notes' must be a list (one '- ' line per entry, or [a, b] on one line), not a single text"),
    (lambda s: screen(s, "approvals").update(roles="manager"), "screen approvals: 'roles' must be a list"),
    (lambda s: listing(s).update(columns="id, employee"), "screen approvals, list: 'columns' must be a list"),
    (lambda s: form(s)["sections"][0]["fields"][1].update(options="Annual, Medical"), "'options' must be a list"),
    (lambda s: form(s)["sections"][0].update(fields={"id": "x"}), "'fields' must be a list"),
    (lambda s: s.update(process_flow={"steps": ["Submit", "Approve"]}), "process_flow: 'steps': entry 1 must be a set of settings (key: value), not a single text"),
    (lambda s: listing(s).update(where="Pending Approval"), "screen approvals, list: 'where' must be a set of settings (key: value), not a single text"),
    (lambda s: s["data"].update(leave_types="Annual Leave"), "data 'leave_types' must be a list of records"),
    (lambda s: s["data"]["applications"][0].update(timeline="Submitted"), "data 'applications', record 1: 'timeline' must be a list of steps"),
    (lambda s: confirm(s, "approve-dialog").update(also_move="cars"), "'also_move' must be a set of settings"),
], ids=["flow-notes", "screen-roles", "list-columns", "field-options", "section-fields", "flow-steps", "list-where", "data-list",
        "record-timeline", "also-move"])
def test_a_text_where_a_list_belongs_is_a_spec_error(change, said):
    """Each of these built, and the mock-up then stopped in the browser with an empty page: the screenshots
    failed with only a browser library's message."""
    spec = sample()
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


def test_a_form_may_name_its_own_record_and_needs_its_data_for_it():
    spec = sample()
    form(spec).update(data="applications", record="LV-2026-014")
    assert mockup.validate(spec) == []
    form(spec)["record"] = "LV-0000"
    assert any("record 'LV-0000' is not in the 'applications' data" in e for e in mockup.validate(spec))
    form(spec).pop("data")
    assert any("screen new-application: record 'LV-0000' needs the screen's data" in e for e in mockup.validate(spec))


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
    (lambda s: confirm(s, "approve-dialog").update(set_status={"Pending Aproval": "approved"}),
     "dialog approve-dialog, button Confirm Approve: set_status 'Pending Aproval' is not a status, nor a step in the progress of its "
     "records (did you mean 'Pending Approval'?)"),
    (lambda s: listing(s).update(where={"waiting_for_me": True}),
     "screen approvals: waiting_for_me looks at each record's progress, and no record of the 'applications' data has a timeline"),
    (lambda s: confirm(s, "approve-dialog").update(set_status={"Pending Approval": "approved", "Approved": "pending"}),
     "dialog approve-dialog, button Confirm Approve: moves a record from Approved to Pending Approval, but in the status rules "
     "Approved may only move to Cancelled"),
], ids=["unknown-status", "against-the-rules", "from-a-final-status", "source-from-the-list", "no-record-on-a-dashboard", "no-record-on-a-toolbar",
        "data-without-status", "misspelt", "label-read-as-true", "unknown-status-to-move-from", "waiting-without-progress",
        "one-step-of-several-against-the-rules"])
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


def test_a_row_action_is_checked_against_every_status_its_list_can_show():
    """Without a `when`, the action shows on every row: those of `where` and of each role's own filter."""
    spec = sample()
    listing(spec)["where_by_role"] = {"hr": {"status": "Cancelled"}}
    listing(spec)["actions"].append({"label": "Approve now", "set_status": "approved"})
    errors = mockup.validate(spec)
    assert errors == ["screen approvals, button Approve now: moves a record from Cancelled to Approved, but in the status rules "
                      "Cancelled is a final status (next: []). Change the button, or the status's 'next'"]


def test_a_button_may_go_by_the_step_a_record_is_waiting_at():
    """Where a chain skips steps, the status does not say whose turn it is: the step in the record's progress does."""
    spec = sample()
    spec["data"]["applications"][0]["timeline"] = [{"step": "Line Manager Approval", "by": "Ahmad Faiz", "at": "", "status": "Pending"}]
    confirm(spec, "approve-dialog")["set_status"] = {"Line Manager Approval": "approved"}
    listing(spec)["where"] = {"status": "Pending Approval", "waiting_for_me": True}
    assert mockup.validate(spec) == []
    move = next(m for m in mockup.status_moves(spec) if m["where"] == "dialog approve-dialog")
    assert move["sources"] is None and move["unknown_from"] is None, "a step is not a status: the status rules are not checked for it"


def test_one_button_may_say_where_each_status_moves_to(tmp_path, capsys):
    """One Approve for a chain of approvers: {status the record is in: status it moves to}."""
    spec = sample()
    confirm(spec, "approve-dialog")["set_status"] = {"Pending Approval": "approved", "Rejected": "pending"}
    assert mockup.validate(spec) == []
    steps = [(m["sources"][0]["id"], m["to"]) for m in mockup.status_moves(spec) if m["where"] == "dialog approve-dialog"]
    assert steps == [("pending", "approved"), ("rejected", "pending")]
    assert mockup.moves_not_shown(spec) == ["Draft to Pending Approval"], "Rejected to Pending Approval is now made by a button"
    support.write_spec(tmp_path / "leave-request", spec)
    mockup.build(tmp_path / "leave-request")
    assert "3 buttons move a record" in capsys.readouterr().out, "a button that serves two steps is still one button"


def test_the_moves_the_rules_allow_but_no_button_makes_are_listed():
    spec = sample()
    assert mockup.moves_not_shown(spec) == ["Draft to Pending Approval", "Rejected to Pending Approval"]
    spec["statuses"][3]["auto"] = ["pending"]   # made by the system on its own: not a move the walk-through leaves out
    assert mockup.moves_not_shown(spec) == ["Draft to Pending Approval"] and mockup.automatic_moves(spec) == ["Rejected to Pending Approval"]
    del spec["statuses"][3]["auto"]
    for dialog in spec["dialogs"]:
        dialog["confirm"].pop("set_status", None)
    assert mockup.moves_not_shown(spec) == [], "a mock-up that moves nothing is not told what it leaves out"


def test_build_says_how_many_buttons_move_a_record_and_what_is_left_out(tmp_path, capsys):
    project = tmp_path / "leave-request"
    support.write_spec(project, sample())
    mockup.build(project)
    out = capsys.readouterr().out
    assert "3 buttons move a record to another status when clicked (for the session: Reset sample data on the presenter's bar puts the sample data back)." in out
    assert "which no button of the mock-up makes: Draft to Pending Approval; Rejected to Pending Approval." in out
    assert "If the client should see one of them acted out, ask Claude to add it to the mock-up; if the system makes it on its own" in out
    assert "set_status" not in out, "the window a BA double-clicks open is not told the spec's words"


# ---------------------------------------------------------------------- a linked record moved along (also_move)
def test_a_button_can_move_a_linked_record_along():
    spec = with_cars(sample())
    assert mockup.validate(spec) == [] and mockup.spec_warnings(spec) == []
    move = next(m for m in mockup.status_moves(spec) if m["where"] == "dialog approve-dialog")
    assert move["also"] == [{"data": "cars", "link": "car", "key": "reg_no", "set_status": "loaned-out", "copy": {"holder": "employee"}}]
    assert [(st["id"], car["reg_no"]) for st, car in mockup.linked_sources(spec, move, move["also"][0])] == [("available", "WXY 1234")]
    assert "Available to Loaned Out" not in mockup.moves_not_shown(spec), "the linked move counts as made"
    assert "Loaned Out to Available" in mockup.moves_not_shown(spec)


def also(spec):
    return confirm(spec, "approve-dialog")["also_move"]


@pytest.mark.parametrize("change, said", [
    (lambda s: also(s).update(data="carz"), "dialog approve-dialog, button Confirm Approve, also_move: data 'carz' is not in data (did you mean 'cars'?)"),
    (lambda s: also(s).update(link="carr"), "also_move: link 'carr' is not a field of the 'applications' data (did you mean 'car'?)"),
    (lambda s: also(s).update(key="reg"), "also_move: key 'reg' is not a field of the 'cars' data"),
    (lambda s: also(s).update(set_status="loaned"), "also_move: set_status 'loaned' is not a status"),
    (lambda s: also(s).pop("link"), "also_move: needs link (data: the linked list"),
    (lambda s: also(s).update(copy={"holdr": "employee"}), "also_move, copy: field 'holdr' is not a field of the 'cars' data"),
    (lambda s: also(s).update(copy={"holder": "employe"}), "also_move, copy: field 'employe' is not a field of the 'applications' data"),
    (lambda s: s["data"]["cars"][0].update(status="In Service"),
     "dialog approve-dialog, button Confirm Approve, also_move: moves the 'cars' record WXY 1234 from In Service to Loaned Out, but in the "
     "status rules In Service may only move to Available. Change also_move, or the status's 'next'"),
    (lambda s: [r.pop("status") for r in s["data"]["cars"]], "also_move: set_status changes a record's 'status' field, and the 'cars' data has none"),
    (lambda s: screen(s, "review-application")["buttons"].append({"label": "Lend", "also_move": dict(also(s))}),
     "screen review-application, button Lend: also_move moves a linked record along with this one, so it needs set_status on the same button"),
    (lambda s: also(s).update(sett_status="x"), "'sett_status' is not an also_move setting (did you mean 'set_status'?)"),
], ids=["unknown-list", "unknown-link", "unknown-key", "unknown-status", "missing-link", "copy-to", "copy-from", "against-the-rules",
        "no-status-field", "without-set-status", "misspelt"])
def test_a_linked_move_that_cannot_work_or_breaks_the_status_rules_is_refused(change, said):
    spec = with_cars(sample())
    change(spec)
    errors = mockup.validate(spec)
    assert any(said in e for e in errors), errors


def test_a_linked_move_does_not_make_the_screenshots_out_of_date():
    plain = with_cars(sample())
    moved = with_cars(sample())
    also(moved)["set_status"] = "available"
    assert mockup.fingerprint(moved) == mockup.fingerprint(plain)


# ---------------------------------------------------------------------- the project's own mock-up code
def test_a_projects_own_code_is_built_in_after_the_engine(tmp_path, capsys):
    project = tmp_path / "leave-request"
    support.write_spec(project, sample())
    mockup.build(project)
    page = (project / "mockup" / "index.html").read_text(encoding="utf-8")
    assert "project.js" not in page and "project.css" not in page
    (project / "spec" / "mockup.js").write_text("// own\n", encoding="utf-8")
    (project / "spec" / "mockup.css").write_text(".own {}\n", encoding="utf-8")
    mockup.build(project)
    page = (project / "mockup" / "index.html").read_text(encoding="utf-8")
    assert page.index("assets/app.js") < page.index("assets/project.js") and page.index("assets/theme.css") < page.index("assets/project.css")
    assert (project / "mockup" / "assets" / "project.js").read_text(encoding="utf-8") == "// own\n"
    (project / "spec" / "mockup.js").unlink()
    mockup.build(project)
    assert not (project / "mockup" / "assets" / "project.js").exists() and "project.js" not in (project / "mockup" / "index.html").read_text(encoding="utf-8")


def test_a_projects_own_code_counts_as_what_the_screenshots_show(tmp_path):
    project = tmp_path / "leave-request"
    spec = sample()
    support.write_spec(project, spec)
    plain = mockup.fingerprint(spec)
    assert mockup.fingerprint(spec, project) == plain, "no code of its own: the value it always had"
    (project / "spec" / "mockup.css").write_text(".own { color: red; }\n", encoding="utf-8")
    with_code = mockup.fingerprint(spec, project)
    (project / "spec" / "mockup.css").write_text(".own { color: blue; }\n", encoding="utf-8")
    assert len({plain, with_code, mockup.fingerprint(spec, project)}) == 3


def test_changing_the_projects_own_code_builds_the_mockup_again(projects):
    project = projects / "leave-request"
    first = mockup.build_stamp(project / "mockup", project)
    (project / "spec" / "mockup.js").write_text("// own\n", encoding="utf-8")
    second = mockup.build_stamp(project / "mockup", project)
    assert second["stamp"] != first["stamp"] and (project / "mockup" / "assets" / "project.js").is_file()


# ---------------------------------------------------------------------- larger text
def test_text_size_is_one_of_three_words():
    spec = sample()
    for size in ("normal", "large", "Larger"):
        spec["project"]["text_size"] = size
        assert mockup.validate(spec) == []
    spec["project"]["text_size"] = "huge"
    assert mockup.validate(spec) == ["project: text_size 'huge' must be one of normal, large, larger"]


def test_larger_text_changes_the_pictures_and_normal_does_not():
    spec = sample()
    plain = mockup.fingerprint(spec)
    spec["project"]["text_size"] = "normal"
    assert mockup.fingerprint(spec) == plain, "saying the default changes nothing"
    spec["project"]["text_size"] = "large"
    assert mockup.fingerprint(spec) != plain


# ---------------------------------------------------------------------- the home page: every mock-up, one click away
def get(url, follow=True):
    """(status, text, where it ended up) of a page."""
    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            return None

    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(Stay)
    try:
        with opener.open(url, timeout=10) as answer:
            return answer.status, answer.read().decode("utf-8", "replace"), answer.url
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location") or url


@pytest.fixture
def projects(temp_workspace):
    """A workspace with two projects that have a spec, one folder that has none, and an archived project."""
    folder = temp_workspace / "projects"
    support.write_spec(folder / "leave-request", sample())
    other = sample()
    other["project"].update(name="Courier Booking System", short_name="CBS", client="Acme Logistics Sdn. Bhd.", client_short="Acme", version="0.3")
    support.write_spec(folder / "courier-booking", other)
    (folder / "no-spec-yet" / "docs").mkdir(parents=True)
    support.write_spec(folder / "_archive" / "old-project", sample())
    return folder


@pytest.fixture
def home(projects):
    server = mockup.make_home(projects, "127.0.0.1", 0)
    server.url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def test_the_projects_with_a_mockup_are_listed_with_what_a_presenter_needs(projects):
    (projects / "leave-request" / "feedback").mkdir()
    (projects / "leave-request" / "feedback" / "feedback.json").write_text(json.dumps([
        {"id": "FB-001", "text": "one"}, {"id": "FB-002", "text": "two", "status": "applied"}, {"id": "FB-003", "text": "three"}]), encoding="utf-8")
    for version in ("v0.1", "v0.9", "v0.10"):
        (projects / "leave-request" / "mockup" / "versions" / version).mkdir(parents=True)
        (projects / "leave-request" / "mockup" / "versions" / version / "index.html").write_text("x", encoding="utf-8")
    found = {m["slug"]: m for m in mockup.mockups(projects)}
    assert set(found) == {"leave-request", "courier-booking"}, "not a folder without a spec, and not an archived project"
    leave, courier = found["leave-request"], found["courier-booking"]
    assert (leave["name"], leave["version"], leave["comments"], leave["waiting"]) == ("Leave Request System", "0.1", 3, 2)
    assert leave["versions"] == ["v0.10", "v0.9", "v0.1"], "newest first, and 0.10 is after 0.9"
    assert (courier["name"], courier["client"], courier["mark"], courier["built"]) == ("Courier Booking System", "Acme", "CBS", None)


def test_a_spec_that_cannot_be_read_is_listed_with_the_reason(projects):
    (projects / "leave-request" / "spec" / "app.yaml").write_text("project: [unclosed\n", encoding="utf-8")
    broken = next(m for m in mockup.mockups(projects) if m["slug"] == "leave-request")
    assert broken["problem"] == "its spec could not be read" and "Cannot be opened: its spec could not be read" in mockup.home_page(projects)


def test_the_home_page_links_every_mockup_and_its_earlier_versions(home, projects):
    get(home.url + "p/leave-request/")                          # opening it builds it, which keeps version 0.1
    spec = sample()
    spec["project"]["version"] = "0.2"
    support.write_spec(projects / "leave-request", spec)
    get(home.url + "p/leave-request/")
    status, page, _ = get(home.url)
    assert status == 200 and "<h1>Mock-ups</h1>" in page
    assert 'href="/p/leave-request/"' in page and 'href="/p/courier-booking/"' in page
    assert "Leave Request System" in page and "Courier Booking System" in page and "Acme" in page
    assert "<dt>Version</dt><dd>0.2</dd>" in page and 'href="/p/leave-request/v/0.1/"' in page, "the earlier version is one click away"
    assert 'href="/p/leave-request/v/0.2/"' not in page, "the version on show is not offered again as an earlier one"
    assert "Not built yet" in page and 'href="/p/no-spec-yet/"' not in page and "old-project" not in page


def test_projects_without_a_mockup_are_named_with_what_to_say_in_claude(projects):
    """They used to be left out, and nothing said how to get one."""
    page = mockup.home_page(projects)
    assert [w["slug"] for w in mockup.without_mockup(projects)] == ["no-spec-yet"], "not a project with a spec, and not an archived one"
    assert '<section class="card span-12" data-none-yet>' in page
    name = mockup.without_mockup(projects)[0]["name"]
    assert f'<span class="name">{name}</span>' in page and f'<span class="say">build a mock-up for {name}</span>' in page


def test_the_projects_without_a_mockup_go_by_their_name_not_their_folder(tmp_path):
    """A BA knows "Courier Booking System", not "courier-app"."""
    folder = tmp_path / "courier-app"
    folder.mkdir()
    (folder / "register.json").write_text(json.dumps({"project": "Courier Booking System", "client": "Acme", "items": []}), encoding="utf-8")
    (tmp_path / "bare").mkdir()
    assert mockup.without_mockup(tmp_path) == [
        {"slug": "bare", "name": "bare", "client": ""},
        {"slug": "courier-app", "name": "Courier Booking System", "client": "Acme"}]
    page = mockup.home_page(tmp_path)
    assert '<span class="name">Courier Booking System</span>' in page and "· Acme" in page
    assert "build a mock-up for Courier Booking System" in page


def test_the_home_page_is_one_card_per_project_with_what_a_presenter_needs(projects):
    """In the overview page's look: a card per project, its version, when it was built and last shown, the
    comments waiting as a dot and a word, earlier versions as quiet links. Never another project's data in a card."""
    (projects / "leave-request" / "feedback").mkdir()
    (projects / "leave-request" / "feedback" / "feedback.json").write_text(json.dumps([{"id": "FB-001", "text": "one"}]), encoding="utf-8")
    kept = projects / "leave-request" / "mockup" / "versions" / "v0.1-presented-20261106-1900"
    kept.mkdir(parents=True)
    (kept / "index.html").write_text("x", encoding="utf-8")
    page = mockup.home_page(projects)
    cards = {m.group(1): m.group(2) for m in __import__("re").finditer(r'<article class="card project span-6" data-project="([^"]+)">(.*?)</article>', page)}
    assert set(cards) == {"leave-request", "courier-booking"}
    leave, courier = cards["leave-request"], cards["courier-booking"]
    assert '<span class="status progress">1 comment waiting</span>' in leave and "<dt>Last shown</dt><dd>6 Nov, 19:00</dd>" in leave
    assert '<span class="status neutral">No comments yet</span>' in courier and "Last shown" not in courier
    assert "Courier" not in leave and "Acme" not in leave and "Leave Request" not in courier, "a card shows its own project only"
    assert "#c84b0b" not in page.lower() and "200, 75, 11" not in page, "no orange: the accent is Cobalt"
    assert "never shows one client another client's project" in page


def test_the_home_page_tells_a_presenter_in_words_how_to_share_with_the_room(projects):
    page = mockup.home_page(projects)
    assert "say in Claude &quot;present &lt;project&gt; to the room&quot;" in page or 'say in Claude "present &lt;project&gt; to the room"' in page


@pytest.mark.parametrize("saved, shown", [
    ("v1.4-presented-20261106-1900", "v1.4 as presented 6 Nov 19:00"), ("v0.2", "v0.2"), ("v1.0-presented-2026xx06-1900", "v1.0-presented-2026xx06-1900")])
def test_an_earlier_version_is_named_in_words(saved, shown):
    assert mockup.version_label(saved) == shown


def test_a_version_kept_at_a_session_reads_as_when_it_was_presented(projects):
    kept = projects / "leave-request" / "mockup" / "versions" / "v0.1-presented-20261106-1900"
    kept.mkdir(parents=True)
    (kept / "index.html").write_text("x", encoding="utf-8")
    page = mockup.home_page(projects)
    assert 'href="/p/leave-request/v/0.1-presented-20261106-1900/">v0.1 as presented 6 Nov 19:00</a>' in page


def test_a_workspace_without_mockups_says_how_to_get_one(temp_workspace):
    assert "No mock-up yet" in mockup.home_page(temp_workspace / "projects")


def test_opening_a_project_builds_its_mockup_and_serves_it(home, projects):
    assert not (projects / "courier-booking" / "mockup").exists()
    status, page, _ = get(home.url + "p/courier-booking/")
    assert status == 200 and '<div id="app">' in page and (projects / "courier-booking" / "mockup" / "index.html").is_file()
    status, script, _ = get(home.url + "p/courier-booking/spec.js")
    assert status == 200 and "Courier Booking System" in script
    status, _, where = get(home.url + "p/courier-booking", follow=False)
    assert status == 301 and where == "/p/courier-booking/", "the mock-up's own links need the closing slash"


def test_a_saved_version_is_served_as_it_was(home, projects):
    get(home.url + "p/leave-request/")
    changed = sample()
    changed["project"].update(version="0.2", name="Leave Request System Two")
    support.write_spec(projects / "leave-request", changed)
    assert "Leave Request System Two" in get(home.url + "p/leave-request/spec.js")[1]
    old = get(home.url + "p/leave-request/v/0.1/spec.js")[1]
    assert '"Leave Request System"' in old and "System Two" not in old
    assert get(home.url + "p/leave-request/v/9.9/")[0] == 404


def test_a_comment_goes_to_the_project_it_was_made_in(home, projects):
    for slug, text in (("leave-request", "for leave"), ("courier-booking", "for courier")):
        request = urllib.request.Request(f"{home.url}p/{slug}/api/feedback", data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as answer:
            assert json.loads(answer.read())["id"] == "FB-001"
    read = lambda slug: [c["text"] for c in json.loads((projects / slug / "feedback" / "feedback.json").read_text(encoding="utf-8"))]
    assert read("leave-request") == ["for leave"] and read("courier-booking") == ["for courier"]
    assert json.loads(get(home.url + "p/leave-request/api/feedback")[1])[0]["text"] == "for leave"
    bad = urllib.request.Request(home.url + "p/leave-request/api/feedback", data=b"{}", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(bad, timeout=10)
    assert refused.value.code == 400


@pytest.mark.parametrize("address", ["p/nowhere/", "p/no-spec-yet/", "p/_archive/", "p/..%2F..%2Fsecret/", "p/leave-request/..%2F..%2F..%2Fcompany.yaml", "elsewhere"])
def test_only_mockups_are_served_from_the_home_page(home, temp_workspace, address):
    (temp_workspace / "company.yaml").write_text("name: Secret Company\n", encoding="utf-8")
    status, page, _ = get(home.url + address)
    assert status == 404 and "Secret Company" not in page


def test_a_project_whose_spec_has_mistakes_says_what_to_do(home, projects):
    spec = sample()
    spec["screens"][1]["list"]["columns"][0]["field"] = "idd"
    support.write_spec(projects / "courier-booking", spec)
    status, page, _ = get(home.url + "p/courier-booking/")
    assert status == 500 and "This mock-up cannot be opened yet" in page and "column &#x27;idd&#x27; is not a field" in page
    assert "build the mock-up" in page and 'href="/"' in page


def test_the_page_that_lists_every_mockup_is_never_shared_with_the_room(temp_workspace):
    """With --lan a client could open it and see another client's project."""
    with pytest.raises(SystemExit) as stop:
        mockup.serve_home(8765, lan=True)
    assert "present <project> --lan" in str(stop.value.code) and "must not see another client's project" in str(stop.value.code)


def test_serve_without_a_project_opens_the_home_page(monkeypatch):
    called = []
    monkeypatch.setattr(mockup, "serve_home", lambda port, lan: called.append((port, lan)))
    monkeypatch.setattr(sys, "argv", ["mockup.py", "serve", "--port", "9010"])
    mockup.main()
    assert called == [(9010, False)]
    monkeypatch.setattr(sys, "argv", ["mockup.py", "build"])
    with pytest.raises(SystemExit):
        mockup.main()   # every other command needs a project


# ---------------------------------------------------------------------- an open mock-up follows its spec
def test_the_build_is_made_again_when_the_spec_changes_and_only_then(projects, monkeypatch):
    project = projects / "leave-request"
    builds = []
    real = mockup.build
    monkeypatch.setattr(mockup, "build", lambda p: builds.append(p) or real(p))
    first = mockup.build_stamp(project / "mockup", project)
    assert first["stamp"] and "problem" not in first and len(builds) == 1, "never built: built now"
    assert mockup.build_stamp(project / "mockup", project) == first and len(builds) == 1, "nothing changed: not built again"
    changed = sample()
    changed["screens"][1]["title"] = "My Leave"
    support.write_spec(project, changed)
    second = mockup.build_stamp(project / "mockup", project)
    assert second["stamp"] != first["stamp"] and len(builds) == 2
    assert "My Leave" in (project / "mockup" / "spec.js").read_text(encoding="utf-8")


def test_a_spec_with_a_mistake_keeps_the_last_build_and_is_not_tried_again_until_it_changes(projects, monkeypatch):
    project = projects / "leave-request"
    good = mockup.build_stamp(project / "mockup", project)
    builds = []
    real = mockup.build
    monkeypatch.setattr(mockup, "build", lambda p: builds.append(p) or real(p))
    broken = sample()
    broken["screens"][1]["list"]["columns"][0]["field"] = "idd"
    support.write_spec(project, broken)
    for _ in range(3):
        answer = mockup.build_stamp(project / "mockup", project)
        assert answer["stamp"] == good["stamp"] and "column 'idd' is not a field" in answer["problem"]
    assert len(builds) == 1, "asked three times, tried once"
    support.write_spec(project, sample())
    back = mockup.build_stamp(project / "mockup", project)
    assert "problem" not in back and back["stamp"] == good["stamp"] and len(builds) == 1, "put back as it was built: nothing to build, nothing to offer"
    mended = sample()
    mended["screens"][1]["title"] = "Mended"
    support.write_spec(project, mended)
    answer = mockup.build_stamp(project / "mockup", project)
    assert "problem" not in answer and answer["stamp"] != good["stamp"] and len(builds) == 2


def test_a_saved_version_never_changes(projects):
    project = projects / "leave-request"
    mockup.build_stamp(project / "mockup", project)
    saved = project / "mockup" / "versions" / "v0.1"
    before = mockup.build_stamp(saved)
    changed = sample()
    changed["project"]["version"] = "0.2"   # a new version: the copy of 0.1 is then kept as it was
    changed["screens"][1]["title"] = "Changed Afterwards"
    support.write_spec(project, changed)
    mockup.build_stamp(project / "mockup", project)   # the working mock-up is built again
    assert mockup.build_stamp(saved) == before and "Changed Afterwards" not in (saved / "spec.js").read_text(encoding="utf-8")


def test_the_servers_answer_which_build_they_show(home, projects, served):
    assert json.loads(get(home.url + "p/leave-request/api/build")[1])["stamp"]
    assert json.loads(get(served.url + "api/build")[1])["stamp"]


# ---------------------------------------------------------------------- what the room is told about a comment
def test_the_room_is_not_sent_internal_notes(served):
    """Everyone with the room's link can read what the mock-up is sent."""
    served.fb_file.parent.mkdir(parents=True, exist_ok=True)
    served.fb_file.write_text(json.dumps([
        {"id": "FB-001", "screen": "approvals", "text": "one", "author": "Ali", "status": "scope", "note": "possible CR, about 3 MD", "register_id": "R-031"},
        {"id": "FB-002", "screen": "approvals", "text": "two", "status": "applied", "note": "renamed the column"},
        {"id": "FB-003", "screen": "approvals", "text": "three", "status": "working"},
        {"id": "FB-004", "screen": "approvals", "text": "four"},
        {"id": "FB-005", "screen": "approvals", "text": "five", "status": "declined", "note": "duplicate of FB-001"},
        {"id": "FB-006", "screen": "approvals", "text": "six", "status": "decision"}, {"id": "FB-007", "screen": "approvals", "text": "seven", "status": "question"}]), encoding="utf-8")
    with urllib.request.urlopen(served.url + "api/feedback", timeout=10) as answer:
        raw = answer.read().decode("utf-8")
    assert "possible CR" not in raw and "R-031" not in raw and "duplicate" not in raw and "renamed" not in raw and "scope" not in raw
    sent = json.loads(raw)
    assert [c["state"] for c in sent] == ["noted", "applied", "working", "received", "noted", "applied", "noted"]
    assert sent[0] == {"id": "FB-001", "screen": "approvals", "text": "one", "author": "Ali", "state": "noted"}
    status, saved_comment = post(served, json.dumps({"text": "eight", "build": "123"}).encode())
    assert status == 200 and saved_comment["state"] == "received" and saved_comment["build"] == "123"


def test_two_programs_do_not_write_the_feedback_file_at_once(tmp_path):
    fb = tmp_path / "feedback" / "feedback.json"
    with mockup.feedback_lock(fb):
        assert (fb.parent / ".feedback.lock").exists()
    assert not (fb.parent / ".feedback.lock").exists(), "released"
    (fb.parent / ".feedback.lock").write_text("", encoding="utf-8")
    os.utime(fb.parent / ".feedback.lock", (1, 1))   # left long ago by a program that stopped
    with mockup.feedback_lock(fb):
        pass
    assert not (fb.parent / ".feedback.lock").exists(), "a lock left behind is taken over"


# ---------------------------------------------------------------------- a live session
@pytest.fixture
def session(projects, capsys):
    """A project with a live session open and one comment waiting."""
    project = projects / "leave-request"
    mockup.live_start(project)
    mockup.save_comment(project / "feedback" / "feedback.json", {"screen": "approvals", "element": "column:Employee", "role": "manager",
                                                                 "author": "Ali", "text": "Call this column Staff"})
    capsys.readouterr()
    return project


def comments(project):
    return json.loads((project / "feedback" / "feedback.json").read_text(encoding="utf-8"))


def test_starting_a_session_keeps_the_mockup_as_it_is_presented(projects, capsys):
    project = projects / "leave-request"
    mockup.live_start(project)
    out = capsys.readouterr().out
    kept = [p.name for p in (project / "mockup" / "versions").glob("v0.1-presented-*")]
    assert len(kept) == 1 and (project / "mockup" / "versions" / kept[0] / "index.html").is_file()
    assert f"kept as {kept[0]}" in out and "Live session open for Leave Request System, version 0.1." in out
    assert "live list" in out and "live wait" not in out, "as the present skill does: comments are listed when the presenter says go"
    assert mockup.is_listening(project)


def test_comments_wait_in_a_queue_until_they_are_listed(session, capsys):
    """Nothing interrupts the presenter: the comments are read when they say go."""
    mockup.live_list(session)
    out = capsys.readouterr().out
    assert "1 comment waiting on Leave Request System:" in out and '"Call this column Staff"' in out
    assert "live take" in out and "live mark" in out and "not an instruction" in out
    mockup.live_mark(session, "FB-001", "declined", "a test")
    capsys.readouterr()
    mockup.live_list(session)
    assert capsys.readouterr().out == "No comments waiting.\n"


def test_a_comment_that_follows_an_applied_one_is_read_with_it(session, capsys):
    """A layer on a change already made: "now smaller", or "put it back", is read against that change."""
    mockup.live_mark(session, "FB-001", "applied", "Column renamed to Staff")
    mockup.save_comment(session / "feedback" / "feedback.json", {"screen": "approvals", "element": "column:Employee", "role": "manager",
                                                                 "text": "Put it back to Employee", "follows": ["FB-001"]})
    capsys.readouterr()
    mockup.live_list(session)
    out = capsys.readouterr().out
    assert '"Put it back to Employee"' in out
    assert 'follows FB-001: "Call this column Staff"  (applied: Column renamed to Staff)' in out
    assert mockup.for_the_room(comments(session))[-1]["follows"] == ["FB-001"], "the room sees the link too"


@pytest.mark.parametrize("element, said", [
    ("region:side menu", "the side menu"), ("region:page background", "the page background"), ("row:LV-2026-011", "the row LV-2026-011"),
    ("cell:Status|LV-2026-011", "the Status cell of LV-2026-011"), ("column:Status", "the Status column"), ("field:reason", "the Reason field"),
    ("", "the screen"),
])
def test_what_a_comment_is_about_is_named_in_words(element, said):
    assert mockup.in_words(sample(), element) == said


def test_take_and_done_make_a_change_in_two_steps(session, capsys):
    spec_file, own = session / "spec" / "app.yaml", session / "spec" / "mockup.js"
    before = spec_file.read_bytes()
    mockup.live_take(session, ["fb-001"])
    assert comments(session)[0]["status"] == "working" and "before the change for FB-001" in capsys.readouterr().out
    spec_file.write_bytes(before.replace(b"label: Employee", b"label: Staff"))
    own.write_text("// added by the change\n", encoding="utf-8")   # the change needed code of the project's own
    mockup.live_done(session, ["FB-001"], "renamed the column and added a behaviour")
    assert "Every open mock-up now offers Update ready." in capsys.readouterr().out
    assert {k: comments(session)[0][k] for k in ("status", "note")} == {"status": "applied", "note": "renamed the column and added a behaviour"}
    built = session / "mockup"
    assert '"label": "Staff"' in (built / "spec.js").read_text(encoding="utf-8") and (built / "assets" / "project.js").is_file()
    mockup.live_undo(session)
    assert spec_file.read_bytes() == before and not own.exists(), "the spec put back, and the code the change added taken out"


def test_undo_makes_the_comments_of_that_change_wait_again_and_says_the_register_is_not_undone(session, capsys):
    """They used to keep reading Applied in the room after their change was gone."""
    mockup.live_take(session, ["FB-001"])
    mockup.live_mark(session, "FB-001", "working", register="R-031")
    mockup.live_done(session, ["FB-001"], "renamed the column")
    capsys.readouterr()
    mockup.live_undo(session)
    out = capsys.readouterr().out
    comment = comments(session)[0]
    assert "status" not in comment and mockup.for_the_room([comment])[0]["state"] == "received"
    assert "FB-001 wait again (the room reads Received)" in out and "declined" in out
    assert "is NOT undone: put it back by hand. Register items linked: FB-001 (R-031)." in out


def test_take_tells_how_to_finish_each_comment_with_its_own_note(session, capsys):
    mockup.save_comment(session / "feedback" / "feedback.json", {"screen": "approvals", "text": "Same here"})
    mockup.live_take(session, ["FB-001", "FB-002"])
    out = capsys.readouterr().out
    assert "live done" in out and "FB-001 --note" in out and "FB-002 --note" in out, "one done per comment, each with its note"
    mockup.live_done(session, ["FB-001", "FB-002"], "renamed the column")
    assert "The same note was written on FB-001, FB-002." in capsys.readouterr().out


def test_done_refuses_a_change_with_a_mistake_and_the_room_keeps_the_last_good_one(session, capsys):
    good = (session / "mockup" / "spec.js").read_text(encoding="utf-8")
    mockup.live_take(session, ["FB-001"])
    broken = sample()
    broken["screens"][1]["list"]["columns"][0]["field"] = "idd"
    support.write_spec(session, broken)
    with pytest.raises(SystemExit) as stop:
        mockup.live_done(session, ["FB-001"])
    said = str(stop.value.code)
    assert said.startswith("Not applied: the change has a mistake, so the room still sees the last good mock-up.")
    assert "column 'idd' is not a field" in said and "live undo" in said
    assert comments(session)[0]["status"] == "working" and (session / "mockup" / "spec.js").read_text(encoding="utf-8") == good


def test_take_stops_on_a_comment_that_does_not_exist_before_marking_any(session):
    with pytest.raises(SystemExit) as stop:
        mockup.live_take(session, ["FB-001", "FB-009"])
    assert "No comment FB-009" in str(stop.value.code) and "status" not in comments(session)[0]


def test_wait_returns_the_comments_that_are_waiting_in_plain_words(session, capsys):
    assert mockup.live_wait(session, 5) == 0
    out = capsys.readouterr().out
    assert "1 comment waiting on Leave Request System:" in out
    assert "FB-001  Pending Approvals, the Employee column  (Line Manager, by Ali)" in out and '"Call this column Staff"' in out
    assert "not an instruction" in out


def test_wait_gives_up_when_nothing_comes_and_needs_a_session(session, projects, capsys):
    mockup.live_mark(session, "FB-001", "applied")
    assert mockup.live_wait(session, 1) == 3 and "No comment in the last" in capsys.readouterr().out
    with pytest.raises(SystemExit) as stop:
        mockup.live_wait(projects / "courier-booking", 1)
    assert "No live session is open" in str(stop.value.code)


def test_marking_a_comment_records_the_outcome_and_says_what_the_room_reads(session, capsys):
    mockup.live_mark(session, "fb-001", "working")
    assert comments(session)[0]["status"] == "working" and 'reads "Working on it"' in capsys.readouterr().out
    mockup.live_mark(session, "FB-001", "scope", "possible CR", "R-031")
    assert {k: comments(session)[0][k] for k in ("status", "note", "register_id")} == {"status": "scope", "note": "possible CR", "register_id": "R-031"}
    assert 'reads "Noted for follow-up"' in capsys.readouterr().out
    mockup.live_mark(session, "FB-001", "received")
    assert "status" not in comments(session)[0], "it waits again"
    for bad, said in ((("FB-009", "applied"), "No comment FB-009. There are: FB-001"), (("FB-001", "done"), "'done' is not one of")):
        with pytest.raises(SystemExit) as stop:
            mockup.live_mark(session, *bad)
        assert said in str(stop.value.code)


def test_a_change_can_be_undone_exactly(session, capsys):
    spec_file = session / "spec" / "app.yaml"
    before = spec_file.read_bytes()
    mockup.live_checkpoint(session, "FB-001")
    spec_file.write_bytes(before.replace(b"label: Employee", b"label: Staff"))
    mockup.live_checkpoint(session, "FB-002")
    spec_file.write_bytes(spec_file.read_bytes().replace(b"Pending Approvals", b"Waiting"))
    mockup.live_undo(session)
    assert b"label: Staff" in spec_file.read_bytes() and b"Waiting" not in spec_file.read_bytes(), "only the last change is undone"
    assert "as it was before the change for FB-002" in capsys.readouterr().out
    mockup.live_undo(session)
    assert spec_file.read_bytes() == before
    with pytest.raises(SystemExit) as stop:
        mockup.live_undo(session)
    assert "Nothing to undo" in str(stop.value.code)


def test_the_usage_names_every_live_command():
    usage = next(line for line in mockup.__doc__.splitlines() if " live " in line)
    assert all(word in usage for word in ("start", "list", "take", "done", "mark", "undo", "end", "wait", "checkpoint"))


def test_ending_a_session_says_what_to_release_and_stops_listening(session, capsys):
    mockup.live_checkpoint(session, "FB-001")
    mockup.live_mark(session, "FB-001", "applied", "renamed the column")
    capsys.readouterr()
    mockup.live_end(session)
    out = capsys.readouterr().out
    assert "1 change made to the spec: for FB-001." in out and "Comments: 1 applied, 0 questions, 0 possible change requests, 0 declined, 0 still waiting." in out
    assert "bump project.version" in out and "kept as mockup/versions/v0.1-presented-" in out
    assert not mockup.is_listening(session)
    with pytest.raises(SystemExit):
        mockup.live_checkpoint(session, "FB-002")   # the session is over


def test_live_means_a_session_is_open_however_long_the_assistant_is_busy(session, monkeypatch, capsys):
    """It used to go out 30 seconds after the assistant's last sign of life: in the middle of making a change."""
    assert mockup.build_stamp(session / "mockup", session)["live"] is True
    monkeypatch.setattr(mockup.time, "time", lambda now=mockup.time.time(): now + 3600)
    assert mockup.build_stamp(session / "mockup", session)["live"] is True
    mockup.live_end(session)
    assert mockup.build_stamp(session / "mockup", session)["live"] is False


def test_the_live_commands_from_the_command_line(session, monkeypatch, capsys):
    run = lambda *args: (monkeypatch.setattr(sys, "argv", ["mockup.py", "live", *map(str, args)]), mockup.main())
    run("mark", session, "FB-001", "question", "--note", "ask the HR lead", "--register", "R-040")
    assert comments(session)[0]["register_id"] == "R-040" and "FB-001: question (ask the HR lead)" in capsys.readouterr().out
    run("checkpoint", session, "FB-001", "rename")
    assert "before the change for FB-001 rename" in capsys.readouterr().out
    run("list", session)
    assert "No comments waiting." in capsys.readouterr().out
    run("take", session, "FB-001")
    run("done", session, "FB-001", "--note", "nothing to change")
    assert comments(session)[0]["status"] == "applied" and comments(session)[0]["note"] == "nothing to change"
    with pytest.raises(SystemExit):
        run("take", session)   # no comment named
    with pytest.raises(SystemExit) as stop:
        run("wait", session, "--timeout", "1")
    assert stop.value.code == 3
    with pytest.raises(SystemExit):
        run("mark", session, "FB-001")   # no status given


def test_the_version_kept_at_the_start_of_a_session_can_be_opened_from_the_home_page(home, projects):
    mockup.live_start(projects / "leave-request")
    kept = next((projects / "leave-request" / "mockup" / "versions").glob("v0.1-presented-*")).name
    assert f'href="/p/leave-request/v/{kept[1:]}/"' in get(home.url)[1]
    assert get(f"{home.url}p/leave-request/v/{kept[1:]}/")[0] == 200


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
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
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
    """800 px wide at twice the pixels, without the side menu (menu=0). At the old 1440 px the mock-up's text
    printed at about 4 pt. The process flow keeps 1000 px: narrower, the words overflow its boxes."""
    narrow = {name: size for name, size in pictures["sizes"].items() if name not in ("wide-list", "process-flow")}
    assert {size[0] for size in narrow.values()} == {1600}, narrow
    assert pictures["sizes"]["process-flow"][0] == 2000


def test_a_screen_that_does_not_fit_is_taken_wider_and_says_so(pictures):
    assert pictures["sizes"]["wide-list"][0] in (2400, 2880)
    assert "wide-list.png (taken" in pictures["log"] and "it does not fit in 800" in pictures["log"]


def test_screenshots_are_cropped_to_the_content(pictures):
    """No minimum height: a list with two rows and the process flow are short pictures, not half-empty ones.
    The window is 900 px tall (1800 in the picture), so well under that is short. Chrome on Linux sets text a little
    wider than Edge on Windows, so a filter bar or a cell can wrap onto a second line: the list was 848 px there."""
    sizes = pictures["sizes"]
    assert sizes["approvals"][1] < 1000 and sizes["process-flow"][1] < 700
    assert sizes["new-application-p1"][1] > sizes["approvals"][1] + 300, "a form is as tall as its fields"
    assert 800 < sizes["login"][1] < 1400, "the login card with space around it"
    assert sizes["review-application-reject"][1] >= sizes["review-application"][1], "a dialog never shortens its screen"


@pytest.fixture(scope="module")
def desk_pictures(tmp_path_factory):
    """The test spec drawn in the desk theme, every screen and dialog screenshot for real."""
    from PIL import Image

    if not shutil.which("node") or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    project = tmp_path_factory.mktemp("desk") / "leave-request"
    spec = mockup_spec()
    spec["project"]["theme"] = "desk"
    spec["process_flow"] = FLOW
    spec["screenshots"] += [{"screen": "car", "role": "manager", "name": "car-detail"},
                            {"screen": "review-application", "role": "manager", "dialog": "approve-dialog", "name": "approve-dialog"},
                            {"screen": "application-details", "role": "hr", "record": "LV-2026-009", "name": "rejected-record"}]
    support.write_spec(project, spec)
    run = subprocess.run([sys.executable, "-I", str(support.ROOT / "tools" / "mockup.py"), "screenshots", str(project)],
                         cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=300)
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stdout + run.stderr
    return {"sizes": {p.stem: Image.open(p).size for p in (project / "mockup" / "screenshots").glob("*.png")}, "log": run.stdout,
            "planned": [s["name"] for s in mockup.shot_list(mockup.load_spec(project))]}


def test_the_desk_theme_draws_every_screen_type_at_800_pixels(desk_pictures):
    """Login, dashboard, lists with filters and row actions, a form in steps, detail screens with their
    progress and a related list, dialogs: all taken 800 px wide without the side menu; the process flow at 1000."""
    sizes = desk_pictures["sizes"]
    assert sorted(sizes) == sorted(desk_pictures["planned"])
    assert {name: size[0] for name, size in sizes.items() if size[0] != (2000 if name == "process-flow" else 1600)} == {}, desk_pictures["log"]
    assert "(taken" not in desk_pictures["log"]


# ---------------------------------------------------------------------- in the browser
@pytest.fixture(scope="module")
def browser(built, tmp_path_factory):
    """The mock-up clicked through in Microsoft Edge by tests/mockup_browser.mjs. Skipped where Node, the
    Node packages (setup) or Edge are missing, as on GitHub."""
    node = shutil.which("node")
    if not node or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    server = serve_in_thread(built / "mockup", tmp_path_factory.mktemp("browser-feedback") / "feedback.json")
    # The same mock-up with a red brand colour, for the look of the danger button.
    red_project = tmp_path_factory.mktemp("red") / "leave-request"
    red_spec = mockup_spec()
    red_spec["project"].update(primary_color="#c8102e", text_size="large")
    support.write_spec(red_project, red_spec)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "stdout", io.StringIO())
        mockup.build(red_project)
    # This one follows its project's spec, as `serve` does: the browser script changes the spec and waits for the page to follow.
    red = mockup.make_server(red_project / "mockup", red_project / "feedback" / "feedback.json", "127.0.0.1", 0, red_project)
    red.url = f"http://127.0.0.1:{red.server_address[1]}/"
    threading.Thread(target=red.serve_forever, daemon=True).start()
    try:
        run = subprocess.run([node, str(BROWSER_SCRIPT), server.url, *GUESSED, *COLOURED],
                             env={**os.environ, "MOCKUP_RED_URL": red.url, "MOCKUP_RED_SPEC": str(red_project / "spec" / "app.yaml"),
                                  "MOCKUP_FILE": str(built / "mockup" / "index.html"),
                                  "MOCKUP_RED_FEEDBACK": str(red_project / "feedback")},
                             cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=240)
    finally:
        for s in (server, red):
            s.shutdown()
            s.server_close()
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    seen["saved"]["file"] = seen["afterRetry"]["file"] = seen["commentEdits"]["file"] = saved(server)
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


# Dialogs.
def test_a_dialog_takes_the_cursor_and_says_it_is_a_dialog(browser):
    assert browser["dialogs"]["focus"] == "TEXTAREA in dialog" and browser["dialogs"]["role"] == "dialog"


@pytest.mark.parametrize("how", ["afterEscape", "afterClickOutside"])
def test_escape_and_a_click_outside_close_a_dialog(browser, how):
    """Only Cancel and the cross used to close it."""
    after = browser["dialogs"][how]
    assert not after["dialog"] and after["screen"] == "review-application" and after["toasts"] == []


def test_the_back_button_does_not_reopen_a_closed_dialog(browser):
    """Opening and closing a dialog used to leave two steps in the browser's history."""
    after = browser["dialogs"]["afterBack"]
    assert not after["dialog"] and after["screen"] == "approvals"


# Required fields.
def test_a_dialog_points_out_its_required_field_before_it_goes_on(browser):
    first = browser["required"]["dialogFirst"]
    assert first["dialog"] and first["screen"] == "review-application" and first["status"] == "Pending Approval", "nothing moved"
    assert first["marked"] == ["field:reason"] and first["notes"] == ["This field is required"]
    assert first["toasts"] == ["A required field is empty. Mock-up: press Confirm Reject again to go on without it."]
    assert first["toastKinds"] == ["toast warn"], "something to look at, not something done"
    assert browser["required"]["dialogTyped"]["marked"] == [], "the mark goes when the field is filled"


def test_pressing_the_button_again_goes_on_without_the_required_fields(browser):
    """A presenter is not made to fill in a whole form to show what happens next."""
    second = browser["required"]["dialogSecond"]
    assert not second["dialog"] and second["screen"] == "approvals" and "Application rejected" in second["toasts"]
    form = browser["required"]["formSecond"]
    assert form["screen"] == "my-applications" and any("submitted" in t for t in form["toasts"])
    # and the room is told that only the mock-up goes on: the real system would not send the form
    assert any(t.startswith("Only the mock-up goes on with required fields empty: the real system will not send the form")
               for t in form["toasts"])
    assert any(t.startswith("Only the mock-up goes on with a required field empty: the real system will not accept it")
               for t in second["toasts"])


def test_the_main_button_of_a_form_in_steps_names_the_step_with_the_empty_required_fields(browser):
    """Submit is on the last step only, so it stays there: the step that holds the fields is named and marked."""
    first = browser["required"]["formFirst"]
    assert first["screen"] == "new-application" and first["page"] == "2", "it stays on the step that has Submit"
    assert first["toasts"] == ["4 required fields are empty, on Step 1. Mock-up: press Submit again to go on without them."]
    assert first["flagged"] == ["Step 1"] and first["marked"] == []
    step1 = browser["required"]["formFirstStep1"]
    assert step1["marked"] == ["field:leave_type", "field:from", "field:to", "field:reason"], "a read-only required field is not asked for"


def test_a_form_in_steps_has_its_main_button_on_the_last_step_only(browser):
    steps = browser["steps"]
    assert steps["first"] == ["Cancel", "Save as Draft", "Next"]
    assert steps["last"]["buttons"] == ["Cancel", "Save as Draft", "Previous", "Submit"] and steps["last"]["page"] == "2"
    assert steps["last"]["toasts"] == [], "Next checks nothing and adds nothing"
    assert steps["back"] == {"buttons": ["Cancel", "Save as Draft", "Next"], "reason": "Kept across steps"}
    assert steps["dialog"] == ["Cancel", "Confirm Reject"]


def test_a_filtered_drop_down_offers_what_its_filter_lets_through_as_the_walk_through_goes(browser):
    assert browser["carChoices"] == {"before": ["WXY 1234"], "afterLoan": []}, "In Service is left out; a car put on loan leaves"


def test_a_detail_screen_shows_the_records_that_name_the_one_shown(browser):
    named, none = browser["related"]["named"], browser["related"]["none"]
    assert named["heading"] == "Applications for this car" and named["rows"] == ["LV-2026-011 Daniel Tan"]
    assert none["rows"] == [] and none["empty"] == "Never lent"


def test_a_step_still_to_come_with_no_word_reads_waiting(browser):
    """It used to show an empty label; the spec's own word (Done, Pending) is kept."""
    assert browser["waitingWord"] == ["Done", "Waiting"]


def test_the_presenters_chrome_is_dark_with_the_cobalt_accent_and_never_orange(browser):
    chrome = browser["chrome"]
    assert chrome["toggle"]["bg"] == "rgb(42, 111, 214)" and chrome["bar"]["bg"].startswith("rgba(28, 28, 30")
    assert chrome["panel"]["bg"] == "rgb(28, 28, 30)"
    css = chrome["css"].lower()
    assert "200, 75, 11" not in css and "#c84b0b" not in css and "rgb(200, 75, 11)" not in css, "the burnt orange is gone"


def test_opening_the_feedback_panel_never_moves_the_page(browser):
    """The panel lies over the page. When the page made room for it, the pins and boxes drawn on the page could
    be placed while it moved, and ended up beside what they were about."""
    room = browser["chrome"]["room"]
    assert room["before"] == room["after"] and not room["overflow"], room


def test_the_presenters_bar_folds_away_and_remembers_it(browser):
    chrome = browser["chrome"]
    assert chrome["folded"]["width"] <= 48 and not chrome["folded"]["panel"] and not chrome["folded"]["feedback"]
    assert chrome["foldedAfterReload"]["width"] <= 48
    assert chrome["unfolded"]["width"] > 200


def test_a_button_that_is_not_the_main_one_does_not_check(browser):
    assert browser["required"]["draft"]["screen"] == "my-applications"


# File and signature fields.
def test_a_file_field_takes_a_sample_file_and_gives_it_back(browser):
    """`browse` used to do nothing."""
    fakes = browser["fakes"]
    assert fakes["fileBefore"] == "Drop file here or browse"
    assert fakes["fileAttached"] == fakes["fileAfterStepChange"] == "sample-document.pdf Remove"
    assert fakes["fileRemoved"] == "Drop file here or browse"


def test_a_signature_field_signs_as_whoever_is_signed_in(browser):
    fakes = browser["fakes"]
    assert fakes["signBefore"] == "Sign here" and fakes["signed"] == fakes["signAfterStepChange"] == "Employee"
    assert fakes["signCleared"] == "Sign here"


# Lists and messages.
def test_filters_are_still_there_after_a_visit_to_a_record(browser):
    """Opening a record and coming back used to show every row again."""
    kept = browser["filtersKept"]
    assert kept["before"] and kept["after"] == kept["before"] and kept["value"] == "Approved"


def test_two_messages_do_not_cover_each_other(browser):
    (top1, bottom1), (top2, bottom2) = browser["twoToasts"]
    assert bottom1 <= top2 or bottom2 <= top1


# The presenter's tools.
def test_the_presenters_tools_are_together_and_not_in_the_systems_top_bar(browser):
    tools = browser["tools"]
    assert tools["onLogin"] == {"badge": "Mock-up v0.1", "viewAsShown": False}
    assert tools["onScreen"] == {"viewAsShown": True, "picked": "employee", "inTopBar": 0}
    assert tools["afterSwitch"]["screen"] == "approvals"
    assert not tools["commentBoxOnTools"], "a click on the tools is not a comment on the mock-up"


def test_the_presenters_tools_do_not_cover_the_buttons_of_a_page(browser):
    """The Feedback button used to sit on top of the last buttons of a screen."""
    assert browser["tools"]["covered"] == []


def test_view_as_a_role_that_starts_on_the_same_screen_shows_that_role(browser):
    """The address did not change, so nothing was drawn again: the header still showed the role before."""
    switched = browser["tools"]["sameScreenSwitch"]
    assert switched == {"user": "Lim Wei · Deputy Manager", "hash": "#/approvals", "picked": "deputy"}


def test_a_form_shows_its_own_record_and_its_buttons_follow_the_record(browser):
    """A form's `record` was ignored, and a button with `when` never showed on a form."""
    form_ = browser["formOnRecord"]
    assert form_["byDefault"]["reason"] == "Family event" and form_["byDefault"]["buttons"] == ["Withdraw"]
    assert form_["rejected"]["reason"] == "Home repair" and form_["rejected"]["buttons"] == ["Resubmit"]
    assert form_["withdrawn"]["buttons"] == [] and form_["withdrawn"]["toasts"] == ["Withdrawn"]
    assert form_["statusAfter"] == "Cancelled", "the button moved the record the form was on"


def test_save_on_a_form_opened_on_a_record_changes_that_record(browser):
    """Edit User's Save showed its message, and the list still showed the old status."""
    saved = browser["editSaved"]
    assert saved["countAfter"] == saved["countBefore"], "no record added"
    assert saved["record"] == {"reason": "Changed in the walk-through", "note": False}, "only the list's own fields are written"
    assert saved["shown"] == "Changed in the walk-through", "every screen that shows the record shows the change"


def test_a_checkbox_without_options_is_one_tick_box(browser):
    """It used to show only its label, with nothing to tick."""
    assert browser["formOnRecord"]["byDefault"]["ticks"] == 1 and browser["formOnRecord"]["ticked"]


def test_approving_also_moves_the_record_it_names_in_another_list(browser):
    """The dialog said the car would be loaned out, and the car stayed Available."""
    assert browser["linkedBefore"] == ["WXY 1234 Available", "VBN 5678 In Service"]
    assert browser["linkedAfter"] == ["WXY 1234 Loaned Out Daniel Tan", "VBN 5678 In Service"], "its status, and the value copied across"


def test_a_project_can_ask_for_larger_text_on_its_screens(browser):
    """project.text_size: the client's screens grow, the presenter's tools do not."""
    normal, large = browser["textSize"]["normal"], browser["textSize"]["large"]
    assert normal == {"menu": "13.5px", "table": "13px", "title": "20px", "tools": "13px"}
    assert large == {"menu": "15.12px", "table": "14.56px", "title": "22.4px", "tools": "13px"}


def test_a_changed_spec_is_offered_as_an_update_and_never_reloads_by_itself(browser):
    """A presenter in the middle of a walk-through must not have the screen pulled from under them."""
    live = browser["live"]
    assert live["offered"] == {"button": True, "title": "Pending Approvals", "typed": "half-typed"}, "offered, and nothing on the page was touched"
    assert live["after"] == "Waiting For Me" and live["hash"] == "#/approvals?role=manager", "pressed: the change, on the screen it was on"
    assert live["toasts"] == [], "something changed, so the panel says what instead of a message"
    assert "Title: Pending Approvals → Waiting For Me" in live["changes"], "What changed lists the renamed screen"
    assert not live["feedbackOn"], "feedback mode is off after an update: the presenter's next click does what it says"
    assert live["wcMini"] == {"panel": False, "on": False} and live["wcBack"] == {"panel": True, "on": True}, "minimised, then back from the bar"


def test_a_spec_with_a_mistake_never_shows_in_the_room(browser):
    """The last good mock-up stays up, with no message and no update to press: the mistake is the assistant's to see."""
    assert browser["live"]["broken"] == {"title": "Waiting For Me", "messages": 0, "button": False}


def test_the_bar_says_live_while_the_assistant_is_listening_and_comments_show_what_became_of_them(browser):
    session = browser["session"]
    assert {k: session["before"][k] for k in ("live", "states")} == {"live": False, "states": []}, "no session: no promise that anyone is listening"
    assert {k: session["listening"][k] for k in ("live", "states")} == {"live": True, "states": ["Received"]}
    assert session["working"]["states"] == ["Working on it"] and session["applied"]["states"] == ["Applied"]


def test_a_comment_can_be_changed_while_it_waits_and_says_why_not_once_it_is_taken(browser):
    session = browser["session"]
    assert session["listening"]["edits"] == 1 and session["listening"]["locked"] == []
    assert session["working"]["edits"] == 0 and "Being worked on" in session["working"]["locked"][0]
    assert session["applied"]["edits"] == 0 and "Already dealt with" in session["applied"]["locked"][0]
    assert "Add a new comment instead" in session["applied"]["locked"][0]
    assert session["scope"]["states"] == ["Noted for follow-up"], "a possible change request reads the same as any follow-up"
    assert "possible CR" not in session["sent"] and "R-031" not in session["sent"] and '"scope"' not in session["sent"]


def test_a_danger_button_is_not_drawn_like_the_main_button_when_the_brand_colour_is_red(browser):
    blue, red = browser["danger"]["blue"], browser["danger"]["red"]
    assert not blue["outline"] and blue["reject"] == "rgb(217, 45, 32)", "with any other brand colour it stays filled"
    assert red["outline"] and red["reject"] == "rgb(255, 255, 255)" and red["approve"] == "rgb(200, 16, 46)"


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


def test_a_reload_keeps_the_walk_through_and_reset_puts_the_sample_data_back(browser):
    again = browser["moveAfterReload"]
    assert again["status"] == "Approved" and again["buttons"] == ["Back"] and again["reset"]
    assert browser["resetAsk"] == {"title": "Reset the sample data?", "action": "Reset"}
    reset = browser["moveAfterReset"]
    assert reset["status"] == "Pending Approval" and reset["buttons"] == ["Back", "Reject", "Approve"] and not reset["reset"]
    assert any("sample data is back" in t for t in reset["toasts"])


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


def test_a_button_that_serves_several_steps_moves_each_status_to_its_own_next(browser):
    assert browser["moveByStatus"]["On Hold"]["status"] == "Pending Approval"
    assert browser["moveByStatus"]["Active Review"]["status"] == "Approved"
    assert browser["moveByStatus"]["Approved"]["status"] == "Approved", "a status the button says nothing about stays as it is"


def test_a_skipped_step_is_not_taken_for_the_one_that_is_waiting(browser):
    done, skipped, handled = browser["moveByStatus"]["On Hold"]["timeline"]
    assert skipped[:4] == ["HR Check", "-", "-", "Skipped"]
    assert handled[:2] == ["Line Manager Approval", "HR Admin"] and handled[3] == "Pending Approval" and len(handled[2]) == 16


def test_a_list_shows_each_role_the_rows_meant_for_it(browser):
    """A task list is the records waiting for whoever is signed in: one filter for everyone showed the same rows to all."""
    manager, hr = browser["rowsByRole"]["manager"], browser["rowsByRole"]["hr"]
    assert manager["rows"] and all(row.endswith(" Approved View") for row in manager["rows"]), "a role not named gets `where`"
    assert hr["rows"] and all(" Rejected " in f" {row} " or " Cancelled " in f" {row} " for row in hr["rows"])
    assert manager["pager"] == f"Showing {len(manager['rows'])} of {len(manager['rows'])} records"


def test_a_list_can_show_what_is_waiting_for_whoever_is_signed_in(browser):
    """LV-T-4's progress waits at the line manager's step, and Ahmad Faiz is who the manager role signs in as."""
    assert [row.split(" ")[0] for row in browser["waiting"]["manager"]["rows"]] == ["LV-T-4"]
    assert browser["waiting"]["hr"]["rows"] == [] and browser["waiting"]["hr"]["empty"] == "Nothing is waiting for you"


def test_a_button_goes_by_the_waiting_step_before_the_status(browser):
    """The record is On Hold and waits at Line Manager Approval: the button names both, and the step decides."""
    signed = browser["waiting"]["signedOff"]
    assert signed["status"] == "Approved"
    assert signed["timeline"][2][:2] == ["Line Manager Approval", "Ahmad Faiz"] and signed["timeline"][2][3] == "Approved"
    assert "Sign off" not in signed["buttons"], "nothing is waiting for the manager any more"
    assert browser["waiting"]["afterSignOff"]["rows"] == []


def test_a_row_action_can_be_for_some_roles_only(browser):
    assert all(row.endswith(" View Reopen") for row in browser["rowsByRole"]["hr"]["rows"])
    assert not any("Reopen" in row for row in browser["rowsByRole"]["manager"]["rows"])


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


def test_feedback_mode_marks_what_is_under_the_pointer_inside_its_own_box(browser):
    """The outline used to be drawn outside the element, where a table that clips its content cut it off."""
    hover = browser["marking"]["hover"]
    assert hover["style"] == "solid" and hover["offset"] == "-2px"
    assert hover["others"] == 1, "only the innermost thing is marked, not the section around it too"


def test_a_comment_names_what_it_is_about_in_plain_words(browser):
    """It used to say "Comment on: column:Employee"."""
    box = browser["marking"]["box"]
    assert box["title"] == "Comment on the Employee column" and box["focus"] == "fb-text"
    assert box["marked"] == ["column:Employee"], "the thing commented on stays marked while the comment is typed"
    assert browser["marking"]["titleOfPage"] == "Comment on the page title"
    assert "The Ref No column" in browser["saved"]["panel"]


def test_escape_or_a_click_outside_backs_out_of_a_comment(browser):
    assert browser["marking"]["afterEscape"] == {"box": 0, "marked": 0, "stillOn": True}
    assert browser["marking"]["afterClickOutside"] == 0


def test_ctrl_enter_saves_a_comment(browser):
    saved = browser["keyboardSave"]
    assert saved["box"] == 0 and "saved with the keyboard" in saved["panel"]


@pytest.mark.parametrize("where, title", [
    ("sideMenu", "Comment on the side menu"), ("header", "Comment on the header"), ("background", "Comment on the page background"),
    ("cell", "Comment on the Employee cell of LV-2026-014"), ("figures", "Comment on the Pending figure"),
])
def test_any_part_of_a_screen_can_be_commented_on(browser, where, title):
    """A click outside a named field, column or button used to be a comment on "this screen"."""
    assert browser["anywhere"][where] == title


def test_the_part_under_the_pointer_is_marked_wherever_it_is(browser):
    assert browser["anywhere"]["hoverSideMenu"] == "solid"


def test_a_projects_own_code_runs_after_every_screen_is_drawn(browser):
    own = browser["ownCode"]
    assert own["first"] == {"text": "own code on approvals as manager", "color": "rgb(1, 2, 3)", "count": 1}
    assert own["next"] == {"text": "own code on review-application as manager", "color": "rgb(1, 2, 3)", "count": 1}
    assert own["api"] == ["changed", "custom", "data", "go", "matches", "onRender", "render", "route", "spec", "toast"]


def test_a_pin_opens_the_comment_it_stands_for(browser):
    assert browser["pinClick"] == {"on": True, "shown": 1}
    assert browser["cardPick"] == {"picked": 1, "outlined": 1, "dialog": 0}, "a picked card shows its comment's place; it opens no comment box"


def test_pins_on_the_same_thing_sit_side_by_side(browser):
    """Four comments on one column used to show one pin: the others were underneath it."""
    places = browser["pinPlaces"]
    assert len(places) == 4 and len(set(places)) == 4


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
    assert [c["text"] for c in state["file"]] == ["saved while the server is up", "typed while the server is down", "from another laptop",
                                                  "saved with the keyboard", "second thought"]  # the later Ctrl + Enter and edit checks


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


# ---------------------------------------------------------------------- in the browser: new records, the walk-through, comments, custom work
def test_submit_on_a_new_form_adds_a_record_that_shows_where_it_belongs(browser):
    made = browser["created"]
    assert made["firstRow"] == "LV-2026-015 Emergency Leave 2026-12-01 2026-12-02 2 Pending Approval View"
    assert int(made["figuresAfter"]["Pending"]) == int(made["figuresBefore"]["Pending"]) + 1, "the counts follow"
    assert "Application LV-2026-015 submitted to your line manager" in made["toasts"]
    detail = made["detail"]
    assert detail["screen"] == "application-details" and detail["status"] == "Pending Approval"
    assert detail["timeline"][0][:2] == ["Submitted", "Employee"] and detail["timeline"][0][3] == "Done", "done by whoever submitted it, now"
    assert detail["timeline"][1] == ["Line Manager Approval", "Ahmad Faiz", "-", "Pending"], "the next step waits, for the person of the sample records"
    fields = made["fields"]
    assert fields["reason"] == "Sister's wedding" and fields["leave_type"] == "Emergency Leave" and fields["from"] == "2026-12-01"
    assert fields["employee"] == "Nur Aisyah", "a field left empty takes its default"
    assert fields["to"] == "2026-12-02", "a sample record's value at the same stage, as far from the From typed in as it is there"
    assert made["approvals"][0] == "LV-2026-015" and "LV-2026-015" in made["tasks"], "in the approver's list and task list"
    assert made["afterReload"].startswith("LV-2026-015 "), "a reload keeps it"


def test_the_walk_through_is_shared_by_every_browser_and_reset_for_all(browser):
    shared = browser["shared"]
    assert "LV-2026-015" in shared["otherSees"], "a record added on one laptop is in the list on another"
    assert shared["firstRowThere"].startswith("LV-2026-015 ") and " Approved " in shared["firstRowThere"], "approved there, seen here without a reload"
    assert shared["rolesKept"] == {"here": "employee", "there": "manager"}, "each keeps their own role"
    assert "LV-2026-015" not in shared["afterReset"]


def test_without_a_server_the_tab_keeps_the_walk_through(browser):
    alone = browser["fileOnly"]
    assert alone["added"].startswith("LV-2026-015 ") and alone["afterReload"].startswith("LV-2026-015 ")
    assert not alone["afterReset"].startswith("LV-2026-015 ")


def test_custom_work_is_tagged_while_presenting_and_never_in_a_screenshot(browser):
    custom = browser["custom"]
    titles = [t["title"] for t in custom["dashboard"] if t["text"] == "Custom development"]
    assert any(t.startswith("Figures with a calculation of their own. Calculated in a script") for t in titles)
    assert any(t.startswith("Built in the project's own mock-up code") for t in titles)
    assert len(custom["dashboard"]) == 2, "the figure, and what the project's own code adds"
    assert custom["switchShown"]
    assert "Not standard on Joget DX" in [t["text"] for t in custom["form"]], "a feature the platform does not support says so"
    assert not any("directory" in t["title"] for t in custom["form"]), "configuration is not tagged"
    assert all("BB-08" not in t["title"] and "docs.example" not in t["title"] for t in custom["dashboard"] + custom["form"])
    assert custom["off"] == [] and custom["offAfterReload"] == {"tags": [], "checked": False}, "the switch is remembered"
    assert custom["onAgain"] == 2 and custom["screenshot"] == 0


def test_a_comment_is_edited_and_deleted_from_the_feedback_panel(browser):
    edits = browser["commentEdits"]
    assert edits["buttons"] == ["Edit", "Delete"] and edits["boxText"] == "first thought"
    assert "second thought" in edits["edited"] and "edited" in edits["edited"]
    assert edits["ask"] == {"title": "Remove this comment?", "action": "Remove"}
    assert "second thought" not in edits["after"]["panel"] and "second thought" not in edits["after"]["room"]
    kept = next(c for c in edits["file"] if c["text"] == "second thought")
    assert kept["withdrawn"] and kept["history"][0]["text"] == "first thought" and kept["owner"], "nothing is erased"


# ---------------------------------------------------------------------- new records from a new, empty form
def test_submit_on_a_new_form_adds_a_record_to_the_list_its_fields_are_shown_from():
    made = mockup.new_records(sample())
    assert [(n["screen"], n["label"], n["data"], n["status"]) for n in made] == [("new-application", "Submit", "applications", "Pending Approval")]
    assert "application-details" in made[0]["how"], "tied by the detail screen that shows the form's fields"


@pytest.mark.parametrize("change, expected", [
    (lambda s: screen(s, "new-application").update(data="applications"), ("Submit", "applications", "Pending Approval")),
    (lambda s: [screen(s, x).pop("fields_from") for x in ("application-details", "review-application")],
     ("Submit", "applications", "Pending Approval")),  # the list Submit goes to
    (lambda s: screen(s, "new-application")["buttons"][2].update(set_status="draft"), ("Submit", "applications", "Draft")),
    (lambda s: screen(s, "new-application")["buttons"][2].update(creates="leave_types"), ("Submit", "leave_types", None)),
])
def test_which_list_a_new_record_goes_to_and_its_status(change, expected):
    spec = sample()
    change(spec)
    assert mockup.validate(spec) == []
    assert [(n["label"], n["data"], n["status"]) for n in mockup.new_records(spec)] == [expected]


def test_save_as_draft_can_add_a_draft_and_creates_false_stops_the_main_button():
    spec = sample()
    buttons = screen(spec, "new-application")["buttons"]
    buttons[1].update(creates=True, set_status="draft")
    buttons[2]["creates"] = False
    assert mockup.validate(spec) == []
    assert [(n["label"], n["status"]) for n in mockup.new_records(spec)] == [("Save as Draft", "Draft")]
    assert "Draft to Pending Approval" in mockup.moves_not_shown(spec), "adding a record in a status is no move from another one"


def test_a_main_button_that_opens_a_dialog_adds_the_record_when_it_is_confirmed():
    spec = sample()
    screen(spec, "new-application")["buttons"][2] = {"label": "Submit", "style": "primary", "dialog": "confirm-submit"}
    spec["dialogs"].append({"id": "confirm-submit", "title": "Submit Application", "message": "Send it to your line manager?",
                            "confirm": {"label": "Yes, submit", "style": "primary", "to": "my-applications", "set_status": "pending"}})
    assert mockup.validate(spec) == [], "the confirm button has the new record to put in a status"
    made = mockup.new_records(spec)
    assert [(n["dialog"], n["confirm"], n["status"]) for n in made] == [("confirm-submit", "Yes, submit", "Pending Approval")]


def test_a_form_with_no_list_to_add_to_adds_nothing_and_the_build_says_so(tmp_path, capsys):
    spec = sample()
    for shown in ("application-details", "review-application"):
        screen(spec, shown).pop("fields_from")
        screen(spec, shown)["sections"] = [{"title": "Application", "fields": [{"id": "reason", "label": "Reason", "type": "textarea"}]}]
    screen(spec, "new-application")["buttons"][2].pop("to")
    assert mockup.new_records(spec) == [] and mockup.forms_without_a_list(spec) == ["New Leave Application"]
    support.write_spec(tmp_path / "leave-request", spec)
    mockup.build(tmp_path / "leave-request")
    assert "The main button of New Leave Application only shows its message: give the screen 'data'" in capsys.readouterr().out


@pytest.mark.parametrize("change, said", [
    (lambda s: screen(s, "new-application")["buttons"][2].update(creates="aplications"), "creates 'aplications' is not a list in data (did you mean 'applications'?)"),
    (lambda s: screen(s, "review-application")["buttons"][0].update(creates=True),
     "creates adds a record from a form opened without one, so it only works on the buttons of a form screen"),
    (lambda s: screen(s, "new-application").update(data="applications", record="LV-2026-014") or screen(s, "new-application")["buttons"][2].update(creates=True),
     "the form shows record LV-2026-014 when it is opened, so it is never empty and adds no record"),
    (lambda s: screen(s, "new-application")["buttons"][2].update(creates=3), "creates is true, false or the name of a data list, not 3"),
])
def test_a_creates_that_cannot_work_is_refused(change, said):
    spec = sample()
    change(spec)
    assert any(said in e for e in mockup.validate(spec)), mockup.validate(spec)


def test_the_build_says_which_forms_add_a_record_and_tells_the_engine(tmp_path, capsys):
    project = tmp_path / "leave-request"
    support.write_spec(project, sample())
    mockup.build(project)
    out = capsys.readouterr().out
    assert ("New records: Submit on New Leave Application adds a record to the applications list, as Pending Approval: "
            "it shows in every list and count it matches.") in out
    made = json.loads((project / "mockup" / "build.js").read_text(encoding="utf-8").removeprefix("window.MOCKUP_BUILD = ").rstrip().rstrip(";"))
    assert made["creates"] == [{"screen": "new-application", "label": "Submit", "dialog": None, "confirm": "Submit", "data": "applications",
                                "status": "Pending Approval"}]
    assert '<script src="build.js"></script><script src="assets/app.js"></script>' in (project / "mockup" / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------- the walk-through, shared through the server
def state(server, body=None):
    request = urllib.request.Request(server.url + "api/state", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


NEW = {"id": "LV-2026-015", "status": "Pending Approval"}


def test_the_server_shares_the_walk_through_and_starts_clean(served, built, tmp_path):
    code, first = state(served)
    assert code == 200 and first["lists"] == {}
    sent = {"lists": {"applications": {"key": "id", "created": [NEW], "changed": {}, "removed": []}}, "touched": {"applications": ["LV-2026-015"]}}
    code, after = state(served, sent)
    assert code == 200 and after["lists"]["applications"]["created"] == [NEW] and after["version"] != first["version"]
    # A browser that has not yet seen that record moves another one: only what it touched is taken from it.
    late = {"lists": {"applications": {"key": "id", "created": [], "changed": {"LV-2026-011": {"status": "Approved"}}, "removed": []}},
            "touched": {"applications": ["LV-2026-011"]}}
    code, merged = state(served, late)
    assert merged["lists"]["applications"]["created"] == [NEW] and merged["lists"]["applications"]["changed"] == {"LV-2026-011": {"status": "Approved"}}
    assert state(served, {"reset": True})[1]["lists"] == {}
    assert state(served, {"lists": "nonsense"})[0] == 400 and state(served, {"lists": {}, "touched": {"applications": "LV-1"}})[0] == 400
    other = serve_in_thread(built / "mockup", tmp_path / "other" / "feedback.json")   # a server started again starts from the sample data
    try:
        state(served, sent)
        assert state(other)[1]["lists"] == {}
    finally:
        other.shutdown()
        other.server_close()
    assert not [p for p in (tmp_path / "feedback").glob("*") if "state" in p.name], "kept in memory only, never beside the project's files"


def test_the_page_that_lists_every_mockup_keeps_each_walk_through_apart(home):
    body = json.dumps({"lists": {"applications": {"key": "id", "created": [NEW]}}, "touched": {"applications": ["LV-2026-015"]}}).encode()
    request = urllib.request.Request(home.url + "p/leave-request/api/state", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as answer:
        assert json.loads(answer.read())["lists"]["applications"]["created"] == [NEW]
    assert json.loads(get(home.url + "p/leave-request/api/state")[1])["lists"]["applications"]["created"] == [NEW]
    assert json.loads(get(home.url + "p/courier-booking/api/state")[1])["lists"] == {}, "never shared across projects"


def test_the_servers_tell_a_browser_whether_it_is_the_presenters(served, home):
    assert json.loads(get(served.url + "api/build")[1])["presenter"] is True, "the machine running the server"
    assert json.loads(get(home.url + "p/leave-request/api/build")[1])["presenter"] is True


# ---------------------------------------------------------------------- editing and deleting a comment
def change(server, action, body):
    request = urllib.request.Request(f"{server.url}api/feedback/{action}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_comment_is_edited_and_withdrawn_by_its_writer_and_nothing_is_erased(served, monkeypatch):
    monkeypatch.setattr(mockup, "from_this_machine", lambda request: False)   # another laptop in the room
    post(served, json.dumps({"screen": "approvals", "text": "Call it Staff", "owner": "laptop-a"}).encode())
    assert change(served, "edit", {"id": "FB-001", "text": "Call it Employee", "owner": "laptop-b"})[0] == 403, "not someone else's"
    code, edited = change(served, "edit", {"id": "FB-001", "text": "Call it Employee", "owner": "laptop-a"})
    assert code == 200 and edited["text"] == "Call it Employee" and edited["edited"] and "owner" not in edited and "history" not in edited
    assert change(served, "edit", {"id": "FB-001", "text": "  ", "owner": "laptop-a"})[0] == 400
    code, gone = change(served, "withdraw", {"id": "FB-001", "owner": "laptop-a", "by": "Ali"})
    assert code == 200 and gone == {"id": "FB-001", "withdrawn": True}
    kept = saved(served)[0]
    assert kept["text"] == "Call it Employee" and kept["history"][0]["text"] == "Call it Staff" and kept["withdrawn"] and kept["withdrawn_by"] == "Ali"
    assert json.loads(get(served.url + "api/feedback")[1]) == [], "gone from the room"
    assert change(served, "withdraw", {"id": "FB-001", "owner": "laptop-a"})[0] == 404


def test_the_presenter_may_change_any_comment_but_not_one_that_is_taken(served):
    post(served, json.dumps({"screen": "approvals", "text": "one", "owner": "laptop-a"}).encode())
    post(served, json.dumps({"screen": "approvals", "text": "two"}).encode())
    assert change(served, "edit", {"id": "FB-002", "text": "two, better"})[0] == 200, "the presenter's own machine"
    items = saved(served)
    items[0]["status"] = "working"
    items[1]["status"] = "applied"
    served.fb_file.write_text(json.dumps(items), encoding="utf-8")
    code, said = change(served, "edit", {"id": "FB-001", "text": "changed", "owner": "laptop-a"})
    assert code == 409 and said["error"] == mockup.LOCKED
    assert change(served, "withdraw", {"id": "FB-002"}) == (409, {"error": mockup.DEALT_WITH})


def test_a_withdrawn_comment_waits_for_nobody_and_an_edited_one_shows_its_latest_text(session, capsys, projects):
    fb = session / "feedback" / "feedback.json"
    mockup.save_comment(fb, {"screen": "approvals", "text": "taken back"})
    items = comments(session)
    items[0].update(text="Call this column Staff Name", edited="2026-11-06T10:15:00", history=[{"text": "Call this column Staff"}])
    items[1].update(withdrawn="2026-11-06T10:16:00", withdrawn_by="Ali")
    fb.write_text(json.dumps(items), encoding="utf-8")
    capsys.readouterr()
    mockup.live_list(session)
    out = capsys.readouterr().out
    assert "1 comment waiting" in out and "taken back" not in out
    assert '"Call this column Staff Name"  (edited at 10:15: this is its latest text)' in out
    with pytest.raises(SystemExit, match="FB-002 was taken back in the mock-up by Ali"):
        mockup.live_take(session, ["FB-002"])
    mockup.live_take(session, ["FB-001"])
    assert 'FB-001: "Call this column Staff Name"  (edited in the mock-up after it was first saved' in capsys.readouterr().out
    mockup.show_feedback(session)
    shown = capsys.readouterr().out
    assert "taken back" not in shown and "(edited)" in shown
    assert next(m for m in mockup.mockups(projects) if m["slug"] == "leave-request")["comments"] == 1


# ---------------------------------------------------------------------- custom work tagged while presenting
def test_custom_work_is_read_from_platform_fit_without_its_internal_parts(tmp_path, capsys):
    spec = sample()
    spec["platform_fit"] = PLATFORM_FIT
    work = mockup.custom_work(spec)
    assert work["tags"] == [
        {"screen": "my-applications", "element": "stat:Leave balance (days)", "label": "Custom development",
         "title": "Figures with a calculation of their own. Calculated in a script, an SQL query or a plugin"},
        {"screen": "new-application", "element": "region:page heading", "label": "Not standard on Joget DX",
         "title": "Signing on screen. A signature plugin from the marketplace"}], "configuration is not tagged"
    assert work["code"] is None, "no code of the project's own"
    project = tmp_path / "leave-request"
    support.write_spec(project, spec)
    (project / "spec" / "mockup.js").write_text(OWN_JS, encoding="utf-8")
    assert mockup.custom_work(spec, project)["code"]["label"] == "Custom development", "what the project's code adds is custom by default"
    mockup.build(project)
    assert '2 parts of the mock-up carry a "Custom development" tag while presenting' in capsys.readouterr().out
    built_js = (project / "mockup" / "build.js").read_text(encoding="utf-8")
    assert "BB-08" not in built_js and "docs.example.test" not in built_js and "PF-17" not in built_js


def test_the_projects_code_is_not_tagged_when_the_platform_check_found_it_configuration(tmp_path):
    spec = sample()
    spec["platform_fit"] = {"features": [{"what": "What the mock-up does beyond the spec", "support": "configuration", "row": "Joget DX PF-32",
                                          "features": ["code:project"], "used_in": ["spec/mockup.js"]}]}
    project = tmp_path / "leave-request"
    support.write_spec(project, spec)
    (project / "spec" / "mockup.js").write_text(OWN_JS, encoding="utf-8")
    assert mockup.custom_work(spec, project) == {"tags": [], "code": None}


def test_a_project_without_a_spec_or_folder_gets_a_sentence_not_an_error_trace(tmp_path):
    """build, screenshots and serve on a project with no spec, or a folder that does not exist, say what to do."""
    tool = support.ROOT / "tools" / "mockup.py"
    empty = tmp_path / "empty-project"
    empty.mkdir()
    for command in ("build", "screenshots"):
        r = subprocess.run([sys.executable, "-I", str(tool), command, str(empty)], capture_output=True, text=True)
        assert r.returncode != 0
        assert "No spec at" in r.stderr and "build a mock-up" in r.stderr and "Traceback" not in r.stderr
    r = subprocess.run([sys.executable, "-I", str(tool), "build", str(tmp_path / "nope")], capture_output=True, text=True)
    assert "No project at" in r.stderr and "Traceback" not in r.stderr


def test_a_half_empty_new_request_borrows_from_another_record_not_the_open_twin(browser):
    """Fields left empty used to be copied from the first open record at the same stage, so a new request was
    that record's twin (same customer, same car). They now come from a finished record, or one at another stage;
    the From typed in is kept, and a category such as the leave type is still a sample value."""
    fresh = browser["fresh"]
    assert fresh["fields"]["from"] == "2026-12-10"
    waiting = [x for x in fresh["others"] if x["status"] == "Pending Approval" and x["id"] != fresh["id"]]
    assert waiting, "the sample still has requests waiting at the same stage"
    assert fresh["fields"]["reason"] and fresh["fields"]["reason"] not in [x["reason"] for x in waiting], f"not the twin of a waiting request: {fresh}"
    assert fresh["fields"]["leave_type"] in ("Annual Leave", "Medical Leave", "Emergency Leave")


# ---------------------------------------------------------------------- the client's look
LOOK_SCRIPT = support.ROOT / "tests" / "mockup_look.mjs"


def tiny_png(width=40, height=10):
    """A made-up logo: a small red-and-white PNG."""
    import struct
    import zlib

    rows = b"".join(b"\0" + b"".join(bytes((200, 30, 60, 255)) if (x // 5) % 2 else bytes((255, 255, 255, 255)) for x in range(width))
                    for _ in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def look_project(folder, **look):
    """The sample in a folder of its own, with a logo file in spec/ and the look settings given."""
    spec = sample()
    spec["project"].update(look)
    project = folder / "looks"
    support.write_spec(project, spec)
    (project / "spec" / "client-logo.png").write_bytes(tiny_png())
    return project


def quiet_build(project):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "stdout", io.StringIO())
        return mockup.build(project)


@pytest.mark.parametrize("look, said", [
    ({"corners": "wobbly"}, "project: corners 'wobbly' must be one of square, small, normal, round"),
    ({"menu": "purple"}, "project: menu 'purple' must be one of light, dark"),
    ({"header": "red"}, "project: header 'red' must be one of light, dark, brand"),
    ({"font": "Lato; color: red"}, "project: font 'Lato; color: red' must be the font's name, as written in Word (e.g. Roboto)"),
    ({"font_file": "lato.woff2"}, "project: font_file needs font, the name of the font in that file"),
    ({"logo": "../secret.png"}, "project: logo '../secret.png' must be a file in the project's spec folder ending .png, .jpg, .jpeg, .svg, .gif, .webp"),
    ({"logo": "logo.pdf"}, "project: logo 'logo.pdf' must be a file in the project's spec folder ending .png, .jpg, .jpeg, .svg, .gif, .webp"),
])
def test_the_look_settings_are_checked(look, said):
    spec = sample()
    spec["project"].update(look)
    assert said in mockup.validate(spec)


def test_the_look_settings_build_in_any_case_and_a_spec_without_them_is_clean():
    spec = sample()
    assert mockup.validate(spec) == []
    spec["project"].update(corners="Square", menu="DARK", header="brand", font="Lato")
    assert mockup.validate(spec) == []


def test_a_logo_or_font_file_must_be_in_the_spec_folder(tmp_path, capsys):
    project = look_project(tmp_path, logo="missing.png")
    with pytest.raises(SystemExit):
        mockup.build(project)
    assert f"project: logo 'missing.png' is not in {project / 'spec'}" in capsys.readouterr().out


def test_the_logo_font_and_look_reach_the_mockup(tmp_path):
    project = look_project(tmp_path, logo="client-logo.png", font="Brand Sans", font_file="brand.woff2", corners="square", menu="dark")
    (project / "spec" / "brand.woff2").write_bytes(b"wOF2 made-up font")
    quiet_build(project)
    assets = project / "mockup" / "assets"
    assert (assets / "logo.png").read_bytes() == (project / "spec" / "client-logo.png").read_bytes()
    assert '"logo": "assets/logo.png"' in (project / "mockup" / "build.js").read_text(encoding="utf-8")
    index = (project / "mockup" / "index.html").read_text(encoding="utf-8")
    assert "assets/look.css" in index and "assets/fonts.css" in index
    assert index.index("assets/theme.css") < index.index("assets/look.css"), "the client's look is drawn over the theme"
    fonts = (assets / "fonts.css").read_text(encoding="utf-8")
    assert 'font-family: "Brand Sans"' in fonts and "url(data:font/woff2;base64," in fonts and "font-weight: 400" in fonts
    spec = (project / "mockup" / "spec.js").read_text(encoding="utf-8")
    assert '"corners": "square"' in spec and '"menu": "dark"' in spec
    # Taking the logo and the font out takes them out of the mock-up too.
    support.write_spec(project, sample())
    quiet_build(project)
    assert not list(assets.glob("logo.*")) and not (assets / "fonts.css").exists()
    assert '"logo": null' in (project / "mockup" / "build.js").read_text(encoding="utf-8")


@pytest.mark.skipif(not (mockup.FONT_PACKAGE / mockup.BUNDLED_FONTS["Geist"]).is_file(), reason="needs the Node packages (run setup)")
def test_desk_carries_geist_and_joget_carries_no_font(tmp_path):
    desk = look_project(tmp_path / "desk", theme="desk")
    quiet_build(desk)
    fonts = (desk / "mockup" / "assets" / "fonts.css").read_text(encoding="utf-8")
    assert 'font-family: "Geist"' in fonts and 'font-family: "Geist Mono"' in fonts and "font-weight: 100 900" in fonts
    joget = look_project(tmp_path / "joget", theme="joget")
    quiet_build(joget)
    assert not (joget / "mockup" / "assets" / "fonts.css").exists()
    assert "fonts.css" not in (joget / "mockup" / "index.html").read_text(encoding="utf-8")


def test_every_corner_of_the_clients_screens_follows_the_corners_setting():
    """A corner drawn in pixels must scale with --rs, or `corners: square` would leave it round. The
    presenter's own tools (fb-, cw-tag) keep theirs."""
    import re

    for css in [mockup.ENGINE / "base.css", *sorted((mockup.ENGINE / "themes").glob("*.css"))]:
        rule = ""
        for line in css.read_text(encoding="utf-8").splitlines():
            if line[:1] not in (" ", "\t", "") and "{" in line:
                rule = line  # the selector a continued line belongs to
            if "fb-" in rule or "cw-tag" in rule:
                continue
            for value in re.findall(r"border-radius:\s*([^;}]+)", line):
                value = value.strip()
                assert value in ("0", "50%") or "var(--rs)" in value, f"{css.name}: {line.strip()[:90]}"


@pytest.mark.parametrize("change", [
    lambda p: p.update(logo="client-logo.png"),
    lambda p: p.update(font="Lato"),
    lambda p: p.update(corners="square"),
    lambda p: p.update(menu="dark"),
    lambda p: p.update(header="brand"),
], ids=["logo", "font", "corners", "menu", "header"])
def test_the_clients_look_changes_the_pictures(change, tmp_path):
    project = look_project(tmp_path)
    spec = sample()
    before = mockup.fingerprint(spec, project)
    change(spec["project"])
    assert mockup.fingerprint(spec, project) != before


def test_a_new_logo_file_changes_the_pictures(tmp_path):
    project = look_project(tmp_path, logo="client-logo.png")
    spec = sample()
    spec["project"]["logo"] = "client-logo.png"
    before = mockup.fingerprint(spec, project)
    (project / "spec" / "client-logo.png").write_bytes(tiny_png(width=60))
    assert mockup.fingerprint(spec, project) != before


def test_a_logo_file_the_spec_does_not_name_leaves_the_pictures(tmp_path):
    """A client logo kept for the document's cover changes nothing on screen until the spec names it."""
    spec = sample()
    bare = tmp_path / "bare"
    support.write_spec(bare, spec)
    with_logo = look_project(tmp_path)
    assert mockup.fingerprint(spec, bare) == mockup.fingerprint(spec, with_logo)


def test_contrast_with_white():
    assert mockup.contrast_with_white("#FFFFFF") == pytest.approx(1)
    assert mockup.contrast_with_white("#000") == pytest.approx(21)
    assert mockup.contrast_with_white("not a colour") is None
    assert mockup.contrast_with_white("#1F5FBF") > 4.5


def test_look_notes_name_hard_to_read_colours_fonts_not_carried_and_custom_work_on_joget():
    spec = sample()
    assert mockup.look_notes(spec) == [], "the sample's look is plain joget on Joget, in a colour white reads on"
    spec["project"].update(primary_color="#FFCC00", font="Lato", menu="dark")
    notes = " ".join(mockup.look_notes(spec))
    assert "White words on #FFCC00" in notes and "hard to read" in notes
    assert "Lato is not carried in the mock-up" in notes
    assert "custom theme work" in notes and "platform-fit" in notes
    spec["project"].update(platform="Custom web build", font_file="lato.woff2", primary_color="#0B3D91")
    assert mockup.look_notes(spec) == []


def test_look_shows_the_look_in_effect(tmp_path, capsys):
    project = look_project(tmp_path, theme="desk", corners="small")
    mockup.show_look(project)
    said = capsys.readouterr().out
    assert "Theme:            desk (calm and ordered" in said
    assert "Corners:          small" in said and "Side menu:        as the theme draws it" in said
    assert "Font:             Geist, the theme's own" in said
    assert "the letters LRS (client-logo.png is in the spec folder: set logo to show one)" in said


def fake_shots(command, quiet=False):
    """The screenshot script, faked: one small picture per planned shot."""
    plan, out = Path(command[3]), Path(command[4])
    out.mkdir(parents=True, exist_ok=True)
    shots = json.loads(plan.read_text(encoding="utf-8"))
    for shot in shots:
        (out / f"{shot['name']}.png").write_bytes(tiny_png())
    return 0, "", [s["name"] for s in shots]


def test_trying_a_look_saves_pictures_now_and_as_tried_and_changes_nothing(tmp_path, monkeypatch, capsys):
    project = look_project(tmp_path)
    spec_before = (project / "spec" / "app.yaml").read_text(encoding="utf-8")
    monkeypatch.setattr(mockup, "run_shots", fake_shots)
    mockup.try_look(project, ["menu=dark", "logo=client-logo.png", "theme=desk"])
    said = capsys.readouterr().out
    preview = project / "mockup" / mockup.LOOK_PREVIEW
    names = sorted(p.name for p in preview.glob("*.png"))
    assert names == sorted(f"{n}-{label}.png" for n in ("login", "my-applications", "new-application", "approvals") for label in ("now", "try"))
    assert (project / "spec" / "app.yaml").read_text(encoding="utf-8") == spec_before, "the project is not changed"
    assert not (project / "mockup" / "index.html").exists(), "the project's own mock-up is not built"
    assert 'menu: "dark"' in said and "custom theme work" in said


def test_trying_a_look_that_does_not_build_keeps_the_last_preview(tmp_path, monkeypatch):
    project = look_project(tmp_path)
    monkeypatch.setattr(mockup, "run_shots", fake_shots)
    mockup.try_look(project, ["corners=round"])
    with pytest.raises(SystemExit) as stop:
        mockup.try_look(project, ["corners=wobbly", "logo=nope.png", "theme=plaid"])
    said = str(stop.value)
    assert "corners 'wobbly'" in said and "logo 'nope.png' is not in" in said and "theme 'plaid' is not one of" in said
    assert (project / "mockup" / mockup.LOOK_PREVIEW / "login-try.png").is_file()
    with pytest.raises(SystemExit, match="key is one of"):
        mockup.try_look(project, ["colour=red"])


def test_the_look_preview_is_never_kept_with_a_version(tmp_path, monkeypatch):
    project = look_project(tmp_path)
    monkeypatch.setattr(mockup, "run_shots", fake_shots)
    mockup.try_look(project, ["menu=light"])
    quiet_build(project)
    version = project / "mockup" / "versions" / "v0.1"
    assert (version / "index.html").is_file() and not (version / mockup.LOOK_PREVIEW).exists()


def test_the_look_in_the_browser_from_the_folder(tmp_path):
    """The mock-up opened from its folder: the logo shows, the carried font loads and the settings draw."""
    node = shutil.which("node")
    if not node or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    project = look_project(tmp_path, theme="desk", logo="client-logo.png", corners="square", menu="dark", header="brand", primary_color="#0B3D91")
    quiet_build(project)
    run = subprocess.run([node, str(LOOK_SCRIPT), str(project / "mockup" / "index.html"), "approvals", "manager"],
                         cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    assert seen["errors"] == []
    login = seen["login"]
    assert login["data"] == {"theme": "desk", "corners": "square", "menu": "dark", "header": "brand"}
    assert login["logo"] == {"loaded": True, "alt": "Sample Client Sdn. Bhd."} and not login["letters"]
    assert login["cardCorners"] == "0px"
    if (mockup.FONT_PACKAGE / mockup.BUNDLED_FONTS["Geist"]).is_file():
        assert "Geist" in login["fonts"], "the carried font loads from a page opened from its folder"
    people = seen["list"].pop("people")
    assert seen["list"] == {"topbar": "rgb(11, 61, 145)", "sidebar": "rgb(29, 29, 31)", "logo": True, "buttonCorners": "0px"}
    # People carry their initials in a data colour; the cell's text stays the name.
    assert people and all(p["initials"] and p["text"] and p["initials"] == "".join(w[0] for w in p["text"].split()[:2]).upper() for p in people)
    assert {p["text"] for p in people} >= {"Ahmad Faiz", "Nur Aisyah", "Daniel Tan"},         "the signed-in manager, and every name in the list's Employee column, also one no role signs in as"
    tints = {p["tone"]: p["tint"] for p in people}
    assert all(t not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)") for t in tints.values()), "initials sit on a tint"
    assert len(set(tints.values())) == len(tints), "each data colour gives its own tint"
    same = {}
    for p in people:
        assert same.setdefault(p["text"], p["tone"]) == p["tone"], "the same person always in the same colour"


# ---------------------------------------------------------------------- colours: one loud accent, a data pair, greys
@pytest.mark.parametrize("colours", [["#1597B0"], "#1597B0", ["#1597B0", "teal"], ["1597B0", "#D55181"], ["#1597B0", "#D55181", "#3478D4"]])
def test_data_colors_are_two_hex_colours(colours):
    spec = sample()
    spec["project"]["data_colors"] = colours
    assert any(e.startswith("project: data_colors") for e in mockup.validate(spec))
    spec["project"]["data_colors"] = ["#1597B0", "#d55181"]
    assert mockup.validate(spec) == []


def test_data_colours_change_the_pictures_only_when_set(tmp_path):
    spec = sample()
    plain = mockup.fingerprint(spec)
    spec["project"]["data_colors"] = list(mockup.DESK_DATA)
    assert mockup.fingerprint(spec) != plain


@pytest.mark.parametrize("colour, clash", [("#34C759", "green"), ("#FF9500", "orange"), ("#D70015", "red"), ("#6A2CF0", "violet or indigo"),
                                           ("#1F5FBF", None), ("#1597B0", None), ("#D55181", None), ("#8E3B78", None), ("#1D1D1F", None)])
def test_a_colour_that_reads_as_status_or_is_violet_is_named(colour, clash):
    said = mockup.colour_clash(colour)
    assert (said is None) if clash is None else (clash in said)


def test_desk_notes_an_accent_or_data_colour_that_breaks_the_rules():
    spec = sample()
    spec["project"].update(theme="desk", platform="Custom web build", primary_color="#1F5FBF", data_colors=["#1597B0", "#D55181"])
    assert mockup.look_notes(spec) == []
    spec["project"].update(primary_color="#2E7D32", data_colors=["#1597B0", "#7B3FF2"])
    notes = " ".join(mockup.look_notes(spec))
    assert "The accent #2E7D32 is close to the green that means status" in notes
    assert "A data colour #7B3FF2 is violet or indigo" in notes
    spec["project"]["theme"] = "modern"
    assert not any("data colour" in n or "The accent" in n for n in mockup.look_notes(spec)), "only desk keeps to the design language"


def test_look_shows_the_data_colours(tmp_path, capsys):
    mockup.show_look(look_project(tmp_path / "desk", theme="desk"))
    assert "Data colours:     #1597B0 and #D55181, the theme's own (people's initials)" in capsys.readouterr().out
    mockup.show_look(look_project(tmp_path / "joget"))
    assert "Data colours:     not used by this theme" in capsys.readouterr().out


def test_a_pair_can_be_tried(tmp_path, monkeypatch, capsys):
    project = look_project(tmp_path, theme="desk")
    monkeypatch.setattr(mockup, "run_shots", fake_shots)
    mockup.try_look(project, ["data_colors=#0E6E7E,#D55181"])
    assert 'data_colors: ["#0E6E7E", "#D55181"]' in capsys.readouterr().out


def test_desk_follows_the_design_languages_sizes():
    """docs/design-language.md: the row of buttons a screen ends with is 44px, cards are 24px apart, list text is
    the 15px body size and columns are 16px apart."""
    css = (mockup.ENGINE / "themes" / "desk.css").read_text(encoding="utf-8")
    for rule in (".form-buttons .btn { height: 44px;", "gap: 24px; margin-bottom: 24px; }", "table.datalist { font-size: calc(15px * var(--ts)); }",
                 ".datalist th { padding: 10px 8px;", "#app .datalist td { padding: 13px 8px;"):
        assert rule in css, rule


# ---------------------------------------------------------------------- user fields and the draft rule
def new_application_fields(spec):
    screen = next(s for s in spec["screens"] if s["id"] == "new-application")
    return screen["sections"][0]["fields"]


def test_a_user_field_may_name_the_roles_whose_people_it_offers():
    spec = mockup_spec()
    new_application_fields(spec).append({"id": "backup", "label": "Backup approver", "type": "user", "roles": ["manager"]})
    assert mockup.validate(spec) == []


def test_roles_on_a_field_must_be_on_a_user_field_and_name_roles_of_the_spec():
    spec = mockup_spec()
    fields = new_application_fields(spec)
    fields.append({"id": "backup", "label": "Backup approver", "type": "user", "roles": ["nobody"]})
    fields.append({"id": "note", "label": "Note", "type": "text", "roles": ["manager"]})
    errors = mockup.validate(spec)
    assert any("roles names 'nobody'" in e for e in errors)
    assert any("field note" in e and "roles is for a user field" in e for e in errors)


def test_submit_after_a_draft_with_no_next_goes_to_the_status_after_it():
    """A draft that lists no `next` used to keep a submitted request as Draft; it now starts in the status
    after the draft, while Save as Draft still makes a draft."""
    spec = mockup_spec()
    for st in spec["statuses"]:
        st.pop("next", None)
    second = spec["statuses"][1]
    assert mockup.first_status(spec, "applications", "Submit") == second["name"]
    assert mockup.first_status(spec, "applications", "Save as Draft") == spec["statuses"][0]["name"]


def test_a_desk_search_box_reads_as_a_field_not_disabled():
    """FB-015 on a client mock-up: a grey-filled search box looked disabled. It is white with its outline and a
    search icon, like every field (docs/design-language.md, Fields)."""
    import re

    css = (mockup.ENGINE / "themes" / "desk.css").read_text(encoding="utf-8")
    rule = re.search(r'\.filter\[data-el\^="search:"\] \.f-input \{([^}]*)\}', css).group(1)
    assert "background: #fff" in rule and "var(--field)" not in rule and "border-color" not in rule
    assert "%3Ccircle" in rule, "a search icon"


# ---------------------------------------------------------------------- what changed, after Update ready
CHANGES_SCRIPT = support.ROOT / "tests" / "mockup_changes.mjs"


def what_changed(tmp_path, before, after):
    node = shutil.which("node")
    if not node or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    project = tmp_path / "changes"
    support.write_spec(project, after)
    quiet_build(project)
    (tmp_path / "before.json").write_text(json.dumps(before, default=str), encoding="utf-8")
    (tmp_path / "after.json").write_text(json.dumps(after, default=str), encoding="utf-8")
    run = subprocess.run([node, str(CHANGES_SCRIPT), str(project / "mockup" / "index.html"), str(tmp_path / "before.json"), str(tmp_path / "after.json")],
                         cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    assert seen["errors"] == []
    return seen["changes"]


def test_what_changed_names_each_change_and_where_to_see_it(tmp_path):
    before = sample()
    after = sample()
    form = next(s for s in after["screens"] if s["id"] == "new-application")
    form["sections"][0]["fields"].append({"id": "contact", "label": "Contact number", "type": "text"})
    form["buttons"] = [b for b in form["buttons"] if b["label"] != "Save as Draft"]
    after["screens"].append({"id": "help", "type": "custom", "title": "Help", "roles": ["employee"], "html": "<p>Help</p>"})
    after["statuses"].append({"id": "withdrawn", "name": "Withdrawn", "color": "grey"})
    after["data"]["applications"][0]["reason"] = "Changed"
    after["project"]["primary_color"] = "#2F6B6A"
    for s in after["screens"]:
        s["description"] = "Reworded for the document only."
    changes = what_changed(tmp_path, before, after)
    said = {c["text"]: c for c in changes}
    assert said["Look: colour"]["look"] is True
    assert said["New field: Contact number"] == {"text": "New field: Contact number", "screen": "new-application", "element": "field:contact"}
    assert said["Button taken out: Save as Draft"]["screen"] == "new-application"
    assert said["New screen: Help"]["screen"] == "help"
    assert "New status: Withdrawn" in said
    assert said["Sample data changed: applications"]["element"] == "region:list"
    assert not any("Changed:" in t for t in said), "rewording a description changes nothing on a screen"


def test_nothing_changed_says_nothing(tmp_path):
    assert what_changed(tmp_path, sample(), sample()) == []


# ---------------------------------------------------------------------- the comments workbook
def test_marking_a_comment_writes_the_comments_workbook(tmp_path):
    """Every comment, one row each, with what became of it and the version it was worked into."""
    from openpyxl import load_workbook

    import sheets

    project = tmp_path / "leave-request"
    spec = sample()
    support.write_spec(project, spec)
    fb = mockup.layout.feedback_file(project)
    fb.parent.mkdir(parents=True, exist_ok=True)
    fb.write_text(json.dumps([
        {"id": "FB-001", "screen": "new-application", "role": "employee", "element": "field:leave_type", "text": "Add sick leave", "author": "amir", "version": "0.1", "received": "2026-11-07T10:00:00"},
        {"id": "FB-002", "screen": "approvals", "role": "manager", "element": "region:area above the list", "text": "Too busy", "author": "amir", "version": "0.1"},
        {"id": "FB-003", "screen": "approvals", "role": "manager", "element": "", "text": "Taken back", "version": "0.1", "withdrawn": "2026-11-07T10:05:00"},
    ]), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "stdout", io.StringIO())
        mockup.live_mark(project, "FB-001", "applied", "Sick leave added", register="R-001")
    book = mockup.layout.comments_xlsx(project)
    assert book.exists(), "written as the comment is marked"
    ws = load_workbook(book)["Comments"]
    header = [c.value for c in ws[1]]
    rows = [dict(zip(header, (c.value for c in row))) for row in ws.iter_rows(min_row=2)]
    assert [r["ID"] for r in rows] == ["FB-001", "FB-002"], "a comment taken back is left out"
    first, second = rows
    assert first["Outcome"] == "Applied" and first["What was done"] == "Sick leave added" and first["Register"] == "R-001"
    assert first["Worked in"] == "v" + str(spec["project"]["version"]) and first["Made on"] == "v0.1"
    assert first["Where"] == "Field: Leave Type" and first["Screen"] == "New Leave Application" and first["From"] == "amir · Employee"
    assert second["Outcome"] == "Open" and second["Where"] == "Area above the list" and not second["Worked in"]
    outcome = ws.cell(row=2, column=header.index("Outcome") + 1)
    assert outcome.number_format == sheets.DOT_FORMAT
    assert "Internal" in ws.oddHeader.center.text


# ---------------------------------------------------------------------- comments drawn as a box
def test_a_box_comment_reads_as_several_things_or_something_new():
    labels = {"from": "From Date", "to": "To Date"}
    several = {"element": "field:from", "elements": ["field:from", "field:to"], "box": {"x": 1, "y": 2, "w": 3, "h": 4}}
    new = {"element": "section:Leave Details", "box": {"x": 1, "y": 2, "w": 3, "h": 4}}
    empty = {"element": "region:page background", "box": {"x": 1, "y": 2, "w": 3, "h": 4}}
    assert mockup.readable_where(several, labels) == "2 things: Field: From Date; Field: To Date"
    assert mockup.readable_where(new, labels) == "New, in Section: Leave Details"
    assert mockup.readable_where(empty, labels) == "New, on the screen"
    assert mockup.readable_where({"element": "field:to"}, labels) == "Field: To Date"


def test_the_room_gets_a_comments_box_and_its_things_back():
    """So every laptop draws the box where it was drawn, after a reload too."""
    saved = [{"id": "FB-001", "screen": "s", "element": "field:a", "elements": ["field:a", "field:b"], "box": {"x": 1, "y": 2, "w": 3, "h": 4},
              "text": "t", "owner": "secret", "note": "internal"}]
    room = mockup.for_the_room(saved)[0]
    assert room["box"] == {"x": 1, "y": 2, "w": 3, "h": 4} and room["elements"] == ["field:a", "field:b"]
    assert "note" not in room and "owner" not in room


def test_a_box_for_something_new_keeps_its_place_when_the_layout_changes(tmp_path):
    """Drawn under the centred sign-in card with the Feedback panel open (the page narrower), it stays centred
    under the card, at the same distance, with the panel closed and in a narrower window. Drawn just left of the
    toolbar's New button where the toolbar wraps under the filters, it stays just left of that button when the
    panel closes and in a wide window, where the toolbar sits beside the filters. Dragging marks nothing, and a
    box over the empty page never picks the page background (only a click comments on that)."""
    node = shutil.which("node")
    if not node or not (support.ROOT / "node_modules" / "playwright-core").is_dir():
        pytest.skip("needs Node.js and the Node packages (run setup.cmd or ./setup.sh)")
    project = tmp_path / "box"
    spec = sample()
    spec["project"]["theme"] = "desk"
    support.write_spec(project, spec)
    quiet_build(project)
    run = subprocess.run([node, str(support.ROOT / "tests" / "mockup_box.mjs"), str(project / "mockup" / "index.html")],
                         cwd=support.ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if run.returncode == 77:
        pytest.skip(f"Microsoft Edge could not be started: {run.stderr.strip()[:200]}")
    assert run.returncode == 0, run.stderr
    seen = json.loads(run.stdout.strip().splitlines()[-1])
    assert seen["errors"] == [] and seen["title"].startswith("Something new")
    for state in ("panelOpen", "panelClosed", "narrower"):
        assert abs(seen[state]["offCentre"]) <= 2 and abs(seen[state]["gapUnderCard"] - 14) <= 2, (state, seen[state])
    assert seen["mini"]["width"] == 0 and seen["mini"]["feedback"] and seen["mini"]["commentsButton"], "minimised: Feedback on, nothing over the page, Comments on the bar"
    assert seen["toolbarTitle"] == "Something new in the area above the list"
    for state in ("toolbarPanelOpen", "toolbarPanelClosed", "toolbarWide"):
        assert abs(seen[state]["gapLeftOfButton"] - 14) <= 2 and abs(seen[state]["offMiddle"]) <= 2, (state, seen[state])
    assert seen["markedWhileDrawing"] == [] and seen["markedOverEmptyPage"] == []
    assert seen["emptyTitle"] == "Something new here" and seen["emptyElement"] == ""
    hidden, part = seen["hiddenPart"], seen["shownPart"]
    assert abs(hidden["left"] - (part["left"] - 6)) <= 3 and abs(hidden["top"] - (part["top"] - 6)) <= 3, (hidden, part)
    assert hidden["width"] <= part["width"] + 16, "a box round two things, one hidden, stays round the one on show"
    gone = seen["allHidden"]
    assert gone["boxesAfter"] == gone["boxesBefore"] - 1, "with all its things hidden, a box is not drawn"
    assert any("folded away or hidden" in n for n in gone["note"]), gone
    notes = dict(seen["away"]["notes"])
    assert notes["role only"].startswith("Made while viewing as Line Manager"), notes
    assert "built since" in seen["away"]["done"] and seen["away"]["doneHead"] and not seen["away"]["oldBox"], "done: in the Done part, no mark"
    assert seen["shownDone"], "Show on the screen brings a done comment's mark back, faded"
    assert seen["clickThrough"] not in ("box", ""), "a box never takes a click: the thing inside it does"
    assert any("these two together" in x for x in seen["earlier"]), "the comment box shows the earlier comment on the same thing"
