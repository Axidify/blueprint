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
| `<date> uat scripts v<version>.xlsx` | The client's testers | One row per step, with columns to fill in: Actual result, Pass/Fail (a list: Pass, Fail, Blocked, Not run), Tester, Date, Defect ref. A Summary sheet counts the results and shows the coverage by requirement group. The Test data sheet lists what the client prepares before UAT (TD-01 …), with Prepared by and Ready to fill in; each scenario's first step names the items it uses |
| `<date> uat scripts v<version>.docx` | The client | The test scripts in your company's document format: purpose, how to record results, the test data to prepare, what is covered, every scenario with its test data, steps and expected results, the requirements not tested and why, and an acceptance block |
| `Defect log.xlsx` | The team and the client's UAT lead | Written after UAT: every failed step as a defect, with its status, scenario, requirements, expected and actual result |

Neither client file holds mandays, rates, cost, internal register items or platform findings.

Rendering again (after the scripts changed) never writes over the testers' results: when the workbook has
anything typed in their columns, `uat.py render` stops; `--force` writes a fresh workbook and keeps theirs
beside it as `<name> - results kept <date> <time>.xlsx`.

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
| Other requirements | Each requirement that plainly names what it is about goes into the scenario that tests it (see below); one the draft cannot tie for certain, or one waiting for an open decision, has a case of its own for Claude to merge or write out |

A process step that no status rule ties to a button is made with the button named after it ("Approve" for
the step "Approve"), and a record sent back to its form (a draft, a rejected application its owner may
change) goes on with the form's own button, so these need no hand work.

**Requirements tied by the draft.** A requirement goes into a scenario only when its words name something of
that scenario:

| The requirement says | It goes into |
|---|---|
| A field of a form is filled in, calculated or read-only; its choices are offered | The form's field rules |
| A field is required; or required for one choice of another field ("for Medical Leave") | The form's required fields, with a step for that choice |
| A dialog's field is required when pressing its button ("a reason when rejecting") | The dialog's required fields |
| Saving a draft | A new case: the draft button pressed on an unfinished form |
| A record is sent or routed to a role | The main process, where that role finds it |
| A button's action ("cancel a Pending or Approved application"), in the statuses and by the roles it names | The cases that press that button |
| An e-mail or notice to a role when a record reaches a status | A new case per status: the move made, then the role's mailbox checked |
| What a screen shows | A new case: the screen opened and its fields looked at |
| Adding, editing or deleting a list's entries | A new case: the list's own buttons pressed |

The sample project's draft has no requirement case left to refine (it had 12 before this). Claude still
reads each link, since a requirement can say more than the steps try.

**Test data.** Every case lists what it needs before it starts (`test_data`): a test account for each role
that signs in (with the role's scope, so the records fall in it), each record its preconditions ask for and
how to get one ("Fill in New Leave Application and press Submit, then Reject (as Line Manager)"), each file it
uploads, and the mailboxes and connections notifications and integrations need. A move the system makes on
its own asks for a record prepared to meet the condition during UAT. The workbook and the document gather
them into one list for the client to prepare.

Claude then merges the requirement cases into the scenarios that test them, adds the edge cases from the
knowledge base's gap patterns that apply (corrections after submission, an approver away, failures,
numbering), removes what makes no sense, and checks that every requirement is covered.

## Each case

`id` (UAT-001 …), `title`, `type`, `priority` (High for the main process, status rules and access),
`roles`, `preconditions`, `test_data` (each a `kind`: account, record, file or other; what is `need`ed; and
`how` to get it), `steps` (each an `action` and its `expected` result, with the `screen` and,
when someone else takes over, the `role`), `requirements` (the requirement ids it covers) and `source`
(what in the spec produced it: Blueprint's own, like `todo` and `related`, and never printed). The format
is at the top of `tools/uat.py`.

## After UAT

Drop the filled-in workbook into the inbox and say "process my inbox". Blueprint lists every failed and
blocked step and keeps the project's **defect log** (`_blueprint/uat/defects/defects.json`, shown as
`6 UAT/Defect log.xlsx`):

- each failed step becomes a defect, `D-001` …, linked to its scenario, step and requirements, with the
  expected and actual result, the tester, the date and the testers' own defect reference;
- a defect goes through **open → fixed → retest → closed**, or ends as **not a defect** (with the reason) or
  **change request** (with its CR id). Set it with
  `python -I tools/uat.py defect projects/<slug> D-001 fixed --note "build 14"`; every change is kept in its
  history;
- the next round's workbook closes the defects marked fixed or retest whose step now passes, and opens again
  those that fail. Reading the same workbook twice changes nothing.

A step where the system does not do what was signed is a defect for the developers: send them the defect
log. A step where the system does what was signed but the client wants something else is a change request:
mark it so, and the `change-request` skill checks it against the signed version. A blocked step is not a
defect: it usually means a test data item was not ready.

See also: [Skills](skills.md#uat-scripts), [Tools](tools.md#uatpy).
