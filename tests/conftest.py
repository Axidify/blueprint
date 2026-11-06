"""Test setup: keep every test away from the real workspace and from Microsoft Word.

Run the tests with `python -m pytest` (see docs/maintaining.md).
"""
import types

import pytest

import support  # also puts tools/ on the import path
import generate_requirements
import project as project_tool
import workspace


def point_at(monkeypatch, folder):
    """Make the tools use `folder` as the workspace: company profile, branding and projects."""
    (folder / "projects").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(workspace, "workspace_dir", lambda: folder)
    monkeypatch.setattr(project_tool, "PROJECTS", folder / "projects")
    monkeypatch.setattr(project_tool, "ARCHIVE", folder / "projects" / "_archive")
    return folder


@pytest.fixture(scope="session", autouse=True)
def sandbox(tmp_path_factory):
    """For the whole run: an empty temp workspace instead of the real one (so the company is the neutral
    "Your Company" and the document format is the app's default), and no Microsoft Word, so documents are
    generated the way they are on a machine without it. `sandbox.finish_in_word` is the real Word step,
    for the tests that check how it fails."""
    monkeypatch = pytest.MonkeyPatch()
    real_finish_in_word = generate_requirements.finish_in_word
    folder = point_at(monkeypatch, tmp_path_factory.mktemp("workspace"))
    monkeypatch.setattr(generate_requirements, "finish_in_word", lambda docx_path: False)
    yield types.SimpleNamespace(workspace=folder, finish_in_word=real_finish_in_word)
    monkeypatch.undo()


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """A workspace of the test's own, for tests that add branding or projects to it."""
    return point_at(monkeypatch, tmp_path / "workspace")


@pytest.fixture(scope="session")
def example(tmp_path_factory):
    """The made-up sample project, generated once into a temp folder (never into examples/)."""
    return support.generate(support.make_project(tmp_path_factory.mktemp("example") / "leave-request"))


@pytest.fixture(scope="session")
def wide(tmp_path_factory):
    """The fixture project with many roles, a long timeline, grouped field tables and named signatories."""
    return support.generate(support.make_project(tmp_path_factory.mktemp("wide") / "wide-project", support.WIDE))
