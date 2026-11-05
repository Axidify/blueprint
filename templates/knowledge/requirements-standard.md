# requirements standard

What every requirements document must contain, and the rules it must meet before it goes to the client. `review-requirements`
checks each line.

## Required sections

The SOW template promises several of these (functional and non-functional requirements, data model, ERD,
use case, activity and data-flow diagrams). If the SOW for the project promises a section, its absence is a
high-severity internal finding.

| # | Section | Must include |
|---|---|---|
| 1 | Cover and version control | Version, dates, prepared/reviewed/approved by, change history |
| 2 | System overview and architecture | Users, modules, external systems |
| 3 | Roles | Every role, including read-only roles (GP-01), with data scope |
| 4 | Access matrix | Every menu and action against every role |
| 5 | Process flow and statuses | Diagram, status table, who may edit/cancel/delete in each status (GP-02) |
| 6 | Integrations | One row per endpoint: purpose, direction, trigger, fields, failure handling (GP-10) |
| 7 | Environments and access readiness | What the client must provide, by when |
| 8 | Functional requirements | Numbered, testable, one behaviour per requirement |
| 9 | Data requirements | Per form and list: field, type, length, mandatory, source, validation (GP-05) |
| 10 | Calculations and KPIs | Formula, worked example, edge cases, data sources (GP-03) |
| 11 | Notifications | Event → recipient → template table (GP-14) |
| 12 | Non-functional requirements | Users, performance, availability, backup, retention, security, browsers (GP-12) |
| 13 | Data model / ERD | Entities and relationships, if promised in the SOW |
| 14 | Diagrams | Use case, activity, data flow, if promised in the SOW |
| 15 | Mock-up screens | Every screen referenced by the requirements |
| 16 | Infrastructure | Environments and sizing |
| 17 | Timeline | Stages, activities and milestones by week from kick-off; what the client must do and by when; the assumptions (team size, review turnaround) behind it |
| 18 | Open issues | Every TBC with owner, due date and estimate impact |
| 19 | Glossary | Every acronym used |
| 20 | Sign-off | Client and supplier signatories |

## Quality rules

1. **Consistent names.** Roles, statuses, modules and field names are spelled the same everywhere,
   including in figures.
2. **Figures match text.** Process diagrams, architecture diagrams and mock-ups say the same as the
   requirements.
3. **No numbering gaps.** Requirement IDs are continuous; a gap usually means a deleted module that is
   still referenced.
4. **Valid cross-references.** Every "see section X / Appendix Y / Figure Z" points to the right place.
5. **Testable requirements.** Each requirement can be passed or failed in UAT.
6. **Every TBC is tracked.** Each TBC, TBD or "if applicable" appears in the open issues table with an
   owner. "If applicable" on scope is never acceptable at sign-off.
7. **Data fits.** Formats fit field lengths; calculated fields state their formula.
8. **Scope matches the SOW.** Every SOW module appears in the requirements document; anything in the requirements document that is not in the
   SOW is flagged as a possible CR before sign-off.
9. **Clean document.** No other project's names (including metadata), no tracked changes, no comments, no
   credentials or IP addresses unless the client approved them.
