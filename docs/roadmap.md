# Roadmap

**Status: draft for agreement.** Nothing below is promised or scheduled yet. This page sets out where
Blueprint could go next, so it is agreed before it is built.

Blueprint started with one job: close requirement gaps before sign-off, so they don't come back as change
requests. It now covers most of a project, from the brief to close-out. The next step is to cover the
documents a project still writes by hand, without losing that original job.

## Principles for anything new

1. **Generated, not written.** A new document is built from what the project already holds: the spec,
   the register, the estimate, the UAT scripts and the CR log. To fix one, change the source, never the
   Word file. That keeps every document in step with the requirements.
2. **Every document looks for gaps.** Writing a user manual or a backlog shows steps, fields and rules that
   nobody decided. Each new document reports these as register items, the same way a review does.
3. **Client and internal stay apart.** Mandays, rates and internal notes never appear in a client
   document, whatever document it is.
4. **One look.** Every Word output uses the company's branding and document format, as the requirements
   document does. Every web page uses the same design language as Blueprint's own pages: calm true greys,
   one accent colour, a status shown as a dot and a word, sentence case.
5. **More documents, not more to learn.** The start menu and the project overview show what fits the
   project's current stage. Nobody should have to know the whole list of skills.
6. **Feed other tools, don't replace them.** Blueprint exports to the tools teams already use (Excel,
   Jira, Azure DevOps, Project Desk, MS Project). It doesn't become a project planner, timesheet or bug tracker.

## The lifecycle at a glance

| Stage | Today | Planned |
|---|---|---|
| Brief and SOW | Manday estimate in ranges, checked against the SOW | Proposal / SOW document (phase 2) |
| Requirements | Review, register, workshops, mock-up, client answers, platform fit, requirements document | — |
| Design | Integrations and data in the requirements document | Data dictionary (phase 1), technical design document (phase 3) |
| Development | Development backlog with traceability, for Excel, Jira, Azure DevOps and Project Desk; change requests | — |
| Testing | UAT scripts, workbook and results | — |
| Go-live | — | Release notes (phase 2), deployment and cutover plan, go-live checklist (phase 3) |
| Handover | — | User manual from the built system (phase 1, after development), quick-reference cards (phase 2), admin guide, support handover (phase 3) |
| Running the project | Register, project overview | Meeting minutes, status report (phase 2) |
| Close-out | Actuals, lessons learned, knowledge base | — |

## Phase 1: built from what is already there

The backlog and the data dictionary come from the spec and the register alone, so they can be built as
soon as the requirements are signed. The user manual uses the same spec but waits for the built system.
In order:

### 1. Development backlog with traceability

**Built:** the `backlog` skill. See [Development backlog](backlog.md).

- **For:** the development team (internal); the traceability sheet can also go to the client.
- **Built from:** requirement groups and items, screens, status rules and register decisions.
- **Contents:** each requirement group becomes an epic and each item a user story ("As a [role], I want
  …, so that …"), with numbered acceptance criteria drawn from the status rules and field checks. A
  traceability sheet links each requirement to its screens, UAT scenarios and change requests.
- **Outputs, all from the same backlog:**
  - an Excel workbook for reading and review;
  - a Jira import file;
  - an Azure DevOps import file;
  - a Project Desk import workbook in its task-import layout (Type Epic, Story or Task, nested under
    their parent, numbered acceptance criteria).
- **Story points:** each story carries story points worked out from the estimate's building blocks,
  with the lead developer's scale (see Decided). The traceability sheet that goes to the client never
  shows them.
- **Finds gaps:** a requirement with no role or screen, a screen no requirement covers, acceptance
  criteria that cannot be tested.
- **Why first:** handing over to the developers is where requirements are most often read differently.
  Traceability also makes the change-request check and UAT coverage easier to show.

### 2. Data dictionary

- **For:** the development team and the client's IT team.
- **Built from:** the fields of every form and list, their types and rules, the sample data and the
  integrations.
- **Format:** an Excel sheet, and optionally an appendix to the requirements document.
- **Finds gaps:** a field without a type, length or rule, a field shown but never captured, data an
  integration sends that no screen holds.

### 3. User manual, once development is complete

- **For:** the client's users, one chapter per role.
- **When:** after development, so the manual shows the real system and not the mock-up.
- **Built from:** the signed spec for the structure (roles, tasks, statuses, status moves, notifications)
  and screenshots Blueprint takes of the built system in its test environment, signed in as each role.
- **Contents:** how to do each task step by step, as that role ("Submit a request", "Approve a request"),
  what each status means, and what the user is notified about.
- **Outputs:** a Word document in the company's format, and a web page users can open from the
  system's help link, searchable, with a chapter per role and the same look as Blueprint's pages.
- **Finds differences:** where the built system does not match the signed spec, the manual does not
  quietly describe what was built. Each difference goes to the register for the team to decide: a
  defect to fix, or a change to record (through `change-request`).

## Phase 2: the rest of the project's paperwork

These need a small amount of new input, such as a meeting's notes or the period a report covers.

| Document | For | Built from | New input |
|---|---|---|---|
| Proposal / SOW document | Client | Estimate, scope, assumptions, timeline | The company's proposal wording, kept in `branding/` |
| Meeting minutes | Client | Workshop agenda, notes or transcript, register changes | The notes or transcript |
| Status report | Client, or internal with figures | Register, CR log, UAT results, timeline | The reporting period |
| Release notes | Client | CR log, spec version history | Which CRs are in the release |
| Quick-reference cards | Client's users | The user manual | — |

Meeting minutes are close to the existing `apply-feedback` step: the decisions and actions they record
go into the register at the same time.

## Phase 3: needs new information in the spec

These describe how the system is built and run, which the spec does not hold today. Each needs new spec
sections, and the lead developer decides what goes in them.

| Document | For | What the spec would need |
|---|---|---|
| Technical design document | Development team, client IT | Architecture, components, environments, data model, how each integration is built |
| Deployment and cutover plan | Development team, client IT | Environments, deployment steps, data migration, rollback |
| Go-live checklist | Project lead, client | Go-live criteria, who signs off each one |
| Admin guide | Client's administrators | Settings, user and role setup, routine tasks |
| Support handover | Support team | Known issues, contacts, escalation, service levels |

## Also planned

- A Figma connection.

## Decided

Agreed on 7 November 2026:

1. **Order:** the backlog first, then the data dictionary. The user manual waits until development is
   complete, so it shows the actual system.
2. **Backlog outputs:** Excel, Jira, Azure DevOps and Project Desk.
3. **User manual:** both a Word document and a web page.
4. **Look:** there are no company samples to copy. New documents follow the design language of the
   existing ones: the requirements document's format for Word, Blueprint's pages for the web.
5. **Screenshots for the user manual** are taken by Blueprint from the system's test environment, signed
   in with a test account for each role. Never from the live system. The link and the test accounts are
   kept in the project's own settings on this machine, never in the app or the shared knowledge base.
6. **Sizes in the backlog** are story points (1, 2, 3, 5, 8, 13), worked out from the estimate's
   building blocks with a scale the lead developer sets in the knowledge base. Without that scale the
   points are left blank, never guessed. The traceability sheet for the client never shows them.
