# Change requests

During development and UAT the client asks for things. Blueprint helps the team answer quickly and with a
reason the client can check: is it already in the requirements the client signed, is the signed document
silent or open on it, or is it a change? Ask with "the client asked for …", "is this in scope?", "is this
a CR?", or drop in a CR list or UAT defect list; see the `change-request` skill in [Skills](skills.md).

| Verdict | Means | What you get |
|---|---|---|
| **In scope** | The signed document already asks for it | A short internal note with the quote: build or fix it, no charge |
| **Ambiguous** | The document is silent, or the point was left open | A client question in the [register](register.md), not a CR yet |
| **New** | It changes or adds to what was signed | A CR in the log, sized for the team, and a note for the client |

## What it is checked against

The version recorded as issued with `python -I tools/project.py issue <slug>` (`output/issued.json`), read
from the spec snapshot the generator keeps beside the document (`output/spec-v<version>.yaml`). Changes made
to the spec after that version went out are not what the client signed, and are left out.

When nothing has been issued, Blueprint compares with the current spec and says so: there is no signed
version yet, so every verdict is provisional. When an issued version's snapshot is missing, it uses the
current spec with a warning to check the cited text against the issued document.

`python -I tools/change_request.py scope projects/<slug> "<request>"` lists the parts of the signed version
that read most like the request (requirements, screens, dialogs, status rules, scope lines, integrations,
notifications, non-functional requirements) with their ids and sections, and the register's decisions made
and items left open or not fixed. It counts shared words, like the register's duplicate check, so it is a
lead: the verdict is always made by reading the cited text, and an In scope or New verdict always quotes it.

## Sizing a change (internal)

A New CR is counted in the knowledge base's building blocks, with the same rules as an
[estimate](estimates.md): ranges, assumptions and a confidence level; rates only from the knowledge base or
the lead developer; a line with no rate is counted, not priced. If the knowledge base's **Calibration notes**
say something about change requests or small changes (extra testing and deployment, for example), Blueprint
shows it and applies it only as written there.

The **sold figure** is the project lead's. Blueprint records the mandays sold (`sold_md`, with who set them)
and a price as the client should read it only when the project lead gives them.

## The files

Everything is in the project's `changes/` folder.

| File | For | Contents |
|---|---|---|
| `crs.json` | Internal | The CR log: the source of the other two |
| `CR log (internal).xlsx` | The project lead and lead developer | **CR log**: every request with its verdict, the signed text it rests on, the gap pattern, status, sizing and sold figure. **Sizing**: every building-block line. **Summary**: counts by verdict, status and gap pattern, and the mandays sold |
| `CR-001 <title> - change request note.docx` | The client | What was asked, why it is a change (what the signed document says, quoted, with its section), what it would change, the impact on the timeline in weeks if known, and the price once the project lead has entered it, otherwise "Quotation to follow". Room for the client's approval |

The client's note is written in the company's document format and branding. It never shows ranges, rates,
building blocks, confidence, gap patterns or the team's reasoning.

## Statuses

`raised` → `quoted` → `approved` → `built`, or `rejected`. Only a New CR is quoted or approved, and a quoted,
approved or built CR needs the mandays sold. An Ambiguous request stays `raised` until the client answers its
register question; its verdict then becomes In scope or New.

## The CR log (`changes/crs.json`)

```json
{
  "project": "Leave Request System",
  "platform": "Joget DX",
  "crs": [
    {"id": "CR-001", "raised": "2026-12-03", "asked_by": "HR manager, during UAT", "stage": "uat",
     "title": "Export all applications to Excel", "request": "HR wants to export every leave application to Excel.",
     "verdict": "new", "basis_version": "0.1",
     "cited": [{"ref": "screen my-applications", "section": "section 5.2", "quote": "The employee's own applications ..."}],
     "reasoning": "No export anywhere in v0.1; the list shows the employee's own applications.",
     "why": "The signed document has no export: each employee sees their own applications on screen only.",
     "changes": ["An Export to Excel button for HR Admin", "A list of every application, with filters"],
     "gap_pattern": "GP-04",
     "lines": [{"id": "L01", "item": "Excel export", "block": "BB-13", "count": 1, "note": "8 columns"}],
     "assumptions": ["Same columns as the list"],
     "status": "quoted", "sold_md": 4, "sold_by": "Project lead", "weeks": [1, 2]}
  ]
}
```

| Key | Meaning |
|---|---|
| `id` | `CR-001`, `CR-002` …, given by `add` |
| `raised`, `asked_by`, `source`, `stage` | When and by whom it was asked, where it came from (a defect list row), `development` or `uat` |
| `title`, `request` | For the client: a short name, and what was asked |
| `verdict` | `in-scope`, `ambiguous` or `new` |
| `basis_version`, `cited` | The signed version it was checked against, and what it says: `{ref, section, quote}`. In scope and New need at least one |
| `reasoning`, `notes` | Internal |
| `why`, `changes`, `weeks` | For the client (New): why it is a change, what it would change, the timeline impact in weeks (a number or `[low, high]`) when known |
| `question`, `severity`, `recommendation`, `effort_impact` | Ambiguous: the register question `ask` adds |
| `gap_pattern`, `gap_note` | The gap pattern it maps to, or `new` with the gap in general terms |
| `lines`, `assumptions`, `confidence`, `confidence_reason` | Internal sizing, in the [estimate file](estimates.md#the-estimate-file)'s line format |
| `register` | Linked register items |
| `status`, `sold_md`, `sold_by`, `price`, `decided_on` | See [Statuses](#statuses); the sold figure only from the project lead |

Text written for the client (`title`, `why`, `changes`, `question`) may not mention mandays, rates, building
blocks or gap patterns: the check refuses it.

## Learning from change requests

Every New and Ambiguous request names the gap pattern that let it through. When the project closes,
`close-project` reads the CR log for the CRs, their gap patterns and the mandays sold, and proposes the
knowledge-base updates. Blueprint never changes the knowledge base without your agreement.
