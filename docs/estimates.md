# Estimates

An estimate says how many mandays a project is likely to take, as a **range**, with the assumptions behind
it and a **confidence level**. It is counted in the building blocks of the [knowledge base](knowledge.md)
(forms, approval steps, lists, integrations, reports, roles …), not by module name. Ask for one with
"estimate this project"; see the `estimate` skill in [Skills](skills.md).

**Estimates are internal.** They are for the lead developer and the project lead. They live in the
project's `estimates/` folder and never appear in the mock-up, the requirements document or the client
sheet of the register. The one thing that leaves them is the project timeline, in weeks (see below).

**Blueprint does not make up figures.** Rates and shares are yours: set them in the knowledge base, or give
them to Blueprint for one estimate. A line with no figure keeps its count and is shown as *not priced*,
left out of the total.

## When to estimate

| When | Counted from | What to expect |
|---|---|---|
| Before the scope of work is written | The brief | A wide range, low confidence, and the questions to ask before pricing |
| The scope of work exists | The scope of work, line by line | How far the sold mandays are from the likely effort, and where |
| After the mock-up and workshops | The project spec | A narrower range, the basis for the timeline in the requirements document |
| After a new spec version | The project spec | How the range moved, and why |

Each estimate is a new dated file, so the folder shows how the figure moved as the requirements firmed up.

## Setting your rates

Everything is in `knowledge/building-blocks.md`, shared by everyone using the workspace:

- **Building-block rates**, per platform: mandays per unit in the `Rate (MD)` column, as a range (`2–4`)
  or a single figure, with a confidence (`low`, `medium`, `high`). `TBD` means not set. Only the figure the
  cell starts with is the rate: after it you may write a unit or a note (`3 (was 5)`, `2–4 per form`). Write
  decimals with a point. A cell that does not start with a number or a range (`1,5`, `from 2`) is not used:
  its lines are not priced, and `blocks` and the estimate say the rate could not be read.
- **Other work** (project management, testing, UAT support, training …): an `Other work` table with a share
  of the building-block subtotal (`10–15%`) or fixed mandays (`2–3 MD`) per item. Add, remove or rename
  rows to match how your company scopes projects. A workspace created before this table existed does not
  have it: ask Blueprint to add it, or copy it from `templates/knowledge/building-blocks.md`.

When the lead developer gives a rate during an estimate, Blueprint offers to save it there, so nobody is
asked twice. It changes the knowledge base only after you agree.

## The files

`projects/<name>/estimates/<date> estimate from <basis>.json` is the source; the Excel file with the same
name is the copy to read. To change an estimate, tell Blueprint what to change (a count, a rate, an
assumption) rather than editing the Excel file: it is rewritten every time.

| Sheet | Contents |
|---|---|
| Summary | The total range, the lines not priced, the range if the open questions are answered the costly way, the cost at your day rate, the confidence level and its reasons, how well the rates are calibrated, and the lines that make the range widest |
| Estimate | Every line: building block, count, rate range and where the rate comes from, mandays low and high, the scope-of-work line it belongs to, and what was counted |
| Against SOW | Each scope-of-work line beside the estimate's range for it, largest differences first; work that is not in the scope of work; scope-of-work lines the estimate does not cover |
| Uncertainty | Open questions (sized in mandays when the lead developer has sized them), lines not priced, open register items that can move the estimate, the gap patterns the project is exposed to, building blocks with no rate yet |
| Assumptions | Everything the figures depend on, including what is left out |
| Questions | The questions that would narrow the range, the ones covering the most mandays first |

## How the figures are worked out

- **Lines.** A building-block line is count × rate. The rate comes from the knowledge base for the
  project's platform. A rate recorded there as a single figure becomes a range by its confidence:
  high −10% to +10%, medium −25% to +25%, low −25% to +50%.
- **A rate for one estimate.** The lead developer can give a range for a block that has none. It is marked
  *provisional* and counts against the confidence level.
- **Not priced.** A line with no rate or share from either source is counted but has no mandays. The total
  then covers the priced lines only, and says so.
- **Other work.** Items from the `Other work` table, as a share of the building-block subtotal or fixed
  mandays; or a figure the lead developer gives for the project.
