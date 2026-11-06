# Workflow

Blueprint follows a typical delivery process. Gaps missed during requirements come back as change
requests (CRs) during development, usually underpriced. Each stage below has a Blueprint step that
catches gaps earlier.

| Stage | What happens | What to ask Blueprint | You get |
|---|---|---|---|
| 1. Brief → SOW | The lead dev scopes the work and estimates mandays | "Start a new project", then share the brief; "estimate this project" | A project folder; the gap patterns worth raising in workshop 1; a first manday range with the questions to ask before pricing |
| 2. Workshop 1 | The BA gathers requirements | "Prepare the workshop" beforehand; afterwards "build a mock-up from the brief / these notes" | A clickable mock-up and open questions in the register |
| 3. Mock-up review (workshop 2) | The client walks through the mock-up | "Prepare the workshop" for the agenda; present with `present.cmd` (or "run a live session" to have comments acted on in the room), then "apply the feedback" | A new mock-up version; decisions, questions and possible CRs in the register |
| 3a. The client answers | The client replies to the open questions: in the register they were sent, by e-mail or in a call | Drop the returned register or the e-mail into the inbox, or say "the client answered" | Each answer on its register item, the spec changed where an answer changes behaviour, follow-up questions and possible CRs flagged, and whether the requirements document or the estimate needs doing again |
| 3b. Before sign-off | The lead dev sizes what the requirements became | "Estimate this project" | A narrower range from the spec, compared line by line with the scope of work while scope that grew can still be raised, and the weeks for the timeline |
| 4. Sign-off | The requirements document goes to the client | "Generate the requirements document" | Word and PDF in the company's layout, with screenshots, an access matrix built from the screens, and an Open Issues section from the register |
| 4a. Any requirements document | Drafts from anyone, including the client | "Review this requirements document" | A review report (also as a Word file) and the Excel register for the BA |
| 4b. Handover to the developers | The team plans the build from what was signed | "Write the backlog" | Epics and user stories with acceptance criteria and story points from the estimate, a traceability sheet for the client, import files for Project Desk, Jira and Azure DevOps, and the gaps the stories show in the register |
| 5. Delivery | Development, UAT, CRs, go-live | "Close the project" with actual effort and the CR list | Estimate vs actual, CRs mapped to gap patterns, a stronger knowledge base |

**Not sure what comes next?** Blueprint works out each project's stage from what is in its folder and
says the next step when a session starts (and in the `/start` menu), in the words to say: review the
documents or build a mock-up, prepare the workshop while important client questions are open, apply the
feedback, generate the requirements document, review it, record it as issued, and close the project after
delivery. It also tells the lead developer when the spec changed since the last estimate.

**Looking in the shared folder?** Every project folder has `Project overview.html` at its top: the same
next step, the open client questions and internal fixes, and every document in the order of the stages
above, each saying who it is for (from the client, for the client, internal). Blueprint keeps it up to
date as its tools write into the project. A project with a mock-up also has **Open the mock-up** beside
it, which starts the mock-up so the comments typed in it are saved.

A document for a system you built before (an archived project, or one delivered and closed) is matched to
that work, so its change requests and actual effort inform the new phase.

**Files in the inbox are never filed on a guess.** Blueprint checks each file against every project
(a comments export made on a project's mock-up, register and requirement ids with their topic, the
project's roles and screens, the people in it) and files it only when one project clearly stands out and
you have said go ahead. One client often has several projects, so the client's name alone is not enough:
for any other file you are asked which project it is for, with the best guesses and why. A file you leave,
or don't answer about, stays in the inbox with a note of why, and the start-up summary says it is waiting.

## How the pieces connect

- **One spec per project** (`projects/<name>/spec/app.yaml`) drives both the mock-up and the requirements document, so the
  screenshots, field tables, statuses and access matrix cannot contradict each other. Change things in
  the spec, never in the generated Word file. See [Spec format](spec-format.md).
- **One register per project** collects every question, gap, assumption and decision from every stage, with
  its status. The BA takes the Excel version to the client; resolved items drop out of the Open Issues
  section automatically. See [The register](register.md).
- **Estimates** are counted from the brief, the scope of work or the spec in the knowledge base's building
  blocks, with the rates you set there, and are kept per project with their date, so you can see how the
  range moved. They are internal: no mandays go into the mock-up or the requirements document. The
  timeline chapter is drafted from the estimate, in weeks. See [Estimates](estimates.md).
- **The knowledge base** grows with every project: each CR becomes evidence for a gap pattern, and each
  gap pattern becomes a standard workshop question and review check. See [Knowledge base](knowledge.md).

## A typical cycle

```
brief ──► new project ──► mock-up v0.1 ──► workshop ──► apply feedback ──► mock-up v0.2 ──► ...
                                                                                 │
              review (any draft) ◄── generate v1.0 ◄─────────────────────────┘
                     │
                     └──► fix in spec ──► regenerate ──► client sign-off ──► delivery ──► close project
```
