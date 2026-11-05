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

### screenshot.mjs

Called by `mockup.py screenshots`; you don't run it directly. Drives the installed Microsoft Edge through
`playwright-core` and crops each screenshot to its content.

### generate_srs.py

```bash
python -I tools/generate_srs.py projects/<slug>
```
Generates the SRS from the spec, screenshots (run `mockup.py screenshots` first) and register, using the
company profile, branding and [SRS format](srs-format.md). Prints warnings for anything to fix in the
spec. With Word installed it also updates the table of contents and page numbers, embeds the fonts and
writes a PDF.

### srs_format.py

```bash
python -I tools/srs_format.py show
python -I tools/srs_format.py learn "<sample.docx>"
python -I tools/srs_format.py preview
```
Shows the SRS format in effect, reports the fonts, sizes, colours, page set-up and chapters of a sample
document, or generates the sample project and renders its pages for review. See [SRS format](srs-format.md).

### workspace.py

Shared helper, not run directly: finds the workspace, reads the company profile, and picks branding files
from the workspace or the neutral templates.

### check_docs.py

```bash
python -I tools/check_docs.py
python -I tools/check_docs.py --pre-commit
```
Checks that the documentation and changelog are in step with the code. See [Maintaining](maintaining.md).
