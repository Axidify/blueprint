---
description: A short review cites the location of each finding and ends with the shared hand-over (where, for whom, the next step in words to say).
tags: [smoke, review-requirements, hand-over]
runs: 1
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

Please review this draft requirements document for our leave-request project and tell me what to ask the
client. It is made up for testing.

---
Leave Request System - Draft Requirements v0.1

2. Roles
2.1 Employee: submits leave requests.
2.2 Line Manager: approves leave requests.
2.3 HR Admin: manages leave balances.

3. Process
3.1 FR-01 The Employee submits a leave request with the dates and the leave type.
3.2 FR-02 The Line Manager approves the request. HR is notified if applicable.
3.3 FR-03 Approved leave is deducted from the Employee's balance.

4. Dashboard
4.1 FR-04 The HR dashboard shows the utilisation rate per department.

5. Integrations
5.1 FR-05 Approved leave is sent to the payroll system (TBC).
---
