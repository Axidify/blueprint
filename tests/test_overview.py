"""tools/overview.py: the overview page at the top of a project folder, the "Open the mock-up" shortcuts, the
review as a Word file (tools/review_doc.py), and the tools that rebuild the page after they write."""
import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest
import yaml
from docx import Document

import support

import estimate
import mockup
import overview
import project as project_tool
import register
import review_doc
import status

SAMPLE_DOC = "Leave Request System – System Requirement Specifications v0.1"


def build_mockup(p):
    """Build the project's mock-up as `mockup.py build` does (it keeps a copy as mockup/versions/v<version>)."""
    with contextlib.redirect_stdout(io.StringIO()):
        mockup.build(p)


def fake_output(p):
    """What generating the requirements document leaves in output/; the built sample's own output is git-ignored."""
    out = p / "output"
    out.mkdir(exist_ok=True)
    (out / f"{SAMPLE_DOC}.docx").write_bytes(b"docx")
    (out / f"{SAMPLE_DOC}.pdf").write_bytes(b"%PDF-1.4 sample")
    shutil.copy(p / "spec" / "app.yaml", out / "spec-v0.1.yaml")


def build_estimate(p):
    """The estimate's Excel file as `estimate.py render` writes it, with the app's starter knowledge base."""
    for f in (p / "estimates").glob("*.json"):
        est = json.loads(f.read_text(encoding="utf-8"))
        res, _ = estimate.compute(est, p, support.ROOT / "templates" / "knowledge")
        estimate.render_xlsx(est, res, f.with_suffix(".xlsx"))


def sample_copy(p):
    """The sample project as a fresh checkout makes it, built here: its mock-up, output and the estimate's
    Excel file are git-ignored."""
    shutil.copytree(support.EXAMPLE, p, ignore=shutil.ignore_patterns("mockup", "output", "*.xlsx"))
    build_mockup(p)
    support.fake_screenshots(p)
    fake_output(p)
    build_estimate(p)


MOMENT = dt.datetime(2026, 11, 6, 21, 40)
REVIEW_MD = """# Review: Leave Request System SRS v1.0

Document: `docs/2026-10-22 SRS v1.0.pdf`. Reviewed 2026-11-06.

## Verdict

**Not ready for sign-off.** The approval rules contradict each other, and *two* screens are missing.

## Top items by risk

1. **R-001 Approval levels (high).** Section 4.2 says one level; Appendix B says two.
2. **R-002 Carry-forward (medium).** Not described.
   - Ask about the cut-off date.

## Counts

| Audience | High | Medium |
|---|---|---|
| Client | 1 | 1 |
| Internal | 0 | 2 |

> Patterns checked and well covered: notifications.
"""


def page_text(project):
    return (project / overview.PAGE).read_text(encoding="utf-8")


def visible(html):
    """The page's words, without tags, styles and links."""
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def links(html):
    return [unquote(h) for h in re.findall(r'href="([^"]+)"', html)]


def rows(html):
    """Each linked row of the page: (link, its words)."""
    return [(unquote(href), visible(inner)) for href, inner in re.findall(r'<a class="row" href="([^"]+)">(.*?)</a>', html, re.S)]


def item(n, audience="client", severity="high", stage="requirements-draft", state="open"):
    return {"id": f"R-{n:03d}", "type": "question" if audience == "client" else "fix", "audience": audience, "severity": severity,
            "category": "GP-02", "stage": stage, "source": "SRS v1.0 §4.2", "finding": f"Finding {n}",
            "question": f"Question {n}?", "status": state, "raised": "2026-11-06"}


def empty_project(root, slug="courier-booking"):
    p = root / slug
    for sub in ("docs", "reviews", "spec", "feedback"):
        (p / sub).mkdir(parents=True)
    (p / "register.json").write_text(json.dumps({"project": "Courier Booking", "client": "Sample Client", "items": []}), encoding="utf-8")
    return p


