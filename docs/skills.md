# Skills

A skill is a task Blueprint knows how to do. You don't need the names: say what you want and Claude Code
picks the skill. You can also type `/` followed by the name, for example `/review-requirements`.

Each skill's full instructions are in `.claude/skills/<name>/SKILL.md`.

**Every skill ends the same way.** When it is done, Blueprint tells you, in plain words: what it made or
changed; where it is (the project's `Project overview.html`, at the top of the project folder, lists every
document); who each output is for, the client or internal; and the next step, as the words to say, for
example "prepare the workshop". How to write a skill: [Maintaining](maintaining.md#writing-a-skill).

### start

**Ask:** `/start`, "help", "what can you do?"
Checks your machine, shows each project with its next step, and offers a menu of the common tasks. It
also points you to each project's overview page (`Project overview.html` at the top of the project folder),
which shows every document, who it is for and the next step to anyone browsing the shared folder.

### tour

**Ask:** "give me a tour", "show me how it works", "I'm new", "try it"
A guided first run of about ten minutes on a copy of the made-up sample project, in six short steps: what
Blueprint is for, a quick review of a one-page draft with gaps planted in it (findings into the Excel
register), the clickable mock-up (View as, acting out an approval, Feedback), a comment turned into a live
change, and the requirements document generated from the same spec. Say "next", "skip" or "stop" at any
step. The copy lives in `.tour/` in the app folder, is never one of your projects and never touches the
workspace or client documents; it is removed at the end. It ends with how to start for real: the inbox or
a new project.
**Output:** nothing that stays, unless you ask to keep the copy for exploring.

### new-project

**Ask:** "start a new project for …", "add a project"
Works out the system name, client, short name and platform from the brief or document you give it and
asks you to confirm them, asking only for what it cannot find, in one question (the mock-up look follows
the platform: `desk`, or `joget` on Joget). Then it creates the project folder and files the documents you
already have. First it looks for earlier work on the same system (an active or archived
project, or one delivered before) and offers to carry on with it, start a new phase linked to it, or start
fresh; a system delivered before brings its change requests and actual effort as context.
**Output:** `projects/<name>/` with an empty register.

### process-inbox

**Ask:** "process my inbox", "I dropped a file in"
Works out which project each file in `inbox/` belongs to and what it is (requirements document, mock-up
feedback, the client's answers, workshop notes, brief, project actuals), shows you a plan, then files each one and runs the
right next step. A document for a system that was archived or delivered before is matched to that work
rather than treated as new. It never files on a guess: a file it isn't sure of is asked about, with its best
guesses and why, or left in the inbox with a note, and the start-up summary says it is waiting.

### review-requirements

**Ask:** "review this requirements document", "find the gaps in this document", "what should we ask the client?"
Reads the whole document including its diagrams and mock-ups, checks consistency, completeness, workflow
edge cases, data and KPI definitions, integrations, open items, scope against the SOW and document hygiene,
and every gap pattern in the knowledge base. Every finding cites its location.
A document the client already signed is reviewed too: its findings become possible change requests for
change control. A scope-of-work or manday appendix inside the document is used as the SOW. For a document
Blueprint generated, fixes go into the spec and most findings are internal.
**Output:** findings in the [register](register.md), `register.xlsx` for the BA, and a review report in
`projects/<name>/reviews/<review>/review.md` with the verdict, top risks and the screens to walk through
with users, also as a Word file beside it (`<document> review.docx`, marked internal on every page); and
the next step (usually preparing the workshop or building the mock-up).

### build-mockup

**Ask:** "build a mock-up from the brief", "add a screen for …", "prepare for workshop 2"
Writes or extends the project spec (roles, statuses, screens, fields, sample data, requirements) and
builds the clickable mock-up. Undecided points become register questions instead of guesses. Whatever the
spec cannot describe is built in the project's own mock-up code rather than left out, and what is custom
work on the platform is tagged "Custom development" while presenting. New mock-ups get the calm `desk` look
in the project's colour (`joget` on a Joget platform); existing ones keep theirs.
**Output:** `projects/<name>/mockup/` (open with `present.cmd`), screenshots, register questions.

### present

**Ask:** "open the mock-up for …", "show me my mock-ups", "present the mock-up", "run a live session for …"
Starts the mock-up and gives you its address: one project, or the page that lists every mock-up. When
only you are looking, it can open in this app's browser pane and you say here what should change. In a
**live session** the comments typed in the mock-up collect while you present; say "go" and Claude shows
you one list of proposed changes, makes the ones you approve and every open mock-up offers **Update
ready**. Anything can be changed, and proposals that add behaviour or go beyond the scope of work are
marked for you to decide. "Undo that" puts the mock-up back and its comments wait again; anything
added to the register for that change is put back with `register.py update`. What is submitted or approved
in the mock-up stays for the session and shows on every laptop in the room; **Reset sample data** starts
again.
**Output:** the open mock-up; after a live session, a new mock-up version with its change note.

### platform-fit

**Ask:** "what can Joget do here?", "check the platform", "the project will use Joget DX and SQL Server"
Checks a project against what its tech stack actually does. Each product is looked up in its own
documentation online (with product and feature words only, never client details), what is found is kept
in the knowledge base's platform sheets after you agree, and the project's spec and register record which
features are custom work or not supported, with the page that says so. Runs on its own when a project's
tech stack is given, after a mock-up is built, in a review and before an estimate.
**Output:** `platform_fit` in the spec (internal), internal register items for custom work, and checked
rows in `knowledge/platforms/`.

### prep-workshop

**Ask:** "prepare the workshop", "get ready for the mock-up review", "what should we ask the client next?"
Builds the agenda for a client session from what is still open: the register's client questions, what the
spec does not say yet and the gap patterns that apply, with those that already cost mandays first. It asks
you the date, the length and who attends, groups the questions the way the client thinks, fits them to the
time and says what it left for later and why.
**Output:** in `projects/<name>/workshops/`: the agenda for the client and the facilitator notes for the
BA (internal), both Word documents.

### client-answers

**Ask:** "the client answered", "here are the client's answers", "they replied to the questions", or drop
the returned register or an answers e-mail into the inbox
Takes the client's answers into the project: from the register Excel file they sent back (what they typed
in **Client response**, or a status they changed, is read from the returned copy), or from an e-mail, call
notes or text you paste. Each answer is matched to its register item (it asks when it is not sure which),
recorded as the client gave it, and acted on: a change to the spec, a decision, a follow-up question, or a
possible change request (flagged, internal, not built until you agree; with `change-request` once a version
was signed). It then says whether the requirements document needs generating again and whether the lead
developer should revisit the estimate.
**Output:** the register (answers on the **For client** sheet), the spec and mock-up where an answer
changed them, and the client's file filed in the project's `docs/`.

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
and team-only text anywhere the client will read it (the mock-up, "proposed", register and feedback ids,
requirement ids of another document), lists the parts still missing before issuing (NFRs, timeline, scope,
signatories), then reviews the document with `review-requirements`.
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
from); it opens on a one-page Overview, and while rates are missing its Rates needed sheet is a form for
the lead developer. Afterwards it offers to save the lead developer's rates in the knowledge base (also
from a returned Rates needed sheet: "save these rates") and to add the questions to the register.

