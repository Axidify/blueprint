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
- **CRs:** each CR, what it changed, mandays billed, and effort actually spent if known.
- **What was deferred** to a later phase, and why.
- **Where the time went:** the lead dev's view of which parts overran and why.

## 2. Write `knowledge/actuals/<slug>.md`

(Start from `templates/project/actuals.md`. It lives in `knowledge/` so it is shared through git; keep
it to effort, CRs and lessons, never client document content.)

Sections: effort table (sold, CRs billed, actual, variance and its value at the day rate), timeline, CRs
(each with its gap pattern), what the SRS already showed (if the SRS is in `docs/`, check whether the
overruns were visible in it), lessons. Keep it factual; no blame.

## 3. Update the knowledge base

1. **`knowledge/projects-log.md`:** add or update the row for this project and phase.
2. **`knowledge/gap-patterns.md`:** map every CR to a pattern. Add the CR as *Cost* evidence on the
   pattern. If no pattern fits, create a new one with the workshop questions that would have caught it.
   Describe the gap in general terms, without client content.
3. **`knowledge/building-blocks.md`:** add this project's building-block counts. Only change a rate when
   effort per block is actually known; record the evidence and adjust the confidence. If only the total is
   known, add a calibration note instead of inventing per-block rates.

## 4. Archive the project

Once the knowledge base is updated, offer to archive the project so it leaves the active list:
`python -I tools/project.py archive <slug>` (restore it any time with `restore`). Its files stay in
`projects/_archive/<slug>/`.

## 5. Report

Summarise to the user: variance and its cost, which gap patterns the CRs fell into, what changed in the
knowledge base, and what data to capture better next time.