- **Totals.** The low ends added up and the high ends added up. There is no single "most likely" figure.
- **Open questions.** A question that would add work if answered the costly way is listed; once the lead
  developer sizes it, it widens the high end only and is shown separately from the total.

## Confidence

The level starts at high and each rule can lower it. The estimator can lower it further, never raise it.

| Rule | Level |
|---|---|
| Fewer than three delivered projects logged on the platform | Low |
| Counted from a brief, a scope of work or workshop notes | Low |
| Any line is not priced | Low |
| More than half of the priced mandays rest on low-confidence rates or figures given for this estimate | Low |
| More than a fifth of them do | Medium at most |
| A high-severity register item is still open | Medium at most |

Confidence improves as projects are closed with `close-project`: each one adds evidence for the rates.

## Against the scope of work

The scope of work's mandays are a commercial figure: they let the client gauge the cost and are often lower
than the likely effort after negotiation. A gap is normal. The comparison shows how large it is and which
lines carry it, and separates a negotiated price from scope that grew (one lookup that became four
endpoints), which is worth raising before sign-off.

## The timeline uses the estimate

The timeline chapter of the requirements document is drafted from the latest estimate, not from the scope
of work's mandays:

```bash
python -I tools/estimate.py weeks projects/<slug> --team 2
```

gives working weeks per scope-of-work line (or per group) for that team size. Only weeks, activities and
milestones go into the spec; mandays, rates and cost stay in the estimate. See `timeline` in
[Spec format](spec-format.md).

## The estimate file

```json
{
  "project": "Courier Booking System",
  "platform": "Joget DX",
  "date": "2026-11-06",
  "basis": "spec v0.3",
  "basis_kind": "spec",
  "sources": ["spec/app.yaml v0.3", "register.json"],
  "lines": [
    {"id": "L01", "group": "Booking", "item": "Booking form", "block": "BB-02", "count": 1,
     "sow_ref": "3.1", "note": "4 pages, 2 calculated fields"},
    {"id": "L02", "group": "Booking", "item": "Tracking API", "block": "BB-09", "count": 3,
     "rate": [2, 4], "rate_note": "Given by the lead developer for this estimate", "sow_ref": "3.4"},
    {"id": "L03", "item": "Data migration from the old system", "md": [3, 6]},
    {"id": "L04", "item": "Project management", "other": "OW-01", "sow_ref": "1"}
  ],
  "risks": [{"ref": "R-012", "item": "Tracking needs a second courier's API", "md": [0, 6]}],
  "assumptions": ["Two approval levels", "Test data provided by the client"],
  "gap_patterns": [{"id": "GP-10", "why": "One integration in the brief, endpoints not listed"}],
  "questions": [{"question": "Which couriers must tracking cover?", "source": "GP-10", "narrows": ["R-012", "L02"]}],
  "sow": {"source": "docs/2026-11-02 SOW.xlsx",
          "lines": [{"ref": "1", "item": "Project management", "mandays": 5}]}
}
```

| Key | Meaning |
|---|---|
| `basis`, `basis_kind` | What it was counted from, in words, and one of `brief`, `sow`, `notes`, `spec`, `requirements-document` |
| `lines` | Each has `id`, `item`, optional `group`, `note`, `sow_ref`, and exactly one of: `block` with `count` (rate from the knowledge base, or `rate: [low, high]` with `rate_note` when the lead developer gives one); `other` (an item of the `Other work` table); `md: [low, high]`; `percent: [low, high]` of the building-block subtotal |
| `risks` | Open questions: `item`, optional `md: [low, high]` once sized, `ref` (a register item) and `note`. Without a `ref` they are numbered K01, K02 … |
| `assumptions` | At least one |
| `gap_patterns` | The patterns the project is exposed to: `id`, `why` |
| `questions` | `question`, `source` (a gap pattern or register item), `narrows` (line or risk IDs) |
| `sow` | The scope of work's own lines: `ref`, `item`, `mandays`. Lines of the estimate point to them with `sow_ref` |
| `confidence`, `confidence_reason` | Optional: a lower level than the rules give |

`examples/leave-request/estimates/` holds a sample: the counts, assumptions and questions for the Leave
Request example, with no figures of its own. Render it with
`python -I tools/estimate.py render examples/leave-request`: it prices whatever your knowledge base has
rates for and lists the rest as not priced.
