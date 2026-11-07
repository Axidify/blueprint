---
name: start
description: Blueprint's start menu. Shows the projects on this machine and what needs doing, then asks what the user wants to do and runs the right skill. Use when the user types /start, says hello or "help", asks what this can do or how to use it, or seems unsure where to begin.
---

# Start menu

The person may never have used Blueprint or Claude Code before. Be brief and plain: no jargon, no file
paths unless they need one.

## 1. Check the machine

Run `python -I tools/doctor.py`. If anything required is MISSING, explain the fix in one or two plain
sentences (usually "double-click setup.cmd", or on a Mac "run ./setup.sh") and stop there.

If the company profile is still the placeholder ("Your Company"), ask for the company name and short name,
the currency, and the platforms the company builds on (only offered as choices when a project is created:
each project still says its own), and write them into `workspace/company.yaml`. Blueprint assumes nothing
until then: no platform, no rate, no manday split. Say that the rates and the split are asked with each
project's estimate, and can become the company's standard figures whenever the lead developer says so. Mention that a logo (`workspace/branding/logo.png`), a Word
template (`document-template.docx`) and standard wording (`document-boilerplate.yaml`) can go in the same folder.

## 2. Show where things stand

Run `python -I tools/status.py` and summarise it in a few lines: each project, what stage it is at, and
its suggested next step (the `next:` line, in the words to say to Claude). An `also:` line is a hint for
the lead developer (an estimate missing or older than the spec): mention it to them. Mention anything
waiting in the inbox.

Tell them, once, that every project folder has a page at its top, `Project overview.html`: double-click it
(in the shared folder too) to see each document in the order of the process, who it is for (from the
client, for the client, internal) and the next step, with the words to say. Teammates who only browse the
folder can use it to find their files. A project with a mock-up also has **Open the mock-up** beside it,
which starts the mock-up so comments are saved. If a page is missing or out of date, run
`python -I tools/overview.py build projects/<slug>` (or `build --all`).

A project `status.py` marks as in the **old folder layout** (a `folders:` line) mixes the files people open
with Blueprint's working files. Offer once, in a sentence, to tidy it: say "migrate the folders" and its
documents go into numbered folders in the order of the process (`1 Client documents`, `2 Reviews` …,
`Internal – estimates and change requests`), with Blueprint's files in `_blueprint`. Both layouts work, so it
is their choice; do not offer again if they decline. When they say it: `python -I tools/project.py migrate
<slug> --dry-run`, summarise the moves in a few lines, and once they agree run it without `--dry-run`. It
refuses, with the reason, while the mock-up is open, a live session runs or one of its files is open in Word
or Excel (on anyone's computer): pass the reason on. `--undo` moves a project back.

## 3. Ask what they want to do

Use AskUserQuestion with these options (the tool adds "Other" automatically):

| Option | Then |
|---|---|
| Start a new project | the `new-project` skill |
| Review a document (SRS, URS, draft) | the `review-requirements` skill |
| Build or update a mock-up | the `build-mockup` skill |
| Process the inbox / apply feedback | the `process-inbox` skill (it routes mock-up feedback to `apply-feedback`) |

When the person seems new (they said so, said hello, there are no projects yet, or they are unsure what
Blueprint does), make the first option **Take a ten-minute tour (new here)** → the `tour` skill, in place
of "Build or update a mock-up". The tour runs on a copy of a made-up sample, never on client documents.

If they pick "Other", or mention generating the requirements document, estimating mandays, presenting a mock-up or
closing a project, or what the platform can do, use the matching skill: `generate-requirements`, `estimate`,
`present` (opening a mock-up or the page that lists them, an earlier version, or a live session with the
client), `platform-fit` (what is standard, custom work or not supported on the project's tech stack),
`prep-workshop` (an agenda for the next client session), `mockup-design` (the mock-up's look: the client's
logo, colours, font, menu), `client-answers` (the client answered the open
questions: a returned register, an e-mail or call notes), `uat-scripts` (test scenarios for the client's
testers), `change-request` (the client asked for something during development or UAT: in scope or a
change request?), `tour` (a guided first run), `close-project`. Recording that a document went to the client: `python -I tools/project.py issue <slug>`.
If `python -I tools/project.py check` reports problems, offer to fix them with `--fix`.

If a project is involved and it is not obvious which, ask which one, listing the projects by name.

## Hand over

Invoke the chosen skill and follow it: its own `## Hand over` tells the person what was made, where, for
whom and the next step. If they only wanted to see where things stand, end with the one next step for the
project they care about, in the words to say (from `status.py`), and that `/start` brings this menu back.
