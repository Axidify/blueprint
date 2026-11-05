"""Generate the SRS Word document from a project's spec and mock-up screenshots.

Usage:
    python -I tools/generate_srs.py <project_dir>

Reads  <project_dir>/spec/app.yaml, <project_dir>/mockup/screenshots/ + shots.json (run
       `python -I tools/mockup.py screenshots <project_dir>` first), optional <project_dir>/register.json
       (open client items become the Open Issues section), optional spec/client-logo.png and
       spec/process-flow.png.
Writes <project_dir>/output/<System> – System Requirement Specifications v<version>.docx and a snapshot of
       the spec used, so every issued version can be traced back to its spec.

Everything (access matrix, status table, data requirement tables, screenshots) comes from the same spec as
the mock-up, so the document cannot contradict the screens.
"""
import json
import re
import shutil
import sys
from pathlib import Path

import yaml
from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for future landscape sections)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402  (company profile and branding)
HEADER_FILL = "1F3864"
SECTION_FILL = "D9E2F3"

TYPE_MAP = {
    "text": "VARCHAR", "textarea": "TEXT", "select": "Drop-down", "radio": "Radio button",
    "checkbox": "Checkbox (multi)", "date": "DATE", "datetime": "DATETIME", "number": "NUMBER",
    "file": "Attachment", "signature": "Signature (image)", "user": "User ID",
}


# ------------------------------------------------------------------ docx helpers
def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def table(doc, header, rows, widths=None, group_rows=()):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        run = c.paragraphs[0].add_run(str(h))
        run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.size = Pt(9)
        shade(c, HEADER_FILL)
    repeat_header(t.rows[0])
    for r_i, row in enumerate(rows):
        cells = t.add_row().cells
        if r_i in group_rows:
            merged = cells[0].merge(cells[-1])
            merged.text = ""
            run = merged.paragraphs[0].add_run(str(row[0]))
            run.bold = True
            run.font.size = Pt(9)
            shade(merged, SECTION_FILL)
            continue
        for i, v in enumerate(row):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run("" if v is None else str(v))
            run.font.size = Pt(9)
    if widths:
        # Word only honours widths with autofit off and the grid columns set as well as the cells.
        t.autofit = False
        tbl_pr = t._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tbl_pr.append(layout)
        for i, w in enumerate(widths):
            t.columns[i].width = Cm(w)
        for row in t.rows:
            for i, w in enumerate(widths):
                if i < len(row.cells):
                    row.cells[i].width = Cm(w)
    doc.add_paragraph()
    return t


def heading(doc, text, level):
    return doc.add_heading(text, level=level)


def para(doc, text, bold=False, size=None, align=None):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if align:
        p.alignment = align
    return p


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    for tag, text in (("begin", None), (None, 'TOC \\o "1-3" \\h \\z \\u'), ("separate", None), (None, None), ("end", None)):
        if tag:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), tag)
            run._r.append(fld)
        elif text:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run._r.append(instr)
        else:
            t = OxmlElement("w:t")
            t.text = "Right-click here and choose Update Field to build the table of contents."
            run._r.append(t)


class Figures:
    def __init__(self, doc):
        self.doc, self.n = doc, 0

    def add(self, image, caption, width_cm=16.0):
        self.n += 1
        self.doc.add_picture(str(image), width=Cm(width_cm))
        self.doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap = self.doc.add_paragraph(f"Figure {self.n}: {caption}", style="Caption")
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER


# ------------------------------------------------------------------ content
def field_rows(fields_sections):
    rows, groups = [], set()
    for sec in fields_sections:
        groups.add(len(rows))
        rows.append([sec.get("title", "")])
        for f in sec.get("fields", []):
            source = f.get("source") or (f"Selection from {f['options_from'].split('.')[0].replace('_', ' ').title()}" if f.get("options_from")
                                         else ("Options: " + ", ".join(map(str, f["options"])) if f.get("options") else "User input"))
            validation = f.get("validation") or ("This field is required" if f.get("required") else "N/A")
            rows.append([f["label"], TYPE_MAP.get(f.get("type", "text"), f.get("type", "")), f.get("length", "N/A"),
                         "Yes" if f.get("required") else "No", source, "No" if f.get("readonly") else "Yes", validation])
    return rows, groups


REF = re.compile(r"\{ref:([a-z]+):([^}]+)\}")
LITERAL_REF = re.compile(r"\b(?:[Ss]ections? \d+(?:\.\d+)+|Appendix [A-Z]\b|Figure \d+)")


def pretty(field):
    return str(field).replace("_", " ").title()


