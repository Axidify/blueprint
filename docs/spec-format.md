# Project spec format (`spec/app.yaml`)

One YAML file per project drives both the clickable mock-up (`tools/mockup.py`) and the generated requirements document
(`tools/generate_requirements.py`). Change the spec, rebuild both, and they stay consistent.
`examples/leave-request/spec/app.yaml` is a complete working example.

## Top level

| Key | Purpose |
|---|---|
| `project` | `name`, `short_name` (shown in the logo box), `client`, `client_short`, `version`, `platform`, `theme` (`joget`, `modern` or `vivid`), `primary_color`, `prepared_by`, `reviewed_by`, `approved_by`, `date`, `status` (shown on the cover and in the page header, e.g. "Draft for client review", "Signed off"), `history: [{version, date, author, changes}]` (document version history table) |
| `overview` | List of paragraphs for the start of document section 1.0 |
| `roles` | `id`, `name`, `description`, `scope` (data scope, e.g. "Own branch only"), `user` (sample person shown in the mock-up header) |
| `statuses` | `id`, `name`, `meaning`. Becomes the requirements document status table |
| `data` | Sample records, by list name. The first key of each record is its identifier |
| `screens` | The screens (below) |
| `dialogs` | Pop-ups opened by buttons (below) |
| `screenshots` | Extra screenshots beyond one per screen: `{screen, role, record, page, dialog, name}` |
| `requirements` | Functional requirement groups: `{id: FR-XXX-001, title, screens, priority, items: [...]}`. `screens` lists the screen ids the group applies to, so requirements and screens link to each other. `priority` (Must, Should, Could) is the group default; set it only when the client has agreed it. Items are numbered `.1`, `.2` … in the requirements document. An item is text, or `{text, priority, screens, tbc: R-019, note}`: `tbc` links an open register item (shown as "Decision needed R-019"), `note` is internal and not printed |
| `signoff` | Everyone who signs: `{name, designation, department, organisation, signing_for, status}`. Client signatories are listed first; `status` is `Pending` (default) or `Signed`. Without it the requirements document has one client and one supplier block to fill in |
| `notifications` | `{event, recipient, template}`. document section 1.6 |
| `integrations` | `{system, purpose, direction, notes}` |
| `nfr` | `{area, requirement}` |
| `glossary` | `{term, meaning}`. document section 1.5 |
| `process_flow` | `{title, steps: [{name, role, optional, status}], reject, notes}`. Drawn as a diagram (mock-up URL `#/__flow`), screenshotted and placed in document section 1.3, so it always matches the statuses |
| `timeline` | The project timeline chapter (below) |
| `extra_sections` | Free-form document sections after the NFRs: `{title, appendix, content: [{heading} \| {text} \| {bullets} \| {table: {header, rows}} \| {image, caption}]}`. `appendix: true` puts it after sign-off as Appendix A, B… Text may use `{client}` and `{system}`. In a table, an unquoted `No` or `Yes` is printed as that word (a first column headed `No` is the narrow numbering column); quote `"On"`, `"Off"`, `"True"` and `"False"` to keep those exact words |

Optional files next to `app.yaml`: `client-logo.png` (document cover) and `process-flow.png` (document section 1.3).

## Timeline

The project timeline chapter: a week-by-week chart, the milestones and the assumptions. Draft it with the
lead developer from the project's [estimate](estimates.md), one activity per scope-of-work (SOW) item;
weeks count from the kick-off, so the plan stays right until a kick-off date is agreed.

```yaml
timeline:
  unit: Week                       # column heading; default Week
  intro: …                         # optional; a standard sentence otherwise
  summary:                         # optional figures above the chart
    - {value: "27 – 32 weeks", label: Kick-off to go-live}
  stages:
    - name: Requirements
      items:
        - {ref: "2", name: Requirement workshops, start: 1, end: 3, client: true}
        - {milestone: M2, name: Requirements signed off, week: 6,
           title: Requirements document signed off, client_action: Review and sign within 5 working days}
  assumptions:
    - Three developers during development …
```

| Item key | Meaning |
|---|---|
| `ref` | The SOW item number, shown before the name, so the client can match each line to the SOW |
| `name` | Activity or milestone name, kept short (one line) |
| `start`, `end` | First and last week of an activity |
| `client` | `true` when the client must take part (workshops, reviews, data, UAT, training): drawn in the accent colour |
| `milestone`, `week` | A milestone's ID (M1, M2 …) and the week it falls in; drawn as a diamond |
| `title`, `client_action` | A milestone's full name and what the client must do, for the milestones table |

