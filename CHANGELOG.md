# Changelog

All notable changes to Blueprint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a major version for changes that need people to change how
they work or migrate their workspace, a minor version for new features, a patch for fixes.

Add every change to **Unreleased** as you make it, under Added, Changed, Deprecated, Removed, Fixed or
Security. Write for the people using Blueprint: say what they can now do, or what behaves differently.
See [docs/maintaining.md](docs/maintaining.md).

## [Unreleased]

## [0.10.0] - 2026-11-06

### Added
- **The mock-up can act the process out.** Give a button `set_status` in the spec and clicking it moves the
  record to that status: approve an application as the manager and it shows as Approved on every screen,
  leaves the list of pending approvals, changes the counts on the dashboards, loses its Approve and Reject
  buttons, and its approval progress records who handled it, when, and the comment typed into the dialog.
  Until now the button showed a message and the record stayed as it was. Nothing is saved: reload the page
  (F5) to put the sample data back and run the walk-through again. Screenshots are not affected. The
  made-up sample project does it for Approve, Reject and Cancel; say "make the buttons move the record"
  to have it added to a project of your own. See [Spec format](docs/spec-format.md#status-moves).
- **The mock-up and the status rules can no longer disagree.** The build stops when a button moves a
  record somewhere the status rules do not allow (for example out of a final status), and it lists the
  moves the rules allow that no button makes, so you know what the walk-through cannot show.

### Fixed
- **A button label starting with Yes, No, On or Off is no longer shown as "true" or "false".** Written
  without quotes, YAML reads such a label as true or false, and the mock-up showed that word on the
  button; the sample project's "Yes, cancel it" button did. The build now stops and says to put the label
  in quotes.

## [0.9.0] - 2026-11-06

### Added
- **Prepare a workshop.** Say "prepare the workshop" or "what should we ask the client next?" and Blueprint
  builds the agenda for a requirement workshop, mock-up review or sign-off meeting: the open questions from
  the register, what the spec does not say yet (status rules, integration details, formulas, scope) and the
  questions of the gap patterns that apply, ordered so the most costly come first and sized to fit the
  time. You get two Word documents in the project's new `workshops/` folder. The **agenda** is for the
  client: the questions, with room to write each decision. The **facilitator notes** are for the BA: the
  same questions with why each one matters, your recommendation, and what was left for later. An agenda
  that leaves out an open high-severity question, or does not fit the time, is refused with the reason.

## [0.8.1] - 2026-11-06

### Fixed
- **The PDF is no longer twice the size it needs to be.** In 0.8.0, putting the screenshots back into the
  PDF at full size stored each of them twice. Each is now stored once, which roughly halves the PDF of a
  document with many screens. Generate the document again to get the smaller file.

## [0.8.0] - 2026-11-06

### Added
- **Blueprint runs on a Mac.** Run `./setup.sh` (or double-click `setup.command`) to set up, and
  `./present.sh <project>` (or `present.command`) to present a mock-up. Setup keeps Blueprint's Python
  packages in a folder of its own (`.venv`), installs the fonts for your user and links the workspace, as
  on Windows. Screenshots use Microsoft Edge, or Google Chrome when Edge is not installed (on Windows
  too). The machine check knows where things are on a Mac. One step stays manual there: Word for Mac
  cannot be driven by Blueprint, so you update the table of contents and save the PDF yourself, and the
  PDF's signing fields are added on Windows only. Linux works the same way as a Mac.
- **What each dashboard figure counts.** Every screen with figures now has a "Figures" table in the
  document. A figure the mock-up counts from its list is described automatically ("the number of records
  where Status is Pending Approval"); a figure typed in as a value takes a new `formula` in the spec, in
  words. A figure with neither shows "To be confirmed".
- **How each integration works.** An integration in the spec can now say what starts it (`trigger`), what
  goes across (`data`) and what happens when it fails (`on_failure`); the document prints them in a second
  table under the external systems. Something left out shows "To be confirmed" and is warned about.
- **A note of screens no requirement refers to.** Where the spec links requirements to screens, generating
  lists the screens nothing points at, which often means a requirement is missing. Notes do not hold a
  version back; warnings do.
- **Status rules in the document.** Each status in the spec can now say who may edit, cancel or delete a
  record while it is in that status, and which statuses it can move to (`edit`, `cancel`, `delete`,
  `next`). The document prints them as a "Status rules" table under the statuses. A rule you have not
  given yet is shown as "To be confirmed" and warned about; a spec with no rules at all still generates,
  with a note. These are the rules most often argued about after go-live when nobody wrote them down.
- **A scope chapter.** A new `scope` part of the spec (`in_scope`, `out_of_scope`, `assumptions`) becomes
  the chapter "Scope and assumptions", after "Users and access". It appears only when the spec has a
  scope. If your company file lists its own `chapters`, add `scope` to it to get the chapter.
- **Decisions made.** Client questions that are resolved and have an answer in the register are now listed
  in the document under "Decisions made", with the answer and where it was agreed. Until now a question
  vanished from the document once it was answered, so the client's answers were on record only in the
  register. Internal items and unanswered ones still never reach the document.

### Changed
- **Screenshots stay sharp in the PDF.** Word's PDF export reduces every picture, so the small text of a
  screenshot went soft when zoomed. After Word has made the PDF, Blueprint now puts each screenshot back
  at its full size. The PDF is larger for it: about as large as its screenshots together.
- **The default standard wording is shorter and says each thing once.** "About this document" and the
  sign-off text went from twelve paragraphs to seven. They no longer say twice that screens may be
  refined, and the sign-off now states that the signed document is the basis for development and for
  acceptance testing, that open decisions are not covered until resolved, and that a change after
  sign-off is a change request. **A company with its own `branding/document-boilerplate.yaml` keeps its
  wording**; copy what you want from `templates/document-boilerplate.yaml`.
- **An estimate with many lines says how to read its total.** The total adds every low end and every
  high end; from five lines with a range, the estimate now says that all of them landing low or all high
  is unlikely, so the outcome is to be expected inside the range. No narrower figure is given: an
  estimate is still never a midpoint or a "most likely" number.
- **Reviews can point to the section numbers the reader sees.** In many Word documents the numbers in
  front of headings and numbered paragraphs ("3.2", "(a)", "Appendix B") are produced by Word and are not
  in the text. They are now worked out when a document is read, so findings can say "section 3.2" and
  cross-references can be checked. Checked against Word itself: the numbers match what Word shows.
  Documents with the numbers typed in are read as before.
- **Everyone in the room sees every comment.** In a mock-up shared with `--lan`, a comment saved on one
  laptop now appears on the others within a few seconds, without reloading, and has the same number
  everywhere (the number it is saved under).
- **`--lan` prints the address to share.** Starting a mock-up for the room now shows the address others
  open, such as `http://192.168.1.20:8765/`; you no longer have to look up your machine's address.
- **Filters and search boxes in the mock-up work.** On a list, choosing a filter value or typing in a
  search box and pressing **Search** (or Enter) now narrows the sample rows, the line under the list
  counts what is shown, and **Clear Filters** brings everything back. They used to do nothing, which
  clients noticed the moment they clicked.
- **What you type in the mock-up stays.** Moving between the steps of a form, or opening and closing a
  dialog, no longer empties the fields already filled in. Opening the form again starts it clean.
- **Typing mistakes in the spec are reported when the mock-up is built.** A column, filter, search or
  condition that names a field the sample data does not have, an `options_from` that points nowhere, an
  unknown field type, a record or role that does not exist, and a setting that nearly spells a real one
  (`colums`, `tittle`) now stop the build with a message that suggests the right name. They used to build
  and show an empty column, an empty drop-down or the wrong record. Settings of your own that the format
  does not know are left alone.
- **Windows: Node.js is now needed for Blueprint's checks in Claude Code**, not only for screenshots. The
  status shown when a session starts and the check before a commit are started through Node, so the same
  settings work on Windows and on a Mac. Setup already asks for Node.js; run `setup.cmd` if the machine
  check says it is missing.

### Fixed
- In the document, a role's heading and its one line of description no longer end a page on their own.
- A comment without a time, for example one merged in from an exported file, no longer breaks the
  Feedback panel in the mock-up.
- **A note in a rate cell no longer changes the rate.** In `building-blocks.md`, every number in a rate
  cell was read, so a note turned a single rate into a range: "3 (was 5)" was priced as 3 to 5 mandays,
  and "0.5 MD each (2023 rate)" as 0.5 to 2023. Only the figure the cell starts with counts now. A cell
  that does not start with a plain number or range, such as "1,5" with a decimal comma (which used to be
  read as 1 to 5), is not priced, and the estimate says which cell could not be read. **Check your
  estimates if any rate cell holds a second number.**
- **The newest estimate is the newest.** With two estimates on one day, "spec v0.9" was taken as newer
  than "spec v0.10". Estimates are now ordered by date and then by version number.
- **One damaged project no longer hides all the others.** The summary shown when a session starts stopped
  with an error if any project had an unreadable register, spec or feedback file. It now lists every
  project and says which file of which project could not be read.
- **Spreadsheet totals are read as figures.** A cell with a formula, such as the total of a scope of work,
  was read as `=SUM(B2:B3)`. Its calculated value is now given with the formula.
- **Text files saved in the Windows encoding or as "Unicode" in Notepad can be read.** They used to stop
  the reading of the document with an error.
- **Answers typed into the Excel register are no longer lost.** The register's Excel file was written
  afresh from `register.json` every time, so a client's answer typed into **Client response**, or a
  changed **Status**, vanished at the next update without a word. Blueprint now reads the Excel file
  first and takes over what was typed since it was written; an answer also moves an open question to
  "answered". If the same item was changed in Excel and by Blueprint, it stops and shows both values. A
  register file that is open in Excel now gives a plain message asking you to close it.
- **Reading a document can no longer delete other files.** The tool that turns a document into text
  emptied its output folder first, whatever that folder was: pointed at a project's `docs/` by mistake,
  it deleted the client's documents. It now replaces only an earlier extraction of its own, leaves any
  other file in that folder alone, and refuses a folder that holds something else.
- **The mock-up of an issued version is kept as the client saw it.** Rebuilding replaced the saved copy in
  `mockup/versions/` every time, also after that version had been issued, so showing "the version the
  client saw" could show something newer. The saved copy of an issued version is no longer replaced; the
  build says so and asks you to bump the version.
- One of the estimate tests failed with the newest version of the test runner, so the test run on GitHub
  had been red since 0.6.0. The test is corrected; nothing in the estimate tool changed.

## [0.7.0] - 2026-11-06

### Added
- **Status colours you choose.** A status in the spec can now say which colour it is shown in:
  `color: green`, `amber`, `red` or `grey`. The mock-up uses it wherever that status appears, and a spec
  with any other colour is reported as an error. Statuses without one are still coloured from their
  wording. See [docs/spec-format.md](docs/spec-format.md).
- **A warning when the screenshots are older than the spec.** Generating the requirements document now
  warns when a screen, dialog, role, status or the sample data changed after the screenshots were taken,
  and when a screen has no picture, with the command that takes them again. Rewording a requirement, a
  description or a rule does not trigger it. For a project you already have, take the screenshots once
  more to switch the check on fully; until then only added and removed screens are noticed.
- **House styles with filled table headers.** The document format has three new settings for companies
  whose documents do not use Blueprint's hairline tables: `tables.header_fill` (a colour for the header
  row, with white header text unless `tables.header_text` says otherwise), `tables.borders: grid` (a box
  round every cell) and `colors.heading` (the colour of chapter and section headings). Ask "make our table
  headers navy" or see [docs/document-format.md](docs/document-format.md). The default look is unchanged.
- **The format and the spec are checked before a document is generated.** A mistake in
  `branding/document-format.yaml` (a misspelt setting such as `colours`, an unknown chapter, a size that
  is not a number) or in the parts of the spec only the document prints (a requirement group with no
  items, a notification with no recipient, two extra sections with one title, a timeline week before 1)
  now stops the run with a list of what to fix, in plain words. These used to end in a Python error or
  were silently ignored. `python -I tools/document_format.py show` lists format mistakes too.
- Automated tests for the mock-up: the build, the comment server and, on a machine with Node and Microsoft
  Edge, the mock-up itself clicked through in the browser. Automated tests for the format tool.

### Changed
- **Screenshots you can read in the document.** Screens are now captured 1000 pixels wide instead of 1440,
  so the text inside a screenshot prints about 40% larger (roughly 6 pt instead of 4 pt). A screen that
  does not fit, such as a list with many columns, is captured wider automatically, and the command says
  which. Each screenshot is cropped to its content, so a short list or the process flow is no longer half
  empty. Screens are laid out a little tighter in the document than in the live mock-up, which still fills
  the window. **Take the screenshots again and regenerate** to get this in a document you already have.
- **The cover shows your document title as you wrote it.** It used to be forced into sentence case, so
  "System Requirement Specifications" printed as "System requirement specifications".
- **The summary page agrees with the rest of the document.** It counts every screen of the Screens chapter
  (the login screen was left out), and lists the signatories client first, as the sign-off chapter does.
- The document generator now stops with the list of errors when the spec has any (an unknown screen,
  role or dialog, for example), the same check the mock-up runs. It used to carry on or crash.

### Fixed
- **A comment is no longer lost when the mock-up cannot save it.** If the window that started the mock-up
  was closed, or the network dropped, a comment used to disappear while the mock-up still said "Saved to
  the project folder". Now a red message says it was not saved, the Feedback button shows how many are
  waiting, and the comment is kept in the browser, also if the page is reloaded. It is saved with the next
  comment that gets through, or with **Try again** in the Feedback panel, and **Export unsaved** gives it as
  a file for `inbox/`.
- **Two mock-ups can no longer share an address.** Starting a second mock-up on Windows while one was
  open gave no error, and comments could then be saved to either project. The second one now stops and
  says the port is in use and how to pick another (`present.cmd <project> --port 8766`), and the
  `present.cmd` window stays open so the message can be read.
- **Negative statuses are no longer shown green.** "Inactive", "Not Approved", "Unavailable" and similar
  were coloured as if they were good news, in the mock-up and so in the screenshots of the requirements
  document. Rebuild the mock-up and take the screenshots again to correct a project that has them.
- **Dialogs close when confirmed.** A dialog whose confirm button only shows a message stayed open after
  the click, and the default OK button did nothing. Both now close the dialog.
- A comment with characters the Windows console cannot show is saved like any other.
- **An old PDF can no longer sit beside a new Word document.** When the Word step did not run, the PDF from
  the previous run stayed in `output/` under the same name as the new document, with different content. The
  old PDF is now removed before the new document is written. If the PDF or the document is open in another
  program, the generator stops and asks you to close it.
- **A failed Word step says why.** Every failure used to be reported as "Word not available", even with
  Word installed. Now the reason is shown (for example the file is in use, or Word did not answer), and
  "Word not available" is said only when Word is not installed.
- **Owners and dates no longer break in the decisions table.** The Owner and Due columns were narrower than
  a date, so "2026-11-20" printed on two lines and a name such as "Operations" broke before its last
  letter. The Impact, Owner and Due columns are now sized to what they hold, and the question takes the
  rest of the width. Requirement IDs and references such as "FR-BKG-001.2" are no longer split across two
  lines at a hyphen, anywhere in the document.
- **Word is no longer left running in the background.** When the Word step failed half-way, a hidden Word
  stayed open with the document locked, and the next run could not write it. Word is now always closed,
  shows no hidden questions, and no longer adds generated documents to your recent files. If Word does
  not answer for four minutes, the message says how to end it in Task Manager.
- **References work in every text.** `{ref:...}`, `{client}`, `{system}` and the other names were resolved
  in some places only; in a role's description, a status meaning, a non-functional requirement, a glossary
  meaning, an integration, a notification event, a requirement group title and the cells of an extra
  section's table they printed as typed. A hand-typed "section 3.2" is now warned about there too.
- **The cover's status dot is green only for a settled status.** "Not approved", "Unsigned draft" and
  "Awaiting final review" were shown green; they are amber now. "Signed off", "Approved" and "Final" stay
  green.
- **Colours in the format file can be written the usual ways:** with or without `#`, in capitals or not.
- **The format tool runs on Python 3.10 and 3.11.** `document_format.py` needed 3.12, though setup accepts
  3.10; none of its commands started on the older versions.
- **The contents fits on fewer pages.** Its lines used the body text's spacing, so a contents of 36 lines
  ran three lines onto an empty page.
- **The summary cards line up with the text.** They were narrower than the tables and text around them.
- A company format file still under its old name, `branding/srs-format.yaml`, is read again.
- **System names with a colon, a slash or an apostrophe.** A colon in the system name (such as
  "Phase 2: Claims System") made Windows hide the generated document inside an empty file, a slash stopped
  the run, and an apostrophe broke the Word step so no PDF was written. The file name now replaces the
  characters Windows cannot store with a hyphen; the name inside the document is unchanged.

## [0.6.0] - 2026-11-06

### Added
- **Estimates.** Say "estimate this project" to get a manday estimate for the lead developer, counted in the
  knowledge base's building blocks from whatever exists: a brief or scope of work early on, the project spec
  later. Every figure is a range, with the assumptions and a confidence level, and what makes it uncertain:
  open high-severity questions, the gap patterns that apply, lines with no rate and how few delivered
  projects the rates rest on. When the project has a scope of work, the sold mandays are compared line by
  line and the largest differences come first. It ends with the workshop questions that would narrow the
  range most, and offers to add them to the register. Each estimate is a dated Excel file in the project's
  new `estimates/` folder; it is internal and never goes into a client document. See
  [docs/estimates.md](docs/estimates.md).
- **Your rates, not Blueprint's.** Estimates use the rates you set in `knowledge/building-blocks.md`, or a
  range the lead developer gives for one estimate. Blueprint never makes up a figure: a line with no rate is
  counted, shown as not priced and left out of the total, and Blueprint offers to save the rates it is
  given.
- **Other work in estimates.** A new `Other work` table in `building-blocks.md` holds your shares for project
  management, testing, UAT support, training and the like, as a percentage of the build or fixed mandays.
  New workspaces get it with every item unset. To add it to an existing workspace, ask Blueprint or copy
  the table from `templates/knowledge/building-blocks.md`.
- A sample estimate for the Leave Request example (counts, assumptions and questions, no figures of its
  own), and `tools/estimate.py` to list the rates, list what a project contains, render an estimate and
  turn it into weeks.
- A third mock-up look, `vivid`, for demos, pitches and clients who want a bold branded UI: a dark gradient
  side menu, a coloured header band with the page floating over it, gradient buttons and a glass login
  screen. Set `theme: vivid` in the spec. All of it follows the project's `primary_color`.
- Automated tests for the tools, so a fix to one part of the requirements document can no longer quietly
  break another. They check the generated Word document (chapter order, cross-references, the access
  matrix, a figure and field table for every screen, the timeline, sign-off forms, locked issued versions,
  and that everything works on a machine without Microsoft Word), the register and its Excel file, project
  housekeeping (issue, file, archive, restore), estimates (rates read from the knowledge base, ranges, the
  comparison with the scope of work, the confidence rules, and that nothing of an estimate reaches a client
  document) and the commit check. Nothing changes for people using
  Blueprint. If you change Blueprint itself: `python -m pip install -r requirements-dev.txt` once, then
  `python -m pytest`; GitHub runs them on every push. See [docs/maintaining.md](docs/maintaining.md#tests).

### Changed
- The **project timeline** is now drafted from the project's estimate instead of the scope of work's
  mandays, which are a commercial figure and often lower than the likely effort. Generating the
  requirements document offers to draft a missing timeline from the latest estimate, in weeks for the team
  size the lead developer gives; mandays never reach the document. Existing timelines are unchanged.
- The `modern` mock-up look is more polished: stat cards with icons and their own accent colours, a menu
  with icons, a user badge in the top bar, softer shadows, clearer form fields with a focus ring, status
  chips with a dot, and row highlighting in lists. The `joget` look is unchanged.

### Fixed
- In the `modern` and `vivid` mock-up looks, long stat card values (for example "RM 48,920") are no longer
  hidden behind the card's icon.
- Tables in a requirements document's extra sections and appendices no longer print "False" or "True"
  where the spec says `No` or `Yes` without quotes, for example a numbering column headed "No" or a
  "Yes"/"No" cell. They now print the word, and a "No" column is narrow again.

## [0.5.0] - 2026-11-06

### Added
- The requirements document can include a **project timeline** chapter: summary figures, a week-by-week
  chart of stages, activities and milestones (activities where the client must take part are highlighted),
  a milestones table with what the client must do, and the assumptions behind the plan. Weeks count from
  the kick-off, so the plan holds until a start date is agreed. Fill in `timeline` in the project spec
  (see the spec format); when it is missing, generating the document offers to draft it from the scope of
  work, one line per SOW item. Projects without a timeline are unchanged.
- Document format: a `timeline` chapter (after the NFRs) and a `timeline_bar` colour. A company format
  that lists its own `chapters` must add `timeline` to show it.

### Changed
- The starter requirements standard describes what a timeline must contain: stages, activities and
  milestones by week, what the client must do, and the assumptions behind it.

## [0.4.1] - 2026-11-06

### Changed
- In the requirements document, each screen's "Requirements · FR-…" line now sits right under the screen's
  description, before its screenshots, so readers see up front what the screen covers.

### Fixed
- Role names in the access matrix header no longer break in the middle of a word. Columns are sized to the
  longest word, and when there are too many roles to fit side by side the names are turned on their side.
- A screen's requirements line can no longer be left alone at the top of a page.
- A group heading inside a field table (for example "Approval Process") is no longer left at the bottom of
  a page without the rows under it.

## [0.4.0] - 2026-11-06

### Changed
- Blueprint now says "requirements document" instead of "SRS", because companies name this document
  differently. **Skills and tools are renamed:** `review-srs` → `review-requirements`, `generate-srs` →
  `generate-requirements`, `srs-format` → `document-format`, `tools/generate_srs.py` →
  `tools/generate_requirements.py`, `tools/srs_format.py` → `tools/document_format.py`. Asking in plain
  words works as before.
- The generated document's title is a company setting: `document.title` and `document.short` in the
  document format, e.g. "System Requirement Specifications" and "SRS". It appears on the cover, in the
  sign-off wording and in file names. The default is "Requirements Specification".
- Workspace files are renamed: `branding/srs-template.docx`, `srs-boilerplate.yaml` and `srs-format.yaml`
  become `document-template.docx`, `document-boilerplate.yaml` and `document-format.yaml`, and
  `knowledge/srs-standard.md` becomes `requirements-standard.md`. **Run `setup.cmd` once** to rename them;
  until then the old branding names still work. Standard wording can name the document with `{document}`.
- Register stages `srs-draft` and `srs-final` are now `requirements-draft` and `requirements-final`; the
  old values remain valid. The spec key `srs_table` is now `doc_table`; the old key still works.

### Fixed
- Claude Code's start-up greeting and commit check failed when a session's current folder was not the
  app folder; they now find the app wherever the session is.

## [0.3.0] - 2026-11-06

### Added
- Issuing: "issue v1.3 to the client" (`tools/project.py issue`) records which SRS version went to whom
  and when, and locks it. Its files become read-only and the generator refuses to overwrite it, so later
  changes become a new version. The status list shows the last issued version.
- Every mock-up version is kept in `mockup/versions/`, and `present.cmd <project> --version 0.2` shows an
  earlier one again.
- Documents are filed with dated, descriptive names, e.g. `2026-11-12 client comments on v1.3.docx`
  (`tools/project.py file`, used by the inbox and new-project skills).
- Archiving: delivered projects move to `projects/_archive/` and leave the status list; they can be
  restored.
- `tools/project.py check` finds projects missing parts of the standard layout; `--fix` adds them.

### Changed
- SRS page flow: every screen starts on a new page (switch off with `layout.screens_new_page: false`),
  headings stay with what follows them, screenshots stay with their captions, tables don't start with a
  lone header at the foot of a page and short tables are kept whole, and paragraphs don't leave single
  lines stranded. Documents are a few pages longer.

### Fixed
- The documentation check that runs before commits made through Claude Code could block every shell
  command while the docs were incomplete. It now only ever acts on `git commit`.

## [0.2.0] - 2026-11-06

### Added
- Documentation in `docs/`: getting started, workflow, skills, tools, the register, knowledge base,
  workspace and company profile, spec format, troubleshooting and maintaining.
- This changelog and a `VERSION` file.
- `tools/check_docs.py`: checks that every skill and tool is documented, the changelog is well formed and
  in step with `VERSION`, and links in the documentation work.
- A check before every commit made through Claude Code: app changes must come with a changelog entry,
  and the documentation check must pass.
- A GitHub Actions workflow that runs the documentation check on every push and pull request.
- `release` skill for maintainers: turns Unreleased into a version, updates `VERSION`, commits and tags.
- A new SRS design, now the default: calm greys, one accent colour, Geist type, hairline tables, and status
  shown as a dot beside a word. New pages and chapters: Document at a glance (counts, how to review it,
  sign-off status, version history), Requirements by role, and Decisions needed before sign-off with
  impact, owner and due date.
- Sign-off for any number of people: list them in the spec's `signoff`, client signatories first. Each
  gets a form kept on one page: name, designation, signature and date rows (left empty to write in when
  not known yet) and a full-height company stamp box. The at-a-glance page shows who
  has signed.
- The PDF has a digital signing field over every signature box: clients can sign in Adobe Acrobat Reader
  instead of printing and scanning. The fields don't print, so paper copies stay clean.
- Requirements link to the screens they apply to (`screens` in the spec), and screens list their
  requirements. Optional `priority` (Must, Should, Could) per requirement.
- The SRS format is configurable without code: `templates/srs-format.yaml` holds the default design and
  `workspace/branding/srs-format.yaml` your changes (colours, fonts, sizes, numbering, section order,
  titles, header and footer).
- `srs-format` skill and `tools/srs_format.py`: change the format from a plain request, learn it from a
  company's existing SRS, and preview it before regenerating real documents.
- Setup installs the Geist and Geist Mono fonts for the current Windows user, and generated documents
  embed their fonts so clients see them as designed. **Run `setup.cmd` again to get the fonts.**

### Changed
- The spec format reference moved from `tools/mockup/SPEC.md` to `docs/spec-format.md`.
- "Open Issues" in the SRS is now "Decisions needed before sign-off", and only points to requirement IDs
  that exist in the current version.
- Requirement IDs, versions and reference formats are set in Geist Mono; field tables have four columns
  (field, type, required, rule or source) instead of seven.

## [0.1.0] - 2026-11-06

First release.

### Added
- Skills: `start`, `new-project`, `process-inbox`, `review-srs`, `build-mockup`, `apply-feedback`,
  `generate-srs`, `close-project`.
- Requirements review that cites every finding, keeps client questions and internal fixes apart, and
  writes an Excel register for the BA.
- Clickable mock-ups from a project spec, with Joget and modern themes, role switching, dialogs, and a
  Feedback mode that pins client comments to screen elements and saves them to the project.
- SRS generation from the same spec: version history, roles, an access matrix built from the screens, a
  process flow drawn from the statuses, requirements with resolvable cross-references, screenshots with
  data tables, NFRs, Open Issues from the register and appendices, in the company's Word template.
- App and workspace separation: company profile, branding, knowledge base, projects and inbox live in a
  workspace that is never committed and can be shared through OneDrive or SharePoint.
- Starter knowledge base: gap patterns with workshop questions, estimating building blocks and the SRS
  standard.
- One-step setup (`setup.cmd`) with a machine check, `present.cmd` for sessions, shared Claude Code
  permissions and a start-up status greeting.

[Unreleased]: https://github.com/Axidify/blueprint/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/Axidify/blueprint/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Axidify/blueprint/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/Axidify/blueprint/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/Axidify/blueprint/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Axidify/blueprint/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Axidify/blueprint/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Axidify/blueprint/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Axidify/blueprint/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Axidify/blueprint/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Axidify/blueprint/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Axidify/blueprint/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Axidify/blueprint/releases/tag/v0.1.0
