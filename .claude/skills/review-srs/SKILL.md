---
name: review-srs
description: Review a requirements document (SRS, URS, FSD, or a draft of one) for contradictions, gaps, open items, scope drift against the SOW and document hygiene, then record every finding in the project register and render the Excel register for the BA. Use when the user drops in, names or pastes a requirements document and asks for a review, gaps, issues or questions for the client.
---

# Review a requirements document

The goal is a register the BA can take straight back to the client, plus a short internal report. Gaps
found here are cheap; the same gaps found in UAT come back as CRs (see `knowledge/projects-log.md`).

## 1. Set up

1. Work out the project. Use `projects/<slug>/` if it exists; otherwise create it with the `new-project` skill
   (or `python -I tools/new_project.py <slug> "<name>" "<client>"`).
2. If the document is outside `docs/`, move it there. Never edit it.
3. Pick a review folder name from the document and version, e.g. `srs-v1.0`, `srs-v1.1-draft`.
4. Extract:
   `python -I tools/extract.py "<path to document>" projects/<slug>/reviews/<review>/extract`
5. Read `meta.json`: metadata, counts, and the list of open-item markers (TBC, TBD, "if applicable").

## 2. Read everything

- Read the whole of `text.md`, in parts if it is long. Do not review from a partial read.
- Look at every image that is a diagram, process flow, architecture or mock-up (skip logos and
  signatures). Figures contradict the text more often than the text contradicts itself.
- For PDFs, `pages/` holds renders of every page with images, formulas or little text. Use them when an
  embedded image is too small to read, or when formulas and tables come out as fragments in `text.md`.
- Read `knowledge/srs-standard.md` and `knowledge/gap-patterns.md`.
- Read the project's `register.json`. For a new version of a document, check each open item: if this
  version resolves it, set `status` to `resolved` and `resolved_in` to the version. Do not raise duplicates.
- If the project's SOW is in `docs/`, extract and read it too.

## 3. Check

Work through every check. Record a finding only when you can point to its location.

**A. Internal consistency.** Role, status, module and field names across all sections, tables and figures.
Requirement ID gaps (often a deleted module still referenced elsewhere). Every cross-reference to a
section, figure or appendix. Counts and lists that should match (statuses in the table vs sort orders vs
dashboards). Field formats vs field lengths.

**B. Figures against text.** Process flow arrows and statuses, role names in diagrams, mock-up fields and
buttons against the data tables. Read the text *inside* mock-ups too: terms and conditions, help text,
placeholder hints and sample data often state business rules (booking limits, fees, eligibility, age or
licence rules) that the requirements never mention. Each such rule is a gap: either it becomes a
requirement or it is removed from the screen.

**B2. Arithmetic.** Re-add every total (manday tables, counts, worked examples, percentages) and check
every formula's worked example. A wrong total in the estimate appendix is a high-severity internal finding.

**C. Required content.** Each section in `srs-standard.md`. Anything the SOW promises that the SRS lacks.

**D. Gap patterns.** Go through every pattern in `gap-patterns.md` and check it explicitly. Patterns with
*Cost* evidence matter most. Note in the report which patterns are covered well, so the BA knows they were
checked.

**E. Workflow edge cases.** For each workflow: reject, withdraw, cancel, edit after submission, delete,
reopen, delegation, reassignment, escalation, concurrency, failure of the real-world activity, and what
happens to approvals already given.

**F. Data, reports and KPIs.** Every list and export: columns, scope, filters, sort. Every KPI: formula,
worked example, data sources, edge cases. Identifier formats: length, reset, overflow, gaps.

**G. Integrations.** For each external system and endpoint: data, direction, trigger, frequency, owner,
failure handling. Any "if applicable" or "TBC" on scope is high severity.

**H. Open items.** Every TBC, TBD and "if applicable" from `meta.json` becomes a register item with a
question and, where possible, a recommendation.

**I. Commercial.** Features in the SRS that are not in the SOW (possible CRs; raise before sign-off).
SOW items missing from the SRS. Effort drivers that grew since the estimate (more endpoints, custom
calculations, extra roles) get `effort_impact` and a note that the estimate should be revisited.

**J. Hygiene (internal only).** Metadata title, author and template leftovers naming other projects;
unaccepted tracked changes and comments; credentials, hostnames or IP addresses; broken TOC headings;
typos in headings and labels.

## 4. Verify before recording

For every candidate finding, re-open the text and confirm the quote and location. Drop anything you
cannot point to, and anything that is a matter of taste rather than a gap. Never invent a requirement: if
the document is silent, the finding is the question, and the recommendation offers options.

**Severity.**
- *High:* blocks sign-off, contradicts itself on scope or behaviour, or would cost mandays if guessed
  wrong (any GP pattern with cost evidence).
- *Medium:* will cause rework or a UAT defect if left.
- *Low:* clarity, naming, small inconsistencies.

**Keep the client list usable.** The BA has one meeting, not a week. If there are more than about 15 high
client items, re-check each one against the definition above and downgrade the rest. Merge findings that
the client would answer with one decision. Small wording and naming issues your team can fix itself are
internal, not client questions.

**Know what a document review cannot catch.** Whether a mock-up element is wanted, or a list has the
right columns, is a user preference: the document can be consistent and still wrong. Do not guess these.
Instead, in `review.md`, list the screens and lists that need a walk-through with users ("for each element:
is this needed?", "for each list: which columns?"), so the BA can cover them in the next session.

## 5. Record

1. Get the next ID with `python -I tools/register.py next-id projects/<slug>` and add items to
   `register.json` (fields are documented at the top of `tools/register.py`).
   - `audience: client` for anything only the client can answer. Write `question` in plain business
     language, answerable in one sentence, without internal jargon or blame.
   - `audience: internal` for anything your team fixes itself (hygiene, figure mismatches your team drew, missing
     sections). These must never go on the client sheet.
   - `category`: the GP id where one fits, otherwise a short slug (`consistency`, `hygiene`, `nfr`,
     `scope`).
   - `stage`: `srs-draft` or `srs-final`.
2. Run `python -I tools/register.py render projects/<slug>`. Fix any validation errors it reports.
3. Write `projects/<slug>/reviews/<review>/review.md`:
   - Verdict in two or three sentences (ready for sign-off or not, and why).
   - The top five items, by risk.
   - Commercial notes: scope drift against the SOW, estimate risk.
   - Patterns checked and found well covered.
   - Screens and lists to walk through with users (see "Know what a document review cannot catch").
   - Counts: client questions, internal fixes, by severity.
4. If the review found a gap that fits no existing pattern, or new evidence for one, propose the update to
   `knowledge/gap-patterns.md` to the user rather than editing it silently.

## 6. Report

Tell the user the verdict, the top items, and the paths to `register.xlsx` and `review.md`. Mention any
part of the document you could not read (unreadable images, scanned pages).
