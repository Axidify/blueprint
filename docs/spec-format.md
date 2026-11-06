# Project spec format (`spec/app.yaml`)

One YAML file per project drives both the clickable mock-up (`tools/mockup.py`) and the generated requirements document
(`tools/generate_requirements.py`). Change the spec, rebuild both, and they stay consistent.
`examples/leave-request/spec/app.yaml` is a complete working example.

## Top level

| Key | Purpose |
|---|---|
| `project` | `name`, `short_name` (shown in the logo box), `client`, `client_short`, `version`, `platform`, `stack` (the other products the system is built with: a database, a directory, a cloud service), `theme` (see [Themes](#themes)), `primary_color`, `text_size` (`normal`, `large` or `larger`: the text of the client's screens, in the mock-up and so in the document's pictures), `prepared_by`, `reviewed_by`, `approved_by`, `date`, `status` (shown on the cover and in the page header, e.g. "Draft for client review", "Signed off"), `history: [{version, date, author, changes}]` (document version history table) |
| `overview` | List of paragraphs for the start of document section 1.0 |
| `roles` | `id`, `name`, `description`, `scope` (data scope, e.g. "Own branch only"), `user` (sample person shown in the mock-up header) |
| `scope` | `{in_scope: [...], out_of_scope: [...], assumptions: [...]}`, each a list of sentences. Becomes the chapter "Scope and assumptions"; left out when the spec has none. Write what the client might otherwise expect to get under `out_of_scope` |
| `statuses` | `id`, `name`, `meaning`, the status rules (below, with `auto` for the moves the system makes on its own), and optionally `color` (`green`, `amber`, `red` or `grey`): the colour of that status wherever the mock-up shows it (see [Status colours](#status-colours)). Becomes the requirements document status table |
| `data` | Sample records, by list name. The first key of each record is its identifier |
| `screens` | The screens (below) |
| `dialogs` | Pop-ups opened by buttons (below) |
| `screenshots` | Extra screenshots beyond one per screen: `{screen, role, record, page, dialog, name, caption}`. Without its own `caption` the requirements document captions it "…, as seen by <role>" or "…, showing record <id>", and warns when two figures share a caption |
| `requirements` | Functional requirement groups: `{id: FR-XXX-001, title, screens, priority, items: [...]}`. `screens` lists the screen ids the group applies to, so requirements and screens link to each other. `priority` (Must, Should, Could) is the group default; set it only when the client has agreed it. Items are numbered `.1`, `.2` … in the requirements document. An item is text, or `{text, priority, screens, tbc: R-019, note}`: `tbc` links an open register item (shown as "Decision needed R-019"), `note` is internal and not printed |
| `signoff` | Everyone who signs: `{name, designation, department, organisation, signing_for, status}`. Client signatories are listed first; `status` is `Pending` (default) or `Signed`. Without it the requirements document has one client and one supplier block to fill in |
| `notifications` | `{event, recipient, template}`. document section 1.6 |
| `integrations` | `{system, purpose, direction, notes}`, and how it works: `trigger` (what starts the exchange), `data` (what goes across) and `on_failure` (what happens when it fails). With these the document adds a table "How each exchange works"; one left out shows "To be confirmed" and is warned about |
| `nfr` | `{area, requirement}` |
| `glossary` | `{term, meaning}`. document section 1.5 |
| `process_flow` | `{title, steps: [{name, role, optional, status}], reject, notes: [...]}` (`notes` is a list, even of one note). Drawn as a diagram (mock-up URL `#/__flow`), screenshotted and placed in document section 1.3, so it always matches the statuses |
| `timeline` | The project timeline chapter (below) |
| `extra_sections` | Free-form document sections after the NFRs: `{title, appendix, content: [{heading} \| {text} \| {bullets} \| {table: {header, rows}} \| {image, caption}]}`. `appendix: true` puts it after sign-off as Appendix A, B… Text may use `{client}` and `{system}`. In a table, an unquoted `No` or `Yes` is printed as that word (a first column headed `No` is the narrow numbering column); quote `"On"`, `"Off"`, `"True"` and `"False"` to keep those exact words |

Optional files next to `app.yaml`: `client-logo.png` (document cover) and `process-flow.png` (document section 1.3).

## Themes

`project.theme` is the look of the client's screens, in the mock-up and so in the document's pictures:

| Theme | Look | When |
|---|---|---|
| `desk` | Calm and ordered: true greys, white cards on a soft grey ground, hairlines that start where the text starts, Geist type, the project's `primary_color` as the one accent (Cobalt `#1F5FBF` when none is set). One solid button per screen, Approve never green and Reject never red, statuses as a dot and a word. Words in sentence case | **New projects**, unless the platform is Joget |
| `joget` | What Joget DX delivers without custom UI work: dark side menu, labels beside fields | New projects on Joget, and **every spec without a `theme`** |
| `modern` | A light, branded custom build with icons and soft shadows | On request |
| `vivid` | A bold showcase: dark gradient menu, coloured header band | Demos and pitches |

A new project's spec is written with `theme: desk`, or `theme: joget` when the platform is Joget
(`mockup.default_theme()`; `new_project.py` says which). A spec without `theme` keeps `joget`, the look it
always had, so no existing project changes look by itself: set `theme: desk` to move one over (its
screenshots are then out of date). In `desk`, write the spec's own words (titles, menu items, labels,
buttons) in sentence case: the mock-up draws them as written, and its own words (Sign out, Clear filters,
Approval progress) already are. Status colours there: `green` is done, `amber` needs attention (orange),
`red` refused or failed, `grey` neutral; a status without a colour whose name says it waits or is in
progress (Pending, Submitted, In Review) takes the accent. Of several `primary` buttons on a screen the first
is drawn solid and the others as the secondary tier; a `danger` button is red words in an outlined button
(solid red only in its dialog), and one that refuses (Reject, Decline, Return, Send back) is a plain one.

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

**Moves the system makes on its own.** A date passing (Loaned Out becomes Overdue) or a linked record moving
is not a button. List those statuses under `auto` as well as `next`:

```yaml
  - {id: loaned-out, name: Loaned Out, next: [returned, overdue], auto: [overdue]}
```

The build then no longer lists them as moves no button makes (it names them as automatic), and the
document's status rules say "Overdue (automatic)". The build stops when `auto` names a status that is not
in the status's `next`.

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

A screen for managing users, roles or permissions counts as user management in the platform check (`screen:user management`): give its list `data` a name like `users`, `roles` or `user_groups`, or limit it to admin roles (`roles`) with a title or menu label about users, roles or permissions.

| `type` | Keys |
|---|---|
| `login` | none |
| `dashboard` | `stats: [{label, value}]` or computed `{label, count: all}` / `{label, count: {status: [...]}}` (counted over the screen's list data), optional `list`, `buttons`. The document lists what each figure counts: a computed one is described from its rule; give a typed-in `value` a `formula`, in words ("Entitlement for the year, less approved days"), or it shows "To be confirmed" |
| `list` | `list`, `buttons` |
| `form` | `sections`, `buttons`; optional `data` so `?record=` pre-fills it, and `record` (a record id from `data`) to show that record when the form is opened without one, as a detail screen does. On a record, the form's buttons follow it: `when` and `set_status` work as on a detail screen. Without a record a button with `when` is not shown, and the main button adds a new record (see [New records](#new-records)) |
| `detail` | `data`, `record` (default record id), `fields_from` (reuse another screen's sections, read-only) or its own `sections`, optional `timeline: [{step, by, at, status, comment}]`, `list` (a related list, below), `buttons`, `screenshot_pages: all` (default: only page 1 is screenshotted). A record's own `timeline` and `notice` (e.g. a rejection notice) override the screen's. A step of the progress with no `at` and no `status` reads **Waiting**; give it a `status` only to say something else (Pending, Not required) |
| `custom` | `html` (raw HTML, for anything the other types cannot show) |

**`list`:** `data` (a key of `data`), `where` (filter, e.g. `{status: "Pending Approval"}` or a list of
allowed values `{status: [Submitted, Approved]}`), `where_by_role` (a filter of its own for a role, e.g.
`{approver: {status: Verified}, deployer: {status: Approved}}`, so a task list shows each role the records
waiting for it; a role it does not name gets `where`, and the screenshot shows the role it is taken as).
Where records carry their own `timeline`, `waiting_for_me: true` in a `where` or `when` keeps the records
whose waiting step is handled by whoever is signed in (see [Status moves](#status-moves)),
`columns: [{field, label, chip}]` (`chip: true` shows
the value as a coloured status), `filters: [field, ...]`,
`actions: [{label, to | toast, when, roles, set_status}]` (per row; `to` opens a screen with that row's record; `when:
{status: Draft}` shows the action only on matching rows; `roles` shows it only to those roles, in the
mock-up and in the document's access matrix; `set_status` moves that row's record, see
[Status moves](#status-moves)),
`toolbar: [{label, to | toast, style}]`, `search: [field]` (text search boxes, partial match). In the
mock-up both work on the sample rows: **Search** applies them and **Clear Filters** resets them. `sort` (text for the requirements document), `empty` (empty-state text). Actions and toolbar buttons appear in the requirements document access matrix unless `access: false`.

**A related list on a detail screen.** A detail screen's `list` shows the records of another list that
name the record shown, under its own heading (`title`, default "Related records"): a car's loans, a
customer's orders. `where_record: {field of the list's rows: field of the record shown}` links them, next to
the usual `where`, columns, filters and row actions. It follows the walk-through, is in the screenshot, and
the document describes it under the screen's fields. The build checks both fields; `where_record` anywhere
but a detail screen's list is an error.

```yaml
  - id: car
    type: detail
    data: cars
    list: {data: loans, title: Loan history, where_record: {car: reg_no}, empty: Never loaned out,
           columns: [{field: loan_no, label: Loan}, {field: status, label: Status, chip: true}]}
```

**`sections`:** `[{title, page, page_title, note, fields}]`. Give sections a `page` number to split a
form into steps (tabs); each page gets its own screenshot. On a form in steps the main button (`style:
primary`) is only on the last step; the steps before it have **Next** in its place, and every step after
the first **Previous**. The other buttons (Cancel, Save as Draft) are on every step. A detail screen's
steps keep all their buttons.

**Fields:** `id`, `label`, `type` (`text`, `textarea`, `select`, `radio`, `checkbox`, `date`,
`datetime`, `number`, `file`, `signature`, `user`), `required`, `readonly`, `default`, `length`,
`options` or `options_from`, `placeholder`, `help`, `source` and `validation` (both go into
the requirements document data requirement table). `options_from: cars.reg_no` offers every value of that
field in the sample data; with a filter, `options_from: {list: cars, field: reg_no, where: {status:
Available}}` offers only the records the `where` lets through (same form as a list's `where`), and follows
the walk-through: a car put on loan leaves the drop-down. The document says "From Cars where Status is
Available". A `checkbox` with `options` is one tick box per option;
without them it is a single tick box (I agree, Urgent), ticked when the record's value is `true` or `Yes`.

**What the mock-up does with fields.** A `required` field is checked by the main button of a form (`style:
primary`) and by a dialog's confirm button: the first press marks the required fields left empty, on
whichever step of the form they are (on a form in steps the button stays on the last step and names
the step that holds them, marked with a dot), and the second press goes on without them. A read-only field is never
asked for. A `file` field takes a sample file when clicked and a `signature` field signs as the signed-in
role's `user`. None of this is in a screenshot.

**Buttons:** `{label, style (primary | danger), to, toast, dialog, roles, when, example, set_status, also_move, creates}`. With a
red `primary_color` a `danger` button is drawn as an outline, so Reject cannot be mistaken for the main
button beside it. `toast` shows a
message (e.g. "Draft saved"; `{id}` in it is the id of the record the button added or moved); `roles` limits who sees the button; `creates` decides
whether a button of a new form adds a record (see [New records](#new-records)); `when` shows it only for matching
records on detail screens and on forms opened on a record; `set_status` moves the record to another status,
and `also_move` a record it names in another list with it (see [Status moves](#status-moves)). Put a label that starts with Yes, No, On or Off in quotes (`label: "Yes,
cancel it"`): YAML otherwise reads it as true or false, and the build stops. Primary, danger and dialog buttons appear as actions in the requirements document access matrix,
except `example: true` buttons (demo-only buttons that open a dialog for screenshots).

## Dialogs

`{id, title, message, fields, list, doc_table, confirm: {label, style, toast, to, set_status}}`. `doc_table: false` (formerly `srs_table`) leaves its field table out of the requirements document. A button opens it with
`dialog: <id>`. `list` shows a table inside the dialog (same format as a screen list). Dialog fields
appear in the requirements document under the screen that opens it.

The confirm button always closes the dialog: it then opens its `to` screen, or stays on the current
screen when it has none (with its `toast`, if any). A dialog without `confirm` gets an OK button that
closes it. Cancel, the cross, Esc and a click outside the dialog close it too. Opening and closing a dialog
leaves no step in the browser's history, so Back goes to the screen before.

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

- **One button for several steps.** Where one Approve button serves a chain of approvers, say where each
  status moves to: `set_status: {Submitted: verified, Verified: approved, Approved: deployed}`. A record in
  a status the button does not name stays as it is. Where the chain can skip steps, the status does not
  say whose turn it is: name the steps of the records' `timeline` instead,
  `set_status: {Verification: verified, Approval: approved, Deployment: deployed}`. The step the record is
  waiting at decides; a step name is looked for before a status.
- **Whose turn it is.** `waiting_for_me: true` in a list's `where` or a button's or action's `when` is true
  for a record whose waiting step (the first line of its own `timeline` with no `at`, not marked Skipped)
  names the signed-in role's `user` in `by`. A task list with `where: {waiting_for_me: true}` then shows
  each role its own work, and follows as a record moves on. It needs records with their own `timeline`
  and roles with a `user`.
- **Which record.** On a detail screen, or a form opened on a record, it is that record, also from a dialog
  opened there. On a row action of a list it is that row. When the button opens a dialog, put `set_status`
  on the dialog's `confirm`: the record moves when the dialog is confirmed, not when it opens.
- **A linked record moves along.** Where the record names a record of another list (a loan's `car` is a
  car's `reg_no`), `also_move` on the same button moves that one too:

  ```yaml
  confirm:
    label: Approve Loan
    set_status: on-loan
    also_move: {data: cars, link: car, key: reg_no, set_status: loaned-out, copy: {loaned_to: customer, due_back: return_date}}
  ```

  `data` is the linked list, `link` the field of this record that names the linked one, `key` the field of
  the linked list it is matched against (default: the list's first field, its identifier), `set_status` the
  status the linked record moves to (one status), and the optional `copy` takes values across: `{field
  there: field here}`. Give a list of them to move several. Everything drawn from the linked record follows
  (the car shows Loaned Out on the dashboard). Its progress is not filled in. The build checks each part
  against the data and the statuses, and the move against the linked records' status rules (`next`): where a
  linked record is comes from the sample data, the records linked from those the button can act on.
- **Progress.** When the record (or the detail screen that shows it) has a `timeline`, the first step still
  waiting (no `at`, and not marked Skipped or Not required) is filled in with the new status, the signed-in role's `user` (or its name), the time,
  and what was typed into the dialog as the comment. With no step waiting, a line is added. After a final
  status (`next: []`) the steps still waiting are dropped.
- **Kept for the session, never in the spec.** The move lasts for the walk-through (see
  [The walk-through](#the-walk-through)): through a reload and **Update ready**, and on every laptop in the
  room when the mock-up is served. **Reset sample data** on the presenter's bar starts again. Screenshots are
  not affected, and adding `set_status` does not make them out of date.
- **Checked against the status rules.** The build stops when `set_status` names no status, when the button
  has no record to move (a toolbar or dashboard button), or when the move contradicts `next`: where the
  record is comes from the button's `when: {status: ...}`, or the `where` of its list. The build also lists
  the moves the rules allow that no button makes, so you can see what the walk-through cannot show.

## New records

On a form opened without a record, the main button (`style: primary`) adds a record to the list the form
fills in, so the presenter can submit a request and show it land in the approver's list. Then it goes where
the button goes (`to`) with its `toast`. Nothing to add to the spec when the form can be tied to its list; the
build says which forms add a record ("New records: Submit on New Leave Application adds a record to the
applications list, as Pending Approval") and which main buttons only show their message.

- **Which list.** The screen's `data`; else the list of a detail screen that shows the form's fields
  (`fields_from: <this form>`); else the list on the screen the button goes to, when most of the form's
  fields are fields of that list. `creates: <data list>` on the button names it outright.
- **Which buttons.** The form's main button. `creates: true` makes another button add one too (Save as Draft
  with `set_status: draft`); `creates: false` stops the main button. A button with `when` is not shown on an
  empty form. When the button opens a dialog, the dialog's confirm button adds the record. A form that names
  its own `record` is never empty and adds nothing.
- **Its status.** The button's `set_status` (or the confirm button's), stored as the list's records store
  theirs (by name, or by id where they use ids). Without one: the first status of `statuses`, or the one
  after it when that is a draft and the button is not about a draft.
- **Its values.** What was typed. A field left empty takes its `default`, a sample file or the signer's
  name, a choice, or the value of a sample record; never made-up filler text. So that a new request is never
  the twin of one already waiting, that record is a finished one (a status with no `next`), or else one at
  another stage, a different one for each new record. Dates come from a record at the same stage and keep
  the distance they have there from a date that was typed. A choice from a list whose records have a status
  of their own (a car, an asset) takes one that no open record holds, where there is one, and the fields
  that belong to it (the car's model) come from that record; a category (a leave type) is shared as usual.
  Other fields of the list that are not on the form come from a sample record in the same status. Fields such as
  `submitted_by`, `requester`, `applicant` or `employee` take the signed-in role's `user`, and `submitted`,
  `created` or `request_date` the time now, in the format the sample data uses.
- **Its id.** The next one after the list's own: LN-2026-00142 is followed by LN-2026-00143, 7 by 8.
- **Its progress.** Where the list's records (or its detail screen) have a `timeline`, the new record gets
  the same steps: the first done by whoever is signed in, now, the next ones waiting for the same people as
  in the sample, so `waiting_for_me` task lists show it to the right person.
- It shows in every list, count and task list its values match, its detail screen opens, and the buttons
  that move records work on it. `also_move` on the same button moves the record it names along.

```yaml
buttons:
  - {label: Save as Draft, creates: true, set_status: draft, toast: "Draft {id} saved", to: my-applications}
  - {label: Submit, style: primary, toast: "Application {id} submitted", to: my-applications}
```

## The walk-through

What the mock-up changes while it is acted out (records added and moved) is kept for the browser tab's
session: through a reload, and through **Update ready** after a change in a live session. Served by
`mockup.py serve` (also with `--lan`, and from the page that lists every mock-up), it is shared: a change
made in one browser shows in every other within a few seconds, each person keeping their own role (**View
as**); the last change to a record wins. It is kept in the server's memory only: restarting the server
starts from the sample data, and it never changes the spec, the screenshots or the document. Opened from the
file without a server, each tab keeps its own.

**Reset sample data** on the presenter's bar (shown once something has changed) asks first, then puts the
sample data back, for everyone viewing the mock-up. When a new build changes the sample data, the changes
that still fit are kept (records added, changed fields the records still have, statuses that still exist)
and the rest are dropped. Screenshots always show the sample data.

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

## Platform fit

`platform_fit` is written by `tools/platform_fit.py apply` (the `platform-fit` skill), not by hand: every
kind of feature in the spec that the project's platform does not give as standard, with its support level,
what it takes, the building block, where it is used (`used_in`: the screen or dialog), the parts of the
mock-up that show it (`elements`: `{screen or dialog, element}`, the element named as the mock-up names it,
such as `stat:Leave balance (days)` or `field:signature`) and the page of the product's documentation that
says so. It is internal: it never appears in the requirements document, and changing it does not make the
screenshots out of date. Run the skill again when the spec or the platform sheets change.

**Custom work in the mock-up.** While presenting, each part that is `custom` carries a small tag
**Custom development**, and each part that is `not supported` **Not standard on <product>**; hovering it
says what the feature is and what it takes. A `platform_fit` written before it named the elements tags the
heading of each screen it is used on. What the project's own mock-up code adds is tagged too (see below),
unless the platform check found that code standard or configuration. Only the label, the feature and what it
takes reach the mock-up: never the sheet row, the building block or the source, and never mandays or cost.
**Custom work** on the presenter's bar hides the tags (the choice is remembered); they are never in a
screenshot or the requirements document.

## The project's own mock-up code

For what the spec cannot describe (a behaviour, an interaction, a layout of its own), a project can have
`spec/mockup.js` and `spec/mockup.css`. They belong to that project alone: the build copies them into the
mock-up, loaded after the engine, and they count as part of what the screenshots show. They are kept and
put back by a live session's undo. The script works through `window.Mockup`:

| | |
|---|---|
| `Mockup.onRender(fn)` | Calls `fn({screen, role, q, root})` after every screen is drawn. `screen` is the screen's id as text (`"review-application"`, `"__flow"` for the process flow), not the screen's settings: find those with `Mockup.spec.screens.find((s) => s.id === view.screen)`. `role` is the role's id, `q` the address's settings (`record`, `page`, `dialog`) and `root` the element the mock-up is drawn in |
| `Mockup.go(screen, {record, page})`, `Mockup.render()`, `Mockup.route()` | Move to a screen, draw the current one again, read where the mock-up is |
| `Mockup.spec`, `Mockup.data` | The spec and its sample data, as the walk-through has changed it |
| `Mockup.changed()` | Call after changing `Mockup.data`: the change is kept for the walk-through and shared with the room like the engine's own |
| `Mockup.custom(el, note)` | Tags `el` **Custom development** while presenting; `note` (optional) is what hovering it says it takes. `Mockup.custom(el, false)` says `el` is standard on the platform: it is never tagged |
| `Mockup.matches(condition, record)`, `Mockup.toast(text)` | The engine's test for `when` and `where`; a message |

Give what the script adds a `data-el="region:<name>"` and it can be commented on like the rest. What it adds
to a screen counts as custom work and is tagged while presenting (see [Platform fit](#platform-fit)), unless
`Mockup.custom(el, false)` says otherwise. An error in it is written to the browser's console and never stops
the mock-up. Describe the behaviour in the spec's `requirements` too: the requirements document is written
from the spec, not from this code.

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
filter, search field or `where` / `where_by_role` / `when` / `count` condition naming a field the sample data
does not have; a `where_by_role` naming a role that does not exist;
an `options_from` that is not `<data list>.<field>` or `{list, field, where}` naming fields of that list;
a `where_record` that is not on a detail screen's list or names a field neither record has; an `auto` that
is not a status in its status's `next`; a field type that is not one of the list above; a
`record` that is not in the data; a role or dialog id used twice; a button label that YAML read as true
or false; a `creates` that is not on a form's button, names no data list, or is on a form that shows its
own record; a `set_status` or `also_move` that cannot work or contradicts the status rules (see
[Status moves](#status-moves)); a single text or number where a list or a set of settings belongs (a
`process_flow` `notes`, a screen's `roles`, a list's `columns`, a field's `options` …), which would leave
the mock-up an empty page; a form's `record` without the screen's `data`. It also reports a setting that
nearly spells a real one, such as `colums` or `tittle`, with the name it expects.

Settings the format does not know at all are **warnings**: the build goes on and lists them, because the
mock-up ignores them. A key with no value is pointed out as a likely comma inside unquoted text between
`{ }` (`{label: Yes, approve}` becomes a label and a stray `approve`). Start a note of your own with an
underscore (`_note: ask about the balance`) and it is never warned about.

When `mockup.py screenshots` finds a screen the mock-up cannot draw, it stops with the name of that screen,
the error the browser reported and the likely cause, instead of waiting in vain.

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
