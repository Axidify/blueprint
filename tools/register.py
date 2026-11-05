"""Project register: validate register.json and render register.xlsx for the BA.

Usage:
    python -I tools/register.py render   projects/<slug>
    python -I tools/register.py validate projects/<slug>
    python -I tools/register.py next-id  projects/<slug>

register.json:
{
  "project": "Courier Booking System",
  "client": "Acme",
  "items": [ { ...item... } ]
}

Item fields (required unless marked optional):
  id              "R-001", sequential, never reused
  type            question | gap | contradiction | assumption | decision | fix
  audience        client (BA takes it to the client) | internal (your team fixes it)
  severity        high | medium | low
  category        a gap pattern id from knowledge/gap-patterns.md (e.g. "GP-02") or a short slug
  stage           sow | workshop-1 | mockup | workshop-2 | srs-draft | srs-final | development | uat
  source          where it was found, e.g. "SRS v1.0 §3.2 FR-REQ-003.1" or "Figure 2"
  finding         what is wrong or missing, stated as fact, with the quote if useful
  question        for client items: the question to ask, in plain business language
  recommendation  optional: your suggested answer or fix
  effort_impact   optional: none | low | medium | high - effect on mandays if resolved the costly way
  status          open | asked | answered | resolved | wont-fix
  answer          optional: the client's answer or the decision taken
  raised          date raised, YYYY-MM-DD
  resolved_in     optional: document version or meeting where it was closed
  owner           optional: who must answer or fix it (default in the SRS Open Issues table: the client)
  due             optional: date by which it is needed, YYYY-MM-DD
"""
import json
import sys
from collections import Counter
from pathlib import Path

TYPES = {"question", "gap", "contradiction", "assumption", "decision", "fix"}
AUDIENCES = {"client", "internal"}
SEVERITIES = {"high", "medium", "low"}
STATUSES = {"open", "asked", "answered", "resolved", "wont-fix"}
STAGES = {"sow", "workshop-1", "mockup", "workshop-2", "srs-draft", "srs-final", "development", "uat"}
REQUIRED = ["id", "type", "audience", "severity", "category", "stage", "source", "finding", "status", "raised"]
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def load(project):
    path = Path(project) / "register.json"
    if not path.exists():
        sys.exit(f"No register at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate(reg):
    errors, seen = [], set()
    for i, it in enumerate(reg.get("items", [])):
        where = it.get("id", f"item #{i + 1}")
        for f in REQUIRED:
            if not it.get(f):
                errors.append(f"{where}: missing {f}")
        if it.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(it.get("id"))
        for field, allowed in (("type", TYPES), ("audience", AUDIENCES), ("severity", SEVERITIES),
                               ("status", STATUSES), ("stage", STAGES)):
            if it.get(field) and it[field] not in allowed:
                errors.append(f"{where}: {field} '{it[field]}' not in {sorted(allowed)}")
        if it.get("audience") == "client" and not it.get("question"):
            errors.append(f"{where}: client items need a question")
    return errors


def next_id(reg):
    nums = [int(it["id"].split("-")[1]) for it in reg.get("items", []) if it.get("id", "").startswith("R-")]
    return f"R-{(max(nums) if nums else 0) + 1:03d}"


def render(project, reg):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    header_fill = PatternFill("solid", fgColor="1F3864")
    sev_fill = {"high": "F8CBAD", "medium": "FFE699", "low": "E2EFDA"}
    wrap = Alignment(wrap_text=True, vertical="top")
    items = sorted(reg["items"], key=lambda it: (it["status"] in ("resolved", "wont-fix"),
                                                 SEV_ORDER.get(it["severity"], 9), it["id"]))

    def sheet(ws, columns, rows):
        for c, (name, width, _) in enumerate(columns, 1):
            cell = ws.cell(row=1, column=c, value=name)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = header_fill
            cell.alignment = wrap
            ws.column_dimensions[get_column_letter(c)].width = width
        for r, it in enumerate(rows, 2):
            for c, (name, _, key) in enumerate(columns, 1):
                value = key(it) if callable(key) else it.get(key, "")
                cell = ws.cell(row=r, column=c, value=value)
                cell.alignment = wrap
                if name == "Severity":
                    cell.fill = PatternFill("solid", fgColor=sev_fill.get(it["severity"], "FFFFFF"))
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
            col = next(i for i, c in enumerate(columns, 1) if c[0] == "Status")
            dv = DataValidation(type="list", formula1='"' + ",".join(sorted(STATUSES)) + '"', allow_blank=False)
            ws.add_data_validation(dv)
            dv.add(f"{get_column_letter(col)}2:{get_column_letter(col)}{len(rows) + 1}")

    cap = lambda k: (lambda it: (it.get(k) or "").capitalize())
    client_cols = [
        ("ID", 8, "id"), ("Severity", 10, cap("severity")), ("Reference", 26, "source"),
        ("Observation", 55, "finding"), ("Question for client", 55, "question"),
        ("Our recommendation", 40, "recommendation"), ("Client response", 45, "answer"),
        ("Status", 12, "status"), ("Raised", 12, "raised"),
    ]
    internal_cols = [
        ("ID", 8, "id"), ("Severity", 10, cap("severity")), ("Type", 13, "type"), ("Category", 12, "category"),
        ("Reference", 26, "source"), ("Finding", 60, "finding"), ("Fix / recommendation", 50, "recommendation"),
        ("Effort impact", 12, "effort_impact"), ("Status", 12, "status"), ("Raised", 12, "raised"),
    ]
    all_cols = internal_cols[:5] + [("Audience", 11, "audience"), ("Stage", 12, "stage")] + internal_cols[5:6] + [
        ("Question for client", 50, "question")] + internal_cols[6:] + [("Answer / decision", 40, "answer"),
                                                                         ("Resolved in", 16, "resolved_in")]

    wb = Workbook()
    ws = wb.active
    ws.title = "For client"
    sheet(ws, client_cols, [it for it in items if it["audience"] == "client"])
    sheet(wb.create_sheet("Internal fixes"), internal_cols, [it for it in items if it["audience"] == "internal"])
    sheet(wb.create_sheet("All items"), all_cols, items)

    s = wb.create_sheet("Summary")
    s.column_dimensions["A"].width = 28
    s.column_dimensions["B"].width = 12
    rows = [(reg.get("project", ""), ""), ("Client: " + reg.get("client", ""), ""), ("", ""), ("Total items", len(items))]
    for label, field in (("By status", "status"), ("By severity", "severity"), ("By audience", "audience"),
                         ("By category", "category")):
        rows += [("", ""), (label, "")]
        rows += sorted(Counter(it[field] for it in items).items())
    for r, (a, b) in enumerate(rows, 1):
        s.cell(row=r, column=1, value=a).font = Font(bold=(b == "" and a != ""))
        s.cell(row=r, column=2, value=b)

    out = Path(project) / "register.xlsx"
    wb.save(out)
    return out


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("render", "validate", "next-id"):
        sys.exit(__doc__)
    cmd, project = sys.argv[1], sys.argv[2]
    reg = load(project)
    if cmd == "next-id":
        print(next_id(reg))
        return
    errors = validate(reg)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    if cmd == "validate":
        print(f"OK: {len(reg['items'])} items")
        return
    out = render(project, reg)
    c = Counter(it["audience"] for it in reg["items"])
    print(f"Wrote {out}: {c['client']} client items, {c['internal']} internal fixes")


if __name__ == "__main__":
    main()
