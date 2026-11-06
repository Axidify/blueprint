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
| `document-template.docx` | Your Word template: styles and page set-up, plus its header and footer when the format says `header_footer: template` (any `{company}` in them is replaced with the company name). The document body is ignored |
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

| Folder or file | What it holds | Managed by |
|---|---|---|
| `docs/` | Documents from the client and your team. New ones are named with the date and what they are, e.g. `2026-11-12 client comments on v1.3.docx` | `process-inbox`, `new-project`, `tools/project.py file` |
| `reviews/<document and version>/` | One folder per reviewed document version: extraction and review report | `review-requirements` |
| `spec/` | The project spec, client logo, process-flow image | `build-mockup`, `apply-feedback` |
| `mockup/` | The current mock-up and screenshots; `mockup/versions/v0.1/`, `v0.2/` … keep every version | `tools/mockup.py` |
| `feedback/` | Comments from mock-up sessions | the mock-up's Feedback mode |
| `output/` | Every generated requirements document (Word and PDF) and the spec that produced it; `issued.json` lists the versions sent to the client | `generate-requirements`, `tools/project.py issue` |
| `estimates/` | Manday estimates, one dated Excel file (and its `.json` source) per estimate. Internal: never sent to the client | `estimate` |
| `workshops/` | One dated agenda (`.json` source) per client session, and the two Word documents made from it: the agenda for the client and the facilitator notes, which are internal | `prep-workshop` |
| `register.json`, `register.xlsx` | The project register | the skills |

Versions sent to the client are **locked**: their files are read-only and the generator refuses to
overwrite them, so every change after issuing becomes a new version. Delivered projects move to
`projects/_archive/` with `tools/project.py archive`, out of the status list; `restore` brings one back.
`python -I tools/project.py check --fix` brings an older project up to this layout.

## Moving or renaming the app folder

The links into the workspace use absolute paths. After moving or renaming the app folder, run
`setup.cmd` again; the machine check (`python -I tools/doctor.py`) reports broken links.
