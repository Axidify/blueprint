# Blueprint

![Tests](https://github.com/Axidify/blueprint/actions/workflows/tests.yml/badge.svg)
![Docs and changelog](https://github.com/Axidify/blueprint/actions/workflows/docs.yml/badge.svg)

Blueprint helps a delivery team get requirements right before anything is built. It reviews requirement
documents for gaps, builds clickable mock-ups to present to clients, collects their feedback, generates
the requirements document with screenshots, and learns from every project's change requests.

You use it by talking to Claude Code. There are no commands to learn. It runs on Windows and on a Mac.

https://github.com/user-attachments/assets/94a044d1-73c5-4213-94d9-ca1990de57b6

*One-minute overview. The client in the video is fictional; results vary with the model and effort setting.*

## Get started (5 minutes)

1. **Install** [Claude Code](https://claude.com/claude-code), [Python 3.12](https://www.python.org/downloads/)
   (on Windows tick "Add python.exe to PATH"), [Node.js LTS](https://nodejs.org/) and
   [Git](https://git-scm.com/downloads) (on a Mac it is offered the first time you type `git`). Microsoft
   Edge or Google Chrome is needed for screenshots; Microsoft Word is optional (on Windows it updates the
   table of contents and makes PDFs).
2. **Clone** this repository (`git clone https://github.com/Axidify/blueprint.git`) and **double-click
   `setup.cmd`** (on a Mac: `setup.command`, or run `./setup.sh`). It installs everything else and checks
   your machine. Run it again any time something looks wrong. On a Mac or Linux, read
   [the few differences](docs/getting-started.md#on-a-mac) first.
3. **Open the folder in Claude Code** and type **`/start`**.

To update Blueprint later, pull the latest version (`git pull` in the folder) and run setup again.

## What you can ask for

Type it in your own words, for example:

- "Give me a tour" (a ten-minute first run on a made-up sample, before your first real document)
- "Start a new project for the courier booking system"
- "Review this requirements document" (drop the file in `inbox/` first, or attach it)
- "Build a mock-up from the brief"
- "Apply the feedback from today's session"
- "Generate the requirements document"
- "Estimate the mandays for this project"
- "Make our documents look like our house style" (colours, fonts, table headers, chapter order)
- "Make the mock-up look like the client's intranet" (their logo, colours, font; or learnt from screenshots
  of their systems, shown before and after)
- "Process my inbox"

To present a mock-up in a meeting, double-click **`present.cmd`** (on a Mac: **`present.command`**) and pick
the project. Press **Feedback**
on the dark bar in the bottom-right corner, click anything on the screen and type a comment, or drag a box:
around several things for one comment about all of them, or where there is nothing yet for something new
("an Export button here"); the box stays beside what it was drawn next to, whatever the width of the
window. Comments are saved automatically, and every comment with what became of it is
listed in the project's `2 Reviews/Mock-up comments.xlsx`. When the mock-up is changed, **Update ready**
appears; press it and **What changed** lists each change, so you can go through them with the room. Submitting a form or approving a request plays out on screen, and the walk-through is kept
(and shared with everyone in the room) until you press **Reset sample data**.

## Where things are

| Folder | What is in it |
|---|---|
| `inbox/` | Drop files here: briefs, requirements drafts, notes, feedback exports. Then say "process my inbox". |
| `projects/<name>/` | One folder per client project. Open its `Project overview.html` first. |
| `projects/<name>/Questions and fixes register.xlsx` | The questions and gaps, with your team's internal fixes. |
| `projects/<name>/Questions for the client.xlsx` | The client's questions alone: the file to send them. |
| `projects/<name>/1 Client documents/` … `7 Change requests/` | What people open, numbered in the order of the process: the client's documents, reviews, workshops, mock-up screenshots, the requirements document (Word and PDF), UAT, change requests. Estimates and the CR log are in `Internal – estimates and change requests/`, never sent. |
| `projects/<name>/_blueprint/` | Blueprint's working files (spec, register, mock-up, comments). Leave them to Blueprint. |
| `knowledge/` | What the team has learnt: gap patterns, estimating building blocks, requirements standard. |

`inbox/`, `projects/` and `knowledge/` live in your **workspace**, together with your company profile
(`company.yaml`) and branding (`branding/`: logo, Word template, standard document wording). By default the
workspace is the `workspace/` folder here. To share one workspace across a team, put it in a shared
folder (OneDrive or SharePoint) and set its path in `.blueprint-local.json`:

```json
{ "workspace_dir": "C:\\Users\\you\\OneDrive - YourCo\\Blueprint Workspace" }
```

then run `setup.cmd` again (on a Mac: `./setup.sh`, with a path such as
`"/Users/you/Library/CloudStorage/OneDrive-YourCo/Blueprint Workspace"`).

The workspace is never committed to git: it holds client documents.

## Documentation

Full documentation is in **[docs/](docs/README.md)**: [getting started](docs/getting-started.md),
[workflow](docs/workflow.md), [skills](docs/skills.md), [the register](docs/register.md),
[workspace and company profile](docs/workspace.md), [spec format](docs/spec-format.md),
[document format](docs/document-format.md), [design language](docs/design-language.md),
[estimates](docs/estimates.md), [tools](docs/tools.md),
[troubleshooting](docs/troubleshooting.md). What changed in each version is in the
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
