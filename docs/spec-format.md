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
| `scope` | `{in_scope: [...], out_of_scope: [...], assumptions: [...]}`, each a list of sentences. Becomes the chapter "Scope and assumptions"; left out when the spec has none. Write what the client might otherwise expect to get under `out_of_scope` |
| `statuses` | `id`, `name`, `meaning`, the status rules (below), and optionally `color` (`green`, `amber`, `red` or `grey`): the colour of that status wherever the mock-up shows it (see [Status colours](#status-colours)). Becomes the requirements document status table |
| `data` | Sample records, by list name. The first key of each record is its identifier |
| `screens` | The screens (below) |
| `dialogs` | Pop-ups opened by buttons (below) |
| `screenshots` | Extra screenshots beyond one per screen: `{screen, role, record, page, dialog, name}` |
| `requirements` | Functional requirement groups: `{id: FR-XXX-001, title, screens, priority, items: [...]}`. `screens` lists the screen ids the group applies to, so requirements and screens link to each other. `priority` (Must, Should, Could) is the group default; set it only when the client has agreed it. Items are numbered `.1`, `.2` … in the requirements document. An item is text, or `{text, priority, screens, tbc: R-019, note}`: `tbc` links an open register item (shown as "Decision needed R-019"), `note` is internal and not printed |
| `signoff` | Everyone who signs: `{name, designation, department, organisation, signing_for, status}`. Client signatories are listed first; `status` is `Pending` (default) or `Signed`. Without it the requirements document has one client and one supplier block to fill in |
| `notifications` | `{event, recipient, template}`. document section 1.6 |
| `integrations` | `{system, purpose, direction, notes}`, and how it works: `trigger` (what starts the exchange), `data` (what goes across) and `on_failure` (what happens when it fails). With these the document adds a table "How each exchange works"; one left out shows "To be confirmed" and is warned about |
| `nfr` | `{area, requirement}` |
| `glossary` | `{term, meaning}`. document section 1.5 |
| `process_flow` | `{title, steps: [{name, role, optional, status}], reject, notes}`. Drawn as a diagram (mock-up URL `#/__flow`), screenshotted and placed in document section 1.3, so it always matches the statuses |
| `timeline` | The project timeline chapter (below) |
| `extra_sections` | Free-form document sections after the NFRs: `{title, appendix, content: [{heading} \| {text} \| {bullets} \| {table: {header, rows}} \| {image, caption}]}`. `appendix: true` puts it after sign-off as Appendix A, B… Text may use `{client}` and `{system}`. In a table, an unquoted `No` or `Yes` is printed as that word (a first column headed `No` is the narrow numbering column); quote `"On"`, `"Off"`, `"True"` and `"False"` to keep those exact words |

Optional files next to `app.yaml`: `client-logo.png` (document cover) and `process-flow.png` (document section 1.3).

## Status rules

Who may change a record while it is in a status, and where it can go next. They are printed as a table
under the statuses in the document. The mock-up does not enforce them, but a button that moves a record
(see [Status moves](#status-moves)) must agree with `next`.

```yaml
statuses:
  - id: pending
    name: Pending Approval
    meaning: Submitted and waiting for the line manager.
    edit: none                  # role ids, or all, or none
    cancel: [employee]
    delete: none
    next: [approved, rejected, cancelled]    # status ids; [] for a final status
```

Leave a key out when the client has not decided it: the document shows "To be confirmed" there and the
generator warns, so it is not forgotten (add a register question for it). A spec with no rules at all
still generates, with a note.

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
| `dashboard` | `stats: [{label, value}]` or computed `{label, count: all}` / `{label, count: {status: [...]}}` (counted over the screen's list data), optional `list`, `buttons`. The document lists what each figure counts: a computed one is described from its rule; give a typed-in `value` a `formula`, in words ("Entitlement for the year, less approved days"), or it shows "To be confirmed" |
| `list` | `list`, `buttons` |
| `form` | `sections`, `buttons`; optional `data` so `?record=` pre-fills it |
| `detail` | `data`, `record` (default record id), `fields_from` (reuse another screen's sections, read-only) or its own `sections`, optional `timeline: [{step, by, at, status, comment}]`, `buttons`, `screenshot_pages: all` (default: only page 1 is screenshotted). A record's own `timeline` and `notice` (e.g. a rejection notice) override the screen's |
| `custom` | `html` (raw HTML, for anything the other types cannot show) |

**`list`:** `data` (a key of `data`), `where` (filter, e.g. `{status: "Pending Approval"}` or a list of
allowed values `{status: [Submitted, Approved]}`), `columns: [{field, label, chip}]` (`chip: true` shows
the value as a coloured status), `filters: [field, ...]`,
`actions: [{label, to | toast, when, set_status}]` (per row; `to` opens a screen with that row's record; `when:
{status: Draft}` shows the action only on matching rows; `set_status` moves that row's record, see
[Status moves](#status-moves)),
`toolbar: [{label, to | toast, style}]`, `search: [field]` (text search boxes, partial match). In the
mock-up both work on the sample rows: **Search** applies them and **Clear Filters** resets them. `sort` (text for the requirements document), `empty` (empty-state text). Actions and toolbar buttons appear in the requirements document access matrix unless `access: false`.

**`sections`:** `[{title, page, page_title, note, fields}]`. Give sections a `page` number to split a
form into steps (tabs); each page gets its own screenshot.

**Fields:** `id`, `label`, `type` (`text`, `textarea`, `select`, `radio`, `checkbox`, `date`,
`datetime`, `number`, `file`, `signature`, `user`), `required`, `readonly`, `default`, `length`,
`options` or `options_from: list.field`, `placeholder`, `help`, `source` and `validation` (both go into
the requirements document data requirement table).

**Buttons:** `{label, style (primary | danger), to, toast, dialog, roles, when, example, set_status}`. `toast` shows a
message (e.g. "Draft saved"); `roles` limits who sees the button; `when` shows it only for matching
records on detail screens; `set_status` moves the record to another status (see
[Status moves](#status-moves)). Put a label that starts with Yes, No, On or Off in quotes (`label: "Yes,
cancel it"`): YAML otherwise reads it as true or false, and the build stops. Primary, danger and dialog buttons appear as actions in the requirements document access matrix,
except `example: true` buttons (demo-only buttons that open a dialog for screenshots).

## Dialogs

`{id, title, message, fields, list, doc_table, confirm: {label, style, toast, to, set_status}}`. `doc_table: false` (formerly `srs_table`) leaves its field table out of the requirements document. A button opens it with
`dialog: <id>`. `list` shows a table inside the dialog (same format as a screen list). Dialog fields
appear in the requirements document under the screen that opens it.

The confirm button always closes the dialog: it then opens its `to` screen, or stays on the current
screen when it has none (with its `toast`, if any). A dialog without `confirm` gets an OK button that
closes it.

## Status moves

Give a button `set_status: <status id or name>` and clicking it in the mock-up moves the record to that
status, so the client can watch the process play out instead of being told about it:

```yaml
screens:
  - id: review-application
    type: detail
    data: applications
    buttons:
      - {label: Approve, style: primary, dialog: approve-dialog, when: {status: Pending Approval}}
dialogs:
  - id: approve-dialog
    title: Approve Application
    confirm: {label: Confirm Approve, toast: "Application approved", to: approvals, set_status: approved}
```

Everything drawn from the record follows: its status on every screen, the lists it belongs to (`where`),
the counts on dashboards (`count`), and the buttons and row actions that depend on its status (`when`).
Give those buttons a `when`, or Approve stays on an application that is already approved.

- **Which record.** On a detail screen, or a form opened on a record, it is that record, also from a dialog
  opened there. On a row action of a list it is that row. When the button opens a dialog, put `set_status`
  on the dialog's `confirm`: the record moves when the dialog is confirmed, not when it opens.
- **Progress.** When the record (or the detail screen that shows it) has a `timeline`, the first step still
  waiting (no `at`) is filled in with the new status, the signed-in role's `user` (or its name), the time,
  and what was typed into the dialog as the comment. With no step waiting, a line is added. After a final
  status (`next: []`) the steps still waiting are dropped.
- **Only in the browser, only until a reload.** Nothing is saved and nobody else in the room sees it.
  Reloading the page (F5) puts the sample data back, which is how to start a walk-through again.
  Screenshots are not affected, and adding `set_status` does not make them out of date.
- **Checked against the status rules.** The build stops when `set_status` names no status, when the button
  has no record to move (a toolbar or dashboard button), or when the move contradicts `next`: where the
  record is comes from the button's `when: {status: ...}`, or the `where` of its list. The build also lists
  the moves the rules allow that no button makes, so you can see what the walk-through cannot show.

A new record is not created: **Submit** on an empty form still only shows its message.

## Status colours

Statuses are shown as coloured labels: in list columns with `chip: true`, on detail screens, in the
approval progress table and in the process flow. Give each status in `statuses` a `color` and the mock-up
uses it wherever a value equals that status's `name` (or `id`):

```yaml
statuses:
  - {id: on-hold, name: On Hold, meaning: Waiting for the requester., color: amber}
```

`green` is for done or good, `amber` for waiting, `red` for refused or failed, `grey` for neutral. Any other
colour is a spec error. A value with no colour set (a step status such as "Done", or a status you left
without one) is coloured from its wording: refusals and negatives ("Rejected", "Inactive", "Not Approved")
red, waiting words amber, "Approved", "Completed", "Active" green, anything else grey. Set `color` whenever
the guess would be wrong.

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
| `{ref:section:roles\|access\|flow\|integrations\|notifications\|glossary\|users\|scope\|by-role\|requirements\|screens\|nfr\|timeline\|decisions}` | that section's number (`open-issues` still works for `decisions`) |
| `{ref:extra:<extra section title>}` | "section n.0" or "Appendix X" |
| `{ref:req:<FR id>}` | the requirement group id |

`{client}`, `{client_short}`, `{system}`, `{company}` and `{company_short}` are replaced with the names from
the spec and the company profile. References and names are resolved in every text the document prints:
overview, role descriptions and scopes, status meanings, requirements and their group titles, screen
descriptions, field rules, notifications, integrations, non-functional requirements, glossary meanings,
the timeline and extra sections, including the cells of their tables.

## What the mock-up build checks

`mockup.py build` (and so `screenshots`, `serve` and the document generator) stops with a list of errors
when the spec points at something that does not exist: a screen, dialog, role or data list; a list column,
filter, search field or `where` / `when` / `count` condition naming a field the sample data does not have;
an `options_from` that is not `<data list>.<field>`; a field type that is not one of the list above; a
`record` that is not in the data; a role or dialog id used twice; a button label that YAML read as true
or false; a `set_status` that cannot work or contradicts the status rules (see
[Status moves](#status-moves)). It also reports a setting that nearly
spells a real one, such as `colums` or `tittle`, with the name it expects. Settings the format does not know
at all are left alone, so you can keep notes of your own in the spec.

## What the generator checks

Before it writes anything, the document generator checks the spec: everything the mock-up needs (unknown
screens, roles and dialogs, duplicate ids, status colours) and the parts only the document prints. Each
requirement group needs an `id` (used once), a `title` and at least one item with text; a notification its
`event` and `recipient`; a non-functional requirement its `area` and `requirement`; a glossary entry its
`term` and `meaning`; every screen a `title`, every field and list column a `label`. Extra sections need
titles that differ from each other, and table rows as long as their header. Every figure in `stats` needs a
`label`, and a `formula` must not be empty. Status rules must name roles
and statuses that exist, and `scope` may hold only `in_scope`, `out_of_scope` and `assumptions`, each a list. Timeline weeks count from 1,
and an activity's `end` is not before its `start`. Mistakes are listed together and nothing is written.
