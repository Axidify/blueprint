---
name: generate-requirements
description: Generate the requirements document (Word and PDF) for a project from its spec and mock-up screenshots, in the company's format and under its own document title (SRS, functional specification …), then review it before it goes to the client. Use when the user asks to create, produce, update or issue the requirements document, SRS or specification for a project that has a spec and mock-up.
---

# Generate the requirements document

The document is built from the project's spec (`_blueprint/spec/app.yaml`) and the mock-up screenshots, in the company's
document format (`docs/document-format.md`; change it with `document-format`), Word template and standard
wording (`workspace/branding/`, else the neutral ones in `templates/`). Access matrix, statuses, field
tables and screenshots all come from the spec, so they cannot contradict each other. What the generator
reads, writes and warns about: `python -I tools/generate_requirements.py --help`; the spec's parts:
`docs/spec-format.md`.

**Rules.** Fix the document in the spec and generate again, never by hand in the Word file (hand edits are
lost). Never invent an exclusion, a priority, a signatory or an answer. Never copy rates, cost or the
estimate's mandays into the spec: the only mandays in the document are the scope of work's, on the timeline's
activities. An issued version is locked.

## 1. Make sure the spec is ready

- Every screen has a `description`; every form field that matters has `length`, `source` and `validation`.
  Requirements cover every screen and workflow step, and requirement groups list their `screens`. Set
  `priority` only where the client agreed it.
- `nfr` and `integrations` are filled in (missing NFRs: GP-12). Every integration has `trigger`, `data` and
  `on_failure`; every typed-in dashboard `value` has a `formula`. Where the client has not decided, leave it
  out and add a register question: the document shows "To be confirmed".
- Every status has its rules (`edit`, `cancel`, `delete`, `next`) or a register question.
- `scope` (`in_scope`, `out_of_scope`, `assumptions`) from the scope of work and the workshops, with what the
  client might assume is included under `out_of_scope`. If missing, draft it and show the user first.
- `sow`: the scope of work's items, each named by the requirement groups that specify it (`sow:` on the
  group), so the document's scope chapter shows where each item is specified. An item no requirement covers
  holds the version back at sign-off: write its requirements, or, once the client agrees to leave it out of
  this version, mark it `deferred` with what was agreed. A group that names no item may be a change request.
- `timeline`: if missing, offer to draft it: one activity per SOW item (`ref`), client activities
  (`client: true`), milestones (kick-off, sign-off, development complete, UAT sign-off, go-live, end of
  warranty) with what the client must do. Durations come from the latest estimate (`estimate.py weeks`;
  run the `estimate` skill first if there is none or it is older than the spec), not the SOW's mandays,
  unless the user asks, and then say the timeline rests on sold figures. Ask the lead developer the team
  size and state it in `assumptions`; weeks of effort are not the calendar (add review turnaround, client
  activities, waiting). Put each SOW item's mandays on its activity (`mandays`), copied from the scope of
  work in `1 Client documents` and re-added (the document shows their total); never the estimate's figures,
  rates or cost. An item the SOW gives no mandays has none. Show the draft before generating.
- Open client questions in the register become **Open Issues**; answered ones are listed under **Decisions
  made**: check each answer reads as the client gave it and `resolved_in` says where it was agreed.
- `project` has the right version, dates, `status` and `history`; `signoff` lists everyone who signs
  (client first; ask if missing). Cross-references use `{ref:...}`, never literal section numbers (a spec
  rebuilt from an older document is full of stale "section N.N" and mock-up remarks: fix them). Each TBC
  in a requirement is linked to its item with `tbc: R-xxx`.

## 2. Generate

1. `python -I tools/mockup.py screenshots projects/<slug>`, always, so the pictures match the spec (no spec
   yet: build a mock-up first).
2. `python -I tools/generate_requirements.py projects/<slug>`. It stops with a list of mistakes in the spec or
   the format: fix them there and run it again. It writes the `.docx` to `5 Requirements document`, a PDF when Word is
   installed, and a spec snapshot (in `_blueprint/output/`).
3. Read every warning and note; **do not issue a version with warnings.**
   - Screenshots older than the screens, or missing: take them again and generate again.
   - Team-only text (the mock-up, "proposed", `FB-` ids, register ids not under Decisions needed,
     requirement ids of another document): fix it where the warning says. `resolved_in` names the version or
     meeting ("Workshop 2, 12 November"), never a comment id.
   - Two figures with one caption: give the extra one a `caption`. A screen no requirement refers to: a
     requirement or a `screens` link is missing. A register `source` naming requirement ids not in this
     spec: put `tbc: R-xxx` on the requirement each is about.
   - MISSING parts (NFRs, timeline, scope, signatories): a workshop draft may go without them, a version for
     sign-off may not: draft them as in step 1 and show the user.
4. "Word step FAILED": no PDF; tell the user the reason it gives (usually the file is open) and generate
   again. "Word not available" only means the PDF and table of contents are missing. Pictures in the PDF
   not at full size: it says why; the PDF is still usable.

If the spec's version was already issued, the generator refuses: bump `project.version`, add a `history`
entry and generate again. Never unlock an issued version: the client has that file.

## 3. Review before it goes out

Run `review-requirements` on the generated document, focused on what generation cannot guarantee: workflow
edge cases, undefined KPIs, integration scope, NFRs and open items. Fix findings in the spec and generate
again. Something the generator does not produce (a process-flow diagram) goes in as a spec file
(`_blueprint/spec/process-flow.png`) or as a change to the generator.

## 4. Issue it

Before a version goes for signature, run `python -I tools/project.py ready <slug>` and work through what it
says: a question still blocking sign-off, a settled item with no agreed decision, a document older than the
spec, then the points to look at (answered items still open, duplicate questions, choices that differ from the
client's answer, "the agreed …" with nothing tracking it, a missing signatory). Fix them in the spec and the
register, generate again, and run it again until nothing stops it.

When the user says the document has gone (or is going) to the client:
`python -I tools/project.py issue <slug> --to "<recipient>"`. It runs the same check and issues nothing while something stops it; if the client really signs it as it is,
`--anyway "<why>"` issues it and keeps the reason. The version is locked; later changes need a new version.

## Hand over

- **What was made:** the version, how many open issues it carries, the warnings left (none, for a version
  going out) and the review's verdict.
- **Where and for whom:** the Word file and PDF in the project's `output` folder, **for the client** once the
  review is clear; the review and register's internal sheets stay **internal**. `Project overview.html`
  shows both files and whether the version was issued.
- **Next step, in the words to say:** with open client questions, "prepare the workshop" (or the sign-off
  meeting); when it goes to the client, "issue v<version> to the client". When it comes back signed or with
  answers: "the client answered".
