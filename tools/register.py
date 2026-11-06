"""Project register: validate register.json and render register.xlsx for the BA.

Usage:
    python -I tools/register.py render   projects/<slug> [--overwrite]
    python -I tools/register.py validate projects/<slug>
    python -I tools/register.py next-id  projects/<slug>

render writes register.xlsx from register.json. First it takes over what was typed into the existing
register.xlsx since it was written: a client's answer (Client response, Answer / decision) or a changed
Status. Those go into register.json, so they are not lost when the Excel file is written again. When
Excel and register.json both changed the same thing, it stops and says so; --overwrite writes the file
from register.json regardless and drops what was typed in Excel.

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
  stage           sow | workshop-1 | mockup | workshop-2 | requirements-draft | requirements-final | development | uat
  source          where it was found, e.g. "v1.0 §3.2 FR-REQ-003.1" or "Figure 2"
  finding         what is wrong or missing, stated as fact, with the quote if useful
  question        for client items: the question to ask, in plain business language
  recommendation  optional: your suggested answer or fix
  effort_impact   optional: none | low | medium | high - effect on mandays if resolved the costly way
  status          open | asked | answered | resolved | wont-fix
  answer          optional: the client's answer or the decision taken
  raised          date raised, YYYY-MM-DD
  resolved_in     optional: document version or meeting where it was closed
  owner           optional: who must answer or fix it (default in the Open Issues table: the client)
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
STAGES = {"sow", "workshop-1", "mockup", "workshop-2", "requirements-draft", "requirements-final", "development", "uat",
          "srs-draft", "srs-final"}  # the last two are the names used before 0.4.0
REQUIRED = ["id", "type", "audience", "severity", "category", "stage", "source", "finding", "status", "raised"]
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
RENDERED = "_rendered"  # a hidden sheet: the status and answer of every item as the file was written
EDITABLE = {"Status": "status", "Client response": "answer", "Answer / decision": "answer"}  # column -> field


def text(value):
    return "" if value is None else str(value).strip()


def excel_edits(project, reg):
    """What was typed into register.xlsx since it was written: ({(id, field): value}, conflicts).

    The hidden sheet says what each cell held when the file was written, so an edit made in Excel can be
    told from a change made in register.json since. A file written by an older Blueprint has no such
    sheet; there the one safe sign of an edit is an answer in Excel where the register has none."""
    from openpyxl import load_workbook

    path = Path(project) / "register.xlsx"
    if not path.exists():
        return {}, []
    try:
        wb = load_workbook(path)
    except Exception as e:
        sys.exit(f"Cannot read {path} to see whether anything was typed into it ({type(e).__name__}). Close it in Excel "
                 "and run this again, or add --overwrite to write it afresh from register.json.")
    written = None
    if RENDERED in wb.sheetnames:
        written = {text(r[0]): {"status": text(r[1]), "answer": text(r[2])}
                   for r in wb[RENDERED].iter_rows(min_row=2, values_only=True) if r and r[0]}
    items = {it.get("id"): it for it in reg.get("items", [])}
    found = {}  # (id, field) -> {value: sheet}
    for ws in wb.worksheets:
        header = [text(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1), [])]
        if ws.title == RENDERED or "ID" not in header:
            continue
        columns = {EDITABLE[name]: i for i, name in enumerate(header) if name in EDITABLE}
        for row in ws.iter_rows(min_row=2, values_only=True):
            rid = text(row[header.index("ID")])
            if rid not in items:
                continue
            for field, i in columns.items():
                value = text(row[i])
                if written is not None:
                    if rid not in written or value == written[rid][field]:
                        continue
                elif field != "answer" or not value or text(items[rid].get("answer")):
                    continue
                found.setdefault((rid, field), {})[value] = ws.title
    edits, conflicts = {}, []
    for (rid, field), values in sorted(found.items()):
        if len(values) > 1:
            conflicts.append(f"{rid} {field}: the sheets of the Excel file disagree ("
                             + "; ".join(f"'{sheet}' has '{value}'" for value, sheet in values.items()) + ")")
            continue
        value = next(iter(values))
        now = text(items[rid].get(field))
        was = written[rid][field] if written is not None else ""
        if now == value:
            continue
        if now != was:
            conflicts.append(f"{rid} {field}: Excel has '{value}', register.json has '{now}'; both changed since the Excel file was written")
        elif field == "status" and value not in STATUSES:
            conflicts.append(f"{rid} status: '{value}' in Excel is not one of {', '.join(sorted(STATUSES))}")
        else:
            edits[(rid, field)] = value
    return edits, conflicts


def take_excel_edits(project, reg, edits):
    """Put the edits into the register and save register.json. Returns what was done, one line each."""
    items = {it["id"]: it for it in reg["items"]}
    done = []
    for (rid, field), value in sorted(edits.items()):
        items[rid][field] = value
        done.append(f"{rid} {field}: {value if len(value) <= 70 else value[:67] + '...'}")
        # An answer came in and nobody moved the status: it is answered (not yet resolved).
        if field == "answer" and value and (rid, "status") not in edits and items[rid].get("status") in ("open", "asked"):
            items[rid]["status"] = "answered"
            done.append(f"{rid} status: answered (it has an answer now)")
    (Path(project) / "register.json").write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return done


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


def render(project, reg, overwrite=False):
    """Write register.xlsx. Unless `overwrite`, what was typed into the existing file is taken into the
    register first (and register.json saved), so writing the file again never loses it. This happens here,
    not in the command around it, so that no caller can write the file without it."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    if not overwrite:
        edits, conflicts = excel_edits(project, reg)
        if conflicts:
            print("register.xlsx and register.json disagree. Nothing was written:")
            print("\n".join(f"  - {c}" for c in conflicts))
            print("Put the value you want into register.json, then run this again with --overwrite.")
            sys.exit(1)
        if edits:
            print("Taken from register.xlsx into register.json:")
            print("\n".join(f"  - {line}" for line in take_excel_edits(project, reg, edits)))

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

    # What each item held as this file is written, so the next render can tell what was typed in Excel since.
    kept = wb.create_sheet(RENDERED)
    kept.append(["id", "status", "answer"])
    for it in items:
        kept.append([it["id"], it["status"], it.get("answer") or ""])
    kept.sheet_state = "veryHidden"

    out = Path(project) / "register.xlsx"
    try:
        wb.save(out)
    except PermissionError:
        sys.exit(f"Cannot write {out}: close it in Excel and run this again.")
    return out


def main():
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2 or args[0] not in ("render", "validate", "next-id") or any(f != "--overwrite" for f in flags):
        sys.exit(__doc__)
    cmd, project = args
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
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
    out = render(project, reg, overwrite="--overwrite" in flags)
    c = Counter(it["audience"] for it in reg["items"])
    print(f"Wrote {out}: {c['client']} client items, {c['internal']} internal fixes")


if __name__ == "__main__":
    main()
