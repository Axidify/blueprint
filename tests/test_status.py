"""tools/status.py: the summary shown when a session starts, and that one damaged project does not hide the rest."""
import datetime as dt
import json
import os
import sys
import time

import pytest

import support

import status


def project(root, slug, register=None, spec=None, feedback=None):
    p = root / "projects" / slug
    p.mkdir(parents=True)
    if register is not None:
        (p / "register.json").write_text(register if isinstance(register, str) else json.dumps(register), encoding="utf-8")
    if spec is not None:
        (p / "spec").mkdir()
        (p / "spec" / "app.yaml").write_text(spec, encoding="utf-8")
    if feedback is not None:
        (p / "feedback").mkdir()
        (p / "feedback" / "feedback.json").write_text(feedback, encoding="utf-8")
    return p


GOOD = {"project": "Leave Request System", "items": [
    {"id": "R-001", "audience": "client", "severity": "high", "status": "open"},
    {"id": "R-002", "audience": "client", "severity": "low", "status": "resolved"},
    {"id": "R-003", "audience": "internal", "severity": "medium", "status": "open"}]}


@pytest.fixture
def run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(status, "ROOT", tmp_path)

    def call(*options):
        monkeypatch.setattr(sys, "argv", ["status.py", *options])
        status.main()
        return capsys.readouterr().out

    return call


def test_a_project_is_summarised(tmp_path, run):
    project(tmp_path, "leave-request", GOOD, "project: {version: 0.3}\n")
    out = run()
    assert "- Leave Request System (leave-request): spec v0.3; 1 client questions open (1 high), 1 internal" in out
    assert "next: " in out and "!" not in out


def test_no_projects_says_how_to_start(tmp_path, run):
    assert "No projects on this machine yet" in run("--brief")


@pytest.mark.parametrize("register, spec, feedback, said", [
    ("{ not json", None, None, "register.json could not be read (JSONDecodeError)"),
    ({"project": "Bad", "items": [{"id": "R-001", "status": "open"}, "not an item"]}, None, None, None),
    (["a list"], None, None, "register.json is not a register"),
    (GOOD, "project: [unclosed\n", None, "app.yaml could not be read"),
    (GOOD, "", None, None),
    (GOOD, None, "{ not json", "feedback.json could not be read (JSONDecodeError)"),
], ids=["damaged-register", "items-missing-fields", "register-not-a-register", "damaged-spec", "empty-spec", "damaged-feedback"])
def test_a_damaged_project_is_reported_and_the_others_are_still_shown(tmp_path, run, register, spec, feedback, said):
    """This runs at the start of every session. One unreadable file used to stop it with an error, so no
    project was shown at all."""
    project(tmp_path, "a-damaged", register, spec, feedback)
    project(tmp_path, "b-fine", GOOD, "project: {version: 1.0}\n")
    out = run("--brief")
    assert "- Leave Request System (b-fine): spec v1.0; 1 client questions open (1 high), 1 internal" in out
    assert "(a-damaged)" in out or "- a-damaged" in out, "the damaged project is still listed"
    if said:
        assert f"    ! {said}" in out
    assert "New here? Type /start for the menu." in out


def test_whatever_else_goes_wrong_with_one_project_the_rest_are_shown(tmp_path, run, monkeypatch):
    project(tmp_path, "a-odd", GOOD)
    project(tmp_path, "b-fine", GOOD)
    real = status.project_status
    monkeypatch.setattr(status, "project_status", lambda p: (_ for _ in ()).throw(OSError("disk")) if p.name == "a-odd" else real(p))
    out = run()
    assert "- a-odd: could not be read (OSError)" in out and "(b-fine)" in out


def test_only_client_items_count_as_high_client_questions(tmp_path, run):
    """The "(n high)" next to the client questions used to count internal high items too."""
    register = {"project": "Leave Request System", "items": [
        {"id": "R-001", "audience": "client", "severity": "high", "status": "open"},
        {"id": "R-002", "audience": "internal", "severity": "high", "status": "open"},
        {"id": "R-003", "audience": "internal", "severity": "high", "status": "open"},
        {"id": "R-004", "audience": "client", "severity": "high", "status": "resolved"}]}
    project(tmp_path, "leave-request", register, "project: {version: 0.3}\n")
    assert "1 client questions open (1 high), 2 internal" in run()


# ------------------------------------------------------------------ the next step, stage by stage
DAY = 86400


def touch(path, when, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (when, when))
    return path


def staged(root, *, docs=False, review=None, spec=None, high=0, medium=0, workshop=None, feedback=0,
           estimate=None, doc=None, issued=None, actuals=False):
    """A project at a stage. Times are in days from now (negative is earlier): spec=-3 means the spec was last
    changed three days ago."""
    now = time.time()
    p = project(root, "leave-request", {"project": "Leave Request System", "items":
        [{"id": f"R-{n:03}", "audience": "client", "severity": "high", "status": "open"} for n in range(high)]
        + [{"id": f"R-{100 + n:03}", "audience": "client", "severity": "medium", "status": "open"} for n in range(medium)]})
    if docs:
        touch(p / "docs" / "2026-11-01 brief.docx", now - 10 * DAY)
    if review is not None:
        name, when = review
        touch(p / "reviews" / name / "review.md", now + when * DAY)
    if spec is not None:
        touch(p / "spec" / "app.yaml", now + spec * DAY, "project: {version: '0.2'}\n")
    if workshop is not None:
        date = (dt.date.today() + dt.timedelta(days=workshop)).isoformat()
        touch(p / "workshops" / f"{date} workshop 2.json", now - DAY, json.dumps({"date": date}))
    if feedback:
        touch(p / "feedback" / "feedback.json", now, json.dumps([{"id": n, "text": "x"} for n in range(feedback)]))
    if estimate is not None:
        touch(p / "estimates" / "2026-11-01 estimate from spec v0.2.json", now + estimate * DAY, "{}")
    if doc is not None:
        version, when = doc
        touch(p / "output" / f"Leave Request System – Requirements v{version}.docx", now + when * DAY)
    if issued:
        touch(p / "output" / "issued.json", now, json.dumps([{"version": issued, "to": "Client", "date": "2026-11-05"}]))
    if actuals:
        touch(root / "knowledge" / "actuals" / "leave-request.md", now)
    return p