@pytest.fixture
def full(tmp_path, monkeypatch):
    """The sample project with something in every stage: a client document, a review, a workshop on its way,
    comments, change notes, an older mock-up version, the generated document and an estimate."""
    p = tmp_path / "leave-request"
    sample_copy(p)
    spec = support.load_spec(p)
    spec["project"]["client"] = "Sample <script>alert('x')</script> & Co"
    support.write_spec(p, spec)
    (p / "docs").mkdir()
    (p / "docs" / "2026-10-22 SRS v1.0.pdf").write_bytes(b"%PDF-1.4 sample")
    (p / "docs" / "2026-10-30 notes & comments #1.txt").write_text("notes", encoding="utf-8")
    items = [item(1), item(2, severity="medium"), item(3, audience="internal", severity="low"), item(4, state="resolved")]
    (p / "register.json").write_text(json.dumps({"project": "Leave Request System", "client": "Sample", "items": items}), encoding="utf-8")
    register.render(p, register.load(p))
    (p / "reviews" / "srs-v1.0").mkdir(parents=True)
    (p / "reviews" / "srs-v1.0" / "review.md").write_text(REVIEW_MD, encoding="utf-8")
    (p / "reviews" / "mockup-v0.1-changes.md").write_text("# Changes\n", encoding="utf-8")
    day = (dt.date.today() + dt.timedelta(days=7)).isoformat()
    (p / "workshops").mkdir()
    agenda = {"project": "Leave Request System", "workshop": "Workshop 2: mock-up review", "date": day, "duration_minutes": 120,
              "goal": "Agree", "sections": [{"title": "Rules", "minutes": 30, "items": [{"ref": "R-001", "question": "Q?"}]}]}
    (p / "workshops" / f"{day} workshop 2.json").write_text(json.dumps(agenda), encoding="utf-8")
    (p / "workshops" / f"{day} workshop 2 - agenda.docx").write_bytes(b"docx")
    (p / "workshops" / f"{day} workshop 2 - facilitator notes (internal).docx").write_bytes(b"docx")
    (p / "feedback").mkdir(exist_ok=True)
    (p / "feedback" / "feedback.json").write_text(json.dumps([
        {"id": "FB-001", "text": "Wider", "status": "applied"}, {"id": "FB-002", "text": "Later", "status": "scope"},
        {"id": "FB-003", "text": "Gone", "withdrawn": True}]), encoding="utf-8")
    shutil.copytree(p / "mockup" / "versions" / "v0.1", p / "mockup" / "versions" / "v0.1-presented-20261106-2052")
    return p


# ---------------------------------------------------------------------- the page
def test_the_page_lists_every_stage_in_process_order_with_the_next_step(full):
    html = page_text(overview.build(full, MOMENT).parent)
    text = visible(html)
    order = [html.index(t) for t in ("Next step", "Questions for the client", "Fixes for our team", "<h2>Client documents</h2>",
                                     "<h2>Review</h2>", "<h2>Workshops</h2>", "<h2>Mock-up</h2>", "<h2>Requirements document</h2>",
                                     "<h2>Estimate</h2>", "working files")]
    assert order == sorted(order)
    assert "Updated by Blueprint 6 November 2026, 21:40" in text
    assert "Leave Request System" in text and "Joget DX" in text
    # Two high client questions open, one of them on the coming workshop's agenda: the workshop is the next step.
    assert "is prepared" in text and 'class="say">present the mock-up<' in html
    assert re.search(r'class="btn-primary" href="workshops/[^"]+ - agenda\.docx">Open the agenda<', unquote(html))
    assert html.count("btn-primary\"") == 1  # one primary button on the page
    figures = re.findall(r'<div class="v">([^<]*)</div><div class="l quiet detail">([^<]*)</div>', html)
    assert figures == [("2", "Questions for the client"), ("1", "Fixes for our team"), ("v0.1", "Mock-up"), ("v0.1", "Requirements document")]
    assert "1 block sign-off" in text
    assert "1 possible change request" in text and "2 comments handled" in text  # the withdrawn comment does not count
    assert "Earlier versions" in text and "v0.1 as presented on 6 Nov, 20:52" in text and 'class="say">show mock-up v0.1<' in html


def test_internal_files_are_marked_internal_and_client_files_say_who_they_are_for(full):
    html = page_text(overview.build(full, MOMENT).parent)
    tags = {href: words for href, words in rows(html)}
    internal = [h for h, w in tags.items() if "Internal" in w]
    assert any(h.startswith("estimates/") and h.endswith(".xlsx") for h in internal)
    assert any("facilitator notes" in h for h in internal)
    assert any(h.startswith("reviews/srs-v1.0/") for h in internal)
    assert "reviews/mockup-v0.1-changes.md" in internal
    assert "Client sheet only" in tags["register.xlsx"]
    assert "From the client" in tags["docs/2026-10-22 SRS v1.0.pdf"]
    assert any("For the client" in w for h, w in tags.items() if h.endswith(" - agenda.docx"))
    assert "Show the client" in tags["mockup/index.html"] and "Can be shared" in tags["mockup/screenshots/"]
    assert all("For the client" in w for h, w in tags.items() if h.startswith("output/"))
    assert html.count('class="tag internal"') == len(internal)
    assert all('<svg' in tag for tag in re.findall(r'<span class="tag internal">(.*?)</span>', html))  # with the lock


