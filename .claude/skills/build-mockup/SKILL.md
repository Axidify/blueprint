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
- Ask the user, if not already known:
  - **Theme:** `joget` (default for Joget projects: shows what Joget delivers without custom UI),
    `modern` (custom builds, or clients who expect a branded UI) or `vivid` (bold showcase look for
    demos and pitches: dark gradient menu, coloured header band, gradient buttons).
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
   `{status it is in: status it moves to}` for every step. Submit on a new, empty form has no record to move
   and keeps its message. The build refuses a move the status rules do not allow, and lists the
   allowed moves no button makes: decide for each whether the client should be able to see it. Where each
   role has a task list, make it show every role the records waiting for it: `where: {waiting_for_me:
   true}` when the sample records carry their approval progress (`timeline`) and the roles a `user`,
   otherwise `where_by_role` by status. Check that each role can open the record it must act on by
   clicking, not only by its address. Every list
   gets explicit columns and filters (GP-05). Every figure on a dashboard says what it counts
   (GP-03): use `count` where it can be counted from the screen's list (the document then describes it),
   and give a typed-in `value` a `formula` in words. Leave the formula out when the client has not defined
   the figure, and add a register question for it.
4. Realistic sample data in the client's language (Malaysian names, real-looking reference numbers).
   Never use real customer data.
5. Requirements: write the functional requirements you are confident about. Where something is not yet
   decided, do not invent it: add a register item (`type: question`, `stage: workshop-1` or `mockup`) so it
   goes on the BA's list, and show a sensible placeholder on the screen.

## 3. Build and check

1. `python -I tools/mockup.py build projects/<slug>` — fix any spec errors it reports.
2. `python -I tools/mockup.py screenshots projects/<slug>` and look at every screenshot. Check for layout
   problems, empty lists, wrong roles, and leftover sample text. Screens are captured 1000 pixels wide so
   their text is readable in the requirements document; if the command says a screen was taken wider
   because it does not fit, its text will print smaller: consider fewer or shorter list columns.
3. Render the register if you added items: `python -I tools/register.py render projects/<slug>`.

## 4. Hand over

Tell the user:
- How to present it: `python -I tools/mockup.py serve projects/<slug>` opens it at http://localhost:8765.
  Add `--lan` so people in the room can comment from their own laptops. It also opens straight from
  `projects/<slug>/mockup/index.html` without the server (comments are then exported with a button).
- How to act the process out: the action buttons move the sample record to its next status, and lists,
  counts and buttons follow. Reloading the page (F5) puts the sample data back for the next run.
- How feedback works: press **Feedback** (or F2), click any element, type a comment. Comments are saved
  to `projects/<slug>/feedback/feedback.json`. The window that started the mock-up must stay open: if it
  is closed, the mock-up says in red that a comment was not saved and keeps it in the browser until the
  mock-up is started again and **Try again** is pressed in the Feedback panel.
- The open questions you added to the register, so the BA covers them in the session. For each screen
  and list, the BA should ask "is this element needed?" and "which columns?" (GP-05, GP-06), because a
  document review cannot catch those later.