def plan_numbers(spec):
    """Section numbers decided before writing, so {ref:...} placeholders can be resolved anywhere."""
    nums = {"section:roles": "section 1.1", "section:access": "section 1.2", "section:flow": "section 1.3",
            "section:integrations": "section 1.4", "section:glossary": "section 1.5", "section:notifications": "section 1.6",
            "section:requirements": "section 2.0", "section:screens": "section 3.0", "section:nfr": "section 4.0"}
    for n, s in enumerate(spec["screens"], 1):
        nums[f"screen:{s['id']}"] = f"section 3.{n}"
    extras = spec.get("extra_sections", []) or []
    number = 5
    for e in [e for e in extras if not e.get("appendix")]:
        nums[f"extra:{e['title']}"] = f"section {number}.0"
        number += 1
    nums["section:open-issues"] = f"section {number}.0"
    for i, e in enumerate([e for e in extras if e.get("appendix")]):
        nums[f"extra:{e['title']}"] = f"Appendix {chr(65 + i)}"
    for g in spec.get("requirements", []):
        nums[f"req:{g['id']}"] = g["id"]
    return nums, number


def build(project):
    project = Path(project)
    spec = yaml.safe_load((project / "spec" / "app.yaml").read_text(encoding="utf-8"))
    spec = json.loads(json.dumps(spec, default=str))
    shots_file = project / "mockup" / "shots.json"
    if not shots_file.exists():
        sys.exit("No screenshots yet. Run: python -I tools/mockup.py screenshots " + str(project))
    shots = json.loads(shots_file.read_text(encoding="utf-8"))
    shot_dir = project / "mockup" / "screenshots"
    co = workspace.company()
    bp = yaml.safe_load(workspace.asset("srs-boilerplate.yaml").read_text(encoding="utf-8"))
    P = spec["project"]
    names = {"system": P["name"], "client": P.get("client", ""), "client_short": P.get("client_short", P.get("client", "")),
             "company": co["name"], "company_short": co.get("short_name") or co["name"]}
    refs, open_number = plan_numbers(spec)
    warnings = []

    def fill(text, where=""):
        """Fill {client}/{system} placeholders and {ref:kind:key} cross-references; warn on literal references."""
        text = str(text)
        for k, v in names.items():
            text = text.replace("{" + k + "}", v)

        def sub(m):
            key = f"{m.group(1)}:{m.group(2)}"
            if key not in refs:
                warnings.append(f"{where}: unknown reference {{ref:{key}}}")
                return m.group(0)
            return refs[key]

        out = REF.sub(sub, text)
        if where and LITERAL_REF.search(REF.sub("", text)):
            warnings.append(f"{where}: literal cross-reference '{LITERAL_REF.search(text).group(0)}' (use {{ref:...}})")
        return out

    dialogs = {d["id"]: d for d in spec.get("dialogs", [])}
    roles = spec["roles"]

    doc = Document(str(workspace.asset("srs-template.docx")))
    for sec in doc.sections:  # "{company}" placeholders in headers and footers (including content controls)
        for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
            for t in part._element.iter(qn("w:t")):
                if t.text and "{company}" in t.text:
                    t.text = t.text.replace("{company}", co["name"])
    figs = Figures(doc)
    cp = doc.core_properties
    cp.title = f"{P['name']} – System Requirement Specifications v{P.get('version', '')}"
    cp.author = co["name"]
    cp.keywords = "SRS"

    # Cover
    logos = doc.add_table(rows=1, cols=2)
    logo = workspace.asset("logo.png")
    if logo:
        logos.rows[0].cells[0].paragraphs[0].add_run().add_picture(str(logo), height=Cm(1.6))
    client_logo = project / "spec" / "client-logo.png"
    if client_logo.exists():
        cell = logos.rows[0].cells[1].paragraphs[0]
        cell.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        cell.add_run().add_picture(str(client_logo), height=Cm(1.6))
    for _ in range(5):
        doc.add_paragraph()
    para(doc, P["name"], bold=True, size=26, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "System Requirement Specifications (SRS)", size=16, align=WD_ALIGN_PARAGRAPH.CENTER)
    for _ in range(4):
        doc.add_paragraph()
    cover = [("Document Version", P.get("version", "")), ("Prepared For", names["client_short"]),
             ("Prepared By", P.get("prepared_by", "")), ("Date", P.get("date", "")), ("Reviewed By", P.get("reviewed_by", ""))]
    if P.get("approved_by"):
        cover.append(("Approved By", P["approved_by"]))
    cover += [("Platform", P.get("platform", "")), ("Document Type", "System Requirement Specifications")]
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in cover:
        cells = t.add_row().cells
        cells[0].text, cells[1].text = k, str(v)
        cells[0].paragraphs[0].runs[0].bold = True
        shade(cells[0], SECTION_FILL)
    page_break(doc)

    # Version history
    if P.get("history"):
        heading(doc, "Version History", 1)
        table(doc, ["Version", "Date", "Author", "Changes"],
              [[h.get("version"), h.get("date"), h.get("author"), fill(h.get("changes", ""))] for h in P["history"]], widths=[1.8, 2.6, 3.5, 8.8])

    # Disclaimer
    heading(doc, "Disclaimer, Confidentiality & Concept Acknowledgement", 1)
    for title, key in (("Disclaimer", "disclaimer"), ("Confidentiality", "confidentiality"), ("Concept Acknowledgement", "concept")):
        para(doc, title, bold=True)
        for line in bp[key]:
            doc.add_paragraph(fill(line))
    page_break(doc)
    doc.add_paragraph("Table of Contents", style="TOC Heading")
    toc(doc)
    page_break(doc)

    # 1. Overview
    heading(doc, "1.0 System Overview", 1)
    for line in spec.get("overview", []) or []:
        doc.add_paragraph(fill(line, "overview"))
    heading(doc, "1.1 System User Roles", 2)
    doc.add_paragraph("This section outlines the user roles that will access and operate the system.")
    table(doc, ["No.", "Role", "Responsibility", "Data Scope"],
          [[i, r["name"], r.get("description", ""), r.get("scope", "")] for i, r in enumerate(roles, 1)], widths=[1.2, 3.5, 8, 4])

    heading(doc, "1.2 User Access Matrix", 2)
    doc.add_paragraph("This section shows which roles can open each menu and perform each action.")
    all_roles = [r["id"] for r in roles]
    rows, seen = [], set()

    def add_row(label, allowed):
        if label in seen:
            return
        seen.add(label)
        rows.append([label] + ["Yes" if r in allowed else "No" for r in all_roles])

    for s in spec["screens"]:
        if s.get("menu"):
            add_row(s["menu"], s.get("roles") or all_roles)
    for s in spec["screens"]:
        allowed_screen = s.get("roles") or all_roles
        lst = s.get("list") or {}
        candidates = (lst.get("toolbar") or []) + (lst.get("actions") or []) + (s.get("buttons") or [])
        for b in candidates:
            if b.get("example") or b.get("access") is False or b.get("label") in ("Back", "Cancel", "View"):
                continue
            add_row(f"{s['title']}: {b['label']}", b.get("roles") or allowed_screen)
    menu_w = 4.4
    other_w = (16.7 - 1.0 - menu_w) / max(1, len(roles))
    table(doc, ["No.", "Menu / Action"] + [r["name"] for r in roles], [[i] + r for i, r in enumerate(rows, 1)],
          widths=[1.0, menu_w] + [other_w] * len(roles))

    if spec.get("statuses"):
        heading(doc, "1.3 Process Flow and Statuses", 2)
        flow = project / "spec" / "process-flow.png"
        if not flow.exists():
            flow = shot_dir / "process-flow.png"  # generated from spec.process_flow
        if flow.exists():
            figs.add(flow, (spec.get("process_flow") or {}).get("title") or f"{P['name']} process flow")
        doc.add_paragraph("A record moves through the following statuses:")
        table(doc, ["No.", "Status", "Meaning"], [[i, s["name"], s.get("meaning", "")] for i, s in enumerate(spec["statuses"], 1)], widths=[1.2, 4, 11.5])
    if spec.get("integrations"):
        heading(doc, "1.4 External System Integration", 2)
        table(doc, ["No.", "System", "Purpose", "Direction", "Notes"],
              [[i, x.get("system"), x.get("purpose"), x.get("direction"), x.get("notes", "")] for i, x in enumerate(spec["integrations"], 1)])
    if spec.get("glossary"):
        heading(doc, "1.5 Acronym Definition", 2)
        table(doc, ["No.", "Acronym", "Description"], [[i, g["term"], g["meaning"]] for i, g in enumerate(spec["glossary"], 1)], widths=[1.2, 3, 12.5])
    if spec.get("notifications"):
        heading(doc, "1.6 E-mail Notifications", 2)
        doc.add_paragraph("Which event sends which e-mail, to whom, using which template.")
        table(doc, ["No.", "Event", "Recipient", "Template"],
              [[i, n["event"], n["recipient"], fill(n.get("template", "TBC"), "notifications")] for i, n in enumerate(spec["notifications"], 1)],
              widths=[1.2, 6, 4.5, 5])

    # 2. Functional requirements. Items are text, or {text, tbc: R-xxx, note} (note is internal, not printed).
    heading(doc, "2.0 Functional Requirements", 1)
    for grp in spec.get("requirements", []):
        heading(doc, f"{grp['id']}: {grp['title']}", 3)
        rows = []
        for i, item in enumerate(grp["items"], 1):
            text = item if isinstance(item, str) else item["text"]
            text = fill(text, f"{grp['id']}.{i}")
            if re.search(r"mock-?up", text, re.I):
                warnings.append(f"{grp['id']}.{i}: mentions the mock-up; requirements should describe the real system")
            if isinstance(item, dict) and item.get("tbc"):
                text += f" (Open issue {item['tbc']})"
            rows.append([f"{grp['id']}.{i}", text])
        table(doc, ["ID", "Requirement Description"], rows, widths=[3.2, 13.5])

    # 3. Mock-up screens
    heading(doc, "3.0 System Conceptual Mock-up Screens", 1)
    doc.add_paragraph(fill(bp["mockup_intro"]))
    by_screen = {}
    for s in shots:
        by_screen.setdefault(s["screen"], []).append(s)
    field_header = ["Field Name", "Data Type", "Length", "Mandatory", "Source", "Editable", "Field Validation / Error Message"]
    field_widths = [3, 2, 1.3, 1.6, 3.6, 1.5, 3.7]
    for n, s in enumerate(spec["screens"], 1):
        role_names = ", ".join(r["name"] for r in roles if r["id"] in (s.get("roles") or [])) or "All Users"
        heading(doc, f"3.{n} {s['title']} ({role_names})", 2)
        if s.get("description"):
            doc.add_paragraph(fill(s["description"], f"screen {s['id']}"))
        screen_shots = by_screen.get(s["id"], [])
        paged = [x for x in screen_shots if x.get("page") and not x.get("dialog") and not x.get("record")]
        for shot in screen_shots:
            img = shot_dir / f"{shot['name']}.png"
            if not img.exists():
                continue
            if shot.get("caption"):
                cap = shot["caption"]
            elif shot.get("dialog"):
                d_title = dialogs[shot["dialog"]]["title"]
                cap = d_title if d_title.lower().startswith(s["title"].lower()) else f"{s['title']}: {d_title} dialog"
            elif len(paged) > 1 and shot in paged:
                cap = f"{s['title']} ({paged.index(shot) + 1} of {len(paged)})"
            else:
                cap = s.get("caption") or s["title"]
            figs.add(img, cap)
        if s.get("sections"):
            heading(doc, f"3.{n}.1 Data Requirements", 3)
            rows, groups = field_rows(s["sections"])
            table(doc, field_header, rows, widths=field_widths, group_rows=groups)
        elif s.get("list"):
            lst = s["list"]
            heading(doc, f"3.{n}.1 Data Requirements", 3)
            table(doc, ["No.", "Column"], [[i, c["label"]] for i, c in enumerate(lst["columns"], 1)], widths=[1.2, 8])
            col_label = {c["field"]: c["label"] for c in lst["columns"]}
            if lst.get("search"):
                doc.add_paragraph("Search: " + ", ".join(col_label.get(f, pretty(f)) + " (partial match)" for f in lst["search"]))
            if lst.get("filters"):
                doc.add_paragraph("Filters: " + ", ".join(col_label.get(f, pretty(f)) for f in lst["filters"]) + (", Clear Filters" if lst.get("search") or lst.get("filters") else ""))
            if lst.get("sort"):
                doc.add_paragraph("Sort: " + fill(lst["sort"], f"screen {s['id']} sort"))
            acts = [a["label"] for a in (lst.get("toolbar") or []) + (lst.get("actions") or []) if not a.get("example")]
            if acts:
                doc.add_paragraph("Actions: " + ", ".join(acts))
        shown = set()
        for b in s.get("buttons", []) or []:
            d = dialogs.get(b.get("dialog"))
            if not d or d["id"] in shown or not d.get("fields") or d.get("srs_table") is False:
                continue
            shown.add(d["id"])
            para(doc, f"{d['title']} dialog", bold=True)
            rows, groups = field_rows([{"title": d["title"], "fields": d["fields"]}])
            table(doc, field_header, rows, widths=field_widths, group_rows=groups)

    # 4. NFR (always present, so later section numbers stay stable)
    heading(doc, "4.0 Non-Functional Requirements", 1)
    if spec.get("nfr"):
        table(doc, ["No.", "Area", "Requirement"], [[i, x["area"], x["requirement"]] for i, x in enumerate(spec["nfr"], 1)], widths=[1.2, 4, 11.5])
    else:
        doc.add_paragraph(f"Non-functional requirements (users, performance, availability, backup, retention, security and supported browsers) are to be confirmed. See {refs['section:open-issues']}.")

    # Extra sections (infrastructure, timeline...) are numbered after the NFRs; appendices go after sign-off.
    def extra_section(extra, title):
        heading(doc, title, 1)
        for block in extra.get("content", []):
            where = f"section '{extra['title']}'"
            if "heading" in block:
                heading(doc, block["heading"], 2)
            if "text" in block:
                doc.add_paragraph(fill(block["text"], where))
            if "bullets" in block:
                for b in block["bullets"]:
                    doc.add_paragraph(fill(b, where), style="List Bullet")
            if "table" in block:
                table(doc, block["table"]["header"], block["table"]["rows"])
            if "image" in block:
                img = project / "spec" / block["image"]
                if img.exists():
                    figs.add(img, block.get("caption", extra["title"]))
                else:
                    warnings.append(f"{where}: image {block['image']} not found")

    extras = spec.get("extra_sections", []) or []
    number = 5
    for extra in [e for e in extras if not e.get("appendix")]:
        extra_section(extra, f"{number}.0 {extra['title']}")
        number += 1

    # Open issues
    heading(doc, f"{open_number}.0 Open Issues", 1)
    reg_file = project / "register.json"
    items = json.loads(reg_file.read_text(encoding="utf-8"))["items"] if reg_file.exists() else []
    open_items = [it for it in items if it["audience"] == "client" and it["status"] not in ("resolved", "wont-fix")]
    if open_items:
        doc.add_paragraph(fill(bp["open_issues_intro"]))
        table(doc, ["ID", "Item", "Owner", "Due", "Status"],
              [[it["id"], it["question"], it.get("owner") or names["client_short"], it.get("due") or "-", it["status"].capitalize()] for it in open_items],
              widths=[1.6, 10.2, 2, 1.8, 1.6])
    else:
        doc.add_paragraph("There are no open issues at the time of this version.")

    # Sign-off
    heading(doc, "Client Acknowledgement and Sign-off", 1)
    for line in bp["signoff"]:
        doc.add_paragraph(fill(line))
    sig = doc.add_table(rows=1, cols=2)
    sig.style = "Table Grid"
    for i, who in enumerate((names["client"], co["name"])):
        c = sig.rows[0].cells[i]
        c.text = ""
        c.paragraphs[0].add_run(who).bold = True
        for label in ("Name:", "Designation:", "Department:", "Signature:", "Date:"):
            c.add_paragraph(label)

    appendices = [e for e in extras if e.get("appendix")]
    if appendices:
        page_break(doc)
    for i, extra in enumerate(appendices):
        extra_section(extra, f"Appendix {chr(65 + i)}: {extra['title']}")

    out_dir = project / "output"
    out_dir.mkdir(exist_ok=True)
    version = P.get("version", "draft")
    out = out_dir / f"{P['name']} – System Requirement Specifications v{version}.docx"
    doc.save(str(out))
    shutil.copy(project / "spec" / "app.yaml", out_dir / f"spec-v{version}.yaml")
    print(f"Wrote {out}")
    print(f"  {figs.n} figures, {len(spec.get('requirements', []))} requirement groups, {len(open_items)} open issues")
    if warnings:
        print(f"  {len(warnings)} WARNING(S) - fix these in the spec before issuing:")
        for w in warnings:
            print("   - " + w)
    if finish_in_word(out):
        print(f"  Table of contents updated; PDF written to {out.with_suffix('.pdf').name}")
    else:
        print("  Word not available: open the file and update the table of contents (right-click > Update Field).")
    return out


def finish_in_word(docx_path):
    """Update the table of contents and export a PDF using Microsoft Word, if it is installed."""
    import subprocess

    pdf = docx_path.with_suffix(".pdf")
    script = (
        "$ErrorActionPreference='Stop';"
        "$w=New-Object -ComObject Word.Application;$w.Visible=$false;"
        f"$d=$w.Documents.Open('{docx_path.resolve()}');"
        "foreach($t in $d.TablesOfContents){$t.Update()};"
        f"$d.Save();$d.ExportAsFixedFormat('{pdf.resolve()}',17);$d.Close();$w.Quit()"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=180)
        return r.returncode == 0 and pdf.exists()
    except Exception:
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    build(sys.argv[1])
