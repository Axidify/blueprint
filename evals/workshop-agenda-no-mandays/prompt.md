---
description: The client's workshop agenda carries the open client questions and never mandays, cost, recommendations or internal items.
tags: [smoke, prep-workshop, internal]
runs: 1
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill]
append_system_prompt: "This is an evaluation run. Blueprint's app folder, its tools and the workspace are not available here: do not try to run commands or open project files. Work only from what the request gives you, and where a skill says to run a tool, say in one line what you would run."
---

Prepare the workshop for the leave-request project (made up for testing): one hour on 20 November with the
client's HR manager. Just show me the agenda text that goes to the client.

The open register items:

| ID | Audience | Severity | Question or finding | Recommendation | Effort impact |
|---|---|---|---|---|---|
| R-001 | client | high | Who may cancel a leave request after it was approved? | Only HR Admin | high |
| R-002 | client | high | How is the utilisation rate on the HR dashboard calculated? | Days taken / days entitled | medium |
| R-003 | client | medium | Must HR be notified of every approved request, or only of long leave? | Only leave over 5 days | low |
| R-004 | internal | medium | Figure 2 shows a status "Returned" the status table does not have. | Remove it from Figure 2 | none |

From the lead developer's estimate (internal): if any approved request can be cancelled, add 6 to 8
mandays; a utilisation formula across departments adds 3 to 5 mandays.
