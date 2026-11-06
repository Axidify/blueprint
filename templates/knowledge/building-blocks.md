# Building blocks for estimating

Estimate by counting building blocks, not by module. A module called "Dashboard" can be 2 days or 30
depending on what is inside it.

**Status: not yet calibrated.** Fill in the rates with your lead dev, then refine them with every project
logged by `close-project`. A rate is mandays per unit, as a range ("2–4") or a single figure; a block left
as TBD is counted in estimates and not priced. Until at least three projects are logged, every estimate
must say it is low-confidence.

## Platform: Joget DX

| ID | Building block | What drives the effort | Rate (MD) | Confidence |
|---|---|---|---|---|
| BB-01 | Simple eForm (single page) | Fields, validations, lookups | TBD | – |
| BB-02 | Multi-page eForm | Pages, conditional sections, calculated fields | TBD | – |
| BB-03 | Workflow step (approval) | Routing rule, reject path, notifications | TBD | – |
| BB-04 | Digital signature capture | Number of signers, storing the image in PDFs | TBD | – |
| BB-05 | Drawing or markup on an image | Inspection diagrams | TBD | – |
| BB-06 | List or datalist with filters | Columns, filters, actions | TBD | – |
| BB-07 | Operational dashboard | Status counts, lists, drill-down levels | TBD | – |
| BB-08 | KPI dashboard with custom calculations | Formulas, calendars, period splitting, charts | TBD | – |
| BB-09 | External API integration, per endpoint | Auth, mapping, error handling, testing with client | TBD | – |
| BB-10 | Generated PDF document | Layout, signatures, e-mail attachment | TBD | – |
| BB-11 | Scheduled job or reminder | Schedule, stop conditions | TBD | – |
| BB-12 | E-mail notification, per event | Template, recipients, placeholders | TBD | – |
| BB-13 | Excel export | Columns, scope, size | TBD | – |
| BB-14 | Role with its own menus | Access rules, data scope | TBD | – |
| BB-15 | Admin CRUD screen (master data) | Validation, uniqueness | TBD | – |
| BB-16 | AD / SSO login integration | Group mapping, environments | TBD | – |
| BB-17 | Audit trail | Which actions, old/new values | TBD | – |
| BB-18 | Environment migration (dev → test → prod) | Number of environments, configuration | TBD | – |

## Other work

Work around the build. Set each item as a share of the building-block subtotal ("10–15%") or as fixed
mandays ("2–3 MD"). An item left as TBD is listed in estimates and not priced. Add or remove rows to match
how your company scopes projects.

| ID | Item | Share or mandays | Notes |
|---|---|---|---|
| OW-01 | Project management | TBD | |
| OW-02 | Requirement workshops and documentation | TBD | |
| OW-03 | Internal testing and fixes before UAT | TBD | |
| OW-04 | UAT support | TBD | |
| OW-05 | Training and user guide | TBD | |
| OW-06 | Warranty support | TBD | |

## Story points

How the backlog turns a story's mandays into story points. Set it with the lead developer: a story gets the
smallest number of points whose "Mandays up to" covers its mandays. A story above the last row is too big
and should be split. While a row is TBD, the backlog leaves story points blank.

| Points | Mandays up to |
|---|---|
| 1 | TBD |
| 2 | TBD |
| 3 | TBD |
| 5 | TBD |
| 8 | TBD |
| 13 | TBD |

## Calibration notes

None yet.
