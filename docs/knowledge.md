# Knowledge base

The knowledge base lives in the workspace (`knowledge/`) and is shared by everyone who uses that
workspace. It makes every review and mock-up better than the last. A new workspace starts with a generic
version from `templates/knowledge/`.

| File | What it holds | How it grows |
|---|---|---|
| `gap-patterns.md` | Recurring requirement gaps, each with what goes wrong, the workshop questions that prevent it and what a review checks | Every CR from a delivered project is mapped to a pattern and added as evidence; new patterns are added when a CR fits none |
| `building-blocks.md` | Estimating units (multi-page form, approval step, signature capture, API endpoint, KPI dashboard …) with mandays per platform and a confidence level | You set the rates, and the shares for other work (project management, testing …) in its `Other work` table; they are then calibrated from logged actuals. A block or item with no figure is counted in [estimates](estimates.md) and not priced. Until three projects are logged, estimates are low-confidence |
| `platforms/<product>.md` | One sheet per product a project is built with (Joget DX to start with): for each kind of feature, whether the product does it as standard, by configuration, by custom work or not at all, what it takes, the building block it is estimated with, and the page of the product's own documentation it was checked against | The `platform-fit` skill looks features up in the product's documentation online and adds what it finds, after you agree; your lead developer confirms rows. See [Platform sheets](#platform-sheets) |
| `requirements-standard.md` | The sections every requirements document needs and the quality rules a review checks | Updated when reviews keep finding the same kind of gap |
| `projects-log.md` | Estimate vs actual for every delivered project | One row per project phase, from `close-project` |
| `actuals/<project>.md` | Effort, CRs, what the requirements document already showed, lessons | Written by `close-project` |

## Platform sheets

A mock-up can show anything; the real system is built on a product. Each sheet in `platforms/` says what
that product gives, so a spec's custom work is found before it is promised to a client. A row looks like
this:

| ID | Feature | Spec | Support | What it takes | Block | Source | Checked | Confirmed |
|---|---|---|---|---|---|---|---|---|
| PF-17 | Figures with a calculation of their own | stat:formula | custom | Calculated in a script, an SQL query or a plugin | BB-08 | (the documentation page) | 2026-11-06 | A. Lead 2026-11-10 |

- **Support:** `standard`, `configuration`, `custom` or `not supported`.
- **Spec:** the parts of a spec the row covers, as `tools/platform_fit.py check` names them; `*` matches
  anything, and the first row that matches is the one used.
- **Source and Checked:** the page of the product's own documentation the row was checked against, and
  when. **Confirmed:** the lead developer who confirmed it.

The starter Joget DX sheet was written from general knowledge and none of its rows is checked: each is
looked up in Joget's documentation the first time a project uses it. Lookups use product and feature words
only, never a client's name or anything from a project.

## Evidence levels

A gap pattern with **cost** evidence came back as a CR or an overrun, with real mandays. A pattern with
**review** evidence was found in a review before it cost anything. Patterns with cost evidence are
raised first in every workshop and weighted highest in reviews.

## Changing the knowledge base

Blueprint proposes changes to the knowledge base and makes them only after you agree, because everyone
sharing the workspace relies on it. Gaps are written in general terms, without client names or content.

To improve the starter knowledge that ships with the app (`templates/knowledge/`), change it in the
repository like any other app change: see [Maintaining](maintaining.md). Never copy client content into it.
