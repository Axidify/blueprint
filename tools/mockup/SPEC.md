# Project spec format (`spec/app.yaml`)

One YAML file per project drives both the clickable mock-up (`tools/mockup.py`) and the generated SRS
(`tools/generate_srs.py`). Change the spec, rebuild both, and they stay consistent.
`examples/leave-request/spec/app.yaml` is a complete working example.

## Top level

| Key | Purpose |
|---|---|
| `project` | `name`, `short_name` (shown in the logo box), `client`, `client_short`, `version`, `platform`, `theme` (`joget` or `modern`), `primary_color`, `prepared_by`, `reviewed_by`, `approved_by`, `date`, `history: [{version, date, author, changes}]` (SRS version history table) |
| `overview` | List of paragraphs for the start of SRS section 1.0 |
| `roles` | `id`, `name`, `description`, `scope` (data scope, e.g. "Own branch only"), `user` (sample person shown in the mock-up header) |
| `statuses` | `id`, `name`, `meaning`. Becomes the SRS status table |
| `data` | Sample records, by list name. The first key of each record is its identifier |
| `screens` | The screens (below) |
| `dialogs` | Pop-ups opened by buttons (below) |
| `screenshots` | Extra screenshots beyond one per screen: `{screen, role, record, page, dialog, name}` |
| `requirements` | Functional requirement groups: `{id: FR-XXX-001, title, items: [...]}`. Items are numbered `.1`, `.2` … in the SRS. An item is text, or `{text, tbc: R-019, note}`: `tbc` links an open register item (printed as "(Open issue R-019)"), `note` is internal and not printed |
| `notifications` | `{event, recipient, template}`. SRS section 1.6 |
| `integrations` | `{system, purpose, direction, notes}` |
| `nfr` | `{area, requirement}` |
| `glossary` | `{term, meaning}`. SRS section 1.5 |
| `process_flow` | `{title, steps: [{name, role, optional, status}], reject, notes}`. Drawn as a diagram (mock-up URL `#/__flow`), screenshotted and placed in SRS section 1.3, so it always matches the statuses |
| `extra_sections` | Free-form SRS sections after the NFRs: `{title, appendix, content: [{heading} \| {text} \| {bullets} \| {table: {header, rows}} \| {image, caption}]}`. `appendix: true` puts it after sign-off as Appendix A, B… Text may use `{client}` and `{system}` |

Optional files next to `app.yaml`: `client-logo.png` (SRS cover) and `process-flow.png` (SRS section 1.3).

## Screens

Every screen has `id`, `type`, `title`, and optionally `screenshot_role` (role used for its screenshot; default the first in `roles`), `menu` (label in the side menu; omit for screens
reached by links), `roles` (who can open it; omit for everyone), `description` (SRS text under the
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
`toolbar: [{label, to | toast, style}]`, `search: [field]` (text search boxes, partial match), `sort` (text for the SRS), `empty` (empty-state text). Actions and toolbar buttons appear in the SRS access matrix unless `access: false`.

**`sections`:** `[{title, page, page_title, note, fields}]`. Give sections a `page` number to split a
form into steps (tabs); each page gets its own screenshot.

**Fields:** `id`, `label`, `type` (`text`, `textarea`, `select`, `radio`, `checkbox`, `date`,
`datetime`, `number`, `file`, `signature`, `user`), `required`, `readonly`, `default`, `length`,
`options` or `options_from: list.field`, `placeholder`, `help`, `source` and `validation` (both go into
the SRS data requirement table).

**Buttons:** `{label, style (primary | danger), to, toast, dialog, roles, when, example}`. `toast` shows a
message (e.g. "Draft saved"); `roles` limits who sees the button; `when` shows it only for matching
records on detail screens. Primary, danger and dialog buttons appear as actions in the SRS access matrix,
except `example: true` buttons (demo-only buttons that open a dialog for screenshots).

## Dialogs

`{id, title, message, fields, list, srs_table, confirm: {label, style, toast, to}}`. `srs_table: false` leaves its field table out of the SRS. A button opens it with
`dialog: <id>`. `list` shows a table inside the dialog (same format as a screen list). Dialog fields
appear in the SRS under the screen that opens it.

## Mock-up URLs

`index.html#/<screen>?role=<role>&record=<id>&page=<n>&dialog=<id>&clean=1`. `clean=1` hides the
feedback tools (used for screenshots).

## Cross-references

Never write "section 3.2", "Appendix B" or "Figure 4" in spec text: numbers change whenever screens or
sections are added. Use a reference the generator resolves, and it warns about any literal one it finds:

| Reference | Becomes |
|---|---|
| `{ref:screen:<screen id>}` | "section 3.n" for that screen |
| `{ref:section:roles\|access\|flow\|integrations\|glossary\|notifications\|requirements\|screens\|nfr\|open-issues}` | the fixed section's number |
| `{ref:extra:<extra section title>}` | "section n.0" or "Appendix X" |
| `{ref:req:<FR id>}` | the requirement group id |

`{client}` and `{system}` are replaced with the project's client and system names.