def test_text_from_the_project_is_escaped(full):
    html = page_text(overview.build(full, MOMENT).parent)
    assert "<script>" not in html
    assert "Sample &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; Co" in html
    assert "notes &amp; comments #1" in html
    assert "docs/2026-10-30%20notes%20%26%20comments%20%231.txt" in html  # a # or & in a file name still opens the file


def test_every_link_opens_a_file_or_folder_of_the_project(full):
    html = page_text(overview.build(full, MOMENT).parent)
    found = links(html)
    assert len(found) >= 12
    for href in found:
        assert not href.startswith(("/", "file:", "http")) and ".." not in href
        assert (full / href).exists(), href


def test_no_mandays_rates_or_cost_even_when_the_estimate_is_priced(full, monkeypatch):
    priced = {"lines": [{"id": "E1"}], "unpriced": [], "partial": False, "confidence": "medium",
              "total": (123.5, 456.5), "build": (100.25, 400.75)}
    monkeypatch.setattr(estimate, "compute", lambda est, project, kdir: (priced, []))
    text = visible(page_text(overview.build(full, MOMENT).parent))
    assert "Priced as a range" in text and "Never send it to the client" in text
    for figure in ("123", "456", "100.25", "400.75"):
        assert figure not in text
    assert not re.search(r"\b(MD|mandays?|man-days?|RM|cost|day rate)\b", text, re.I)


def test_the_estimate_says_when_it_is_older_than_the_spec(full):
    os.utime(full / "spec" / "app.yaml", (dt.datetime.now().timestamp() + 60,) * 2)
    text = visible(page_text(overview.build(full, MOMENT).parent))
    assert "Older than the spec" in text and "For the lead developer" in text and "estimate this project" in text


def test_an_empty_project_shows_how_to_get_to_each_stage(tmp_path):
    p = empty_project(tmp_path)
    html = page_text(overview.build(p, MOMENT).parent)
    text = visible(html)
    for hint in ("No documents yet", "Nothing reviewed yet", "No workshop prepared yet", "No mock-up yet",
                 "No requirements document yet", "No estimate yet"):
        assert hint in text
    for words in ("process my inbox", "build a mock-up", "prepare the workshop", "generate the requirements document", "estimate this project"):
        assert f'class="say">{words}<' in html
    assert "btn-primary" not in html.split("</style>")[1]  # nothing to open yet
    assert not (p / overview.SHORTCUT_WINDOWS).exists() and not (p / overview.SHORTCUT_MAC).exists()
    assert links(html) == []


@pytest.mark.parametrize("stage, heading, button", [
    ("documents", "Review the requirements document for a draft, or build a mock-up from a brief", ("Open the document", "docs/")),
    ("reviewed", "Reviewed", ("Open the review", "reviews/srs-v1.0/SRS v1.0 review.docx")),
    ("mock-up", "1 high-priority client question open", ("Open the register", "register.xlsx")),
    ("issued", "v0.1 went to the client", ("Open the requirements document", "output/")),
])
def test_the_next_step_follows_the_projects_stage(tmp_path, stage, heading, button):
    p = empty_project(tmp_path)
    (p / "docs" / "2026-11-01 brief.docx").write_bytes(b"docx")
    if stage != "documents":
        (p / "reviews" / "srs-v1.0").mkdir()
        (p / "reviews" / "srs-v1.0" / "review.md").write_text(REVIEW_MD, encoding="utf-8")
        (p / "register.json").write_text(json.dumps({"project": "Courier Booking", "items": [item(1), item(2, "internal")]}), encoding="utf-8")
        register.render(p, register.load(p))
    if stage in ("mock-up", "issued"):
        shutil.copytree(support.EXAMPLE / "spec", p / "spec", dirs_exist_ok=True)
        build_mockup(p)
    if stage == "issued":
        fake_output(p)
        (p / "output" / "issued.json").write_text(json.dumps([{"version": "0.1", "date": "2026-11-05", "to": "Client", "files": []}]), encoding="utf-8")
    html = unquote(page_text(overview.build(p, MOMENT).parent))
    focus = re.search(r'<section class="card focus span-12">(.*?)</section>', html, re.S).group(1)
    assert heading in visible(focus)
    label, target = button
    assert re.search(rf'class="btn-primary" href="{re.escape(target)}[^"]*">{label}<', focus), focus
    if stage == "issued":
        assert "Sent to the client on 5 Nov 2026" in visible(html)


