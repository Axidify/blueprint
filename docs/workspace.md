# Workspace and company profile

## App and workspace

Blueprint is split in two:

- **The app** is this repository: tools, skills, the mock-up engine and neutral templates. It contains no
  company or client information and is safe to share.
- **The workspace** holds everything about your company and your clients. It is never committed to git.

| Workspace item | What it is |
|---|---|
| `company.yaml` | Your company profile (below) |
| `branding/` | Optional logo, Word template and standard document wording |
| `knowledge/` | Your team's knowledge base, see [Knowledge base](knowledge.md) |
| `projects/` | One folder per client project |
| `inbox/` | Files waiting to be sorted |

`projects/`, `knowledge/` and `inbox/` also appear in the app folder: they are links into the workspace,
made by `setup.cmd` (`setup.sh` on a Mac), so you can work with them as if they were ordinary folders.

The workspace is `workspace/` inside the app folder unless you point it elsewhere (see below). On first
setup it is created from `templates/`: a placeholder company profile and a starter knowledge base.

## Company profile (`company.yaml`)

```yaml
name: Acme Solutions Sdn. Bhd.   # on the document cover, footer, standard wording and sign-off
short_name: Acme                 # used in the standard wording, e.g. "Acme Solutions Sdn. Bhd. (Acme)"
day_rate: 1500                   # used to cost estimates and variances
currency: RM
platforms: [Joget DX]            # offered when you create a project
```

## Branding (`branding/`)

Each file is optional. Without it, Blueprint uses the neutral version in `templates/`.

| File | Effect |
|---|---|
| `logo.png` | Your logo on the document cover |
| `document-template.docx` | Your Word template: styles and page set-up, plus its header and footer when the format says `header_footer: template` (any `{company}` in them is replaced with the company name). Nothing else of it is used: its body, comments, footnotes and file properties (title, subject, last saved by) never reach a generated document, so a template made from an earlier document is safe |
| `document-boilerplate.yaml` | Your standard document wording (disclaimer, confidentiality, sign-off). Start from `templates/document-boilerplate.yaml`. Placeholders: `{system}`, `{client}`, `{client_short}`, `{company}`, `{company_short}` |
| `document-format.yaml` | Your changes to the document design: colours, fonts, sizes, section order and numbering. Only the keys you set change. See [Document format](document-format.md) |

## Sharing a workspace with your team

Put the workspace in a shared folder, such as OneDrive or SharePoint synced to each machine, so everyone
works on the same projects and knowledge base:

1. One person moves their `workspace/` folder to the shared location (or creates an empty folder there).
2. Everyone creates `.blueprint-local.json` in their app folder:
   ```json
   { "workspace_dir": "C:\\Users\\you\\OneDrive - YourCo\\Blueprint Workspace" }
   ```
3. Everyone runs `setup.cmd`. It links `projects/`, `knowledge/` and `inbox/` to the shared workspace.

`.blueprint-local.json` is personal (paths differ per machine) and is not committed.

Two people editing the same project at the same moment can conflict in a synced folder. Agree who is
working on which project, especially during a session.

## Inside a project folder

Teammates often look in a project folder without Claude, from OneDrive or SharePoint. So what people open
is at the top, in numbered folders that sort in the order of the process, and Blueprint's working files are
tucked away in `_blueprint`. A folder appears only once the project has something for it.

| Folder or file | What it holds | For whom | Made by |
|---|---|---|---|
| `Project overview.html` | The project at a glance: the next step, the open questions and fixes, and every document in the order of the process, each a link with a line saying what it is and who it is for (see below) | everyone | `tools/overview.py`, rebuilt by the tools |
| `Open the mock-up.cmd`, `Open the mock-up.command` | Double-click to open the project's mock-up so comments typed in it are saved (`.cmd` on Windows, `.command` on a Mac). Only in a project with a mock-up | everyone | `tools/overview.py` |
| `Questions and fixes register.xlsx` | The project register for the BA: client questions, internal fixes and a hidden record of every item. Never sent | internal | the skills, `tools/register.py render` |
| `Questions for the client.xlsx` | The client's questions alone, written with the register: the file to send. The client's answers in a returned copy are taken in with `register.py render --from` | for the client | `tools/register.py render` |
| `1 Client documents/` | The client's documents (and your team's notes), kept as received. New ones are named with the date and what they are, e.g. `2026-11-12 client comments on v1.3.docx` | from the client | `process-inbox`, `new-project`, `tools/project.py file` |
| `2 Reviews/` | Each review as a Word file (`<document> review.docx`), the mock-up's change notes (`Mock-up v0.2 changes.docx`), and `Mock-up comments.xlsx`: every comment on the mock-up, one row each across all versions, with its outcome, note, register item and the version it was worked into | internal | `review-requirements`, `apply-feedback`, `tools/overview.py` |
| `3 Workshops/` | For each session, the agenda for the client and the facilitator notes, which are internal | client / internal | `prep-workshop` |
| `4 Mock-up screenshots/` | The pictures of the mock-up, as used in the requirements document | can be shared | `tools/mockup.py screenshots` |
| `5 Requirements document/` | Every generated requirements document version, Word and PDF | for the client | `generate-requirements` |
| `6 UAT/` | The testers' workbook and the UAT scripts document | for the client | `uat-scripts` |
| `7 Change requests/` | The client's change request notes | for the client | `change-request` |
| `Internal – estimates and change requests/` | Manday estimates (one dated Excel file each) and the CR log. Mandays, rates and cost live here only: never send these | internal | `estimate`, `change-request` |
| `_blueprint/` | Blueprint's working files, with a `README.txt` saying to leave them as they are: the spec and the project's own mock-up code (`spec/`), `register.json`, comments from sessions (`feedback/`), the built mock-up and every version of it (`mockup/`, `mockup/versions/v0.1/` …), each review's extraction and `review.md` and the change notes (`reviews/`), the `.json` source of each workshop, estimate, UAT script and the CR log, and the spec of each generated version with `issued.json`, the record of what went to the client (`output/`) | Blueprint | the tools |

