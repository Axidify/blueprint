# Blueprint

Blueprint helps a delivery team get requirements right before anything is built. It reviews requirement
documents for gaps, builds clickable mock-ups to present to clients, collects their feedback, generates
the SRS with screenshots, and learns from every project's change requests.

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
- "Review this SRS" (drop the file in `inbox/` first, or attach it)
- "Build a mock-up from the brief"
- "Apply the feedback from today's session"
- "Generate the SRS"
- "Process my inbox"

To present a mock-up in a meeting, double-click **`present.cmd`** and pick the project. Press **Feedback**
in the bottom-right corner, click anything on the screen and type a comment. Comments are saved
automatically.

## Where things are

| Folder | What is in it |
|---|---|
| `inbox/` | Drop files here: briefs, SRS drafts, notes, feedback exports. Then say "process my inbox". |
| `projects/<name>/` | One folder per client project: documents, register, mock-up, generated SRS. |
| `projects/<name>/register.xlsx` | The questions and gaps to take back to the client. |
| `projects/<name>/output/` | Generated SRS (Word and PDF). |
| `knowledge/` | What the team has learnt: gap patterns, estimating building blocks, SRS standard. |

`inbox/`, `projects/` and `knowledge/` live in your **workspace**, together with your company profile
(`company.yaml`) and branding (`branding/`: logo, Word template, standard SRS wording). By default the
workspace is the `workspace/` folder here. To share one workspace across a team, put it in a shared
folder (OneDrive or SharePoint) and set its path in `.blueprint-local.json`:

```json
{ "workspace_dir": "C:\\Users\\you\\OneDrive - YourCo\\Blueprint Workspace" }
```

then run `setup.cmd` again.

The workspace is never committed to git: it holds client documents.

## For maintainers

- `tools/` – scripts (Python, plus Node for screenshots). `tools/mockup/SPEC.md` documents the mock-up spec.
- `.claude/skills/` – one skill per task; `CLAUDE.md` – instructions Claude follows in this repo.
- `templates/` – neutral defaults for new workspaces (company profile, Word template, SRS wording,
  starter knowledge, project template).
- `examples/leave-request/` – a made-up sample project for testing the pipeline.
