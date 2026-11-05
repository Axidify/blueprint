---
name: start
description: Blueprint's start menu. Shows the projects on this machine and what needs doing, then asks what the user wants to do and runs the right skill. Use when the user types /start, says hello or "help", asks what this can do or how to use it, or seems unsure where to begin.
---

# Start menu

The person may never have used Blueprint or Claude Code before. Be brief and plain: no jargon, no file
paths unless they need one.

## 1. Check the machine

Run `python -I tools/doctor.py`. If anything required is MISSING, explain the fix in one or two plain
sentences (usually "double-click setup.cmd") and stop there.

If the company profile is still the placeholder ("Your Company"), ask for the company name and short name
and write them into `workspace/company.yaml`. Mention that a logo (`workspace/branding/logo.png`), a Word
template (`srs-template.docx`) and standard wording (`srs-boilerplate.yaml`) can go in the same folder.

## 2. Show where things stand

Run `python -I tools/status.py` and summarise it in a few lines: each project, what stage it is at, and
its suggested next step. Mention anything waiting in the inbox.

## 3. Ask what they want to do

Use AskUserQuestion with these options (the tool adds "Other" automatically):

| Option | Then |
|---|---|
| Start a new project | the `new-project` skill |
| Review a document (SRS, URS, draft) | the `review-srs` skill |
| Build or update a mock-up | the `build-mockup` skill |
| Process the inbox / apply feedback | the `process-inbox` skill (it routes mock-up feedback to `apply-feedback`) |

If they pick "Other", or mention generating the SRS, presenting a mock-up or closing a project, use the
matching skill: `generate-srs`, presenting (`present.cmd <project>` or
`python -I tools/mockup.py serve projects/<slug>`), `close-project`.

If a project is involved and it is not obvious which, ask which one, listing the projects by name.

## 4. Hand over

Invoke the chosen skill and follow it. At the end, tell the person where their output is (Excel register,
Word SRS, mock-up link) in plain words, and what the sensible next step is.
