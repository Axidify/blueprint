# Workspace and company profile

## App and workspace

Blueprint is split in two:

- **The app** is this repository: tools, skills, the mock-up engine and neutral templates. It contains no
  company or client information and is safe to share.
- **The workspace** holds everything about your company and your clients. It is never committed to git.

| Workspace item | What it is |
|---|---|
| `company.yaml` | Your company profile (below) |
| `branding/` | Optional logo, Word template and standard SRS wording |
| `knowledge/` | Your team's knowledge base, see [Knowledge base](knowledge.md) |
| `projects/` | One folder per client project |
| `inbox/` | Files waiting to be sorted |

`projects/`, `knowledge/` and `inbox/` also appear in the app folder: they are links into the workspace,
made by `setup.cmd`, so you can work with them as if they were ordinary folders.

The workspace is `workspace/` inside the app folder unless you point it elsewhere (see below). On first
setup it is created from `templates/`: a placeholder company profile and a starter knowledge base.

## Company profile (`company.yaml`)

```yaml
name: Acme Solutions Sdn. Bhd.   # on the SRS cover, footer, standard wording and sign-off
short_name: Acme                 # used in the standard wording, e.g. "Acme Solutions Sdn. Bhd. (Acme)"
day_rate: 1500                   # used to cost estimates and variances
currency: RM
platforms: [Joget DX]            # offered when you create a project
```

## Branding (`branding/`)

Each file is optional. Without it, Blueprint uses the neutral version in `templates/`.

| File | Effect |
|---|---|
| `logo.png` | Your logo on the SRS cover |
| `srs-template.docx` | Your Word template: styles and page set-up, plus its header and footer when the format says `header_footer: template` (any `{company}` in them is replaced with the company name). The document body is ignored |
| `srs-boilerplate.yaml` | Your standard SRS wording (disclaimer, confidentiality, sign-off). Start from `templates/srs-boilerplate.yaml`. Placeholders: `{system}`, `{client}`, `{client_short}`, `{company}`, `{company_short}` |
| `srs-format.yaml` | Your changes to the SRS design: colours, fonts, sizes, section order and numbering. Only the keys you set change. See [SRS format](srs-format.md) |

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

## Moving or renaming the app folder

The links into the workspace use absolute paths. After moving or renaming the app folder, run
`setup.cmd` again; the machine check (`python -I tools/doctor.py`) reports broken links.
