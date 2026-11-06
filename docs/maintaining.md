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
| Where something is in a project folder | `tools/layout.py` (the only place that knows), `docs/workspace.md` (Inside a project folder), the "Project folders" section of `CLAUDE.md` |
| The starter knowledge base | `docs/knowledge.md` if its structure changes |
| The overall process | `docs/workflow.md`, `README.md` |

## Writing changelog entries

Add entries under **Unreleased** in `CHANGELOG.md`, in one of: Added, Changed, Deprecated, Removed, Fixed,
Security. Write for the people using Blueprint, not for developers:

- Good: "Generated requirements documents now include the copyright and page-number footer."
- Not useful: "Fix footerReference in sectPr."

Mention anything people must do (run `setup.cmd` again, move a file in their workspace) at the start of
the entry.

## Writing a skill

A skill (`.claude/skills/<name>/SKILL.md`) is read by Claude, for people who may be new to Claude Code.

- **Say what to achieve, the judgement and the order; leave the exact commands to the tool.** A skill names
  the tool and the command it needs ("add them with `register.py add`, `--check` first") and tells Claude to
  read `python -I tools/<tool>.py --help` (or the format at the top of the tool) for the options. Copy a
  command line in full only where it is needed at that moment. Options and formats written out in a skill
  drift from the tool; the tool's help is checked by its tests. Before removing anything from a skill, check
  that the tool's help says it; if it does not, keep it in the skill or add it to the help.
- **Never trim a rule.** What must never happen (an invented rate, mandays in a client document, an internal
  item on the client sheet, a finding without its location, a knowledge-base change the user did not agree
  to) stays in the skill, in plain words.
- **End with `## Hand over`**, the last section of every skill people use. It tells the person, in plain
  words:
  1. **what was made or changed**;
  2. **where it is**, in plain words (a path only when they need one), and that the project's
     `Project overview.html` lists it where that helps;
  3. **who each output is for**: the client, or internal (the team, the BA, the lead developer);
  4. **the next step, as the words to say to Claude**: one main step, and at most one other (often for the
     lead developer).

  `python -I tools/check_docs.py` fails when a skill has no `## Hand over` or another section comes after
  it. `release` is exempt: it is for the people who maintain the app, and ends by saying what was released.
- Add the skill to `docs/skills.md` and the skills list in `CLAUDE.md`.

## The documentation check

```bash
python -I tools/check_docs.py
```

It fails when:
- a skill in `.claude/skills/` has no `### <name>` section in `docs/skills.md`, or is missing from the
  skills list in `CLAUDE.md`;
