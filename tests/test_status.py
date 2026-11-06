"""tools/status.py: the summary shown when a session starts, and that one damaged project does not hide the rest."""
import json
import sys

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
