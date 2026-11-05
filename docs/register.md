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

`open` → `asked` → `answered` → `resolved` (or `wont-fix`). When the client answers, put the answer in
**Client response** and tell Blueprint ("the client answered R-012 and R-019"). Resolved client items
drop out of the Open Issues section at the next generation.

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
| `stage` | `sow`, `workshop-1`, `mockup`, `workshop-2`, `requirements-draft`, `requirements-final`, `development`, `uat` |
| `source` | Where it was found: section, requirement ID, page or figure |
| `finding` | What is wrong or missing, stated as fact |
| `question` | For client items: the question in plain business language |
| `recommendation` | Optional: your suggested answer or fix |
| `effort_impact` | Optional: `none`, `low`, `medium`, `high`: the effect on mandays if resolved the costly way |
| `status` | See above |
| `answer` | Optional: the client's answer or the decision taken |
| `raised` / `resolved_in` | Date raised; document version or meeting where it was closed |
| `owner` / `due` | Optional: who must answer, and by when (shown in the Open Issues table) |
