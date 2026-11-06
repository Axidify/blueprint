---
description: A request the signed version already covers is judged In scope, quoting the requirement with its section.
tags: [smoke, change-request]
runs: 1
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

During UAT on the leave-request project (made up for testing) the client asked: "Can the line manager
reject a leave request and give a reason? We need this." Is this a CR?

This is the relevant part of the version the client signed (v1.0, issued 1 October):

---
4. Approvals
4.1 FR-APR-01 The Line Manager sees every submitted request of their team in Pending Approvals.
4.2 FR-APR-02 The Line Manager can approve or reject a submitted request. A rejection requires a reason,
    which the Employee sees on the request.
4.3 FR-APR-03 An approved request cannot be edited by the Employee.

9. Out of scope
9.1 Delegation of approvals while the Line Manager is away.
---
