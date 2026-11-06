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
   (`green`, `amber`, `red` or `grey`) so the mock-up does not have to guess it from the wording.
3. Screens: one per menu item, plus detail, review and dialog screens for each workflow step. Every list
   gets explicit columns and filters (GP-05). Every KPI on a dashboard gets a `description` stating its
   formula or saying it is still to be defined (GP-03).
4. Realistic sample data in the client's language (Malaysian names, real-looking reference numbers).
   Never use real customer data.
5. Requirements: write the functional requirements you are confident about. Where something is not yet
   decided, do not invent it: add a register item (`type: question`, `stage: workshop-1` or `mockup`) so it
   goes on the BA's list, and show a sensible placeholder on the screen.

## 3. Build and check

1. `python -I tools/mockup.py build projects/<slug>` — fix any spec errors it reports.
2. `python -I tools/mockup.py screenshots projects/<slug>` and look at every screenshot. Check for layout
   problems, empty lists, wrong roles, and leftover sample text.
3. Render the register if you added items: `python -I tools/register.py render projects/<slug>`.

## 4. Hand over

Tell the user:
- How to present it: `python -I tools/mockup.py serve projects/<slug>` opens it at http://localhost:8765.
  Add `--lan` so people in the room can comment from their own laptops. It also opens straight from
  `projects/<slug>/mockup/index.html` without the server (comments are then exported with a button).
- How feedback works: press **Feedback** (or F2), click any element, type a comment. Comments are saved
  to `projects/<slug>/feedback/feedback.json`. The window that started the mock-up must stay open: if it
  is closed, the mock-up says in red that a comment was not saved and keeps it in the browser until the
  mock-up is started again and **Try again** is pressed in the Feedback panel.
- The open questions you added to the register, so the BA covers them in the session. For each screen
  and list, the BA should ask "is this element needed?" and "which columns?" (GP-05, GP-06), because a
  document review cannot catch those later.
