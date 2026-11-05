# Document format

Generated requirements documents follow a format: how they look (fonts, sizes, colours) and how they are built
(which sections, in what order, how they are numbered). Blueprint ships one default design; each company
can change any part of it. The easiest way is to ask: "make our table headers navy", "learn our format
from this document" (the `document-format` skill).

## What the document is called

Blueprint calls it a **requirements document** everywhere in the app, because companies name it
differently: System or Software Requirements Specification (SRS), Functional Specification (FS or FSD),
Business Requirements Document (BRD), Product Requirements Document (PRD). The generated document uses
your company's own name for it, set with `document.title` (below). The default is "Requirements
Specification".

## The default design

Calm and easy to scan: true greys, one accent colour for links and the number that matters on a page,
Geist type with Geist Mono for IDs, hairline tables instead of grids, and status shown as a coloured dot
beside a word (orange: needs an answer, red: blocks sign-off, green: done).

| Part | What it contains | Built from |
|---|---|---|
| Cover | Logos, system name, client, status, version, dates, authors, platform | Spec `project` |
| Document at a glance | Counts (roles, screens, requirements, decisions needed), how to review it, sign-off status, version history | Spec, register |
| About this document | Disclaimer, confidentiality, concept acknowledgement | Standard wording |
| Contents | Chapters and sections (updated by Word) | |
| 1 Users and access | Overview, roles with data scope, access matrix (ticks), process flow and statuses, external systems, e-mail notifications, terms | Spec |
| 2 Requirements by role | Per role: what they see, their screens with section numbers, what they can do, e-mails they receive, decisions that affect them | Spec, register |
| 3 Functional requirements | Each group with its requirements, priority (when set) and the screens it applies to | Spec `requirements` |
| 4 Screens | Each screen: who uses it, screenshot, fields (type, required, rule or source), list columns, dialogs, linked requirements | Spec, mock-up |
| 5 Non-functional requirements | Areas and measurable requirements, or a "to be confirmed" note | Spec `nfr` |
| 6 onwards | Extra sections: environments, infrastructure, timeline … | Spec `extra_sections` |
| Decisions needed before sign-off | Every open client question with its impact, owner, due date and the requirements it affects | Register |
| Client acknowledgement and sign-off | Standard wording; what is being signed (version, open decisions excluded, how to sign); one form per signatory, client first: name, designation, signature and date rows and a company stamp box | Spec `signoff` |
| Appendices | Appendix A, B … | Spec `extra_sections` with `appendix: true` |

Every page except the cover has a header (system, version, status) and a footer (company, confidential,
page number).

## Page flow

Generated documents are laid out so nothing is cut off awkwardly between pages:

- every chapter, and every screen, starts on a new page (screens can run on; see `layout` below);
- a heading always stays on the same page as the text, screenshot or table that follows it;
- a screenshot and its caption are never separated;
- tables never start with a lone header at the foot of a page, short tables (up to six rows) are kept
  whole, rows never split, and the header row repeats on every page of a long table;
- short lists (a role's screens) stay together, and each sign-off form stays on one page;
- no paragraph leaves a single line stranded at the top or bottom of a page.

## Changing the format

Write only the keys you want to change in `workspace/branding/document-format.yaml`; everything else keeps the
default from `templates/document-format.yaml`.

```yaml
colors:
  accent: 0B6E4F          # links and highlights
numbering: decimal         # 1.0, 1.1 instead of 1, 1.1
chapters: [users_access, requirements, screens, nfr, extras, decisions, signoff]   # no role section
titles:
  decisions: Open issues
```

| Key | What it controls |
|---|---|
| `document.title`, `document.short` | What your company calls this document, e.g. "System Requirement Specifications" and "SRS", or "Functional Specification" and "FS". Used on the cover, in the sign-off wording and in file names. Default: "Requirements Specification" |
| `fonts.body`, `fonts.heading`, `fonts.mono` | Typefaces. The defaults (Geist, Geist Medium, Geist Mono) are installed by `setup.cmd`; any other font must be installed on the machines that generate documents |
| `sizes.*` | Point sizes: `body`, `table`, `table_header`, `caption`, `h1`, `h2`, `h3`, `cover_title` |
| `colors.*` | Hex colours without `#`: `text`, `secondary`, `separator` (row lines), `line` (header line), `field` (tags), `ground` (cards and screenshot frames), `accent`, `ok`, `warning`, `error` |
| `numbering` | `plain` (1, 1.1) or `decimal` (1.0, 1.1) |
| `layout.screens_new_page` | `true` (default): every screen in the Screens chapter starts on a new page; `false`: screens run on |
| `header_footer` | `generated` (system, version, status / company, page) or `template` (keep the header and footer of `branding/document-template.docx`; `{company}` in it is replaced) |
| `front` | Front matter in order: `cover`, `at_a_glance`, `about`, `contents` |
| `chapters` | Chapters in order: `users_access`, `by_role`, `requirements`, `screens`, `nfr`, `extras`, `decisions`, `signoff` |
| `titles.*` | Chapter and page titles |
| `labels.*` | Words used in the document: impact levels, "Decision needed", the default status, "Confidential" |

Other branding files in `workspace/branding/`: `logo.png` (cover), `document-template.docx` (styles, page
set-up, and the header and footer when `header_footer: template`), `document-boilerplate.yaml` (standard
wording). See [Workspace and company profile](workspace.md).

## Learning an existing format

```bash
python -I tools/document_format.py learn "<an existing requirements document>.docx"
```

Reports the fonts, sizes, table fills, colours, page set-up and chapter headings of a sample document, as
a starting point for the overrides. The `document-format` skill does this for you and proposes the changes.

## Previewing

```bash
python -I tools/document_format.py preview
```

Generates the made-up sample project with the current format and writes page images to
`examples/leave-request/output/preview/`, so you can check a change before regenerating a real requirements document.

## Signing

Each signatory gets a small form, kept on one page: a caption with their organisation and what they sign
for, then a bordered grid with name, designation, signature and date rows (left empty to write in when
the spec does not name them) and a full-height company stamp box on the right.

- **By hand:** print the sign-off pages, sign, stamp and scan them.
- **Digitally:** in the PDF, every signature box is a signing field. The client opens the PDF in Adobe
  Acrobat Reader and clicks a box to sign with a digital ID; each box can be signed separately and in any
  order. The fields show on screen but not on paper, so printed copies stay clean.

Signing fields are added when Word is installed (it produces the PDF). Name the signatories in the spec's
`signoff` list; see [Spec format](spec-format.md).

## Fonts in delivered documents

When Word is installed, Blueprint embeds the fonts used in each generated document, so clients see it as
intended even without Geist installed. The PDF always contains its fonts.
