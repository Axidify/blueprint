---
description: Answers in a client e-mail are matched to the right register items; a question the e-mail does not answer stays open.
tags: [smoke, client-answers]
runs: 1
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

The client answered our questions for the leave-request project (made up for testing). Which answer goes
with which question, and what happens with each?

Open client questions in the register:
- R-001: Who may cancel a leave request after it was approved?
- R-002: Does HR need an e-mail when a leave request is approved?
- R-003: How many approval levels are needed for leave longer than 5 days?

The client's e-mail, 12 November:

> Hi, about your questions: HR doesn't need e-mails, they check the dashboard every morning. For long
> leave, the line manager approves first and then the head of department. Thanks, Mei Ling
