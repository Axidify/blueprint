# Building blocks for estimating

Estimate by counting building blocks, not by module. A module called "Dashboard" can be 2 days or 30
depending on what is inside it.

**Status: not yet calibrated.** Fill in the rates with your lead dev, then refine them with every project
logged by `close-project`. A rate is mandays per unit, as a range ("2–4") or a single figure; a block left
as TBD is counted in estimates and not priced. Until at least three projects are logged, every estimate
must say it is low-confidence.

## All platforms

Blocks that count on any platform: forms, lists, approvals, integrations, reports, a mobile app, working
offline, planning logic and a second language. Blueprint assumes no platform: the rates are TBD until the
lead developer sets them for the platforms your company builds on, and each project counts on its own.

When a platform's figures differ, add a table of its own, headed `## Platform: <name as the projects name it>`,
with the same columns: a row there with the same ID gives that block its rate on that platform and wins, and
a block only that platform has gets an ID of its own. A project is never priced from another platform's table.

| ID | Building block | What drives the effort | Rate (MD) | Confidence |
|---|---|---|---|---|
| BB-01 | Form, single page | Fields, validations, lookups | TBD | – |
| BB-02 | Form, several pages | Pages, conditional sections, calculated fields | TBD | – |
| BB-03 | Workflow step (approval) | Routing rule, reject path, notifications | TBD | – |
| BB-04 | Digital signature capture | Number of signers, storing the image in PDFs | TBD | – |
| BB-05 | Drawing or markup on an image | Inspection diagrams | TBD | – |
| BB-06 | List with filters | Columns, filters, actions | TBD | – |
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
| BB-31 | Mobile app foundation, per app | Platforms (Android, iOS or both), sign-in, menus, build and distribution, supported devices | TBD | – |
| BB-32 | Mobile app screen, per screen | Fields and states shown, actions, steps in a flow | TBD | – |
| BB-33 | Camera photo on the phone, per place it is taken | Photos per record, categories, size and compression, upload | TBD | – |
| BB-34 | Barcode, QR or VIN scan, per place it is scanned | Code types, typing it when the scan fails, checking it against the data | TBD | – |
| BB-35 | Signature on the phone, per place it is signed | Who signs, no-signature reasons, where the image goes (PDF, record) | TBD | – |
| BB-36 | Location on the phone (GPS), per place it is recorded | Recorded once or tracked, accuracy, shown on a map | TBD | – |
| BB-37 | Push notification, per event | Recipients, what tapping it opens, the service that sends it | TBD | – |
| BB-38 | Offline working foundation, per app | How long offline, what is kept on the phone, sync, unsent changes shown, retries | TBD | – |
| BB-39 | Offline data, per kind of record | What is downloaded to the phone, what is sent back, attachments | TBD | – |
| BB-40 | Sync conflict rule, per kind of record changed in two places | Which change wins, what the user is told, records cancelled or reassigned meanwhile | TBD | – |
| BB-41 | Planning board, per board | Calendar or timeline view, drag to assign, capacity shown, filters | TBD | – |
| BB-42 | Scheduling rule, per rule | Time slots, capacity limits, availability, cut-off times, what happens when it is broken | TBD | – |
| BB-43 | Automatic grouping or assignment, per method | Route or area grouping, suggested assignment, inputs (addresses, distances), overriding it | TBD | – |
| BB-44 | Second language, per language added | Screens, notifications and documents translated, who translates, switching language, data entered in two languages | TBD | – |

### What each block counts

Count one unit for each of the things below. A question under a block is one to ask before its count and
rate settle; the `estimate` skill turns them into workshop questions.

**Forms, lists and workflow**

- **BB-01 Form, single page** – one per form on one page. Includes its fields, validations, lookups and
  saving. *Ask:* How many fields, and which are lookups? Which checks must pass before saving?
- **BB-02 Form, several pages** – one per form that runs over several pages or tabs. Includes moving between
  pages, conditional sections and calculated fields. *Ask:* Which sections appear only in some cases? What is
  calculated, and from what?
