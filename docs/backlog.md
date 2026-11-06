# Development backlog

Handing the requirements to the developers is where they are most often read differently. Blueprint writes
the backlog from the project spec, so every user story is tied to what the client signed: its requirement,
its screens and its acceptance criteria. Ask for it with "write the backlog" (the `backlog` skill).

Writing the stories also shows what nobody decided: a screen no requirement asks for, estimated work no
requirement covers, a story waiting on an open client question. Those go into the register, the same way a
review's findings do.

## What you get

In `projects/<name>/backlog/`:

| File | For | What it is |
|---|---|---|
| `<date> backlog v<version>.json` | Blueprint | The backlog. The other files are made from it; change this one and render again |
| `<date> backlog v<version>.xlsx` | The team (internal) | **Summary** (counts, story points, the gaps found), **Backlog** (epics and stories with the user story, numbered acceptance criteria, priority, points, requirements, screens and open questions) and **Points** (how each story's points were worked out) |
| `… - traceability.xlsx` | The client | Each requirement with what it says, its priority, its screens, the user stories that build it, the UAT scenarios that test it and the change requests that touched it |
| `… - Project Desk import.xlsx` | The team | The Tasks sheet Project Desk's task import reads: epics and stories nested by their number (1, 1.1 …), with type, status, priority, story points, description and acceptance criteria |
| `… - Jira import.csv` | The team | For Jira's CSV import: Issue ID and Parent link each story to its epic |
| `… - Azure DevOps import.csv` | The team | For Azure DevOps' CSV import: each epic as a Feature with its user stories under it |

The traceability sheet never holds story points, mandays, estimate lines, notes or internal register items.

## Which version it follows

The backlog follows the version issued to the client last (`output/spec-v<version>.yaml`), because the team
builds what was signed. With nothing issued yet it follows the current spec, and says so.

## How the draft is made

| Part | From |
|---|---|
| Epics | One per requirement group |
| User stories | One per requirement item, with a first guess at the role and the wording. Claude then writes each as the user would say it: "As an Employee, I want to cancel my application before the leave starts, so that …" |
| Acceptance criteria | From the screens: the status moves each button makes, required fields, field rules, dialogs that need a reason, messages and notifications. Each is placed on the story it reads most like; Claude places the rest and adds what the requirement implies |
| Screens | The screens the story's criteria come from, and the screens of its requirement group |
| Estimate lines | The estimate's lines whose name matches the epic. Claude links the rest |

Claude then refines it: role, "want" and "so that" in plain words, short titles, criteria a tester can
check, stories split or merged, technical work as Tasks, and every requirement in a story or excluded with
a reason.

## Story points

Story points come from the estimate, never from a guess:

1. Each story names the estimate lines it delivers. A line shared by several stories is split evenly
   between them, unless a story takes a given share of it.
2. The story's mandays are its share of those lines, at the rates in the knowledge base.
3. The middle of that range becomes points with the **story-point scale** in
   `knowledge/building-blocks.md`: a story gets the smallest number of points whose "Mandays up to" covers
   it. A story above the last row is too big and should be split.

The scale is the lead developer's to set, once, for the team:

| Points | Mandays up to |
|---|---|
| 1 | TBD |
| 2 | TBD |
| 3 | TBD |
| 5 | TBD |
| 8 | TBD |
| 13 | TBD |

New workspaces have this table in their knowledge base. An existing workspace can get it with
`python -I tools/backlog.py scale`, which prints the table to add. Until the scale is set, or while a line a
story delivers has no rate, or when there is no estimate, the story has no points and the Points sheet says
why.

## Importing into the team's tool

- **Project Desk:** open the project, then Schedule, Import / export, Import from file, and choose the
  Project Desk import file. Check the preview and import. Epics and stories keep their nesting.
- **Jira:** use the CSV import (as a Jira administrator: Settings, System, External system import, CSV; or
  the project's own import). Map Issue ID, Parent, Issue Type, Summary, Description and Priority to the
  fields of the same name, and Story Points to your story points field ("Story point estimate" in
  team-managed projects). Each story's acceptance criteria are in its description.
- **Azure DevOps:** Boards, Queries, Import work items, then choose the Azure DevOps file. It is made for
  the Agile process (Feature, User Story, Story Points, acceptance criteria in the description). For a team
  on the Scrum process, ask for it again for Scrum: Product Backlog Item, Effort and the Acceptance Criteria
  field.

Every item's description ends with its story id in Blueprint, so it can be traced back.

## The backlog file

The format is at the top of `tools/backlog.py` (`python -I tools/backlog.py --help`). In short: `epics`
(`id`, `title`, `group`, `description`), `stories` (`id`, `epic`, `type` Story or Task, `title`, `role`,
`want`, `so_that`, `acceptance`, `requirements`, `screens`, `priority`, `lines`, `register`, `notes`) and
`excluded` (`requirement`, `reason`).