### close-project

**Ask:** "close the project", "here are the actuals and the CR list"
Records estimate vs actual effort and each CR, maps every CR to a gap pattern, and proposes updates to
the knowledge base: it shows you every change (actuals, projects log, gap patterns, rates) and writes only
what you agree to, because the knowledge base is shared by everyone using the workspace.
**Output:** `knowledge/actuals/<name>.md`, a row in `knowledge/projects-log.md`, gap-pattern and
building-block updates, each after you agree. Afterwards it offers to archive the project (`projects/_archive/`).

### change-request

**Ask:** "the client asked for …", "is this in scope?", "is this a CR?", "price this change request", or drop
in a CR list or UAT defect list
Checks each request against the version the client signed and decides, quoting the signed text with its
section: **In scope** (a short internal note, no charge), **Ambiguous** (the document is silent or the point
was left open: a client question goes into the register) or **New** (a change request). A new CR is sized in
the knowledge base's building blocks with the estimate's rules (ranges, never an invented rate) for the
team, mapped to a gap pattern so `close-project` can learn from it, and written up for the client. See
[Change requests](change-requests.md).
**Output:** `projects/<name>/changes/crs.json` and `CR log (internal).xlsx` (internal), and for a new CR
`CR-001 <title> - change request note.docx` for the client: what was asked, why it is a change, what it
would change, the timeline impact in weeks, and the price once the project lead has set it ("Quotation to
follow" until then).

### backlog

**Ask:** "write the backlog", "user stories for the developers", "import the requirements into Project
Desk / Jira / Azure DevOps", "traceability matrix"
Turns what the client signed (the version issued last, or the current spec, and it says which) into the
development backlog: an epic for each requirement group and a user story for each requirement, written as
the user would say it, with acceptance criteria from the screens and status rules, and story points worked
out from the estimate with the lead developer's story-point scale (never guessed: a story without them says
why). Technical work becomes Tasks. Gaps found while writing (estimated work no requirement asks for, a
screen no requirement covers, a story waiting on an open client question) go into the register. See
[Development backlog](backlog.md).
**Output:** in `projects/<name>/backlog/`: the backlog workbook for the team (internal), a traceability
sheet for the client (each requirement with its screens, stories, UAT scenarios and change requests, never
points), and import files for Project Desk, Jira and Azure DevOps; and the `.json` they are made from.

### uat-scripts

**Ask:** "prepare the UAT scripts", "write the test scenarios", "test cases for UAT", "get ready for UAT"
Writes the user acceptance test scripts from what the client signed (the version issued last, or the
current spec when nothing is issued yet, and it says which): the main process signed in as each role in
turn, every other status move such as reject and cancel, what each role may not do in each status, the
field checks of every form and dialog, the screens each role may not open, the dashboard figures, and the
notifications and integrations. It then adds the edge cases from the gap patterns that apply, merges and
removes what overlaps, and checks that every requirement is covered or excluded with a reason. See
[UAT scripts](uat.md).
**Output:** in `projects/<name>/uat/`: a workbook for the client's testers (one row per step, with Actual
result, Pass/Fail, Tester, Date and Defect ref) and the test scripts as a Word document in your company's
format, both for the client; and the `.json` they are made from. After UAT, drop the filled-in workbook into
the inbox: failed steps are listed, and those that are really new wishes go to `change-request`.

### release

**Ask:** "release a new version of Blueprint"
For maintainers: checks the docs, moves the changelog's Unreleased entries into a new version, updates
`VERSION`, and commits and tags it. Asks before pushing or publishing a GitHub release.
See [Maintaining](maintaining.md).

## Planned

A Figma connection. For the documents that could come next across the project lifecycle, see the
[Roadmap](roadmap.md).
