# Building blocks for estimating

Estimate by counting building blocks, not by module. A module called "Dashboard" can be 2 days or 30
depending on what is inside it.

**Status: not yet calibrated.** Fill in the rates with your lead dev, then refine them with every project
logged by `close-project`. Until at least three projects are logged, every estimate must say it is
low-confidence.

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

## Calibration notes

None yet.
