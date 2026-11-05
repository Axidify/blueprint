# Gap patterns

Recurring requirement gaps on your projects. Each pattern has the workshop questions that would have
caught it and what a requirements document review should check.

**Evidence levels.** *Cost* = it already came back as a CR or an overrun, with real mandays.
*Review* = found in a requirements document review before it cost anything. Patterns with cost evidence go first in every
workshop.

When `close-project` or `review-requirements` finds a new gap, add it to an existing pattern's evidence or create a
new pattern. Keep client content out: describe the gap in general terms.

---

## GP-01 Unidentified viewers and read-only stakeholders
**What goes wrong:** Workshops cover the people who *do* the work. People who only need to *see* it
(management, business owners, auditors, regional heads) surface after go-live as new roles.
**Evidence:** none yet.
**Workshop questions:**
- Besides the people who use this daily, who needs to see the data? Management, owners, auditors, other
  departments?
- Do any of them need a different scope (one branch, one region, everything)?
- Does anyone need reports or exports without logging in?
**Document check:** The roles table and access matrix include read-only roles, and every role has a data scope.

## GP-02 Correcting records after submission
**What goes wrong:** The happy path is specified (create → submit → approve). What happens when someone
made a mistake after submitting is not: edit, withdraw, cancel, reopen, or delete.
**Evidence:** none yet.
**Workshop questions:**
- After a record is submitted or approved, who can change it, until when, and does it need re-approval?
- Can the requester withdraw or cancel? What happens to approvals already given?
- Can anything be deleted, or only cancelled? What must stay for audit?
**Document check:** Every status in the lifecycle lists who may edit, cancel or delete, and what happens to the
approval chain and audit trail.

## GP-03 KPIs and calculations not defined
**What goes wrong:** "Dashboard" or "utilisation report" is scoped as a screen. The calculation rules
(denominators, calendars, period boundaries, exclusions) are discovered later and turn into custom logic.
**Evidence:** none yet.
**Workshop questions:**
- For every number on the dashboard: what is the formula, with a worked example?
- What happens at month or year boundaries, for partial days, for excluded periods?
- Where do the reference data come from (working-day calendars, targets, mappings)?
- Do totals at higher levels sum the lower levels, or recalculate from raw data?
**Document check:** Each KPI has a formula, a worked example, data sources and edge cases. Any KPI without one is
a high-severity gap and an estimate risk.

## GP-04 Reporting and export scope
**What goes wrong:** Exports are specified for one screen or one user's data. Users actually need
everything, across all units, in one file.
**Evidence:** none yet.
**Workshop questions:**
- Who exports what, for which branches, regions or periods?
- Which columns must the export contain? Is it the same as the screen or more?
- How many rows at most (performance)?
**Document check:** Every export states its scope, filters, columns and file name.

## GP-05 List columns, sorting and filters
**What goes wrong:** Lists are mocked up with sample columns that nobody confirms.
**Evidence:** none yet.
**Workshop questions:** For each list: which columns, in what order, sorted how, filtered by what?
**Document check:** Every list has a data-requirements table with its columns, default sort and filters.

## GP-06 Mock-up elements nobody validated
**What goes wrong:** Mock-up details (views, buttons, sections) are taken as agreed because nobody objected.
Some are not needed and get removed later, after they were built.
**Evidence:** none yet.
**Workshop questions:** Walk through every element of each mock-up screen and ask "is this needed?", not
"is this OK?".
**Document check:** Screens and data tables match the mock-up; elements without a requirement are flagged.

## GP-07 Segregation of duties
**What goes wrong:** Nothing stops one person from holding several steps of an approval chain, or from
approving their own request.
**Evidence:** none yet.
**Workshop questions:** Can the same person request and approve? Approve and execute? Is there an audit
or compliance rule?
**Document check:** Conflicting role combinations are stated and enforced, or explicitly allowed.

