# Knowledge base

The knowledge base lives in the workspace (`knowledge/`) and is shared by everyone who uses that
workspace. It makes every review and mock-up better than the last. A new workspace starts with a generic
version from `templates/knowledge/`.

| File | What it holds | How it grows |
|---|---|---|
| `gap-patterns.md` | Recurring requirement gaps, each with what goes wrong, the workshop questions that prevent it and what a review checks | Every CR from a delivered project is mapped to a pattern and added as evidence; new patterns are added when a CR fits none |
| `building-blocks.md` | Estimating units (multi-page form, approval step, signature capture, API endpoint, KPI dashboard …) with mandays per platform and a confidence level | You set the rates, and the shares for other work (project management, testing …) in its `Other work` table; they are then calibrated from logged actuals. A block or item with no figure is counted in [estimates](estimates.md) and not priced. Until three projects are logged, estimates are low-confidence |
| `requirements-standard.md` | The sections every requirements document needs and the quality rules a review checks | Updated when reviews keep finding the same kind of gap |
| `projects-log.md` | Estimate vs actual for every delivered project | One row per project phase, from `close-project` |
| `actuals/<project>.md` | Effort, CRs, what the requirements document already showed, lessons | Written by `close-project` |

## Evidence levels

A gap pattern with **cost** evidence came back as a CR or an overrun, with real mandays. A pattern with
**review** evidence was found in a review before it cost anything. Patterns with cost evidence are
raised first in every workshop and weighted highest in reviews.

## Changing the knowledge base

Blueprint proposes changes to the knowledge base and makes them only after you agree, because everyone
sharing the workspace relies on it. Gaps are written in general terms, without client names or content.

To improve the starter knowledge that ships with the app (`templates/knowledge/`), change it in the
repository like any other app change: see [Maintaining](maintaining.md). Never copy client content into it.
