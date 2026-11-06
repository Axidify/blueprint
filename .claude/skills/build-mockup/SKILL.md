---
name: build-mockup
description: Create or extend the clickable mock-up for a project from a brief, workshop notes, an existing requirements document or the project register, ready to present to the client in a requirement session. Use when the user asks for a mock-up, screens, a prototype or a demo for a project, or to prepare for workshop 2.
---

# Build a mock-up

The mock-up is generated from `projects/<slug>/spec/app.yaml`. The same spec later generates the requirements document,
so every decision put into the spec shows up in both. Format: `docs/spec-format.md`. Working example:
`examples/leave-request/spec/app.yaml`.

## 1. Gather inputs

- The project folder (create it with the `new-project` skill if it does not exist).
- Whatever exists: the brief, the SOW, workshop notes or transcripts, a requirements document draft, `register.json`.
- Ask the user only what is not known yet:
  - **Theme** (`docs/spec-format.md`, Themes): a new spec gets `theme: desk` (the calm, ordered default,
    in the project's colour), or `theme: joget` when the platform is Joget (shows what Joget delivers
    without custom UI). Offer `modern` (a branded custom build) or `vivid` (a bold showcase for demos) only
    when asked. Always write `theme` into a new spec. A spec that has none keeps `joget`: never change an
    existing project's theme unless the user asks (its screenshots would be out of date).
    In `desk`, write titles, menu items, labels and buttons in sentence case ("New application", "Leave
    type"), give the screen's main action `style: primary` and leave the rest unstyled.
  - Brand colour, and the client logo (put it at `spec/client-logo.png`).

## 2. Write the spec

1. Roles first, each with a data scope. Ask yourself the GP-01 question: who only needs to *see* the data?
2. Statuses for every record that moves through a workflow, including the unhappy ones (rejected,
   cancelled, returned) — see GP-02 and GP-09 in `knowledge/gap-patterns.md`. Give each status a `color`
   (`green`, `amber`, `red` or `grey`) so the mock-up does not have to guess it from the wording, and its
   rules where they are known: `edit`, `cancel`, `delete` (role ids, `all` or `none`) and `next` (the
   statuses it can move to). Leave a rule out when it is not decided and add a register question for it:
   never guess who may cancel or delete (GP-02).
3. Screens: one per menu item, plus detail, review and dialog screens for each workflow step. Give every
   button that moves an existing record on (approve, reject, cancel, return, resubmit, complete)
   `set_status` and a `when` for the statuses it shows in, so the client can act the process out in the
   session: approve as one role, switch role, see what the next person sees. On a button that opens a
   dialog, `set_status` goes on the dialog's `confirm`; where one dialog serves a chain of approvers, give it
   `{status it is in: status it moves to}` for every step. Submit on a new, empty form adds a record to
   the list the form fills in, so the client sees it land in the approver's list: tie the form to its list
   (the screen's `data`, or a detail screen with `fields_from` the form), give Submit the status a new record
   starts in (`set_status`, else the first status that is not a draft is used), and Save as Draft
   `creates: true` with `set_status: draft` where drafts are shown (`docs/spec-format.md`, New records). The
   build says which forms add a record and which main buttons only show their message. Where the move also changes a record of another list that this one names (approving
   a loan puts its courtesy car on loan), add `also_move` on the same button (`docs/spec-format.md`, Status
   moves), so the dashboard of the other list follows too. The build refuses a move the status rules do not allow, and lists the
   allowed moves no button makes: decide for each whether the client should be able to see it. Where each
   role has a task list, make it show every role the records waiting for it: `where: {waiting_for_me:
   true}` when the sample records carry their approval progress (`timeline`) and the roles a `user`,
   otherwise `where_by_role` by status. Check that each role can open the record it must act on by
   clicking, not only by its address. Moves the system makes on its own (a date passing, a record that
   follows its linked one) go under the status's `auto` as well as `next`: the build then stops listing
   them as moves no button makes. A future step of a record's progress needs no `status`: it reads
   "Waiting" (never write "Not Started"). Where a record's own screen should show the records that name it
   (a car's loans, a customer's orders), give the detail screen a `list` with `where_record`; where a
   drop-down should offer only some records (the cars available), use `options_from: {list, field, where}`.
   A form in steps shows its main button on the last step only, with Next and Previous before it. Every list
   gets explicit columns and filters (GP-05). Every figure on a dashboard says what it counts
   (GP-03): use `count` where it can be counted from the screen's list (the document then describes it),
   and give a typed-in `value` a `formula` in words. Leave the formula out when the client has not defined
   the figure, and add a register question for it.
4. Realistic sample data in the client's language (Malaysian names, real-looking reference numbers).
   Never use real customer data.
5. Requirements: write the functional requirements you are confident about. Where something is not yet
   decided, do not invent it: add a register item (`type: question`, `stage: workshop-1` or `mockup`) with
   `python -I tools/register.py add projects/<slug> --file <items.json>` (`--check` first: it names likely
   duplicates) so it goes on the BA's list, and show a sensible placeholder on the screen.
6. **Build everything; label custom work.** Whatever the client should see is in the mock-up. What the spec
   cannot describe (a behaviour, a layout, an interaction, an integration, faked with sample data) is built
   in the project's own mock-up code, `spec/mockup.js` and `spec/mockup.css` ("The project's own mock-up
   code" in `docs/spec-format.md`), and its behaviour written into `requirements`. Leave something out only
   when a browser genuinely cannot show it, and tell the user what and why. What is custom work or not
   supported on the platform is tagged in the mock-up while presenting (step 3.3 records it); the project's
   own code is tagged as custom unless you mark a part `Mockup.custom(el, false)` because the platform sheet
   says it is standard. The tags never show mandays, cost or "change request".

## 3. Build and check

1. `python -I tools/mockup.py build projects/<slug>` — fix any spec errors it reports, and the settings it
   says the mock-up ignores (a misspelling, or a comma inside unquoted text between `{ }`).
2. `python -I tools/mockup.py screenshots projects/<slug>` and look at every screenshot. If it stops at a
   screen, it names that screen and the error the browser reported: fix the spec or `spec/mockup.js` there. Check for layout
   problems, empty lists, wrong roles, and leftover sample text. Screens are captured 1000 pixels wide so
   their text is readable in the requirements document; if the command says a screen was taken wider
   because it does not fit, its text will print smaller: consider fewer or shorter list columns.
3. Check it against the platform: `python -I tools/platform_fit.py check projects/<slug>`. Before the client sees
   the mock-up, tell the user which features are custom work or not supported on the project's platform, and
   what the standard way would be. Features no sheet covers, or not yet checked against the product's
   documentation, are looked up with the `platform-fit` skill, which also records the result in the spec
   and the register. `python -I tools/platform_fit.py apply projects/<slug>` then records where each is drawn,
   and the mock-up tags those parts **Custom development** (or **Not standard on <product>**) while
   presenting, never in screenshots.
4. Render the register if you added items: `python -I tools/register.py render projects/<slug>`.

## Hand over

- **What was made:** the mock-up version, its screens (one line), what is built in the project's own
  mock-up code, which features are custom work or not supported on the platform (and the standard way), and
  the open questions added to the register, so the BA covers them in the session. For each screen and list
  the BA should ask "is this element needed?" and "which columns?" (GP-05, GP-06): a document review cannot
  catch those later.
- **Where and for whom:** the mock-up and its screenshots in the project's `mockup` folder, **for the
  client** to see in a session (opened with **Open the mock-up** on `Project overview.html`, or
  `present.cmd`); the register's questions on its **For client** sheet; the custom-work findings
  **internal** (the room sees only the Custom development tags).
- **Next step, in the words to say:** "present the mock-up" (the `present` skill explains the presenter's
  bar, acting the process out and how comments are saved), or first "prepare the workshop" for the agenda.
  For the lead developer, when custom work turned up: "estimate this project".