- a skill (other than `release`) does not end with a `## Hand over` section (see
  [Writing a skill](#writing-a-skill));
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
| `tests/test_generate_requirements.py` | The generated Word document, read back with python-docx: chapters in the order of the document format, cross-references resolved, the access matrix, a figure and field table for every screen, the timeline chapter, decisions from the register, one sign-off form per signatory, that an issued version is locked, and that generating works without Word. Also what protects the output: a spec with errors is refused, screenshots older than the spec's screens (or missing) are warned about while rewording is not, an old PDF is removed, a failed Word step gives its reason, and a system name Windows cannot store is cleaned in the file name only. Also the checks before generating (each mistake in the format file or in the spec's document parts is named), references resolved in every text, the cover's status dot, the house-style settings (filled header, grid, heading colour), and that the Word script always closes Word. The PDF step after Word is tested on hand-made PDFs: the full-size pictures put back, and the signing fields. And the content the standard asks for: status rules, the scope chapter, decisions made, what each figure counts, how each integration works, and the note of screens no requirement refers to; automatic moves in the status rules, a filtered drop-down's source and a detail screen's related list. Also pictures shared by identical figures sharpened once, warnings for team-only text (mock-up, proposed, FB-/R- ids, requirement ids not in the spec), Decisions needed pointing only at this spec's requirements, the missing-parts list (nfr, timeline, scope, signatories), extra-screenshot captions, the plain message for a missing spec, and the sign-off cards |
| `tests/test_register.py` | Register validation (missing fields, unknown stage and other values, duplicates) and the Excel file, including that internal items never reach the client sheet, and that what was typed into the Excel file (an answer, a status) is taken into the register before the file is written again, with a stop when both sides changed the same item; a copy returned by the client taken in with `--from` (read only, after the project's own file, a conflict naming both values, an unreadable file refused); adding items (ids, defaults, a bad batch refused whole, duplicate hints, `--check`, stdin), `similar` and `update` |
| `tests/test_extract.py` | Extraction writes into a folder of its own: an earlier extraction is replaced, other files are kept, and a folder holding anything else is refused untouched. Also a text file in each encoding, a spreadsheet formula with its value, a generated Word document, and the numbers Word shows in front of headings and lists: `tests/fixtures/word-numbering/` holds a document built by Word and the numbers Word reported for it |
| `tests/test_layout.py` | The two folder layouts: every location resolved in both, a teammate's project in either layout read by the tools that read projects, a new project starting in the new layout; `project.py migrate` listing every move on a dry run and moving nothing, moving everything to its agreed place (issued files still read-only, comment ids kept, the log written) and `--undo` putting it back byte for byte, files added after the move going back too, `--all`, and `check` naming old-layout projects; the refusals (a mock-up server running, a live session open, a file open in Word or Excel or with its `~$` lock file, a target that exists) and a failed move put back; the register's Excel take-over finding the renamed file; the overview's links resolving after the move; and every tool the skills use run on a migrated copy of the sample (build, screenshots, generate, issue, register add and render, workshop, estimate, UAT, change requests, platform fit, filing, the review's Word file, status and the overview), none writing into the old places |
| `tests/test_project.py` | Issuing and locking a version, filing documents under dated names, archiving and restoring (and refusing to archive over an archived project of the same name), `find` matching earlier work on the same system, `new_project.py` (refusing an archived name, warning about similar earlier work), and the layout check |
| `tests/test_estimate.py` | Estimates, each with a knowledge base of its own in a temp folder: rates read per platform (a single figure widened by its confidence, ranges, `TBD`), provisional rates, shares and totals, open questions widening the high end only, the comparison with the scope of work, the confidence rules, the checks on the estimate file, and the `blocks`, `inventory`, `render`, `weeks` and `rates-from` commands, including the Excel file's sheets (the Overview headline with no total while the build is not priced, each figure explained on its own row, no line ids there, the Lines, Rates needed, Against SOW and Risks and questions sheets), its print setup and internal marking on every sheet, `rates-from` reading a filled-in Rates needed sheet, and that nothing of an estimate reaches the requirements document. |
| `tests/test_mockup.py`, `tests/mockup_browser.mjs` | The mock-up tool: the build, the page that lists every mock-up (what it shows, building on opening, earlier versions, comments going to the right project, nothing else served, never shared with the room), the mock-up following its spec (built again only when it changed, a mistake keeping the last build), a live session (the version kept at its start, the queue of comments, taking and finishing a change, a change with a mistake refused, undo putting back the spec and the project's own code, waiting for comments, marking, ending, Live meaning the session is open, and that the room is never sent internal notes), the text-size setting, the project's own mock-up code (loaded after the engine, built again when it changes, counted as what the screenshots show), the spec check for status colours, each way a button that moves a record (`set_status`) can be wrong or contradict the status rules, the comment server (a comment saved with an id, anything else refused with an answer, only the mock-up folder served) that a second server cannot take a port in use, the note of which screens the screenshots show (what changes it, what does not, and that it is the value 0.7.0 computed), each kind of typing mistake the spec check reports (also wrong shapes and unknown keys), `also_move`, a form's own record, the screenshot stop message, live undo putting comments back to Received, per-comment done notes, and that the saved mock-up of an issued version is not replaced. Also which forms add a record (the list a form is tied to, its status, `creates`, a dialog that confirms it, what the build says and refuses), the walk-through shared through the server (only the records a browser touched taken from it, reset, a restarted server starting clean, each mock-up of the home page kept apart), editing and withdrawing a comment (by its writer or the presenter, locked once taken, nothing erased, left out of `feedback`, `live list`, `take` and the counts), and the custom-work tags read from `platform_fit` without its internal parts. Where Node, the Node packages and Microsoft Edge are installed, the mock-up is also clicked through in Edge: status colours, dialogs (closing by button, Esc or a click outside, taking the cursor, and not coming back with the Back button), required fields pointed out on the first press and passed on the second, file and signature fields answering a click, filters kept across a visit to a record, messages stacking, the presenter's bar (version, role switch, clear of the page's buttons), the danger button drawn as an outline for a red brand colour, a changed spec offered as Update ready and never reloading by itself, a mistake in the spec never showing in the room, the bar saying Live and comments showing what became of them, larger text, the project's own code running after every screen is drawn, any part of a screen (header, side menu, background, a cell, a figure) commented on and named in words, feedback mode (the mark drawn inside the element, plain-word names, Esc and Ctrl + Enter, pins side by side that open their comment), a list showing each role its own rows or what waits for whoever is signed in, a row action shown to some roles only, a record moved by Approve, Reject, Cancel, a row action or a button that serves several steps (its status, buttons, progress, lists and counts following, and a reload putting it back), filters and search boxes narrowing a list, typed input surviving a step change, a comment saved by someone else appearing without a reload, and a comment the server does not take being kept, flagged and saved by **Try again**; Submit on a new form adding a record (its id, values, status and progress, in the lists, counts and task lists it matches, its detail screen), the walk-through kept through a reload, shared with a second browser (each keeping its role) and put back by **Reset sample data**, also without a server; Edit and Delete on a comment, locked once it is worked on; and the Custom development tags (on the parts named and on what the project's code adds, hidden by the switch, remembered, never with clean=1); and the screenshot command is run for real: every planned picture is taken, 1000 pixels wide and cropped to its content, and a screen that does not fit is taken wider; the same in the `desk` theme, where every screen type (login, dashboard, lists, a form in steps, detail screens with progress and a related list, dialogs, the process flow) must fit in 1000 pixels. Also the themes (a spec without one keeps `joget`, new projects get `desk` unless on Joget), filtered drop-downs (`options_from` with `where`), related lists (`where_record`) and automatic moves (`auto`) checked by the build, and the page that lists every mock-up (a card per project with nothing of another project in it, the projects without one, no orange). In Edge also: a form in steps with its main button on the last step only (Next and Previous before it, the step with empty required fields named), the filtered drop-down following the walk-through, the related list, Waiting for a step still to come, and the presenter's chrome (dark with the Cobalt accent and never orange, the open Feedback panel never covering the last column, the bar folding away and remembering it) Elsewhere, as on GitHub, those browser tests are skipped |
| `tests/test_document_format.py` | The format tool: `show` prints the format in effect and lists the mistakes in a company's file, `learn` reads a sample document (with plain messages for a PDF, .doc, damaged or missing sample, and `&amp;` decoded), and no tool uses syntax newer than Python 3.10 |
| `tests/test_workshop.py` | The workshop tool: what a spec still lacks, the gap patterns read from either way of writing them, each mistake the agenda check names (a closed or internal reference, an unknown screen, too little time, a high-severity question left out), and the two documents, including that nothing internal reaches the client's agenda |
| `tests/test_setup.py` (present scripts) | With no project named, `present.sh` and `present.cmd` open the page that lists every mock-up; with one, that project; an unknown name is refused with the list |
| `tests/test_platform.py` | The platform check: the starter Joget DX sheet (complete, every row unchecked, covering every feature of the sample), the features a spec uses, finding a product's sheet by name, the check's report, `apply` keeping every other line of the spec, naming the parts of the mock-up each feature is drawn in (for the Custom development tags) and never reaching the screenshots or the requirements document, and keeping the sheets (`record`, `sheet`, never writing to the starter knowledge by accident) |
| `tests/test_status.py` | The start-up summary: a project is summarised, high-severity counts are of client items only, files left in the inbox with a note are reported apart, the next step follows the project's stage (with the lead developer's estimate hint), and a damaged register, spec or feedback file is reported under its project while the other projects are still shown; a comment taken back in the mock-up is not counted as waiting |
| `tests/test_tour.py` | The tour's scratch copy: made from the sample without changing it (file hashes compared) and ignored by git, `start` again starting over, `end` removing the copy and refusing any other folder or one the tour did not make, the copy never listed as a project, the planted draft holding its gaps, and the mock-up tool and sample comment working on the copy |
| `tests/test_match.py` | Matching an inbox file to its project: a comments export from a project's mock-up matches clearly, a project's roles and screens point to it, the client's name alone is never enough, ids unique to a project weigh heavily, archived projects are listed apart and never offered, and the note kept for a file left in the inbox |
| `tests/test_overview.py` | The project overview page (a sample at every stage, hints for empty stages, the next step and its button, Internal marks, escaping, links that resolve, no mandays, rates or cost even with a priced estimate, rewritten only when it changes, `--all`); the Open the mock-up shortcuts (contents, the message without Blueprint, starting `present` with the folder); the review as a Word file; the rebuild hooks, a failure never stopping them, and the sample and start-up summary never writing the page |
| `tests/test_uat.py` | UAT scripts drafted from a sample copy (main process, reject path, what a role may not do, validation, access, every requirement covered or listed), the issued version preferred, the check, the workbook and document, nothing internal in them, and reading the results of a filled-in workbook |
| `tests/test_change_request.py` | The signed basis (issued snapshot, later changes left out, warnings when falling back), the lookup finding requirements, scope lines, decisions, open items and status rules, each mistake the CR log check names, sizing with rates and calibration notes, the Excel log, the client note holding nothing internal and showing "Quotation to follow", and an Ambiguous request becoming a register question |
| `tests/test_check_docs.py` | The commit hook acts only on `git commit`, and the documentation check itself, on a small made-up repository: also that a skill without `## Hand over` (or with a section after it) fails except `release` |
| `tests/test_skills.py` | The skills against the tools: every tool a skill sends Claude to with `--help` prints its usage |
| `tests/test_setup.py` | What makes Blueprint run on Windows, macOS and Linux alike: the hook commands in `.claude/settings.json` start the right Python and pass on the result, the machine check runs and names the right setup script, and the shell scripts keep Unix line endings |
| `tests/conftest.py`, `tests/support.py` | The temp workspace and the helpers for making projects and reading documents |

**Not covered.** How pages look (fonts, spacing, page breaks, where tables split), the table of contents
and page numbers, and the PDF: Word makes all of these, so check them by eye on a generated document
before a release. Also not covered: how the project overview page looks, most of the mock-up engine (how each screen type looks in each theme, beyond the desk theme fitting 1000 pixels,
navigation between screens) and its screenshots, most of what `extract.py` reads (PDFs, spreadsheets,
tracked changes, comments),
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
