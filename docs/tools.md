# Tools

The skills run these scripts for you. Run them yourself when you want a single step. Run them from the
app folder, always with `python -I` (it keeps Python from loading stray files).

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
Lists the projects with their stage, open register items and suggested next step, plus files waiting in
the inbox. The `--brief` form is what you see when Claude Code starts. A project with a damaged register,
spec or feedback file is still listed, with a line saying which file could not be read; the other projects
are shown as usual.

### new_project.py

```bash
python -I tools/new_project.py courier-booking "Courier Booking System" "Acme Logistics Sdn. Bhd." --platform "Joget DX"
```
Creates `projects/<slug>/` with `docs/`, `reviews/`, `spec/`, `feedback/` and an empty register.

### extract.py

```bash
python -I tools/extract.py "<document>" projects/<slug>/reviews/<review>/extract
```
Turns a Word, PDF, Excel, Markdown or text file into `text.md` (reading order, tables as rows, tracked
changes, comments), `meta.json` (metadata, counts, every TBC / TBD / "if applicable") and `images/`. For
PDFs it also renders pages with diagrams or formulas to `pages/`.

In a Word document, headings and numbered paragraphs carry the number Word shows in front of them
(`## 3.2 Roles`, `- (a) ...`), worked out from the document's numbering definitions, because Word does not
store those numbers in the text.

A spreadsheet cell with a formula is given as its calculated value followed by the formula
(`B4=15 (formula =SUM(B2:B3))`). Text files are read whether saved as UTF-8, as Notepad's "Unicode" or in
the Windows encoding; `meta.json` says which.

