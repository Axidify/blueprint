---
description: A file that could belong to two projects of the same client is asked about, never filed on a guess.
tags: [smoke, process-inbox]
runs: 1
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

Process my inbox. Everything here is made up for testing.

The inbox has one file, `meeting notes 5 Nov.docx`. Its text:

> Meeting with Acme, 5 November. Attendees: Hafiz, Mei Ling. We went through the request screen. The
> approver wants to see the history of earlier requests before approving. Next meeting in two weeks.

The active projects:
- `courier-booking`: Courier Booking System for Acme. Roles: Sender, Dispatcher, Approver.
- `fleet-request`: Fleet Vehicle Request for Acme. Roles: Requester, Fleet Manager, Approver.

`project.py match` said: verdict `likely`; fleet-request 0.41 (matched: Approver, request, Acme),
courier-booking 0.38 (matched: Approver, Acme, Hafiz).