- **BB-03 Workflow step (approval)** – one per step a record waits at. Includes who it goes to, approve,
  reject or return, and the notifications. *Ask:* Who approves, and who stands in when they are away? What
  happens on reject?
- **BB-04 Digital signature capture** – one per place a signature is taken. *Ask:* How many signers? Where
  does the signature appear (the record, a PDF)?
- **BB-05 Drawing or markup on an image** – one per image people draw on. *Ask:* What is marked (damage,
  areas)? Is the marked image kept or printed?
- **BB-06 List with filters** – one per list. Includes its columns, filters, search, sorting and row
  actions. *Ask:* Which columns and filters? Who sees which rows?
- **BB-07 Operational dashboard** – one per dashboard of counts and lists. *Ask:* Which figures, for whom,
  and what does clicking one open?
- **BB-08 KPI dashboard with custom calculations** – one per dashboard whose figures need formulas. *Ask:*
  The formula of each figure, its period and calendar (working days, holidays)? Charts?
- **BB-09 External API integration, per endpoint** – one per call to or from another system. Includes
  authentication, mapping, error handling and testing with the other side. *Ask:* What starts it, what goes
  across, and what happens when it fails? Is there a test environment on the other side?
- **BB-10 Generated PDF document** – one per document layout. *Ask:* Who receives it and how (download,
  e-mail)? Signatures or a letterhead on it?
- **BB-11 Scheduled job or reminder** – one per job. *Ask:* When does it run, and when does it stop? Who is
  told?
- **BB-12 E-mail notification, per event** – one per event that sends a message. *Ask:* Who receives it,
  and what does it say? Is the wording set by the client?
- **BB-13 Excel export** – one per export. *Ask:* Which columns and rows, and how many at most?
- **BB-14 Role with its own menus** – one per role. Includes its menus, what it may do and the data it sees.
  *Ask:* What does this role only see, and what may it change?
- **BB-15 Admin CRUD screen (master data)** – one per kind of master data kept in the system. *Ask:* Who
  maintains it? What must be unique, and what happens to records using an entry that is removed?
- **BB-16 AD / SSO login integration** – one per sign-in method. *Ask:* Which directory or provider? How do
  groups map to roles? Do outside users sign in differently?
- **BB-17 Audit trail** – one per kind of record whose changes are logged. *Ask:* Which actions, old and new
  values, who may see the log, and for how long is it kept?
- **BB-18 Environment migration (dev → test → prod)** – one per environment the system is moved to. *Ask:*
  How many environments, and who deploys to the client's?

**Mobile app**

- **BB-31 Mobile app foundation** – one per app (one per platform when Android and iOS are built
  separately). Includes the project set-up, sign-in on the phone, the menu and navigation, app versions and
  updates, building the installer and putting it on the store or the company's device management, and the
  devices and OS versions tested. *Ask:* Android, iOS or both? Company phones or the users' own? How is the
  app installed and updated (store, device management, a file)? Which OS versions and screen sizes?
- **BB-32 Mobile app screen** – one per screen on the phone (in a spec, the `m-` screens): a list, a detail,
  each step of a multi-step flow. A dialog that only confirms is part of its screen. Includes the layout for
  phone sizes, its states (empty, loading, waiting to upload) and its actions. *Ask:* What does the user do on
  this screen that they cannot do in the web portal? Must it also work on a tablet?
- **BB-33 Camera photo** – one per place in the app where a photo is taken. Includes taking or choosing the
  picture, compressing it, its category or caption, and uploading it (later, when offline). *Ask:* How many
  photos per record, and is any required? Any size or quality rule? How long are photos kept?
- **BB-34 Barcode, QR or VIN scan** – one per place a code is scanned. Includes the camera scanner, typing
  the code when it cannot be read, and checking it against the record. *Ask:* Which code types? What happens
  when the scanned code is not the expected one? Is a dedicated scanner device used?
