---
name: close-project
description: Record what a delivered project actually cost — effort, change requests and lessons — and feed it back into the knowledge base (gap patterns, building-block rates, projects log). Use when the user shares project tracker data, actual mandays, a CR list or a post-mortem for a project or phase.
---

# Close a project or phase

The knowledge base only gets better when actuals are recorded honestly. This is the feedback loop.

## 1. Gather the facts

Ask the user for anything missing. Do not guess numbers.

- **Estimate:** mandays sold per SOW line, especially development.
- **Actual effort:** people × time. Task durations from a tracker are *not* effort: check how many people
  worked, and what share of their time. Watch for parallel tasks that double-count (several tasks with the
  same dates).
- **CRs:** each CR, what it changed, mandays billed, and effort actually spent if known. If
  `projects/<slug>/changes/crs.json` exists, read it first: each CR's verdict, gap pattern, sizing and sold
  mandays, and the requests found Ambiguous (gaps even when they were not billed).
- **What was deferred** to a later phase, and why.
- **Where the time went:** the lead dev's view of which parts overran and why.

## 2. Draft the actuals record

Draft `knowledge/actuals/<slug>.md` from `templates/project/actuals.md`. The knowledge base is part of the
workspace (often a shared OneDrive or SharePoint folder), shared with everyone who uses it; it is never in
git. Keep it to effort, CRs and lessons, never client document content.

Sections: effort table (sold, CRs billed, actual, variance and its value at the day rate), timeline, CRs
(each with its gap pattern), what the requirements document already showed (if the requirements document
is in `docs/`, check whether the overruns were visible in it), lessons. Keep it factual; no blame.

## 3. Propose the knowledge-base changes

Work out every change first, without writing anything to `knowledge/`:

1. **Actuals:** the record drafted in step 2.
2. **`knowledge/projects-log.md`:** the row to add or update for this project and phase.
3. **`knowledge/gap-patterns.md`:** each CR mapped to a pattern, added as *Cost* evidence. If no pattern
   fits, a new pattern with the workshop questions that would have caught it. Describe the gap in general
   terms, without client content.
4. **`knowledge/building-blocks.md`:** this project's building-block counts. Only propose a new rate when
   effort per block is actually known, with the evidence and the confidence; if only the total is known,
   propose a calibration note instead of per-block rates.

Show the user the proposal in plain words: one short block per file, with the lines to be added or changed
(a table row, a pattern's new evidence, a rate before and after). Say that the knowledge base is shared,
so these changes reach everyone using the workspace. Ask once (AskUserQuestion: "Apply all" / "Change
something" / "Not now").

## 4. Apply what was agreed

Write only what the user agreed to. If they changed something, show that part again before writing it.
Nothing is committed: the workspace is never part of git.

## 5. Archive the project

Once the knowledge base is updated, offer to archive the project so it leaves the active list:
`python -I tools/project.py archive <slug>` (restore it any time with `restore`). Its files stay in
`projects/_archive/<slug>/`. If an archived project with the same name exists (an earlier phase), the tool
refuses and moves nothing: rename this project's folder first (for example `<slug>-phase-2`).

## Hand over

- **What changed:** the variance and its cost, which gap patterns the CRs fell into, what changed in the
  knowledge base (and what was left out at the user's request), and what data to capture better next time.
- **Where and for whom:** the actuals record, the projects log, gap patterns and building blocks in
  `knowledge/`, all **internal** and shared by everyone using the workspace; the archived project in
  `projects/_archive/`.
- **Next step, in the words to say:** the next estimate on this platform uses these figures ("estimate this
  project" on a live project); a new phase of the same system starts with "start a new project", which finds
  this one and its actuals.
