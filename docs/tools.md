# Tools

The skills run these scripts for you. Run them yourself when you want a single step. Run them from the
app folder, always with `python -I` (it keeps Python from loading stray files).

`--help` prints a tool's commands, options and file formats (for example
`python -I tools/estimate.py --help`). The skills read it rather than repeating the options, so it is the
reference that is kept up to date.

Paths inside a project below are those of the project folder layout (see
[Inside a project folder](workspace.md#inside-a-project-folder)): `_blueprint/...` for Blueprint's working
files, the numbered folders for what people open. A project not yet migrated keeps the old layout
(`docs/`, `spec/`, `output/` … at the top); every tool finds its files in either, through `layout.py`.

### doctor.py

```bash
python -I tools/doctor.py
```
Checks Python and its packages, Node and the screenshot tool, Edge, Word (optional), the workspace, the
company profile and the workspace links. Prints the fix for anything missing. `setup.cmd` runs it at the end, as does `setup.sh` on
macOS and Linux; it knows where the browser, Word and the fonts are on each system.

### status.py

```bash
python -I tools/status.py
python -I tools/status.py --brief
```
Lists the projects with their stage, open register items (the "high" count next to the client questions
counts client items only) and suggested next step, plus files waiting in the inbox. The next step follows
the stage, in the words to say to Claude: review the documents or build a mock-up, prepare the workshop
while high-priority client questions are open (or present the mock-up when one is prepared), apply
feedback, generate the requirements document (again, when the spec changed since), review the generated
document, record it as issued, close the project after delivery. A second `also:` line tells the lead
developer when there is no estimate yet or the spec changed since the last one. The `--brief` form is what you see when Claude Code starts. A project with a damaged register,
spec or feedback file is still listed, with a line saying which file could not be read; the other projects
are shown as usual.

### new_project.py

```bash
python -I tools/new_project.py courier-booking "Courier Booking System" "Acme Logistics Sdn. Bhd." --platform "Joget DX"
```
Creates `projects/<slug>/` in the project folder layout (`1 Client documents/`, and `_blueprint/` with
`spec/`, `feedback/`, an empty register and a README), says
which look its mock-up starts with (`desk`, or `joget` when the platform is Joget) and what to do next. It refuses a folder name an archived project already has (restore that one with
`project.py restore`), and warns when an active, archived or delivered project has the same or a similar
system name (see `project.py find`).

### extract.py

```bash
python -I tools/extract.py "<document>" projects/<slug>/_blueprint/reviews/<review>/extract
```
Turns a Word, PDF, Excel, Markdown or text file into `text.md` (reading order, tables as rows, tracked
changes, comments), `meta.json` (metadata, counts, every open-item marker: TBC, TBD, "to be confirmed",
"if applicable", "subject to confirmation" or "subject to change", and "pending" where something is still
awaited, not a status such as "Pending Approval") and `images/`. For PDFs it also renders to `pages/` the
pages with diagrams, formulas, little text or mostly figures (a manday table), and reads document properties
saved in the wrong character set correctly ("Microsoft® Word", not "MicrosoftÂ® Word"). It prints a short
plain summary. For a requirements document Blueprint generated, it says how many markers are the
document's own "To be confirmed" labels: each is something the spec does not say yet.

In a Word document, headings and numbered paragraphs carry the number Word shows in front of them
(`## 3.2 Roles`, `- (a) ...`), worked out from the document's numbering definitions, because Word does not
store those numbers in the text.

A spreadsheet cell with a formula is given as its calculated value followed by the formula
(`B4=15 (formula =SUM(B2:B3))`). Text files are read whether saved as UTF-8, as Notepad's "Unicode" or in
the Windows encoding; `meta.json` says which.

Give it a folder of its own. It replaces an earlier extraction there and leaves any other file in that
folder alone; a folder that holds files and is not an earlier extraction (a project's client documents, say) is
refused and nothing in it is touched.

### register.py

```bash
python -I tools/register.py add      projects/<slug> --file <items.json> [--check]
python -I tools/register.py add      projects/<slug> [--check] < items.json
python -I tools/register.py similar  projects/<slug> "<question or finding>" [--top 5]
python -I tools/register.py update   projects/<slug> R-001 [R-002 ...] --set field=value [--set ...] [--check]
python -I tools/register.py update   projects/<slug> --file <changes.json> [--check]
python -I tools/register.py validate projects/<slug>
python -I tools/register.py render   projects/<slug> [--overwrite] [--from "<returned register.xlsx>"]
python -I tools/register.py next-id  projects/<slug>
```
Adds items, finds items like a given one, changes fields of items, validates `register.json` (in
`_blueprint/`), renders `register.xlsx` (`Questions and fixes register.xlsx` at the top of the project), or
prints the next free item ID.

`add` takes one item or a list (JSON, UTF-8, from a file or standard input), gives them the next IDs,
fills `raised` and `status` where missing, refuses the whole batch if any item is invalid, names likely
duplicates of existing items by the words of the question and finding, and prints the IDs given;
`--check` reports without writing. `update` refuses unknown fields and values that are not allowed;
`update --file` takes many changes at once (`[{"id": "R-012", "set": {"answer": "...", "status": "resolved"}}, ...]`),
for answers that came by e-mail, and checks the whole file before it writes anything; `--check` reports
without writing. When an answer or decision replaces an earlier one (by `update`, or taken from Excel by
`render`), the earlier text is kept in the item's `history` with the day it was replaced, and the output
says so, since the client may have changed their mind.
Both write `register.json` in one step (a temporary file, then put in place) and leave the Excel file to
`render`.

`render` first takes over what was typed into the existing `register.xlsx` since it was written (a
client's answer, a changed status) and saves it in `register.json`, so the Excel file can be edited by
the BA without losing anything. A hidden sheet in the file records what it held when written, which is
how an edit in Excel is told from a change made in `register.json`. When both changed the same item it
stops and lists them; `--overwrite` writes the file from `register.json` and drops what was typed.
`--from` also takes over a copy that came back from the client (the `register.xlsx` they were sent, with
their answers in **Client response** or a status changed), after the project's own file and by the same
rules; the returned file is only read. An item that was also changed in `register.json` since the copy was
written stops it, with both values. The `client-answers` skill uses it.
In both files the client's items are in two sheets: **For client**, the questions still to answer (open or
asked), and **Already answered**, the rest; both are read back. The All items sheet shows the earlier answers.
Beside it, `render` writes `Questions for the client.xlsx`: the client's items alone, and no internal item in
any sheet, hidden or not, the only register file to send (the register's own file holds the internal fixes and a hidden record of
every item). A copy of it that comes back filled in is taken in with `--from` like the register itself.
Its Where column, like the register's For client sheet, says places in the client's words: a mock-up
comment's id becomes "mock-up comment", and a spec id of a screen or dialog becomes its title. `render`
warns about any client item whose Where still holds a reference of the team's (a mock-up comment, building
block, gap pattern or spec id). The internal sheets keep the references as written.
See [The register](register.md).

### mockup.py

```bash
python -I tools/mockup.py build       projects/<slug>
python -I tools/mockup.py serve       projects/<slug> [--port 8765] [--lan]
python -I tools/mockup.py screenshots projects/<slug>
python -I tools/mockup.py feedback    projects/<slug>
python -I tools/mockup.py look        projects/<slug> [--try key=value ...]
```
`serve` on a project whose mock-up is already open does not start a second server: it opens the running one
and says where it is. `look` prints the look of the client's screens (theme, colour, data colours, text size, font, corners, side menu, top bar,
logo and the project's own CSS), says when the current version was issued, and notes white words that are
hard to read on the project's colour (below 4.5 to 1), a font the mock-up does not carry, an accent or data colour in `desk` that
is close to a status colour or is violet or indigo, and a look that is custom work on a Joget platform.
`--try data_colors=#1597B0,#D55181` tries a pair. With `--try` (for example `--try menu=dark corners=square
logo=client-logo.png`; `key=none` takes a setting out) it builds a scratch copy as the project is now and one
with the settings tried, and saves the sign-in page and the first dashboard, list and form of each to
`_blueprint/mockup/look-preview/` as `<screen>-now.png` and `<screen>-try.png`. The project is not changed, and the
preview is never kept with a mock-up version. See [The client's look](spec-format.md#the-clients-look).

`serve` without a project opens a page that lists every mock-up on this machine, one click from each and
from its earlier versions (a version kept at the start of a live session reads "v1.4 as presented 6 Nov
19:00"); it is only shown on this computer, and `--lan` needs a project, so one client never sees
another's. Each project with a mock-up is a card (its version, when it was last built and last shown in a
live session, the comments waiting, earlier versions as links); projects without a mock-up yet are listed
below, each with what to say in Claude to make one. A mock-up is built when it is opened if its spec changed.

An open mock-up follows its spec: when the spec changes it is built again and the presenter's bar offers
**Update ready** (nothing reloads by itself; after the update feedback mode is off). After it a **What changed** panel lists what is new or different since the version on screen:
screens, fields, buttons, list columns, figures, dialogs, statuses, roles, sample data and the look, each
with the comments worked in for it, and the comments dealt with elsewhere. Click a change, or press **Start**
and **Next**, to open its screen (as a role that can see it) with the element outlined; **What changed** on
the bar opens the list again until the next update.
The comparison is made in the page, from the spec it was opened with and the new one; text only the
requirements document prints (descriptions, captions, requirements) is left out. A spec with a mistake
keeps the last good mock-up on show.

The walk-through (records added by a new form's Submit and moved by action buttons) is kept for the browser
tab's session, through a reload and Update ready. `serve` (and the page that lists every mock-up) shares it
between every browser showing that mock-up within a few seconds, kept in the server's memory only:
restarting the server starts from the sample data. **Reset sample data** on the presenter's bar puts it back
for everyone. A comment can be edited or deleted from the Feedback panel while it waits, by the browser that
wrote it or by the presenter on the machine running `serve`; a deleted comment stays in `feedback.json`
marked `withdrawn` (an edit keeps the earlier text in `history`) and is left out of `feedback`, `live list`
and every count.

```bash
python -I tools/mockup.py live start projects/<slug>
python -I tools/mockup.py live list  projects/<slug>
python -I tools/mockup.py live take  projects/<slug> <FB-id> [<FB-id> ...]
python -I tools/mockup.py live done  projects/<slug> <FB-id> [--note "..."]
python -I tools/mockup.py live mark  projects/<slug> <FB-id> <status> [--note "..."] [--register R-031]
python -I tools/mockup.py live undo  projects/<slug>
python -I tools/mockup.py live end   projects/<slug>
```
A live session, used by the `present` skill. `start` keeps the mock-up as it is presented
(`_blueprint/mockup/versions/v<version>-presented-<date>`). `list` shows the comments waiting. `take` marks
comments "Working on it" and keeps the spec and the project's own mock-up code as they are; `done` builds
the change, refuses it when it has a mistake, and marks the comments applied: run it once per comment, each
with its own note (several ids share one note). `mark` records what became of a comment (`working`, `applied`, `question`, `decision`,
`scope`, `declined`, or `received` to make it wait again); it also works outside a session and is the safe
way to write to `feedback.json` while a mock-up is open. Marking a comment records the spec's version as the
one it was worked into, and writes `Mock-up comments.xlsx` again (in `2 Reviews/`; `feedback/comments.xlsx` in
the old layout): every comment, one row each across all versions, with where it was made, who wrote it, its
outcome as a dot and a word, the note, the register item and the version it was worked into, filterable,
with a summary by outcome and by version. The project overview writes it too when the comments changed. `undo` puts the spec and the project's own code
back as they were before the last change, and makes its comments wait again (Received); it does not touch
the register, so register items made for that change are put back with `register.py update` (it names them).
When the copy kept before the change is missing, `undo` stops and changes nothing. `end` closes the session and says what to release. (`wait`,
which returns as soon as a comment arrives, and `checkpoint`, which keeps the project without marking a
comment, are there for working on each comment at once.) The mock-up is only ever sent a
comment's text and one of four words (Received, Working on it, Applied, Noted for follow-up): notes,
register items and the word "scope" stay in the project.

Builds the mock-up from the spec (self-contained: `_blueprint/mockup/index.html` opens without a server), serves it
with feedback capture, captures screenshots with Edge, or lists saved feedback by screen.
`present.cmd` runs `serve` (`present.sh` on macOS and Linux). See [Spec format](spec-format.md).

When buttons in the spec move a record to another status (`set_status`, and `also_move` for a linked
record), `build` says how many, lists the moves the status rules allow that no button makes, and names the
moves the rules mark as made by the system on its own (`auto`). It says which theme it drew (`theme joget:
the spec sets no theme, so it keeps joget` when the spec has none). It says
which forms add a record when submitted (and to which list, in which status), and which main buttons only
show their message, and how many parts of the mock-up carry a "Custom development" tag (from the spec's
`platform_fit` and the project's own code). It also lists, as warnings, settings the mock-up ignores (a
misspelling, a stray key from a comma in unquoted text, a `style`, `creates` or `example` on a row
action), and text the client would read in the mock-up that names a register item (`R-…`) or a mock-up comment
(`FB-…`), with where it is: say in words what is agreed, or move the note to a key that starts with `_`.

Every build keeps a copy of the mock-up in `_blueprint/mockup/versions/v<version>/`. The copy of a version that
was issued to the client is never replaced: bump `project.version` to keep a new one.

`screenshots` writes the pictures into `4 Mock-up screenshots/` and notes which screens they show
(`_blueprint/mockup/screenshots/taken-from.json`), so the
document generator can warn when the spec's screens have changed since. When a screen cannot be drawn, it
stops with that screen's name, the error the browser reported and the likely cause (the spec, or the
project's `spec/mockup.js`). The new pictures replace the last ones only once all of them are taken: a run
that stops, or finds no browser, leaves the pictures of the last run that worked and their note as they were.

With `--lan`, `serve` prints the address others on the same network open. Comments saved by anyone appear
on every open copy of the mock-up within a few seconds, numbered as they are saved (`FB-007` shows as 7).

`serve` takes its port for itself: when the port is already in use (another mock-up is still open) it
stops and says so; close the other one or add `--port 8766`. A comment the server cannot save is kept in
the browser that made it, shown as not saved, and sent again with the next comment or with **Try again**
in the Feedback panel.

### screenshot.mjs

Called by `mockup.py screenshots`; you don't run it directly. Drives the installed Microsoft Edge through
`playwright-core`, or Google Chrome where there is no Edge (common on a Mac and on Linux; Chromium is not
used). When neither starts, it says so and quotes why the browser the system usually has (Edge on Windows,
Chrome elsewhere) did not start.

- **Width.** A screenshot is printed about 15 cm wide in the requirements document, so the narrower the
  window it is taken in, the larger the screen's text on paper. Each screen is taken 800 pixels wide
  without the side menu (text prints at about 7.5 pt; the access matrix lists each role's menu). A screen
  that does not fit, for example a list with many columns, is taken 1000, 1200 or 1440 pixels wide instead,
  and the command says so; its text prints smaller. The process flow is taken 1000 pixels wide, so the words
  in its boxes fit.
- **Height.** Each screenshot is cropped to its content, with no minimum: a list with one row is a short
  picture. The login card and an open dialog are centred with space around them.
- **Sharpness.** Pictures have twice the pixels of the screen. The Word file keeps them whole. Word's PDF
  export reduces every picture to about 200 dots per inch, so the document generator puts the originals
  back into the PDF afterwards.

### generate_requirements.py

```bash
python -I tools/generate_requirements.py projects/<slug>
```
Generates the requirements document from the spec, screenshots (run `mockup.py screenshots` first) and register, using the
company profile, branding and [Document format](document-format.md). Prints warnings for anything to fix in the
spec. It writes the Word file (and the PDF) into `5 Requirements document/` and the spec it was made from into
`_blueprint/output/`. With Word installed it also updates the table of contents and page numbers, embeds the fonts and
writes a PDF.

- **The spec and the format are checked first.** The spec with the check the mock-up runs, plus the
  parts only the document prints (requirement groups and their items, notifications, non-functional
  requirements, glossary, extra sections, the timeline); the document format for settings that do not
  exist and values that cannot be used. Mistakes stop the run with the list of what to fix.
- **Screenshots are checked against the spec.** It warns when the screens changed after the screenshots
  were taken (`mockup.py screenshots` notes what they show in `_blueprint/mockup/screenshots/taken-from.json`) and
  when a screen has no picture. Text only the document prints (requirements, descriptions, rules, the
  version) does not count as a change.
- **The PDF always matches the Word file.** A PDF from an earlier run is removed before the new document
  is written. If the PDF or the document is open in another program, the run stops and says so.
- **Pictures in the PDF are full size.** After Word has exported the PDF, each figure in it is replaced by
  the file it was made from. Word keeps two identical screenshots once; that picture is replaced once for
  both. If the pictures in the PDF cannot be matched one for one with the figures, the PDF is left as Word
  made it; the last lines of the run say how many were replaced and, when not all, why.
- **Team-only text is warned about**, wherever the document prints spec or register text (descriptions,
  status meanings, rules, captions, labels, scope, requirements, the questions, answers and "agreed in" of
  the register): the mock-up, "proposed", mock-up comment ids (`FB-…`), register ids (`R-…`) that are not
  among the decisions needed, and requirement ids that are not in this spec. Each warning says where it is
  in the spec. The timeline and the version history may speak of the mock-up.
- **Decisions needed point at this document.** Each one shows the requirements that carry it as `tbc`, or
  else the requirement ids its register `source` names when this spec has them. A source that names ids of
  another document (the client's original, say) is not printed; a note lists those items.
- **Figures of the same screen have different captions.** An extra screenshot from the spec's
  `screenshots` takes its `caption`, or says the role or record it shows; two figures still alike are warned about.
- **Parts still missing** are listed after the warnings, "before issuing": no non-functional requirements,
  no timeline, nothing in scope, out of scope or assumed, and signatories with no name (or none listed).
  A draft may lack them; a version for sign-off should not.
- **Notes** are printed for things worth knowing that do not hold a version back: a spec with no status
  rules, no integration details or no formulas for its figures, and screens no requirement refers to.
  Warnings do hold it back.
- **The sign-off chapter says what is signed**: the version and its date, how many decisions are still open
  and that they are not part of the sign-off (with their section), and how to sign. Dates from the spec
  print as "6 November 2026" on the cover, in the version history and at sign-off.
- **No spec yet** is said in a sentence: build a mock-up first, which writes the spec.
- **When the Word step fails it says why.** "Word not available" means Word is not installed; anything
  else is reported as a failure with the reason. Word is closed whatever happens, so it is never left
  running hidden with the document locked.
- **The file name** is `<system> – <document title> v<version>`, with the characters Windows cannot store
  (`\ / : * ? " < > |`) replaced by a hyphen. The name inside the document is as the spec has it.

### workshop.py

```bash
python -I tools/workshop.py gaps   projects/<slug>
python -I tools/workshop.py check  projects/<slug> ["<agenda.json>"]
python -I tools/workshop.py render projects/<slug> ["<agenda.json>"]
```
`gaps` lists what a workshop has to settle: the open client questions, what the spec does not say yet
(including the scope of work's items that no requirement specifies) and the gap patterns with their evidence. `check` checks an agenda file in `_blueprint/workshops/`:
every reference is an open client question, every screen exists, the sections fit the time, no open
high-severity question is left out without a reason, and nothing the client's agenda prints (the goal, the
questions and options, what to bring, parked items) uses the team's words (mandays, rates, building blocks). `render` checks it and writes two Word documents into
`3 Workshops/`: the agenda for the client, and the facilitator notes for the BA, which add why each question
matters, your own view of the answer (`internal_view`; an older agenda's `recommendation` is read the same
way) and what was left for later. The notes are internal; neither document holds
mandays or cost. The file format is at the top of the script. Used by the `prep-workshop` skill.

### uat.py

```bash
python -I tools/uat.py draft   projects/<slug> [--current] [--date YYYY-MM-DD] [--force]
python -I tools/uat.py check   projects/<slug> ["<scripts.json>"]
python -I tools/uat.py render  projects/<slug> ["<scripts.json>"] [--force]
python -I tools/uat.py results projects/<slug> ["<filled-in workbook.xlsx>"]
python -I tools/uat.py defects projects/<slug>
python -I tools/uat.py defect  projects/<slug> D-001 [D-002 ...] <status> [--note "..."] [--cr CR-004]
```
`draft` writes `_blueprint/uat/<date> uat scripts v<version>.json` from the spec, the same way every
time: the main process as each role in turn (every status change made with the button that makes it, on the
screen where it is, signed in as the role allowed to press it; when the statuses belong to more than one kind
of record, told apart by the screens' `data`, each kind has a main process of its own), the other status moves, what each role may not do in each
status, field checks, access, dashboard figures, notifications and integrations. Each requirement that
plainly names a field, a dialog, a draft, a role it is sent to, a button, an e-mail on a status, a screen or
a list's add and edit goes into the scenario that tests it, or gets one written for it; the rest (and any
waiting for an open decision) get a case of their own to refine. A process step without a status rule is
made with the button named after it, and a draft or rejected record goes on with its form's own button.
Every case lists its `test_data` (test accounts, records in their status and how to get one, files,
mailboxes and connections). It uses the version issued last (`_blueprint/output/spec-v<version>.yaml`), or the
current spec when nothing is issued or with `--current`, and refuses to replace a draft of the same name
without `--force`. `check` checks that every requirement is covered or excluded with a reason, case ids are
unique, every step has an expected result, roles and screens exist and nothing internal is in it (mandays,
rates, internal register items, platform findings), and lists the draft's `todo`s still open and any case
without test data. `render`
checks and writes, into `6 UAT/`, the workbook for the testers (one row per step, Pass/Fail chosen from a
list, a summary of coverage and results, and the Test data sheet the client prepares before UAT) and the
test scripts as a Word document in the company's format, with the same test data list.
When the testers have already typed results into that workbook (a Pass/Fail, an actual result, a tester, a
date or a defect), `render` stops rather than write over them; `--force` writes it anyway and first keeps
their workbook beside it as `<name> - results kept <date> <time>.xlsx`.
`results` reads a filled-in workbook, lists the failed and blocked steps and brings the project's defect log
(`_blueprint/uat/defects/defects.json`) up to date: each failed step not yet logged becomes a defect
(`D-001` …, open) linked to its scenario, step and requirements; one marked fixed or retest that fails again
is open again, one whose step now passes is closed; a workbook read before changes nothing. It writes
`6 UAT/Defect log.xlsx`. `defects` lists the log and writes the Excel file again. `defect` sets the status of
one or more defects (open, fixed, retest, closed, "not a defect" with a `--note` saying why, or "change
request", with `--cr` for its CR id), keeping each change in the defect's history. The file format is at the top
of the script. Used by the `uat-scripts` skill. See [UAT scripts](uat.md).

### platform_fit.py

```bash
python -I tools/platform_fit.py check  projects/<slug>
python -I tools/platform_fit.py apply  projects/<slug>
python -I tools/platform_fit.py show   "<product>"
python -I tools/platform_fit.py sheet  "<product>" --docs <address> [--project projects/<slug>]
python -I tools/platform_fit.py record "<product>" <PF-id | new> [--feature ...] [--spec ...] [--support ...] [--takes ...] [--block ...] [--source <address>] [--confirmed "<name> <date>"]
```
`check` lists the features a spec uses (its screens, fields, lists, figures, workflow, notifications,
integrations, the project's own mock-up code) and what the platform sheets in `knowledge/platforms/` say
about each: custom work and what is not supported first, then features no sheet covers, products of the
stack with no sheet, and rows not yet checked against the product's documentation. A screen for managing
users, roles or permissions counts as `screen:user management` (its list data is users, roles, groups or
permissions, or only admin roles can open it and its title, menu label or id is about users, roles or
permissions). A stack entry that names the client is reported as the client's own system, not a product:
it belongs under `integrations` in the spec, and no sheet is suggested for it; `sheet --project` refuses a
product name with the client's name in it, because the sheets are shared. `apply` writes the
result into the spec as `platform_fit`, with the parts of the mock-up each feature is drawn in
(`elements`). It is internal: never in the requirements document; the mock-up only uses it to tag those
parts "Custom development" while presenting, with what each takes. `sheet` and `record` keep the sheets; `--source` records the documentation page and the date it
was checked. The tool never goes online itself: the `platform-fit` skill does the lookups. It writes to the
starter knowledge in `templates/` only when given `--knowledge`.

### estimate.py

```bash
python -I tools/estimate.py blocks    "Joget DX"
python -I tools/estimate.py inventory projects/<slug>
python -I tools/estimate.py render    projects/<slug> ["<estimate.json>"] [--force]
python -I tools/estimate.py weeks     projects/<slug> --team 2 ["<estimate.json>"]
python -I tools/estimate.py rates-from "<estimate.xlsx>" [--json]
```
`blocks` lists the building blocks and rates for a platform, then those of the *All platforms* table (a
mobile app, offline working, planning logic), the shares set for other work, and how many delivered
projects they rest on. `inventory` lists what a project has to count from: documents, screens, forms,
lists, integrations and open register items, and, when the spec has them, its mobile app screens (`m-`
screens) with the signatures, photos, scans and locations on them, and where it mentions offline working
or planning and scheduling, or a second language. `render` checks an estimate file, works out the
ranges, the confidence level and the comparison with the scope of work, and writes the Excel file into
`Internal – estimates and change requests/`; lines with no rate or share are listed as not priced and left out of the total. While a building
block has no rate, it gives no total at all: it says the build is not priced and shows what is priced so
far, and lists the scope-of-work lines that cannot be compared yet. When rates were typed into the *Rates
needed* sheet of the Excel file it would replace, `render` stops (take them in with `rates-from` first);
`--force` writes it anyway and keeps that file beside it (`… - rates kept <date> <time>.xlsx`). `weeks` turns the
estimate into working weeks for a team size (`--days` sets the working days a week, default 5), for
drafting the project timeline. `rates-from` reads the figures a lead developer filled in on the
*Rates needed* sheet of an estimate's Excel file and prints them as rows for `knowledge/building-blocks.md`
(low confidence), with the blocks left empty and any figure it could not read; `--json` prints the same
for Claude. It changes nothing: the rates are saved only after you agree. `render` and `weeks` take the newest file in `_blueprint/estimates/` (by the date its name starts with, then by
version number, so "spec v0.10" is newer than "spec v0.9") unless you name
one. Add `--knowledge <folder>` before the command to use another knowledge base.
See [Estimates](estimates.md).

### change_request.py

```bash
python -I tools/change_request.py scope  projects/<slug> "<request>" [--file <requests.txt>] [--top 8] [--version 1.0]
python -I tools/change_request.py add    projects/<slug> --file <cr.json>
python -I tools/change_request.py update projects/<slug> CR-001 --set status=quoted --set sold_md=4 --set sold_by="<name>"
python -I tools/change_request.py ask    projects/<slug> CR-002 [--check]
python -I tools/change_request.py check  projects/<slug>
python -I tools/change_request.py render projects/<slug>
python -I tools/change_request.py note   projects/<slug> CR-001
```
`scope` lists what in the version the client signed (the latest in `_blueprint/output/issued.json`, from its spec
snapshot; with nothing issued, the current spec, with a warning) reads most like a request: requirements,
screens, dialogs, status rules, scope lines, integrations, notifications, non-functional requirements, and
the register's decisions and open items, with ids and sections. It is a lead, not a verdict. `add` puts
CRs in `_blueprint/changes/crs.json` with the next ids and checks the log; `update` changes their status and the sold
figure the project lead gives. `ask` adds an Ambiguous request's client question to the register.
`check` checks the log and sizes each CR in building blocks with the estimate's rules, and shows the
knowledge base's calibration notes about change requests; `render` also writes
`Internal – estimates and change requests/CR log (internal).xlsx`. `note` writes the client's change request note (Word, company format,
into `7 Change requests/`) for a New CR: no sizing in it, and "Quotation to follow" until the project lead has entered the sold
figure. The file format is at the top of the script. Used by the `change-request` skill. See
[Change requests](change-requests.md).

### project.py

```bash
python -I tools/project.py ready   <slug>
python -I tools/project.py issue   <slug> [--to "the client"] [--date 2026-11-12] [--note "..."] [--without-pdf] [--anyway "<why>"]
python -I tools/project.py issued  <slug>
python -I tools/project.py file    <slug> "<file>" --kind "client comments" [--responds-to 1.3] [--date 2026-11-12] [--copy]
python -I tools/project.py archive <slug>
python -I tools/project.py restore <slug>
python -I tools/project.py find    "<system name>" [--client "<client>"]
python -I tools/project.py match   "<file>" [--text <extracted text.md>] [--json]
python -I tools/project.py hold    "<file>" --reason "not sure which project"
python -I tools/project.py check   [<slug>] [--fix]
python -I tools/project.py migrate <slug> | --all [--dry-run] [--undo]
```
Project housekeeping. `ready` says whether the current version can go to the client for signature. It stops
on a client question still marked "Blocks sign-off" (open or answered, high), on settled items with no agreed
`decision` (the document would print the client's raw answer as what is signed), on a scope of work item
(the spec's `sow`) that no requirement specifies and nobody agreed to leave out (`deferred`), and on a document
older than the spec or the register. It also lists what to look at: answered items still open, two questions that look
the same, a field whose choices differ from the ones the client listed in an answer, "the agreed …" or "to be
confirmed" in a requirement with no `tbc` item behind it, a requirement group that names no scope of work
item (a possible change request), a spec with no `sow` at all, and a side with nobody to sign. `issue` runs the
same check and issues nothing while something stops it; `--anyway "<why>"` issues it all the same and keeps
the reason with the issue. `issue` records that the current document version went to the client and locks it (its
files become read-only and the generator refuses to overwrite it, so the next change needs a new version).
It takes that version's Word file and PDF by their exact names, and needs the PDF: without one (the Word step
did not finish) it stops, and `--without-pdf` issues the Word file alone. A version written without quotes in
the spec is refused (YAML reads `1.10` as 1.1), here and by the generator. The record of what was issued is
written in one step, and a copy OneDrive made when two people issued at once (`issued-<computer>.json`) counts
too. `file` moves a document into `1 Client documents/` with a dated, descriptive name such as
`2026-11-12 client comments on v1.3.docx`. A file open in another program is not filed (it is never left in
both places), and `--date` must be a date. `archive` moves a delivered project to `projects/_archive/`,
out of the status list; `restore` brings it back. `archive` refuses when an archived project already has
that name, and moves nothing. Both move the folder in one step or not at all: when a file in it is open
(in Excel or Word, or OneDrive is syncing) they stop, move nothing and say to close it. `find` lists earlier work on the same or a similar system name (words like
"system" and "phase 2" are ignored; hyphens and dots inside a name do not count, so "E-PASS" is "EPASS"; one
distinctive word in common is enough, though not words many systems share such as "request"; `--client` puts
that client's own earlier projects first and marks them "same client"): active and archived projects, and systems delivered before, from
`knowledge/actuals/` and the projects log; `new-project` and `process-inbox` run it so a new document for a
system you already built is not treated as brand new. `check` reports projects missing parts of the
standard layout, and `--fix` creates them; it also names the projects still in the old folder layout, with
the command that moves them.

`migrate` moves a project from the old folder layout to the new one (see
[Moving a project to the new folder layout](workspace.md#moving-a-project-to-the-new-folder-layout)).
`--dry-run` lists every move and moves nothing; `--undo` moves a project back; `--all` does every active
project and reports on each. Nothing moves, and it says why, while the project's mock-up is served or a live
session is open, while one of its Word, Excel or PDF files is open (on Windows a file another program holds;
anywhere, a file with Office's `~$` lock file beside it, which a teammate's open copy leaves in a synced
folder), or when a folder of the other layout is already there. Folders move whole where they can, so a
synced folder sees few changes; a move that fails half-way puts back everything moved so far. Issued files
stay read-only, comments keep their ids, the moves are logged in `_blueprint/migration.json`, and the
overview page and shortcuts are made again (with the mock-up's change notes as Word files in `2 Reviews/`).

`match` says which active project a file belongs to, so that `process-inbox` never files one on a guess. It
reads Word, PDF (its text), Excel, text files and mock-up comments exports (`--text` uses an extraction made
earlier instead), scores the file against every active project and lists the evidence for each, strongest
first:

| Evidence | Points |
|---|---|
| Comments made on the project's mock-up (the build stamp of a comments export, any saved version) | 100 |
| Comments on screens only that project has / on screens missing from its spec | 15 a screen, at most 45 / −10 a screen, at most −30 |
| An id of the project (R-, FB-, UAT-, CR- or a requirement id) with the words around it matching that item | 25, or 20 when another project has the same id; at most 75 |
| An id only that project has, the words around it not matching | 5, at most 15 |
| Its system name / short name, when no other project has it | 30 / 15 |
| A distinctive word of its system name, not the whole name | 10 |
| Role names, screen titles, status names, field labels only that project has | 8 / 6 / 4 / 2 each (half for one word; a word as common as "User" or "Details" counts nothing), at most 40 |
| The client's name | 12 when only one active project is for that client, otherwise 5 |
| Names of its people (sample users, signatories, workshop attendees) / e-mail domains only it has | 4 / 12 each, at most 12 / 24 |
| The file name holding its system name, short name or folder name / only a distinctive word of them | 20 / 15 |

The verdict is **clear** when the best project has at least 40 points, at least 25 more than the next and at
least twice its score, and no archived project comes within 25 points of it; **likely** when it has at
least 15 points and 8 more than the next; otherwise **unknown**. Only a clear file may go into the plan
without a question about it; the client's name alone (5 points) never decides. Archived projects and
systems delivered before are listed apart, never as a place to file: restore first. `--json` gives the same
for the skill (`verdict`, `best`, `summary`, `projects`, `archived`, `delivered`, `note`).

`hold` leaves a file where it is with a note of why, in a hidden `.notes.json` beside it (one file per
folder, keyed by file name with the date and the reason); `match` shows the note, and `file` removes it when
the file is filed.

### overview.py

```bash
python -I tools/overview.py build projects/<slug>
python -I tools/overview.py build --all
```
Writes `Project overview.html` at the top of the project folder: one self-contained page that anyone can
open from the shared folder. It shows the next step (the same one `status.py` gives, with the words to say
to Claude and a button that opens the document it needs), four figures (client questions and how many
block sign-off, internal fixes, the mock-up, the requirements document), and then a card per stage in the
order of the process: client documents, review, workshops, mock-up, requirements document and the
estimate for the lead developer. Each document is a row that opens the real file, with a line about what
it is and who it is for (From the client, For the client, Show the client, Can be shared, Internal; the
register is Internal and `Questions for the client.xlsx` For the client); a stage with nothing yet says how to get there. Estimates, facilitator notes, reviews
and change notes are marked Internal, and the page never shows mandays, rates or cost. It is rewritten only
when something on it changed. For a project with a mock-up it also writes the **Open the mock-up**
shortcuts (`Open the mock-up.cmd` for Windows, `Open the mock-up.command` for a Mac): they find Blueprint on
the computer they are opened on (in `~/.blueprint/app-path`, which setup writes) and start the mock-up
through `present`, so comments are saved; without Blueprint set up they say what to do. It also makes the
Word version of any review that has none, and in the new folder layout of each mock-up change note (in
`2 Reviews/`). It works on a project in either layout. `register.py` (add, update, render), `workshop.py render`,
`estimate.py render`, `generate_requirements.py`, `project.py file` and `issue`, `new_project.py` and
`review_doc.py` rebuild the page after they write; a failure there never stops them (they print one line).
The start-up summary does not. The made-up sample in `examples/` is left alone.

### review_doc.py

```bash
python -I tools/review_doc.py projects/<slug> [<review>]
```
Turns a review's `review.md` (written by the `review-requirements` skill in `_blueprint/reviews/<review>/`)
into `2 Reviews/<document> review.docx` (beside `review.md` in the old layout), for example `SRS v1.0 review.docx`: headings, numbered and
bulleted lists, tables, bold, italic and code, in the company's Word template and document format (as the
workshop documents are). Every page says it is internal. Without a review named it takes the one written
last. `review.md` stays the source: change it and run this again.

### document_format.py

```bash
python -I tools/document_format.py show
python -I tools/document_format.py learn "<sample.docx>"
python -I tools/document_format.py preview
```
Shows the document format in effect, reports the fonts, sizes, colours, page set-up and chapters of a sample
document, or generates the sample project and renders its pages for review. `show` also lists any
mistakes in the company's format file and exits with an error when there are some. `learn` reads a Word
file (`.docx` or `.dotx`): given a PDF, an old `.doc` or a damaged file, it says so and asks for the Word
version. See [Document format](document-format.md).

### tour.py

```bash
python -I tools/tour.py start
python -I tools/tour.py comment
python -I tools/tour.py end
```
The scratch copy the `tour` skill works on. `start` copies the made-up sample (`examples/leave-request`,
without what is built from it) into `.tour/leave-request` in the app folder, gives it an empty register and
lays it out in the project folder layout a new project has, puts a one-page draft requirements document
with a few gaps planted in it in its `1 Client documents/`; running it again
starts over. The copy is ignored by git and is not one of the projects (`status.py` and the page that lists
every mock-up never show it); every tool that takes `projects/<slug>` works on `.tour/leave-request`.
`comment` saves one sample comment on the copy's mock-up, as the mock-up's Feedback would. `end` removes the
copy and refuses any other folder, or a folder the tour did not make. Nothing reads or writes the workspace.

### workspace.py

Shared helper, not run directly: finds the workspace, reads the company profile, and picks branding files
from the workspace or the neutral templates.

### sheets.py

Shared helper, not run directly: the look of every Excel workbook Blueprint writes (the register, the
estimate, the UAT workbook, the CR log), following [the design language](design-language.md#spreadsheets).
It sets fonts, the header row, hairlines, status as a dot and a coloured word, the cells to fill in and the
print set-up; the tools still decide the sheets, columns and values.

### layout.py

```bash
python -I tools/layout.py projects/<slug>
```
Says which folder layout a project is in and where each part of it is. Every tool asks it where a part of a
project is (the spec, the register and its Excel file, the client documents, reviews, workshops, the
mock-up, its screenshots and versions, comments, the requirements documents and issued versions, estimates,
UAT and change requests, the overview page), so all of them work on both layouts: a project with a
`_blueprint/` folder is in the new layout, any other in the old one. It also holds the migration that
`project.py migrate` runs, and the map from each old place to its new one.

### check_docs.py

```bash
python -I tools/check_docs.py
python -I tools/check_docs.py --pre-commit
```
Checks that the documentation and changelog are in step with the code. See [Maintaining](maintaining.md).