- **BB-35 Signature on the phone** – one per place a signature is captured. Includes the signing pad, the
  signer's name, the reason when nobody signs, and storing the image (and placing it in a generated PDF,
  which is its own block). *Ask:* Who signs, and what if they are not there? Must the signature appear on a
  document?
- **BB-36 Location (GPS)** – one per place a location is recorded. Includes asking for permission, accuracy
  and what happens without a fix. Live tracking or a map view is more than one unit. *Ask:* A position at a
  moment, or tracking? Who sees it, and on a map?
- **BB-37 Push notification** – one per event. Includes the message, who gets it and what tapping it opens;
  the first one also sets up the sending service. *Ask:* Which events must reach the phone at once, rather
  than by e-mail or when the app is opened?

**Offline working**

- **BB-38 Offline working foundation** – one per app that works without a signal. Includes storing data on
  the phone (and protecting it), the queue of unsent changes, sending it when back online with retries,
  showing what is still waiting, and sign-in while offline. *Ask:* How long must the app work offline (a
  trip, a shift, days)? What must the user see about unsent work? What if the phone is lost before it syncs?
- **BB-39 Offline data** – one per kind of record the app keeps or changes offline (tasks, photos, parts
  used …). Includes what is downloaded and when, what is sent back, and attachments. *Ask:* Which records
  must be on the phone, and how many (a day's tasks or the whole catalogue)? How fresh must they be?
- **BB-40 Sync conflict rule** – one per kind of record that can be changed both on the phone and elsewhere
  (the office, another phone) while offline. Records only the phone changes need none. Includes the rule for
  which change wins, what the user is told, and records cancelled or reassigned while the phone was offline.
  *Ask:* If the office changes or cancels a task while the driver is offline, what happens to the driver's
  update? Who decides, the system or a person?

**Planning and scheduling**

- **BB-41 Planning board** – one per board where people assign work to people, vehicles or time slots.
  Includes the calendar or timeline view, assigning (dragging or picking), the capacity used so far and its
  filters. A plain list of plans is a list, not a board. *Ask:* Who plans, how far ahead, and how many items
  per plan? Does a plan need approval before it is released?
- **BB-42 Scheduling rule** – one per rule the plan must follow or check: time slots, capacity per vehicle or
  person, working hours, availability, cut-off times. Includes what the planner is told when it is broken and
  whether they may override it. *Ask:* Which limits are hard and which only warn? Where do capacities and
  availability come from, and who keeps them up to date?
- **BB-43 Automatic grouping or assignment** – one per method the system uses to propose a plan: grouping
  stops into routes or areas, suggesting who takes what. Includes its inputs (addresses, distances, map
  data), the planner changing the result, and testing it on real data. Route optimisation with a map
  service is usually several units or a figure from the lead developer. *Ask:* Must the system propose the
  plan, or does a person build it? By area, by a fixed list or by distance? Does it need a map service?

**Languages**

- **BB-44 Second language** – one per language added beyond the first, for the whole system (web and app
  together); a mobile app and a web portal built separately are one each. Includes making every label,
  message, e-mail and push notification translatable, the language switch (or the language taken from the
  user's profile or phone), dates and numbers in that language's format, and checking every screen in it.
  The translating itself is listed as an assumption (who does it, by when), not counted here; generated
  documents and master data in two languages (names of items, reasons) add to it. Do not count a second
  language as extra screens. *Ask:* Which parts must be in the second language: the app, the web portal,
  notifications, generated documents? Who provides and checks the translations? Is any data entered or
  shown in both languages? Is any language written right to left?

## Other work

Work around the build. Set each item as a share of the building-block subtotal ("10–15%") or as fixed
mandays ("2–3 MD"). An item left as TBD is listed in estimates and not priced. Add or remove rows to match
how your company scopes projects. These are the company's starting figures: each project's split is agreed
with the lead developer for what that project needs, and an estimate line can carry its own figure.

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
