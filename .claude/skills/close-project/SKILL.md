---
name: close-project
description: Record what a delivered project actually cost — effort, change requests and lessons — and feed it back into the knowledge base (gap patterns, building-block rates, projects log). Use when the user shares project tracker data, actual mandays, a CR list or a post-mortem for a project or phase.
---

# Close a project or phase

The knowledge base only gets better when actuals are recorded honestly. This is the feedback loop.

## 1. Gather the facts

Ask the user for anything missing. Do not guess numbers: a figure nobody gave stays "not given".

- **Estimate:** mandays sold per SOW line, especially development (from the project lead; the lead developer
  may not have them).
- **Actual effort:** people × time. Task durations from a tracker are *not* effort: check how many people
  worked, and what share of their time. Watch for parallel tasks that double-count (several tasks with the
  same dates).
- **CRs:** what the lead developer counts as change requests, with the effort each took. The project's own CR
  log (`_blueprint/changes/crs.json`) holds each logged CR's verdict, gap pattern and sold mandays, and the
  requests found Ambiguous (gaps even when they were not billed); the tool reads it.
- **What was deferred** to a later phase, and why.
- **Where the time went:** the lead dev's view of which parts overran and why.
- **Test data?** Figures from a rehearsal or a test run are marked `"test": true`.

Write them into `_blueprint/close/actuals.json` (the format is at the top of `tools/close.py`; read
`python -I tools/close.py --help` for the options). Keep it to effort, CRs and lessons, never client
document content.

## 2. Hold every CR against the signed version

`python -I tools/close.py check projects/<slug>`. A CR the log calls In scope, or one whose text reads
closely like a requirement, screen, rule or decision of the version the client signed, is flagged: it was
not a change request, and billing it or learning from it as a gap would be wrong. Read each cited text in
the signed document; for a "check against" match, decide and record `"verdict"` on that CR in the actuals
file. Tell the user which "CRs" were in the signed version.

## 3. Draft the close-out

`python -I tools/close.py draft projects/<slug>` writes, into `_blueprint/close/` and nowhere else:
`actuals draft.md` (the record for `knowledge/actuals/<slug>.md`: effort, variance, the CRs, the ones that
were in the signed version, deferred work, lessons) and `knowledge proposal.md` (the projects-log row,
gap-pattern evidence, building-block notes and the CR check). Read both. Add what only people know: the
timeline, and what the requirements document already showed (if it is in `1 Client documents`, check
whether the overruns were visible in it). Keep it factual; no blame.

Then work out the rest, still without writing to `knowledge/`:

1. **`knowledge/gap-patterns.md`:** each real CR as evidence of its pattern (*Cost* when it was billed or
   took effort, *Review* otherwise). If no pattern fits, a new pattern with the workshop questions that
   would have caught it. Describe the gap in general terms, without client content. Nothing from a CR that
   was in the signed version.
2. **`knowledge/building-blocks.md`:** only propose a new rate when effort per block is actually known, with
   the evidence and the confidence; if only the total is known, a calibration note instead. Never from
   test data.

Show the user the proposal in plain words: one short block per file, with the lines to be added or changed
(a table row, a pattern's new evidence, a rate before and after). Say that the knowledge base is shared,
so these changes reach everyone using the workspace, and say so plainly when the figures are test data
(the row is then marked TEST, so estimates never count it). Ask once (AskUserQuestion: "Apply all" /
"Change something" / "Not now").

## 4. Apply what was agreed

Write only what the user agreed to. If they changed something, change the draft and show that part again.
`python -I tools/close.py apply projects/<slug>` writes the actuals record and the projects-log row
(`--only actuals` or `--only log` for one of them; it keeps an existing record unless `--force`, which needs
the user's yes). Gap patterns and building blocks you edit by hand, exactly as agreed. Nothing is committed:
the workspace is never part of git.

## 5. Archive the project

Once the knowledge base is updated, offer to archive the project so it leaves the active list:
`python -I tools/project.py archive <slug>` (restore it any time with `restore`). Its files stay in
`projects/_archive/<slug>/`. If an archived project with the same name exists (an earlier phase), the tool
refuses and moves nothing: rename this project's folder first (for example `<slug>-phase-2`).

## Hand over

- **What changed:** the variance and its cost, which gap patterns the CRs fell into, which "CRs" were in the
  signed version (not billed, not learnt as gaps), whether the figures are test data, what changed in the
  knowledge base (and what was left out at the user's request), and what data to capture better next time.
- **Where and for whom:** the actuals record, the projects log, gap patterns and building blocks in
  `knowledge/`, all **internal** and shared by everyone using the workspace; the archived project in
  `projects/_archive/`.
- **Next step, in the words to say:** the next estimate on this platform uses these figures ("estimate this
  project" on a live project); a new phase of the same system starts with "start a new project", which finds
  this one and its actuals.