The names are kept short so the full path stays well inside what Windows allows, even with the workspace
deep in a OneDrive folder.

### The overview page and the mock-up shortcut

A project folder holds a few hundred files once the mock-up has screenshots and versions, nearly all of
them in `_blueprint`. `Project overview.html` is the way in: double-click it, from the shared folder too,
to see what is open, what to do next (in the words to say to Claude) and every document as a row that
opens it. Each row says who the file is for: **From the client**, **For the client** (among them
`Questions for the client.xlsx`), **Show the client**, **Can be shared**, or **Internal** with a lock (the
register, estimates, facilitator notes, reviews and change notes: never send these). The page never
shows mandays, rates or cost. Blueprint rebuilds it whenever one of its tools writes into the project; to
rebuild it by hand, `python -I tools/overview.py build projects/<slug>` (or `build --all`).

**Open the mock-up** starts the mock-up the way `present.cmd` does, so the comments people type in it are
saved to the project (opening the mock-up's `index.html` in `_blueprint/mockup` directly only shows it). The
shortcut is the same in every project and works on any machine with Blueprint set up, wherever the app
folder is: `setup.cmd` (`setup.sh` on a Mac) records where the app is in `.blueprint/app-path` in the
person's home folder, and the shortcut reads it. On a machine without Blueprint it says what to do. On a
Mac, a `.command` file that came through a synced folder may need to be allowed once (right-click, Open); if
it still does not start, ask Claude to "present the mock-up". On Linux, use `./present.sh <slug>`.

Versions sent to the client are **locked**: their files are read-only and the generator refuses to
overwrite them, so every change after issuing becomes a new version. Delivered projects move to
`projects/_archive/` with `tools/project.py archive`, out of the status list; `restore` brings one back.
`python -I tools/project.py check --fix` brings a project up to its layout's standard folders.

## Moving a project to the new folder layout

Projects started before this layout keep the old one: `docs/`, `reviews/`, `spec/`, `mockup/`, `feedback/`,
`output/`, `workshops/`, `estimates/`, `uat/`, `changes/`, `register.json` and `register.xlsx` all at the
top. Nothing has to change: every tool works on both, and so does Blueprint on a teammate's machine while
the team moves over. `python -I tools/status.py` and `project.py check` name the projects still in the old
layout.

To move one, say **"migrate the folders"** to Claude, or run it yourself:

```bash
python -I tools/project.py migrate <slug> --dry-run     lists every move; nothing moves
python -I tools/project.py migrate <slug>               moves it
python -I tools/project.py migrate --all                every active project, with a line per project
python -I tools/project.py migrate <slug> --undo        moves it back to the old layout
```

- **Where things go.** `docs/` becomes `1 Client documents/`; each review's Word file goes to `2 Reviews/`;
  the workshop documents to `3 Workshops/`; the screenshots to `4 Mock-up screenshots/`; the requirements
  documents (Word and PDF) to `5 Requirements document/`; the UAT workbook and document to `6 UAT/`; the
  client's CR notes to `7 Change requests/`; the estimate Excel files and the CR log to `Internal – estimates
  and change requests/`; `register.xlsx` becomes `Questions and fixes register.xlsx`. Everything else
  (`spec/`, `register.json`, `feedback/`, the built mock-up and its versions, the review extractions, the
  `.json` sources, the spec snapshots and `issued.json`) goes into `_blueprint/`. Anything else at the top of
  the folder is left where it is, and listed.
- **What it keeps.** Issued files stay read-only, comments keep their ids, the register's Excel file is still
  read back by its column headings (answers typed into it are taken in as before), and saved mock-up
  versions can still be shown. The overview page and the Open the mock-up shortcuts are made again, and
  the mock-up's change notes get a Word copy in `2 Reviews/`. A log of the moves is kept in
  `_blueprint/migration.json`.
- **When it refuses**, nothing is moved and it says why: the project's mock-up is open (close its window, or
  press Ctrl+C where it runs), a live session is still open (end it), one of its Word, Excel or PDF files is
  open (here, or on a teammate's computer: Office leaves a `~$` lock file beside an open file in a synced
  folder), or a folder of the new layout is already there. If a move fails half-way, everything moved so
  far is put back.
- **Undo** puts every file back where it was, byte for byte, including files added since in the numbered
  folders; the Word copies of the change notes and the README go.

Agree a moment with the team: a teammate with the project open in Word or Excel, or presenting its mock-up,
stops the move until they close it.

## Moving or renaming the app folder

The links into the workspace use absolute paths. After moving or renaming the app folder, run
`setup.cmd` again; the machine check (`python -I tools/doctor.py`) reports broken links.
