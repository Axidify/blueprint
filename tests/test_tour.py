"""tools/tour.py: the tour's scratch copy of the made-up sample, and the draft with gaps planted in it.

Every test makes its copy under a temp folder standing in for the app folder: the real app folder, the
sample in examples/ and the workspace are never written to.
"""
import hashlib
import json
import shutil
import subprocess
import sys

import pytest
import yaml

import support

import extract
import layout
import mockup
import project as project_tool
import status
import tour


def fingerprint(folder):
    """Every file under a folder, with a hash of its content."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


@pytest.fixture
def app(tmp_path):
    """A temp folder standing in for the app folder."""
    return tmp_path / "app"


def test_start_makes_a_copy_and_leaves_the_sample_alone(app):
    before = fingerprint(tour.EXAMPLE)
    copy = tour.start(root=app)
    assert copy == app / ".tour" / "leave-request"
    assert layout.is_new(copy), "the copy is in the folder layout a new project has"
    assert (copy / "_blueprint" / "spec" / "app.yaml").read_bytes() == (tour.EXAMPLE / "spec" / "app.yaml").read_bytes()
    assert (copy / tour.MARKER).is_file()
    for sub in ("1 Client documents", "_blueprint/spec", "_blueprint/feedback"):
        assert (copy / sub).is_dir()
    assert not (copy / "spec").exists() and not (copy / "docs").exists()
    register = json.loads((copy / "_blueprint" / "register.json").read_text(encoding="utf-8"))
    assert register["project"] == "Leave Request System" and register["items"] == []
    assert tour.draft_of(copy) is not None and tour.draft_of(copy).parent == copy / "1 Client documents"
    # what is built from the sample is built afresh by the tour, never copied
    assert not layout.mockup_dir(copy).exists() and not layout.output_dir(copy).exists() and not list(copy.rglob("*.xlsx"))
    tour.remove_copy(root=app)
    assert fingerprint(tour.EXAMPLE) == before


def test_the_copy_is_ignored_by_git():
    if not shutil.which("git") or not (support.ROOT / ".git").exists():
        pytest.skip("needs git and the app's repository")
    probe = subprocess.run(["git", "check-ignore", "-q", ".tour/leave-request/spec/app.yaml"], cwd=support.ROOT)
    assert probe.returncode == 0, ".tour/ must be in .gitignore: the tour's copy is never committed"


def test_start_again_starts_over(app):
    copy = tour.start(root=app)
    (copy / "stray.txt").write_text("left from an earlier tour", encoding="utf-8")
    layout.spec_file(copy).write_text("project: {name: changed}\n", encoding="utf-8")
    tour.add_comment(root=app)
    again = tour.start(root=app)
    assert again == copy
    assert not (copy / "stray.txt").exists() and not layout.feedback_file(copy).exists()
    assert layout.spec_file(copy).read_bytes() == (tour.EXAMPLE / "spec" / "app.yaml").read_bytes()


def test_end_removes_the_copy_and_nothing_else(app):
    copy = tour.start(root=app)
    other = app / "projects" / "real-project"
    other.mkdir(parents=True)
    (other / "register.json").write_text("{}", encoding="utf-8")
    for refused in (other, app / "projects", tour.EXAMPLE, app / ".tour"):
        with pytest.raises(SystemExit):
            tour.remove_copy(refused, root=app)
    assert (other / "register.json").exists() and (tour.EXAMPLE / "spec" / "app.yaml").exists() and copy.exists()

    assert tour.remove_copy(root=app) is True
    assert not copy.exists() and not (app / ".tour").exists()
    assert (other / "register.json").exists()
    assert tour.remove_copy(root=app) is False  # nothing left to remove


def test_end_refuses_a_folder_the_tour_did_not_make(app):
    stranger = tour.tour_copy(app)
    stranger.mkdir(parents=True)
    (stranger / "notes.txt").write_text("not the tour's", encoding="utf-8")
    with pytest.raises(SystemExit):
        tour.remove_copy(root=app)
    assert (stranger / "notes.txt").exists()
    with pytest.raises(SystemExit):  # nor does a sample comment go into it
        tour.add_comment(root=app)


def test_the_tour_is_not_one_of_the_projects(app, monkeypatch, capsys):
    tour.start(root=app)
    (app / "projects").mkdir()
    monkeypatch.setattr(status, "ROOT", app)
    monkeypatch.setattr(project_tool, "PROJECTS", app / "projects")
    monkeypatch.setattr(sys, "argv", ["status.py"])
    status.main()
    out = capsys.readouterr().out
    assert "No projects on this machine yet" in out and "leave-request" not in out
    assert project_tool.active_slugs() == []  # nor on the page that lists every mock-up


def test_the_planted_draft_has_its_gaps(app, monkeypatch, capsys):
    copy = tour.start(root=app)
    out = layout.reviews_dir(copy) / "draft-v0.1" / "extract"
    monkeypatch.setattr(sys, "argv", ["extract.py", str(tour.draft_of(copy)), str(out)])
    extract.main()
    text = (out / "text.md").read_text(encoding="utf-8")
    for gap in tour.PLANTED:
        line = next((x for x in text.splitlines() if x.startswith(gap["where"])), "")
        assert gap["sign"] in line, f"{gap['where']} should show {gap['gap']}"
    markers = " ".join(i["text"] for i in json.loads((out / "meta.json").read_text(encoding="utf-8"))["open_items"])
    assert "TBC" in markers and "if applicable" in markers
    assert "reject" not in text.lower()  # no reject path
    assert "formula" not in text.lower() and "calculat" not in text.lower()  # the KPI has no formula
    roles = [r[0] for r in tour.DRAFT_ROLES[1:]]
    assert "Supervisor" not in roles and "Line Manager" in roles  # a role the roles table does not define
    assert "Blueprint tour" in text  # says it is made up


def test_the_tools_work_on_the_copy(app, capsys):
    copy = tour.start(root=app)
    mockup.build(copy)
    assert (copy / "_blueprint" / "mockup" / "index.html").exists()
    saved = tour.add_comment(root=app)
    assert saved["id"] == "FB-001"
    spec = yaml.safe_load(layout.spec_file(copy).read_text(encoding="utf-8"))
    screen = next(s for s in spec["screens"] if s["id"] == saved["screen"])
    assert saved["element"].split(":")[1] in [f["id"] for sec in screen["sections"] for f in sec["fields"]]
    assert saved["role"] in screen["roles"]
    comments = json.loads(layout.feedback_file(copy).read_text(encoding="utf-8"))
    assert [c["id"] for c in comments] == ["FB-001"]