## GP-08 Delegation, reassignment and absence
**What goes wrong:** Approvals are routed to a named person. When they are on leave or leave the company,
records get stuck.
**Evidence:** none yet.
**Workshop questions:** What happens when the assigned approver is away? Can they delegate? Can an admin
reassign? Is there an escalation after N days?
**Document check:** Delegation, reassignment and escalation are specified for every approval step.

## GP-09 Failure and exception paths
**What goes wrong:** Only the success path is specified. What happens when the real-world activity fails
(a delivery fails, goods arrive damaged, an item is rejected at the last step) is left open.
**Evidence:** none yet.
**Workshop questions:** What happens when this step fails or goes wrong? Who is told, and what status does
the record get? Can the process restart from the middle?
**Document check:** Every workflow step has its failure outcome and resulting status.

## GP-10 Integration scope ambiguity
**What goes wrong:** Integrations are scoped as "retrieve data from system X" or "if applicable". They turn
out to be several endpoints, or become mandatory, after the estimate is fixed.
**Evidence:** none yet.
**Workshop questions:**
- For each external system: which data, which direction, how often, who owns the API, does it exist yet?
- Is it in this phase or not? Get a yes or no, never "if applicable".
- What happens when the other system is down or returns no match?
**Document check:** One row per endpoint (purpose, direction, trigger, fields, failure handling). Every
"if applicable" is a high-severity item until it is a yes or no.

## GP-11 Where roles and users come from
**What goes wrong:** The requirements document says users come from Active Directory and also that an admin manages roles in
the app, without saying which one wins. User lifecycle (joiners, movers, leavers) is missing.
**Evidence:** none yet.
**Workshop questions:** Is login through AD/SSO? Are roles from AD groups or managed in the app? What
happens when a user leaves or moves branch?
**Document check:** One source of truth for authentication and for roles; the user lifecycle is specified.

## GP-12 Non-functional requirements missing
**What goes wrong:** The SOW promises non-functional requirements but the requirements document has none, so performance,
availability, backup, retention and security expectations are never agreed.
**Evidence:** none yet.
**Workshop questions:** Users and peak concurrency? Hours of use? Acceptable downtime? How long must data
and audit logs be kept? Backup and restore expectations? Supported browsers and devices?
**Document check:** NFR section present, with measurable values.

## GP-13 Identifier and numbering rules
**What goes wrong:** Reference number formats are specified without length, reset rules, overflow or
behaviour for deleted drafts.
**Evidence:** none yet.
**Workshop questions:** Does the running number reset each year? What if it passes 999? Must there be no
gaps?
**Document check:** Format fits the field length; reset, overflow and gap rules stated.

## GP-14 Notification rules
**What goes wrong:** Templates exist, but which event sends which template to whom, and whether reminders
are automatic or manual, is inconsistent.
**Evidence:** none yet.
**Workshop questions:** For each event: who gets an e-mail, using which template? Are reminders automatic
(how often, until when) or manual? Can anyone switch them off?
**Document check:** An event → recipient → template table, consistent with the template list.

## GP-16 Business rules hidden in screen text
**What goes wrong:** Terms and conditions, help text and placeholder hints on mock-ups state business rules
(maximum booking period, late fees, eligibility, age or licence requirements) that no requirement covers. The
rule is either built by accident, or the client expects it enforced and finds it is not.
**Evidence:** none yet.
**Workshop questions:**
- Which rules in your current paper form or T&Cs must the system enforce, and which are just text?
- What happens when a rule is broken (period exceeded, fee due)?
**Document check:** Every rule stated on a screen is either a requirement with validation or explicitly
display-only.

## GP-15 Document hygiene and template leftovers
**What goes wrong:** Documents reuse another project's template, leaving its name in metadata, templates or
headings. Clients notice.
**Evidence:** none yet.
**Document check:** Internal only. Metadata, headers, appendices and templates mention only this project;
tracked changes accepted; no credentials or IP addresses unless approved.
