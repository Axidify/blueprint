# Tools

The skills run these scripts for you. Run them yourself when you want a single step. Run them from the
app folder, always with `python -I` (it keeps Python from loading stray files).

### doctor.py

```bash
python -I tools/doctor.py
```
Checks Python and its packages, Node and the screenshot tool, Edge, Word (optional), the workspace, the
company profile and the workspace links. Prints the fix for anything missing. `setup.cmd` runs it at the end.

### status.py

```bash
python -I tools/status.py
python -I tools/status.py --brief
```
Lists the projects with their stage, open register items and suggested next step, plus files waiting in
the inbox. The `--brief` form is what you see when Claude Code starts.

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

### register.py

```bash
python -I tools/register.py validate projects/<slug>
python -I tools/register.py render   projects/<slug>
python -I tools/register.py next-id  projects/<slug>
```
Validates `register.json`, renders `register.xlsx`, or prints the next free item ID.
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
`present.cmd` runs `serve`. See [Spec format](spec-format.md).

`screenshots` also notes which screens the pictures show (`mockup/screenshots/taken-from.json`), so the
document generator can warn when the spec's screens have changed since.

`serve` takes its port for itself: when the port is already in use (another mock-up is still open) it
stops and says so; close the other one or add `--port 8766`. A comment the server cannot save is kept in
the browser that made it, shown as not saved, and sent again with the next comment or with **Try again**
in the Feedback panel.

### screenshot.mjs

Called by `mockup.py screenshots`; you don't run it directly. Drives the installed Microsoft Edge through
`playwright-core` and crops each screenshot to its content.

### generate_requirements.py

```bash
python -I tools/generate_requirements.py projects/<slug>
```
Generates the requirements document from the spec, screenshots (run `mockup.py screenshots` first) and register, using the
company profile, branding and [Document format](document-format.md). Prints warnings for anything to fix in the
spec. With Word installed it also updates the table of contents and page numbers, embeds the fonts and
writes a PDF.

- **The spec is checked first**, with the same check the mock-up runs; errors stop the run.
- **Screenshots are checked against the spec.** It warns when the screens changed after the screenshots
  were taken (`mockup.py screenshots` notes what they show in `mockup/screenshots/taken-from.json`) and
  when a screen has no picture. Text only the document prints (requirements, descriptions, rules, the
  version) does not count as a change.
- **The PDF always matches the Word file.** A PDF from an earlier run is removed before the new document
  is written. If the PDF or the document is open in another program, the run stops and says so.
- **When the Word step fails it says why.** "Word not available" means Word is not installed; anything
  else is reported as a failure with the reason.
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
drafting the project timeline. `render` and `weeks` take the newest file in `estimates/` unless you name
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
document, or generates the sample project and renders its pages for review. See [Document format](document-format.md).

### workspace.py

Shared helper, not run directly: finds the workspace, reads the company profile, and picks branding files
from the workspace or the neutral templates.

### check_docs.py

```bash
python -I tools/check_docs.py
python -I tools/check_docs.py --pre-commit
```
Checks that the documentation and changelog are in step with the code. See [Maintaining](maintaining.md).