@pytest.mark.parametrize("stage, said", [
    (dict(), "drop the brief or scope of work into the inbox"),
    (dict(docs=True), "say 'review the requirements document' for a draft, or 'build a mock-up' from a brief"),
    (dict(docs=True, review=("requirements-v1.0", -5), high=3), "reviewed: say 'build a mock-up' to show in the next workshop, then 'prepare the workshop'"),
    (dict(spec=-3, high=2), "2 high-priority client question(s) open: say 'prepare the workshop'"),
    (dict(spec=-3, high=2, workshop=4), "is prepared: say 'present the mock-up' there"),
    (dict(spec=-3, high=2, workshop=-2), "say 'prepare the workshop'"),
    (dict(spec=-3, high=2, feedback=4), "4 mock-up comment(s) not worked in yet: say 'apply the feedback'"),
    (dict(spec=-3, medium=2), "say 'generate the requirements document' (its Open Issues section lists the 2 client question(s) still open)"),
    (dict(spec=-3, doc=("0.2", -4)), "the spec changed since the document was generated"),
    (dict(spec=-3, doc=("0.1", -1)), "the spec changed since the document was generated"),
    (dict(spec=-3, doc=("0.2", -2)), "say 'review the generated requirements document' (v0.2)"),
    (dict(spec=-3, doc=("0.2", -2), review=("requirements-v0.2", -2.5)), "v0.2 is generated and reviewed: when it goes to the client"),
    (dict(spec=-3, doc=("0.2", -2), review=("generated", -1)), "v0.2 is generated and reviewed"),
    (dict(spec=-3, doc=("0.2", -2), review=("requirements-v0.1", -2.5)), "say 'review the generated requirements document'"),
    (dict(spec=-3, doc=("0.2", -2), issued="0.2"), "v0.2 went to the client: after delivery, say 'close the project'"),
    (dict(spec=-3, doc=("0.2", -2), issued="0.1"), "say 'review the generated requirements document'"),
    (dict(spec=-3, actuals=True), "say 'archive this project'"),
], ids=["nothing", "docs", "reviewed-no-spec", "spec-high-open", "workshop-coming", "workshop-past", "feedback",
        "no-document", "document-older-than-spec", "document-of-older-version", "not-reviewed", "reviewed-by-name",
        "reviewed-after", "review-of-another-version", "issued", "new-version-after-issue", "delivered"])
def test_the_next_step_follows_the_stage(tmp_path, run, stage, said):
    staged(tmp_path, **stage)
    out = run()
    assert f"    next: {said}" in out or said in out.split("next: ", 1)[1].splitlines()[0], out
    assert run("--brief").count("    -> ") == 1


@pytest.mark.parametrize("estimate, hint", [
    (None, "for the lead developer: no estimate yet; say 'estimate this project'"),
    (-5, "for the lead developer: the spec changed since the last estimate"),
    (-1, None),
])
def test_the_lead_developer_is_told_when_the_estimate_is_missing_or_older_than_the_spec(tmp_path, run, estimate, hint):
    staged(tmp_path, spec=-3, high=1, estimate=estimate)
    out = run()
    if hint:
        assert f"    also: {hint}" in out
    else:
        assert "also:" not in out
    assert "also:" not in run("--brief"), "the start-up summary keeps to one step per project"


def test_comments_taken_back_in_the_mockup_are_not_counted_as_waiting(tmp_path, run):
    p = staged(tmp_path, spec=-3, high=2, feedback=1)
    comments = [{"id": "FB-001", "text": "waiting"}, {"id": "FB-002", "text": "taken back", "withdrawn": "2026-11-06T10:00:00"},
                {"id": "FB-003", "text": "done", "status": "applied"}]
    (p / "feedback" / "feedback.json").write_text(json.dumps(comments), encoding="utf-8")
    assert "1 mock-up comment(s) not worked in yet" in run()


def test_files_left_in_the_inbox_are_said_apart(tmp_path, run):
    """A file left in the inbox with a note of why (project.py hold) is reported apart from new files; the
    notes file itself, notes of files since filed and a damaged notes file are never shown."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "minutes.docx").write_bytes(b"x")
    (inbox / "brief.pdf").write_bytes(b"x")
    (inbox / ".notes.json").write_text(json.dumps({
        "minutes.docx": {"date": "2026-11-05", "reason": "not sure which project"},
        "gone.docx": {"date": "2026-11-01", "reason": "filed since"}}), encoding="utf-8")
    out = run("--brief")
    assert "- inbox/ has 1 file(s) waiting: brief.pdf. Say 'process my inbox'." in out
    assert "- inbox/: 1 file waiting: not sure which project (minutes.docx). Say 'process my inbox' to choose." in out
    assert ".notes.json" not in out and "gone.docx" not in out
    (inbox / ".notes.json").write_text("{ damaged", encoding="utf-8")
    assert "- inbox/ has 2 file(s) waiting" in run("--brief")


def test_dates_in_the_next_step_are_written_for_people():
    assert status.readable_date("2026-11-13") == "13 Nov 2026"
    assert status.readable_date("next week") == "next week"