Give it a folder of its own. It replaces an earlier extraction there and leaves any other file in that
folder alone; a folder that holds files and is not an earlier extraction (a project's `docs/`, say) is
refused and nothing in it is touched.

### register.py

```bash
python -I tools/register.py validate projects/<slug>
python -I tools/register.py render   projects/<slug> [--overwrite]
python -I tools/register.py next-id  projects/<slug>
```
Validates `register.json`, renders `register.xlsx`, or prints the next free item ID.

`render` first takes over what was typed into the existing `register.xlsx` since it was written (a
client's answer, a changed status) and saves it in `register.json`, so the Excel file can be edited by
the BA without losing anything. A hidden sheet in the file records what it held when written, which is
how an edit in Excel is told from a change made in `register.json`. When both changed the same item it
stops and lists them; `--overwrite` writes the file from `register.json` and drops what was typed.
See [The register](register.md).

### mockup.py

```bash
python -I tools/mockup.py build       projects/<slug>
python -I tools/mockup.py serve       projects/<slug> [--port 8765] [--lan]
python -I tools/mockup.py screenshots projects/<slug>
python -I tools/mockup.py feedback    projects/<slug>
```
Builds the mock-up from the spec (self-contained: `mockup/index.html` opens without a server), serves it
with feedback capture, captures screenshots with Edge, or lists saved feedback by screen.
`present.cmd` runs `serve` (`present.sh` on macOS and Linux). See [Spec format](spec-format.md).

Every build keeps a copy of the mock-up in `mockup/versions/v<version>/`. The copy of a version that
was issued to the client is never replaced: bump `project.version` to keep a new one.

`screenshots` also notes which screens the pictures show (`mockup/screenshots/taken-from.json`), so the
document generator can warn when the spec's screens have changed since.

With `--lan`, `serve` prints the address others on the same network open. Comments saved by anyone appear
on every open copy of the mock-up within a few seconds, numbered as they are saved (`FB-007` shows as 7).

`serve` takes its port for itself: when the port is already in use (another mock-up is still open) it
stops and says so; close the other one or add `--port 8766`. A comment the server cannot save is kept in
the browser that made it, shown as not saved, and sent again with the next comment or with **Try again**
in the Feedback panel.

### screenshot.mjs

Called by `mockup.py screenshots`; you don't run it directly. Drives the installed Microsoft Edge through
`playwright-core`, or Google Chrome where there is no Edge (common on a Mac).

- **Width.** A screenshot is printed about 14 cm wide in the requirements document, so the narrower the
  window it is taken in, the larger the screen's text on paper. Each screen is taken 1000 pixels wide
  (text prints at about 6 pt). A screen that does not fit, for example a list with many columns, is taken
  1200 or 1440 pixels wide instead, and the command says so; its text prints smaller.
- **Height.** Each screenshot is cropped to its content, with no minimum: a list with one row is a short
  picture. The login card and an open dialog are centred with space around them.
- **Sharpness.** Pictures have twice the pixels of the screen. The Word file keeps them whole; Word's PDF
  export reduces every picture to about 200 dots per inch.

### generate_requirements.py

```bash
python -I tools/generate_requirements.py projects/<slug>
```
Generates the requirements document from the spec, screenshots (run `mockup.py screenshots` first) and register, using the
company profile, branding and [Document format](document-format.md). Prints warnings for anything to fix in the
spec. With Word installed it also updates the table of contents and page numbers, embeds the fonts and
writes a PDF.

- **The spec and the format are checked first.** The spec with the check the mock-up runs, plus the
  parts only the document prints (requirement groups and their items, notifications, non-functional
  requirements, glossary, extra sections, the timeline); the document format for settings that do not
  exist and values that cannot be used. Mistakes stop the run with the list of what to fix.
- **Screenshots are checked against the spec.** It warns when the screens changed after the screenshots
  were taken (`mockup.py screenshots` notes what they show in `mockup/screenshots/taken-from.json`) and
  when a screen has no picture. Text only the document prints (requirements, descriptions, rules, the
  version) does not count as a change.
- **The PDF always matches the Word file.** A PDF from an earlier run is removed before the new document
  is written. If the PDF or the document is open in another program, the run stops and says so.
- **Notes** are printed for things worth knowing that do not hold a version back: a spec with no status
  rules, no integration details or no formulas for its figures, and screens no requirement refers to.
  Warnings do hold it back.
- **When the Word step fails it says why.** "Word not available" means Word is not installed; anything
  else is reported as a failure with the reason. Word is closed whatever happens, so it is never left
  running hidden with the document locked.
- **The file name** is `<system> – <document title> v<version>`, with the characters Windows cannot store
  (`\ / : * ? " < > |`) replaced by a hyphen. The name inside the document is as the spec has it.

### estimate.py

```bash
python -I tools/estimate.py blocks    "Joget DX"
python -I tools/estimate.py inventory projects/<slug>
python -I tools/estimate.py render    projects/<slug> ["<estimate.json>"]
python -I tools/estimate.py weeks     projects/<slug> --team 2 ["<estimate.json>"]
```
`blocks` lists the building blocks and rates for a platform, the shares set for other work, and how many
delivered projects they rest on. `inventory` lists what a project has to count from: documents, screens,
forms, lists, integrations and open register items. `render` checks an estimate file, works out the
ranges, the confidence level and the comparison with the scope of work, and writes the Excel file next to
it; lines with no rate or share are listed as not priced and left out of the total. `weeks` turns the
estimate into working weeks for a team size (`--days` sets the working days a week, default 5), for
drafting the project timeline. `render` and `weeks` take the newest file in `estimates/` (by the date its name starts with, then by
version number, so "spec v0.10" is newer than "spec v0.9") unless you name
one. Add `--knowledge <folder>` before the command to use another knowledge base.
See [Estimates](estimates.md).

### project.py

```bash
python -I tools/project.py issue   <slug> [--to "the client"] [--date 2026-11-12] [--note "..."]
python -I tools/project.py issued  <slug>
python -I tools/project.py file    <slug> "<file>" --kind "client comments" [--responds-to 1.3] [--date 2026-11-12] [--copy]
python -I tools/project.py archive <slug>
python -I tools/project.py restore <slug>
python -I tools/project.py check   [<slug>] [--fix]
```
Project housekeeping. `issue` records that the current document version went to the client and locks it (its
files become read-only and the generator refuses to overwrite it, so the next change needs a new version).
`file` moves a document into `docs/` with a dated, descriptive name such as
`2026-11-12 client comments on v1.3.docx`. `archive` moves a delivered project to `projects/_archive/`,
out of the status list; `restore` brings it back. `check` reports projects missing parts of the standard
layout, and `--fix` creates them.

### document_format.py

```bash
python -I tools/document_format.py show
python -I tools/document_format.py learn "<sample.docx>"
python -I tools/document_format.py preview
```
Shows the document format in effect, reports the fonts, sizes, colours, page set-up and chapters of a sample
document, or generates the sample project and renders its pages for review. `show` also lists any
mistakes in the company's format file and exits with an error when there are some. See
[Document format](document-format.md).

### workspace.py

Shared helper, not run directly: finds the workspace, reads the company profile, and picks branding files
from the workspace or the neutral templates.

### check_docs.py

```bash
python -I tools/check_docs.py
python -I tools/check_docs.py --pre-commit
```
Checks that the documentation and changelog are in step with the code. See [Maintaining](maintaining.md).
