"""The mock-up tool: the build, the spec check for status colours, the server that saves comments, and
(where Node and Microsoft Edge are installed) the mock-up itself, clicked through in the browser."""
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
], ids=["requirement", "version-and-cover", "screen-description", "field-rule", "role-text", "status-meaning", "document-chapters"])
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
    assert [c["text"] for c in state["file"]] == ["saved while the server is up", "typed while the server is down"]