def test_a_review_of_the_generated_document_sits_with_the_document(full):
    folder = full / "reviews" / "requirements-v0.1-generated"
    folder.mkdir()
    (folder / "review.md").write_text("# Review of v0.1\n\nFine.\n", encoding="utf-8")
    html = page_text(overview.build(full, MOMENT).parent)
    document = visible(html[html.index("<h2>Requirements document</h2>"):html.index("<h2>Estimate</h2>")])
    assert "Review of v0.1" in document and "What to fix before it goes to the client" in document
    assert "requirements-v0.1-generated" not in visible(html[html.index("<h2>Review</h2>"):html.index("<h2>Workshops</h2>")])


def test_building_again_without_changes_leaves_the_page_alone(full):
    page = overview.build(full, MOMENT)
    first = page.read_text(encoding="utf-8")
    overview.build(full, MOMENT + dt.timedelta(hours=3))
    assert page.read_text(encoding="utf-8") == first  # only the time would have changed: the synced file is not touched
    (full / "docs" / "2026-11-02 SOW.pdf").write_bytes(b"%PDF")
    overview.build(full, MOMENT + dt.timedelta(hours=3))
    assert "6 November 2026, 00:40" not in page.read_text(encoding="utf-8") and "SOW" in page.read_text(encoding="utf-8")
    assert "6 November 2026" in page.read_text(encoding="utf-8") or "7 November 2026" in page.read_text(encoding="utf-8")


def test_a_damaged_register_is_named_on_the_page_and_the_rest_still_shows(full):
    (full / "register.json").write_text("{ not json", encoding="utf-8")
    text = visible(page_text(overview.build(full, MOMENT).parent))
    assert "Register.json could not be read" in text and "Mock-up" in text


def test_build_all_builds_every_active_project(temp_workspace, monkeypatch, capsys):
    one, two = empty_project(temp_workspace / "projects", "one"), empty_project(temp_workspace / "projects", "two")
    (temp_workspace / "projects" / "_archive" / "old").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["overview.py", "build", "--all"])
    overview.main()
    assert (one / overview.PAGE).exists() and (two / overview.PAGE).exists()
    assert not (temp_workspace / "projects" / "_archive" / "old" / overview.PAGE).exists()
    assert capsys.readouterr().out.count("Wrote ") == 2


