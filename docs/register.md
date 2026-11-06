# The register

Each project has one register: every question, gap, assumption, decision and fix found at any stage,
with its status. `register.json` is the source of truth; `register.xlsx` is the copy the BA takes to the
client. The skills keep both up to date.

## The Excel file

| Sheet | For | Contents |
|---|---|---|
| For client | The BA, to take to the client | Questions only the client can answer, with the observation behind each, a suggested answer and an empty **Client response** column |
| Internal fixes | Your team | Things you fix yourselves: document hygiene, figure mismatches, missing sections, tool issues |
| All items | Anyone | Everything, including resolved items and answers |
| Summary | Anyone | Counts by status, severity, audience and category |

Open items come first, then by severity. The Status column has a drop-down.

Internal fixes never appear on the client sheet.

## Statuses

`open` → `asked` → `answered` → `resolved` (or `wont-fix`). When the client answers, type the answer into
**Client response** in `register.xlsx`, or change the **Status** from its drop-down, save the file and
tell Blueprint ("the client answered R-012 and R-019"). When the client sends the file back with their answers typed in, drop
it into the inbox (or say "the client answered" and name the file): Blueprint files it in the project's
`docs/` and reads the answers from that copy (`register.py render --from`), by the same rules. Blueprint reads the Excel file before it writes
it again, so what you typed goes into the register and is not lost; an answer moves an open question to
`answered`. Close the file in Excel first, or Blueprint cannot write it. If you and Blueprint both changed
the same item, it stops and shows the two values so you can say which is right. Resolved client items
drop out of the Open Issues section at the next generation. Those with an answer move to **Decisions
made** in the same chapter, with the answer and `resolved_in`, so the document the client signs records
what was agreed. Write the answer as you want the client to read it.

## Adding and updating items

Blueprint never edits `register.json` by hand. It writes new items to a JSON file (one item, or a list)
and adds them with `python -I tools/register.py add projects/<slug> --file <items.json>`, or passes them
on standard input. The tool gives each item the next free ID (an ID in the file is ignored, so IDs are
never reused or doubled), fills `raised` with today and `status` with `open` where they are missing, and
checks every item with the same rules as `validate`. One bad item stops the whole batch and nothing is
written. A file is safer than JSON typed on the command line, where Windows quoting breaks it.

Before writing, `add` compares each new item's question and finding with every item already in the
register, and with the items before it in the same batch, and names the likely duplicates (`R-047 may be
a duplicate of R-010 (similarity 0.72, open)`). The comparison counts shared words, so it catches the
same question asked in other words, not the same idea put entirely differently: it is a hint, and
Blueprint reads each pair. With `--check` it only checks and reports, and writes nothing, which is how a
large batch (a document review) is checked before it is added. To check one candidate finding first:
`python -I tools/register.py similar projects/<slug> "<question or finding>"`.

To answer or close items: `python -I tools/register.py update projects/<slug> R-012 --set status=resolved
--set answer="..." --set resolved_in="Workshop 2"`. Several IDs can be given at once (`R-012 R-019
--set status=asked`). Unknown fields and values that are not allowed are refused and nothing changes; an
empty value (`--set owner=`) removes an optional field. An answer on an open or asked item moves it to
`answered`, as in Excel, unless the status is set too. Both commands write `register.json` only; render
the Excel file afterwards.

## Severity

- **High:** blocks sign-off, contradicts itself on scope or behaviour, or would cost mandays if guessed wrong.
- **Medium:** will cause rework or a UAT defect if left.
- **Low:** clarity, naming, small inconsistencies.

## Fields (`register.json`)

| Field | Meaning |
|---|---|
| `id` | `R-001`, `R-002` … never reused |
| `type` | `question`, `gap`, `contradiction`, `assumption`, `decision`, `fix` |
| `audience` | `client` (the BA asks the client) or `internal` (your team fixes it) |
| `severity` | `high`, `medium`, `low` |
| `category` | A gap pattern ID such as `GP-02`, or a short label such as `consistency`, `hygiene`, `scope`, `generator` |
| `stage` | `sow`, `workshop-1`, `mockup`, `workshop-2`, `requirements-draft`, `requirements-final` (found in a document the client already signed: a possible change request), `development`, `uat` |
| `source` | Where it was found: section, requirement ID, page or figure |
| `finding` | What is wrong or missing, stated as fact |
| `question` | For client items: the question in plain business language |
| `recommendation` | Optional: your suggested answer or fix |
| `effort_impact` | Optional: `none`, `low`, `medium`, `high`: the effect on mandays if resolved the costly way |
| `status` | See above |
| `answer` | Optional: the client's answer or the decision taken |
| `raised` / `resolved_in` | Date raised; document version or meeting where it was closed |
| `owner` / `due` | Optional: who must answer, and by when (shown in the Open Issues table) |
