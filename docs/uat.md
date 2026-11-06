# UAT scripts

User acceptance testing (UAT) is where the client checks the built system against what they signed.
Blueprint writes the test scripts from the project spec, so every scenario follows the agreed screens,
statuses and rules, and every requirement is tested or excluded with a reason. Ask for them with
"prepare the UAT scripts" (the `uat-scripts` skill).

## What you get

In the project's `6 UAT` folder (the `.json` in `_blueprint/uat/`):

| File | For | What it is |
|---|---|---|
| `<date> uat scripts v<version>.json` | Blueprint | The scripts. The other two files are made from it; change this one and render again |
| `<date> uat scripts v<version>.xlsx` | The client's testers | One row per step, with columns to fill in: Actual result, Pass/Fail (a list: Pass, Fail, Blocked, Not run), Tester, Date, Defect ref. A Summary sheet counts the results and shows the coverage by requirement group |
| `<date> uat scripts v<version>.docx` | The client | The test scripts in your company's document format: purpose, how to record results, what is covered, every scenario with its steps and expected results, the requirements not tested and why, and an acceptance block |

Neither client file holds mandays, rates, cost, internal register items or platform findings.

## Which version is tested

The scripts follow the version issued to the client last (`_blueprint/output/spec-v<version>.yaml`), because UAT
tests what was signed. With nothing issued yet they follow the current spec, and say so. The document
names the version on its first page.

## What the draft covers

The draft is made the same way every time, then Claude refines it:

| Kind | From the spec |
|---|---|
| Main process | The process flow, or the statuses' `next`: from submitting the record to its last status, signed in as each role in turn, with the real buttons and dialogs |
| Status changes | Every other move the status rules allow (reject, cancel, resubmit …), and changing or deleting where a role may. A move the system makes on its own (`auto` on the status) is a case without a button, with the condition left to write |
| What may not be done | For each status, each role that can open the record is shown not to be able to change, cancel or delete it where the rules say so |
| Field checks | Required fields, lengths, validation rules, choices (for a filtered drop-down, only the records it offers) and filled-in fields of every form and dialog |
| Access | The screens each role may not open, and the records it may see (its scope) |
| Figures | What each figure on a dashboard counts |
| Notifications and integrations | Each one, "as specified", with what starts it and what happens when the other system fails |
| Other requirements | One case for every requirement no scenario covers yet, for Claude to merge or write out |

Claude then merges the requirement cases into the scenarios that test them, adds the edge cases from the
knowledge base's gap patterns that apply (corrections after submission, an approver away, failures,
numbering), removes what makes no sense, and checks that every requirement is covered.

## Each case

`id` (UAT-001 …), `title`, `type`, `priority` (High for the main process, status rules and access),
`roles`, `preconditions`, `steps` (each an `action` and its `expected` result, with the `screen` and,
when someone else takes over, the `role`), `requirements` (the requirement ids it covers) and `source`
(what in the spec produced it: Blueprint's own, like `todo` and `related`, and never printed). The format
is at the top of `tools/uat.py`.

## After UAT

Drop the filled-in workbook into the inbox and say "process my inbox". Blueprint lists every failed and
blocked step. A step where the system does not do what was signed is a defect for the developers. A step
where the system does what was signed but the client wants something else is a change request: the
`change-request` skill checks it against the signed version.

See also: [Skills](skills.md#uat-scripts), [Tools](tools.md#uatpy).
