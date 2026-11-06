# Maintaining Blueprint

## The rule

**Every change to the app ships with its documentation and a changelog entry, in the same commit.**

"The app" is everything in the repository except the documentation itself: `tools/`, `.claude/`,
`templates/`, `examples/`, `tests/`, `setup.*`, `present.*`, `requirements.txt`, `package.json`, `CLAUDE.md`.
The workspace is never part of a change.

| If you change … | Also update |
|---|---|
| Anything people will notice | `CHANGELOG.md` → Unreleased |
| A skill (new, renamed, removed, or what it does) | `docs/skills.md`, the skills list in `CLAUDE.md` |
| A tool or its options | `docs/tools.md`, and its tests in `tests/` (see [Tests](#tests)) |
| The spec format or mock-up engine | `docs/spec-format.md` |
| Register fields or the Excel layout | `docs/register.md` |
| The estimate file, its rules or its Excel layout | `docs/estimates.md` |
| Setup, workspace, company profile or branding | `docs/workspace.md`, `docs/getting-started.md`, `docs/troubleshooting.md` if relevant |
| The starter knowledge base | `docs/knowledge.md` if its structure changes |
| The overall process | `docs/workflow.md`, `README.md` |

## Writing changelog entries

Add entries under **Unreleased** in `CHANGELOG.md`, in one of: Added, Changed, Deprecated, Removed, Fixed,
Security. Write for the people using Blueprint, not for developers:

- Good: "Generated requirements documents now include the copyright and page-number footer."
- Not useful: "Fix footerReference in sectPr."

Mention anything people must do (run `setup.cmd` again, move a file in their workspace) at the start of
the entry.

## The documentation check

```bash
python -I tools/check_docs.py
```

It fails when:
- a skill in `.claude/skills/` has no `### <name>` section in `docs/skills.md`, or is missing from the
  skills list in `CLAUDE.md`;
- a script in `tools/` has no `### <script>` section in `docs/tools.md`;
- `CHANGELOG.md` has no Unreleased section, versions are out of order, or the newest version does not
  match `VERSION`;
- a relative link in `README.md`, `CHANGELOG.md` or `docs/` points to a file that does not exist;
- an app file contains a company or client name from the current workspace profile.

`--pre-commit` also fails when app files are staged without `CHANGELOG.md`.

### Where it runs

- **Before every commit made through Claude Code**: a hook in `.claude/settings.json` runs
  `check_docs.py --pre-commit` and blocks the commit if it fails, with the reason.
- **On GitHub**: `.github/workflows/docs.yml` runs the check on every push and pull request.
  (The tests run there too, in their own workflow: see [Tests](#tests).)

If you commit outside Claude Code, run the check yourself first.

## Tests

The tools have automated tests in `tests/`. Install the test runner once, then run them from the app folder:

```bash
python -m pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

They take about half a minute and need neither Microsoft Word, Node nor a browser (the mock-up's browser
tests run only where Node and Microsoft Edge are found, and are skipped elsewhere). Run them whenever you
change anything in `tools/` or `templates/`, and add or update a test with the change. On GitHub,
`.github/workflows/tests.yml` runs them on Linux on every push and pull request.
`.github/workflows/systems.yml` runs them on macOS, on Windows and on Python 3.10, and then does the
whole path on a Mac with nothing faked: `setup.sh`, the sample's screenshots, its generated document and
a comment saved through `present.sh`. It runs for each release tag, when you start it from the Actions
tab, and for any branch whose name starts with `ci/` (push one to check a change on a Mac before
merging).

The tests never read or write your workspace. Every project they use is made in a temp folder from the
made-up sample in `examples/leave-request/` or from `tests/fixtures/wide-project/` (a made-up project with
many roles, a 52-week timeline, a form in steps, extra sections and named signatories), with plain grey
images in place of mock-up screenshots. The company is always the neutral "Your Company". Keep it that
way: never put a real company, client or project into `tests/`.

| File | What it checks |
|---|---|
| `tests/test_generate_requirements.py` | The generated Word document, read back with python-docx: chapters in the order of the document format, cross-references resolved, the access matrix, a figure and field table for every screen, the timeline chapter, decisions from the register, one sign-off form per signatory, that an issued version is locked, and that generating works without Word. Also what protects the output: a spec with errors is refused, screenshots older than the spec's screens (or missing) are warned about while rewording is not, an old PDF is removed, a failed Word step gives its reason, and a system name Windows cannot store is cleaned in the file name only. Also the checks before generating (each mistake in the format file or in the spec's document parts is named), references resolved in every text, the cover's status dot, the house-style settings (filled header, grid, heading colour), and that the Word script always closes Word |
| `tests/test_register.py` | Register validation (missing fields, unknown stage and other values, duplicates) and the Excel file, including that internal items never reach the client sheet |
| `tests/test_project.py` | Issuing and locking a version, filing documents under dated names, archiving and restoring, and the layout check |
| `tests/test_estimate.py` | Estimates, each with a knowledge base of its own in a temp folder: rates read per platform (a single figure widened by its confidence, ranges, `TBD`), provisional rates, shares and totals, open questions widening the high end only, the comparison with the scope of work, the confidence rules, the checks on the estimate file, and the `blocks`, `inventory`, `render` and `weeks` commands, including that the Excel file is marked internal and that nothing of an estimate reaches the requirements document. |
| `tests/test_mockup.py`, `tests/mockup_browser.mjs` | The mock-up tool: the build, the spec check for status colours, the comment server (a comment saved with an id, anything else refused with an answer, only the mock-up folder served) that a second server cannot take a port in use, the note of which screens the screenshots show (what changes it, what does not, and that it is the value 0.7.0 computed), each kind of typing mistake the spec check reports, and that the saved mock-up of an issued version is not replaced. Where Node, the Node packages and Microsoft Edge are installed, the mock-up is also clicked through in Edge: status colours, dialogs closing, filters and search boxes narrowing a list, typed input surviving a step change, and a comment the server does not take being kept, flagged and saved by **Try again**; and the screenshot command is run for real: every planned picture is taken, 1000 pixels wide and cropped to its content, and a screen that does not fit is taken wider. Elsewhere, as on GitHub, those browser tests are skipped |
| `tests/test_document_format.py` | The format tool: `show` prints the format in effect and lists the mistakes in a company's file, `learn` reads a sample document, and no tool uses syntax newer than Python 3.10 |
| `tests/test_check_docs.py` | The commit hook acts only on `git commit`, and the documentation check itself, on a small made-up repository |
| `tests/test_setup.py` | What makes Blueprint run on Windows, macOS and Linux alike: the hook commands in `.claude/settings.json` start the right Python and pass on the result, the machine check runs and names the right setup script, and the shell scripts keep Unix line endings |
| `tests/conftest.py`, `tests/support.py` | The temp workspace and the helpers for making projects and reading documents |

**Not covered.** How pages look (fonts, spacing, page breaks, where tables split), the table of contents
and page numbers, and the PDF: Word makes all of these, so check them by eye on a generated document
before a release. Also not covered: most of the mock-up engine (how each screen type is drawn, the themes,
navigation between screens) and its screenshots, `extract.py`, `status.py`, `new_project.py`,
`document_format.py preview` and `setup.cmd` (`setup.sh` is run for real by the Mac check on GitHub).

One test does use Word, and is skipped unless you ask for it. On a Windows machine with Word, this
generates the fixture project for real and checks that the PDF exists and has a signing field for each
signatory (PowerShell):

```powershell
$env:BLUEPRINT_TEST_WORD = "1"; python -m pytest -k with_word; Remove-Item Env:BLUEPRINT_TEST_WORD
```

## Releasing a version

Ask Blueprint to "release a new version" (the `release` skill), or by hand:

1. Pick the version: **patch** (0.1.1) for fixes only, **minor** (0.2.0) for new features, **major** (1.0.0)
   for changes that need people to change how they work or migrate their workspace.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [x.y.z] - YYYY-MM-DD`, add a new empty
   `## [Unreleased]` above it, and update the comparison links at the bottom.
3. Put the version in `VERSION`.
4. Run `python -I tools/check_docs.py` and `python -m pytest`.
5. Commit ("Release x.y.z"), tag `vx.y.z`, push the commit and the tag.
6. Optionally publish a GitHub release with the changelog section as its notes.

People pick up a release with `git pull`, then run `setup.cmd` if the changelog says so.