Projects longer than 40 weeks show one column per 2 or more weeks. Durations come from the estimate, not from the
SOW's mandays, which are a commercial figure and often lower than the likely effort:
`python -I tools/estimate.py weeks projects/<slug> --team 2` gives the working weeks per SOW item for a team
size. State the team size and the other assumptions behind the weeks. Mandays, rates and cost never go
into the spec.

## Screens

Every screen has `id`, `type`, `title`, and optionally `screenshot_role` (role used for its screenshot; default the first in `roles`), `menu` (label in the side menu; omit for screens
reached by links), `roles` (who can open it; omit for everyone), `description` (document text under the
screenshot) and `caption`.

| `type` | Keys |
|---|---|
| `login` | none |
| `dashboard` | `stats: [{label, value}]` or computed `{label, count: all}` / `{label, count: {status: [...]}}` (counted over the screen's list data), optional `list`, `buttons` |
| `list` | `list`, `buttons` |
| `form` | `sections`, `buttons`; optional `data` so `?record=` pre-fills it |
| `detail` | `data`, `record` (default record id), `fields_from` (reuse another screen's sections, read-only) or its own `sections`, optional `timeline: [{step, by, at, status, comment}]`, `buttons`, `screenshot_pages: all` (default: only page 1 is screenshotted). A record's own `timeline` and `notice` (e.g. a rejection notice) override the screen's |
| `custom` | `html` (raw HTML, for anything the other types cannot show) |

**`list`:** `data` (a key of `data`), `where` (filter, e.g. `{status: "Pending Approval"}` or a list of
allowed values `{status: [Submitted, Approved]}`), `columns: [{field, label, chip}]` (`chip: true` shows
the value as a coloured status), `filters: [field, ...]`,
`actions: [{label, to | toast, when}]` (per row; `to` opens a screen with that row's record; `when:
{status: Draft}` shows the action only on matching rows),
`toolbar: [{label, to | toast, style}]`, `search: [field]` (text search boxes, partial match), `sort` (text for the requirements document), `empty` (empty-state text). Actions and toolbar buttons appear in the requirements document access matrix unless `access: false`.

**`sections`:** `[{title, page, page_title, note, fields}]`. Give sections a `page` number to split a
form into steps (tabs); each page gets its own screenshot.

**Fields:** `id`, `label`, `type` (`text`, `textarea`, `select`, `radio`, `checkbox`, `date`,
`datetime`, `number`, `file`, `signature`, `user`), `required`, `readonly`, `default`, `length`,
`options` or `options_from: list.field`, `placeholder`, `help`, `source` and `validation` (both go into
the requirements document data requirement table).

**Buttons:** `{label, style (primary | danger), to, toast, dialog, roles, when, example}`. `toast` shows a
message (e.g. "Draft saved"); `roles` limits who sees the button; `when` shows it only for matching
records on detail screens. Primary, danger and dialog buttons appear as actions in the requirements document access matrix,
except `example: true` buttons (demo-only buttons that open a dialog for screenshots).

## Dialogs

`{id, title, message, fields, list, doc_table, confirm: {label, style, toast, to}}`. `doc_table: false` (formerly `srs_table`) leaves its field table out of the requirements document. A button opens it with
`dialog: <id>`. `list` shows a table inside the dialog (same format as a screen list). Dialog fields
appear in the requirements document under the screen that opens it.

## Mock-up URLs

`index.html#/<screen>?role=<role>&record=<id>&page=<n>&dialog=<id>&clean=1`. `clean=1` hides the
feedback tools (used for screenshots).

## Cross-references

Never write "section 3.2", "Appendix B" or "Figure 4" in spec text: numbers change whenever screens or
sections are added. Use a reference the generator resolves, and it warns about any literal one it finds:

| Reference | Becomes |
|---|---|
| `{ref:screen:<screen id>}` | the screen's section, e.g. "section 4.3" |
| `{ref:role:<role id>}` | the role's section in Requirements by role |
| `{ref:section:roles\|access\|flow\|integrations\|notifications\|glossary\|users\|by-role\|requirements\|screens\|nfr\|timeline\|decisions}` | that section's number (`open-issues` still works for `decisions`) |
| `{ref:extra:<extra section title>}` | "section n.0" or "Appendix X" |
| `{ref:req:<FR id>}` | the requirement group id |

`{client}` and `{system}` are replaced with the project's client and system names.
