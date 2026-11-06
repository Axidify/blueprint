# Skills

A skill is a task Blueprint knows how to do. You don't need the names: say what you want and Claude Code
picks the skill. You can also type `/` followed by the name, for example `/review-requirements`.

Each skill's full instructions are in `.claude/skills/<name>/SKILL.md`.

### start

**Ask:** `/start`, "help", "what can you do?"
Checks your machine, shows each project with its next step, and offers a menu of the common tasks.

### new-project

**Ask:** "start a new project for …", "add a project"
Asks for the system name, client, platform and mock-up look, creates the project folder and files any
documents you already have.
**Output:** `projects/<name>/` with an empty register.

### process-inbox

**Ask:** "process my inbox", "I dropped a file in"
Works out which project each file in `inbox/` belongs to and what it is (requirements document, mock-up
feedback, workshop notes, brief, project actuals), shows you a plan, then files each one and runs the
right next step.

### review-requirements

**Ask:** "review this requirements document", "find the gaps in this document", "what should we ask the client?"
Reads the whole document including its diagrams and mock-ups, checks consistency, completeness, workflow
edge cases, data and KPI definitions, integrations, open items, scope against the SOW and document hygiene,
and every gap pattern in the knowledge base. Every finding cites its location.
**Output:** findings in the [register](register.md), `register.xlsx` for the BA, and a review report in
`projects/<name>/reviews/<review>/review.md` with the verdict, top risks and the screens to walk through
with users.

### build-mockup

**Ask:** "build a mock-up from the brief", "add a screen for …", "prepare for workshop 2"
Writes or extends the project spec (roles, statuses, screens, fields, sample data, requirements) and
builds the clickable mock-up. Undecided points become register questions instead of guesses.
**Output:** `projects/<name>/mockup/` (open with `present.cmd`), screenshots, register questions.

### apply-feedback

**Ask:** "apply the feedback", "here are the notes from today's session"
Turns comments left in the mock-up, BA notes or a meeting transcript into spec changes, decisions,
questions and possible change requests (flagged, not built, until you agree), then releases a new
mock-up version.
**Output:** updated spec and mock-up, register items, `reviews/mockup-v<version>-changes.md`.

### generate-requirements

**Ask:** "generate the requirements document", "issue version 1.0"
Builds the requirements document from the spec and fresh screenshots in your company's format: cover, document at a
glance (counts, how to review it, sign-off status, version history), users and access, requirements by
role, functional requirements linked to screens, every screen with its fields, NFRs, the project timeline (drafted from the project's
estimate, in weeks), decisions needed before sign-off, a sign-off block per signatory, and appendices. It warns about stale cross-references
and mock-up remarks in requirements, then reviews the document with `review-requirements`.
See [Document format](document-format.md).
**Output:** `projects/<name>/output/<System> – System Requirement Specifications v<version>.docx`, a PDF
when Word is installed, and a snapshot of the spec used.
When the document goes to the client, say "issue v1.3 to the client": the version is recorded and
locked, so later changes become a new version.

### document-format

**Ask:** "make our table headers navy", "number sections 1.0, 2.0", "learn our format from this document"
Changes how generated requirements documents look and are structured, from a plain request or by reading a
company's existing requirements document, and shows a preview before any real requirements document is regenerated.
**Output:** `workspace/branding/document-format.yaml` (and optionally the Word template and logo), preview
pages in `examples/leave-request/output/preview/`. See [Document format](document-format.md).

### estimate

**Ask:** "estimate this project", "how many mandays is this?", "check the SOW's mandays"
Counts the project in the knowledge base's building blocks, from the firmest thing that exists (a brief or
scope of work early on, the project spec later), and applies your rates for the project's platform and
your shares for other work (project management, testing …). It never makes up a figure: where the
knowledge base has no rate it asks the lead developer, and a line nobody has a figure for is counted and
shown as not priced. Every figure is a range, with the assumptions and a confidence level, and what makes
it uncertain: open high-severity questions, gap patterns that apply, lines not priced and how few delivered
projects the rates rest on. When there is a scope of work, it compares the sold mandays line by line and
puts the largest differences first. It ends with the workshop questions that would narrow the range most.
The estimate is internal and never goes into a client document; the project timeline is drafted from it,
in weeks. See [Estimates](estimates.md).
**Output:** `projects/<name>/estimates/<date> estimate from <basis>.xlsx` (and the `.json` it is rendered
from). Afterwards it offers to save the lead developer's rates in the knowledge base and to add the
questions to the register.

### close-project

**Ask:** "close the project", "here are the actuals and the CR list"
Records estimate vs actual effort and each CR, maps every CR to a gap pattern, and proposes updates to
the knowledge base.
**Output:** `knowledge/actuals/<name>.md`, a row in `knowledge/projects-log.md`, proposed gap-pattern and
building-block updates. Afterwards it offers to archive the project (`projects/_archive/`).

### release

**Ask:** "release a new version of Blueprint"
For maintainers: checks the docs, moves the changelog's Unreleased entries into a new version, updates
`VERSION`, and commits and tags it. Asks before pushing or publishing a GitHub release.
See [Maintaining](maintaining.md).

## Planned

`prep-workshop` (question bank per module),
`price-cr` (price a change request from building blocks), a Figma connection.
