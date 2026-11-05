# Blueprint

![Docs and changelog](https://github.com/Axidify/blueprint/actions/workflows/docs.yml/badge.svg)

Blueprint helps a delivery team get requirements right before anything is built. It reviews requirement
documents for gaps, builds clickable mock-ups to present to clients, collects their feedback, generates
the requirements document with screenshots, and learns from every project's change requests.

You use it by talking to Claude Code. There are no commands to learn.

## Get started (5 minutes)

1. **Install** [Claude Code](https://claude.com/claude-code), [Python 3.12](https://www.python.org/downloads/)
   (tick "Add python.exe to PATH") and [Node.js LTS](https://nodejs.org/). Microsoft Edge is needed for
   screenshots; Microsoft Word is optional (it updates the table of contents and makes PDFs).
2. **Clone** this repository and **double-click `setup.cmd`**. It installs everything else and checks your
   machine. Run it again any time something looks wrong.
3. **Open the folder in Claude Code** and type **`/start`**.

## What you can ask for

Type it in your own words, for example:

- "Start a new project for the courier booking system"
- "Review this requirements document" (drop the file in `inbox/` first, or attach it)
- "Build a mock-up from the brief"
- "Apply the feedback from today's session"
- "Generate the requirements document"
- "Process my inbox"

To present a mock-up in a meeting, double-click **`present.cmd`** and pick the project. Press **Feedback**
in the bottom-right corner, click anything on the screen and type a comment. Comments are saved
automatically.

## Where things are

| Folder | What is in it |
|---|---|
| `inbox/` | Drop files here: briefs, requirements drafts, notes, feedback exports. Then say "process my inbox". |
| `projects/<name>/` | One folder per client project: documents, register, mock-up, generated requirements document. |
| `projects/<name>/register.xlsx` | The questions and gaps to take back to the client. |
| `projects/<name>/output/` | Generated requirements document (Word and PDF). |
| `knowledge/` | What the team has learnt: gap patterns, estimating building blocks, requirements standard. |

`inbox/`, `projects/` and `knowledge/` live in your **workspace**, together with your company profile
(`company.yaml`) and branding (`branding/`: logo, Word template, standard document wording). By default the
workspace is the `workspace/` folder here. To share one workspace across a team, put it in a shared
folder (OneDrive or SharePoint) and set its path in `.blueprint-local.json`:

```json
{ "workspace_dir": "C:\\Users\\you\\OneDrive - YourCo\\Blueprint Workspace" }
```

then run `setup.cmd` again.

The workspace is never committed to git: it holds client documents.

## Documentation

Full documentation is in **[docs/](docs/README.md)**: [getting started](docs/getting-started.md),
[workflow](docs/workflow.md), [skills](docs/skills.md), [the register](docs/register.md),
[workspace and company profile](docs/workspace.md), [spec format](docs/spec-format.md),
[tools](docs/tools.md), [troubleshooting](docs/troubleshooting.md). What changed in each version is in the
**[changelog](CHANGELOG.md)**.

## For maintainers

Every change to the app ships with its documentation and a changelog entry: see
[docs/maintaining.md](docs/maintaining.md). `python -I tools/check_docs.py` checks it, before every commit
made through Claude Code and on GitHub for every push.

- `tools/` – scripts (Python, plus Node for screenshots).
- `.claude/skills/` – one skill per task; `CLAUDE.md` – instructions Claude follows in this repo.
- `templates/` – neutral defaults for new workspaces (company profile, Word template, document wording,
  starter knowledge, project template).
- `examples/leave-request/` – a made-up sample project for testing the pipeline.