# ---------------------------------------------------------------------- the shortcuts
def test_a_project_with_a_mock_up_gets_the_two_shortcuts(full):
    overview.build(full, MOMENT)
    win, mac = full / overview.SHORTCUT_WINDOWS, full / overview.SHORTCUT_MAC
    assert b"\r\n" in win.read_bytes() and b"\r\n" not in mac.read_bytes()
    windows = win.read_text(encoding="utf-8")
    assert r"%USERPROFILE%\.blueprint\app-path" in windows and r'call "%APP%\present.cmd" "%PROJECT%"' in windows
    assert "Blueprint is not set up on this computer" in windows
    unix = mac.read_text(encoding="utf-8")
    assert unix.startswith("#!/usr/bin/env bash") and "$HOME/.blueprint/app-path" in unix and 'bash "$app/present.sh" "$project"' in unix
    assert "Blueprint is not set up on this computer" in unix
    for text in (windows, unix):
        assert "leave-request" not in text and "Leave Request" not in text  # the same file in every project
    if sys.platform != "win32":
        assert os.access(mac, os.X_OK)


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows shortcut runs on Windows")
def test_the_windows_shortcut_explains_what_to_do_when_blueprint_is_not_set_up(full, tmp_path):
    overview.build(full, MOMENT)
    home = tmp_path / "home"
    home.mkdir()
    run = subprocess.run(["cmd", "/c", str(full / overview.SHORTCUT_WINDOWS)], env={**os.environ, "USERPROFILE": str(home)},
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert "Blueprint is not set up on this computer" in run.stdout and "setup.cmd" in run.stdout and run.returncode == 1


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows shortcut runs on Windows")
def test_the_windows_shortcut_starts_the_mock_up_of_its_own_folder_through_the_app(full, tmp_path):
    overview.build(full, MOMENT)
    app, home = tmp_path / "my app", tmp_path / "home"
    app.mkdir()
    (home / ".blueprint").mkdir(parents=True)
    (home / ".blueprint" / "app-path").write_text(str(app), encoding="utf-8")
    shutil.copy(support.ROOT / "present.cmd", app / "present.cmd")
    stand_in = tmp_path / "bin"
    stand_in.mkdir()
    (stand_in / "python.bat").write_text("@echo started: %*\r\n", encoding="utf-8")  # stands in for Python: shows what is started
    env = {**os.environ, "USERPROFILE": str(home), "PATH": f"{stand_in};{os.environ.get('PATH', '')}"}
    run = subprocess.run(["cmd", "/c", str(full / overview.SHORTCUT_WINDOWS)], env=env,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    assert f'started: -I tools\\mockup.py serve "{full}"' in run.stdout, run.stdout + run.stderr


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="the Mac shortcut runs in bash")
def test_the_mac_shortcut_finds_the_app_or_says_what_to_do(full, tmp_path):
    overview.build(full, MOMENT)
    home = tmp_path / "home"
    home.mkdir()
    shortcut = str(full / overview.SHORTCUT_MAC)
    run = subprocess.run(["bash", shortcut], env={**os.environ, "HOME": str(home)}, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    assert "Blueprint is not set up on this computer" in run.stdout and "setup.command" in run.stdout and run.returncode == 1
    app = tmp_path / "my app"
    (app / ".venv" / "bin").mkdir(parents=True)
    stand_in = app / ".venv" / "bin" / "python"
    stand_in.write_text('#!/usr/bin/env bash\necho "started: $*"\n', encoding="utf-8", newline="\n")
    stand_in.chmod(0o755)
    shutil.copy(support.ROOT / "present.sh", app / "present.sh")
    (home / ".blueprint").mkdir()
    (home / ".blueprint" / "app-path").write_text(f"{app}\n", encoding="utf-8")
    run = subprocess.run(["bash", shortcut], env={**os.environ, "HOME": str(home)}, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True, timeout=30)
    assert f"started: -I tools/mockup.py serve {full}" in run.stdout, run.stdout + run.stderr


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash scripts: checked on macOS and Linux")
def test_present_takes_a_project_folder_as_well_as_a_name(tmp_path):
    app, project = tmp_path / "app", tmp_path / "shared" / "courier booking"
    (project / "spec").mkdir(parents=True)
    (project / "spec" / "app.yaml").write_text("project: {}\n", encoding="utf-8")
    (app / ".venv" / "bin").mkdir(parents=True)
    stand_in = app / ".venv" / "bin" / "python"
    stand_in.write_text('#!/usr/bin/env bash\necho "started: $*"\n', encoding="utf-8", newline="\n")
    stand_in.chmod(0o755)
    shutil.copy(support.ROOT / "present.sh", app / "present.sh")
    run = subprocess.run(["bash", "present.sh", str(project)], cwd=app, capture_output=True, text=True, timeout=30)
    assert f"started: -I tools/mockup.py serve {project}" in run.stdout, run.stdout + run.stderr


def test_setup_writes_where_the_app_is_for_the_shortcuts():
    assert ".blueprint" in (support.ROOT / "setup.ps1").read_text(encoding="utf-8") and "app-path" in (support.ROOT / "setup.ps1").read_text(encoding="utf-8")
    assert 'pwd > "$HOME/.blueprint/app-path"' in (support.ROOT / "setup.sh").read_text(encoding="utf-8")
    script = (support.ROOT / "present.cmd").read_text(encoding="utf-8")
    assert 'if exist "%PROJECT%\\spec\\app.yaml" set "FOLDER=%PROJECT%"' in script


# ---------------------------------------------------------------------- the review as a Word file
def test_the_review_becomes_an_internal_word_document(full):
    out = review_doc.render(full, full / "reviews" / "srs-v1.0")
    assert out.name == "SRS v1.0 review.docx"
    doc = Document(str(out))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert headings == ["Verdict", "Top items by risk", "Counts"]
    texts = [p.text for p in doc.paragraphs]
    assert "Leave Request System SRS v1.0" in texts  # under the word Review, so not "Review: ..." twice
    verdict = next(p for p in doc.paragraphs if p.text.startswith("Not ready for sign-off."))
    assert verdict.runs[0].bold and any(r.italic and r.text == "two" for r in verdict.runs)
    code = next(p for p in doc.paragraphs if p.text.startswith("Document: "))
    assert any(r.text == "docs/2026-10-22 SRS v1.0.pdf" and r.font.name for r in code.runs)
    numbered = [p for p in doc.paragraphs if p.style.name.startswith("List Number")]
    assert [p.text.split(".")[0] for p in numbered] == ["R-001 Approval levels (high)", "R-002 Carry-forward (medium)"]
    assert any(p.style.name.startswith("List Bullet") and p.text == "Ask about the cut-off date." for p in doc.paragraphs)
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["Audience", "High", "Medium"]
    assert [c.text for c in table.rows[2].cells] == ["Internal", "0", "2"]
    header = " ".join(p.text for s in doc.sections for part in (s.header, s.footer, s.first_page_footer) for p in part.paragraphs)
    assert "Internal: not for the client" in header
    assert any("Internal: not for the client" in t for t in texts)


def test_the_page_links_the_word_review_and_builds_it_when_missing(full):
    html = unquote(page_text(overview.build(full, MOMENT).parent))
    assert (full / "reviews" / "srs-v1.0" / "SRS v1.0 review.docx").exists()
    assert 'href="reviews/srs-v1.0/SRS v1.0 review.docx"' in html and "review.md" not in html


def test_the_review_tool_takes_the_newest_review_and_rebuilds_the_page(full, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["review_doc.py", str(full)])
    review_doc.main()
    out = capsys.readouterr().out
    assert "SRS v1.0 review.docx" in out and "Internal" in out
    assert (full / overview.PAGE).exists()


@pytest.mark.parametrize("folder, name", [("srs-v1.0", "SRS v1.0"), ("requirements-v0.2-generated", "Requirements v0.2 generated"),
                                          ("urs_draft_v2", "URS draft v2")])
def test_review_names_read_like_words(folder, name):
    assert review_doc.readable_name(folder) == name


# ---------------------------------------------------------------------- rebuilt by the tools
def test_the_tools_rebuild_the_page_after_they_write(full, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["register.py", "update", str(full), "R-001", "--set", "status=resolved"])
    register.main()
    assert "Questions for the client" in page_text(full)
    before = page_text(full)
    monkeypatch.setattr(sys, "argv", ["register.py", "render", str(full)])
    register.main()
    assert page_text(full) == before or "Questions for the client" in page_text(full)


def test_a_failing_page_never_stops_the_tool_that_wrote(full, monkeypatch, capsys):
    def broken(project, moment=None):
        raise RuntimeError("broken")

    monkeypatch.setattr(overview, "build", broken)
    monkeypatch.setattr(sys, "argv", ["register.py", "update", str(full), "R-001", "--set", "status=resolved"])
    register.main()
    out = capsys.readouterr().out
    assert "Changed in register.json" in out
    assert out.strip().splitlines()[-1].startswith("(The project overview page was not updated: RuntimeError.")
    assert json.loads((full / "register.json").read_text(encoding="utf-8"))["items"][0]["status"] == "resolved"


def test_filing_and_a_new_project_rebuild_the_page(temp_workspace, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sys, "argv", ["new_project.py", "courier-booking", "Courier Booking", "Sample Client"])
    import new_project
    new_project.main()
    p = temp_workspace / "projects" / "courier-booking"
    assert "No documents yet" in visible(page_text(p))
    brief = tmp_path / "brief.docx"
    brief.write_bytes(b"docx")
    monkeypatch.setattr(sys, "argv", ["project.py", "file", "courier-booking", str(brief), "--kind", "brief", "--date", "2026-11-01"])
    project_tool.main()
    assert "2026-11-01%20brief.docx" in page_text(p)


def test_the_made_up_sample_and_the_start_up_summary_never_write_the_page(tmp_path, monkeypatch):
    assert overview.refresh(support.EXAMPLE) is None
    assert not (support.EXAMPLE / overview.PAGE).exists()
    root = tmp_path / "app"
    p = empty_project(root / "projects")
    monkeypatch.setattr(status, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["status.py", "--brief"])
    status.main()
    assert not (p / overview.PAGE).exists()


def test_layout_check_accepts_the_new_files_at_the_top_of_a_project(full, monkeypatch, temp_workspace):
    p = temp_workspace / "projects" / "leave-request"
    shutil.copytree(full, p)
    overview.build(p, MOMENT)
    problems, fixed, notes = project_tool.check_one("leave-request", fix=False)
    assert problems == [] and not any("overview" in n.lower() or "mock-up.cmd" in n for n in notes)
