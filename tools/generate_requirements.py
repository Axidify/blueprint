"""Generate the requirements document (Word and PDF) from a project's spec, mock-up screenshots and register.

Usage:
    python -I tools/generate_requirements.py <project_dir>

Reads  <project_dir>/spec/app.yaml, <project_dir>/mockup/screenshots/ + shots.json (run
       `python -I tools/mockup.py screenshots <project_dir>` first), <project_dir>/register.json (open
       client items become "Decisions needed"), optional spec/client-logo.png and spec/process-flow.png.
Uses   the company profile and branding from the workspace (see tools/workspace.py), and the document format:
       templates/document-format.yaml, overridden key by key by workspace/branding/document-format.yaml.
Writes <project_dir>/output/<System> – <document title> v<version>.docx, a PDF when
       Microsoft Word is installed, and a snapshot of the spec used. A PDF from an earlier run is removed
       first, so the Word file and the PDF in output/ are always the same version of the content.
Warns  when the screenshots were taken before the spec's screens last changed, or one is missing.

Everything (access matrix, roles, statuses, screens, field tables) comes from the same spec as the
mock-up, so the document cannot contradict the screens. Format reference: docs/document-format.md.
"""
import copy
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

import yaml
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402  (company profile and branding)

TYPE_MAP = {
    "text": "Text", "textarea": "Long text", "select": "Drop-down", "radio": "Choice",
    "checkbox": "Checkboxes", "date": "Date", "datetime": "Date and time", "number": "Number",
    "file": "Attachment", "signature": "Signature", "user": "User",
}
REF = re.compile(r"\{ref:([a-z]+):([^}]+)\}")
LITERAL_REF = re.compile(r"\b(?:[Ss]ections? \d+(?:\.\d+)+|Appendix [A-Z]\b|Figure \d+)")
SKIP_ACTIONS = {"Back", "Cancel", "View"}


def pretty(field):
    return str(field).replace("_", " ").capitalize()


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


FRONT = ("cover", "at_a_glance", "about", "contents")
CHAPTERS = ("users_access", "scope", "by_role", "requirements", "screens", "nfr", "timeline", "extras", "decisions", "signoff")
STATUS_RULES = (("edit", "May edit"), ("cancel", "May cancel"), ("delete", "May delete"))  # plus `next`
SCOPE_PARTS = (("in_scope", "In scope"), ("out_of_scope", "Out of scope"), ("assumptions", "Assumptions"))
INTEGRATION_DETAILS = (("trigger", "Trigger"), ("data", "Data exchanged"), ("on_failure", "If it fails"))
SCOPE_INTRO = ("What this version of {system} covers, what it leaves out, and what has been assumed. "
               "Work outside this scope is agreed separately as a change request.")
DECISIONS_MADE_INTRO = "Questions raised during the requirement study and the answers given. These answers are part of what is signed."
OPTIONAL_COLORS = ("heading",)  # may be left empty


def default_format():
    return yaml.safe_load((ROOT / "templates" / "document-format.yaml").read_text(encoding="utf-8"))


def own_format_file():
    """The company's format file in the workspace (under its current or its pre-0.4.0 name), or None."""
    own = workspace.asset("document-format.yaml")
    return own if own and own.parent != ROOT / "templates" else None


def load_format():
    fmt = default_format()
    own = own_format_file()
    if own:
        fmt = deep_merge(fmt, yaml.safe_load(own.read_text(encoding="utf-8")) or {})
    return fmt


def format_errors(fmt):
    """Mistakes in a document format, as sentences for whoever edited it; empty when it is in order.
    Colours are tidied in place on the way: a leading '#' is dropped and letters are upper-cased."""
    base, errors = default_format(), []

    def unknown(where, keys, known):
        for k in keys:
            if k not in known:
                close = difflib.get_close_matches(str(k), [str(x) for x in known], 1, 0.6)
                errors.append(f"{where}'{k}' is not a setting" + (f" (did you mean '{close[0]}'?)" if close else ""))

    unknown("", fmt, base)
    for section, defaults in base.items():
        if isinstance(defaults, dict):
            if not isinstance(fmt.get(section), dict):
                errors.append(f"'{section}' must be a group of settings, like the one in templates/document-format.yaml")
                fmt[section] = defaults
            else:
                unknown(f"{section}: ", fmt[section], defaults)

    def colour(section, key, optional=False):
        value = fmt[section].get(key)
        if value in (None, "") and optional:
            fmt[section][key] = ""
            return
        text = str(value).strip().lstrip("#").upper()
        if isinstance(value, bool) or len(text) != 6 or any(ch not in "0123456789ABCDEF" for ch in text):
            hint = " Put it in quotes: digits alone are read as a number." if isinstance(value, int) else ""
            errors.append(f"{section}.{key}: '{value}' is not a colour. Use six hex digits, for example \"1F5FBF\".{hint}")
        else:
            fmt[section][key] = text

    for key in base["colors"]:
        colour("colors", key, key in OPTIONAL_COLORS)
    for key in ("header_fill", "header_text"):
        colour("tables", key, optional=True)
    if fmt["tables"].get("borders") not in ("hairline", "grid"):
        errors.append(f"tables.borders: '{fmt['tables'].get('borders')}' must be hairline or grid")
    for key in base["sizes"]:
        value = fmt["sizes"].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            errors.append(f"sizes.{key}: '{value}' must be a point size, for example 10")
    for key in base["fonts"]:
        if not isinstance(fmt["fonts"].get(key), str) or not fmt["fonts"][key].strip():
            errors.append(f"fonts.{key}: must be the name of a font")
    if fmt.get("numbering") not in ("plain", "decimal"):
        errors.append(f"numbering: '{fmt.get('numbering')}' must be plain or decimal")
    if fmt.get("header_footer") not in ("generated", "template"):
        errors.append(f"header_footer: '{fmt.get('header_footer')}' must be generated or template")
    if not isinstance(fmt["layout"].get("screens_new_page"), bool):
        errors.append("layout.screens_new_page: must be true or false")
    for key, allowed in (("front", FRONT), ("chapters", CHAPTERS)):
        if not isinstance(fmt.get(key), list):
            errors.append(f"{key}: must be a list, for example [{', '.join(allowed[:3])}]")
            continue
        for part in fmt[key]:
            if part not in allowed:
                close = difflib.get_close_matches(str(part), allowed, 1, 0.6)
                errors.append(f"{key}: '{part}' is not one of {', '.join(allowed)}" + (f" (did you mean '{close[0]}'?)" if close else ""))
    for key in list(CHAPTERS) + ["at_a_glance", "about"]:
        if key != "extras" and not str(fmt["titles"].get(key) or "").strip():
            errors.append(f"titles.{key}: needs a title")
    for key in base["labels"]:
        if not str(fmt["labels"].get(key) or "").strip():
            errors.append(f"labels.{key}: needs a wording")
    return errors


def document_errors(spec):
    """Mistakes in the parts of a spec that only the document prints, as sentences; empty when in order.
    The mock-up's own check (mockup.validate) covers what the screens need."""
    errors = []

    def need(where, item, *keys):
        if not isinstance(item, dict):
            errors.append(f"{where}: must have {', '.join(keys)}")
            return False
        for k in keys:
            if item.get(k) in (None, "", []):
                errors.append(f"{where}: missing '{k}'")
        return True

    def each(key):
        value = spec.get(key) or []
        if not isinstance(value, list):
            errors.append(f"{key}: must be a list")
            return []
        return list(enumerate(value, 1))

    if not (spec.get("project") or {}).get("name"):
        errors.append("project: missing 'name'")
    for i, r in each("roles"):
        need(f"role {i}", r, "id", "name")
    role_ids = {r.get("id") for r in spec.get("roles") or [] if isinstance(r, dict)}
    status_ids = {s.get("id") for s in spec.get("statuses") or [] if isinstance(s, dict)}
    for i, s in each("statuses"):
        if not need(f"status {i}", s, "name"):
            continue
        for key, _ in STATUS_RULES:
            value = s.get(key)
            if value is None or value in ("all", "none"):
                continue
            if not isinstance(value, list):
                errors.append(f"status {s['name']}: '{key}' must be a list of role ids, or all, or none")
            else:
                for r in value:
                    if r not in role_ids:
                        errors.append(f"status {s['name']}: '{key}' names an unknown role '{r}'")
        nxt = s.get("next")
        if nxt is not None and not isinstance(nxt, list):
            errors.append(f"status {s['name']}: 'next' must be a list of status ids (empty for a final status)")
        for other in nxt if isinstance(nxt, list) else []:
            if other not in status_ids:
                errors.append(f"status {s['name']}: 'next' names an unknown status '{other}'")
    scope = spec.get("scope")
    if scope is not None:
        if not isinstance(scope, dict):
            errors.append("scope: must have in_scope, out_of_scope and assumptions")
        else:
            for key in scope:
                if key not in dict(SCOPE_PARTS):
                    errors.append(f"scope: '{key}' is not one of in_scope, out_of_scope, assumptions")
                elif not isinstance(scope[key], list) or any(not isinstance(x, str) or not x.strip() for x in scope[key]):
                    errors.append(f"scope: '{key}' must be a list of sentences")
    for i, s in each("screens"):
        if not need(f"screen {s.get('id', i) if isinstance(s, dict) else i}", s, "id", "title"):
            continue
        for sec in s.get("sections") or []:
            for f in sec.get("fields") or []:
                need(f"screen {s['id']}, field {f.get('id', '?') if isinstance(f, dict) else '?'}", f, "id", "label")
        for c in (s.get("list") or {}).get("columns") or []:
            need(f"screen {s['id']}, a list column", c, "field", "label")
    for i, d in each("dialogs"):
        if need(f"dialog {i}", d, "id", "title"):
            for f in d.get("fields") or []:
                need(f"dialog {d['id']}, field {f.get('id', '?') if isinstance(f, dict) else '?'}", f, "id", "label")
    seen = set()
    for i, g in each("requirements"):
        where = f"requirement group {g.get('id', i) if isinstance(g, dict) else i}"
        if not need(where, g, "id", "title"):
            continue
        if g.get("id") in seen:
            errors.append(f"{where}: the id is used twice")
        seen.add(g.get("id"))
        items = g.get("items")
        if not isinstance(items, list) or not items:
            errors.append(f"{where}: needs 'items', the list of its requirements")
            continue
        for j, item in enumerate(items, 1):
            text = item.get("text") if isinstance(item, dict) else item
            if not isinstance(text, str) or not text.strip():
                errors.append(f"{where}, item {j}: needs its text")
    for i, n in each("notifications"):
        need(f"notification {i}", n, "event", "recipient")
    for i, x in each("nfr"):
        need(f"non-functional requirement {i}", x, "area", "requirement")
    for i, x in each("glossary"):
        need(f"glossary entry {i}", x, "term", "meaning")
    for i, x in each("integrations"):
        need(f"integration {i}", x, "system")
    for i, s in each("screens"):
        for stat in (s.get("stats") or []) if isinstance(s, dict) else []:
            if not isinstance(stat, dict) or not stat.get("label"):
                errors.append(f"screen {s.get('id', i)}: every figure in 'stats' needs a label")
            elif "formula" in stat and (not isinstance(stat["formula"], str) or not stat["formula"].strip()):
                errors.append(f"screen {s.get('id', i)}, figure {stat['label']}: 'formula' must say in words how it is worked out")
    for i, x in each("signoff"):
        if not isinstance(x, dict):
            errors.append(f"signatory {i}: must have name, organisation and signing_for")
    titles = set()
    for i, e in each("extra_sections"):
        if not need(f"extra section {i}", e, "title"):
            continue
        if e["title"] in titles:
            errors.append(f"extra section '{e['title']}': two sections have this title; give each its own")
        titles.add(e["title"])
        for block in e.get("content") or []:
            table = block.get("table") if isinstance(block, dict) else None
            if table is not None and need(f"extra section '{e['title']}', a table", table, "header", "rows"):
                if any(not isinstance(row, list) or len(row) != len(table["header"]) for row in table["rows"]):
                    errors.append(f"extra section '{e['title']}': every table row needs {len(table['header'])} cells, like its header")
    timeline = spec.get("timeline")
    if timeline is not None and not isinstance(timeline, dict):
        errors.append("timeline: must have stages")
    stages = (timeline.get("stages") or []) if isinstance(timeline, dict) else []
    for st in stages:
        for it in (st.get("items") or []) if isinstance(st, dict) else []:
            where = f"timeline item '{it.get('name') or it.get('milestone') or '?'}'" if isinstance(it, dict) else "timeline item"
            if not need(where, it, "name"):
                continue
            weeks = [it.get("week", it.get("start"))] if "milestone" in it else [it.get("start"), it.get("end", it.get("start"))]
            if any(isinstance(w, bool) or not isinstance(w, int) or w < 1 for w in weeks):
                errors.append(f"{where}: " + ("'week'" if "milestone" in it else "'start' and 'end'") + " must be week numbers from 1")
            elif len(weeks) == 2 and weeks[1] < weeks[0]:
                errors.append(f"{where}: 'end' is before 'start'")
    return errors


# ====================================================================== low-level Word helpers
def rgb(hexstr):
    return RGBColor.from_string(hexstr.upper())


def set_fonts(rpr_owner, name):
    """Set every font slot (Latin, complex script, East Asian) so Word does not substitute."""
    rpr = rpr_owner.get_or_add_rPr() if hasattr(rpr_owner, "get_or_add_rPr") else rpr_owner
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.insert(0, fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), name)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        fonts.attrib.pop(qn(attr), None)


def shade(el_pr, fill):
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    el_pr.append(shd)


def box(cell, color, size=4):
    """A line on all four sides of a cell, replacing any lines it had."""
    tc_pr = cell._tc.get_or_add_tcPr()
    old = tc_pr.find(qn("w:tcBorders"))
    if old is not None:
        tc_pr.remove(old)
    for side in ("top", "left", "bottom", "right"):
        cell_border(cell, side, color, size)


def cell_border(cell, side, color, size=4):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    b = OxmlElement(f"w:{side}")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), str(size))
    b.set(qn("w:color"), color)
    borders.append(b)


def para_border_bottom(paragraph, color, size=6):
    p_pr = paragraph._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    b = OxmlElement("w:bottom")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), str(size))
    b.set(qn("w:space"), "1")
    b.set(qn("w:color"), color)
    bdr.append(b)
    p_pr.append(bdr)


def table_base(t, cell_spacing=None, pad=(70, 110)):
    tbl_pr = t._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "nil")
        borders.append(b)
    tbl_pr.append(borders)
    mar = OxmlElement("w:tblCellMar")
    for side, w in (("top", pad[0]), ("bottom", pad[0]), ("left", pad[1]), ("right", pad[1])):
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), str(w))
        m.set(qn("w:type"), "dxa")
        mar.append(m)
    tbl_pr.append(mar)
    if cell_spacing:
        sp = OxmlElement("w:tblCellSpacing")
        sp.set(qn("w:w"), str(cell_spacing))
        sp.set(qn("w:type"), "dxa")
        tbl_pr.append(sp)


def fixed_widths(t, widths):
    t.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)
    for i, w in enumerate(widths):
        t.columns[i].width = Cm(w)
    for row in t.rows:
        for i, w in enumerate(widths):
            if i < len(row.cells):
                row.cells[i].width = Cm(w)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def keep_row_together(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def no_break_hyphens(run):
    """Keep an ID such as FR-BKG-001.2 on one line. Word breaks a line at an ordinary hyphen; its own
    non-breaking hyphen is drawn with the same glyph (the document fonts have no U+2011 of their own)."""
    for t in list(run._r.findall(qn("w:t"))):
        first, *rest = (t.text or "").split("-")
        if not rest:
            continue
        t.text, at = first, t
        for part in rest:
            hyphen = OxmlElement("w:noBreakHyphen")
            at.addnext(hyphen)
            at = OxmlElement("w:t")
            at.set(qn("xml:space"), "preserve")
            at.text = part
            hyphen.addnext(at)


def add_field(paragraph, instr):
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, instr), ("separate", None), (None, ""), ("end", None)):
        if tag:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), tag)
            run._r.append(fld)
        elif text is not None and text != "":
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = text
            run._r.append(it)
        else:
            t = OxmlElement("w:t")
            t.text = "1"
            run._r.append(t)
    return run


# ====================================================================== the document writer
class Writer:
    """Writes styled content. Text segments are (text, style) pairs so one line can mix plain words,
    secondary text, mono IDs, accent references, tags and status dots."""

    def __init__(self, doc, fmt):
        self.doc, self.f = doc, fmt
        self.c, self.s, self.fn = fmt["colors"], fmt["sizes"], fmt["fonts"]
        self.figures = 0
        self.pictures = []  # the image file of every figure, in order: put back at full size in the PDF
        sec = doc.sections[0]
        self.text_width = (sec.page_width - sec.left_margin - sec.right_margin) / 360000  # cm

    # ---- styles
    def setup_styles(self):
        st = self.doc.styles
        normal = st["Normal"]
        normal.font.size = Pt(self.s["body"])
        normal.font.color.rgb = rgb(self.c["text"])
        set_fonts(normal.element, self.fn["body"])
        normal.paragraph_format.space_after = Pt(5)
        normal.paragraph_format.widow_control = True  # no single lines stranded at a page edge
        normal.paragraph_format.line_spacing = 1.15
        for name, size, before, after in (("Heading 1", self.s["h1"], 0, 8), ("Heading 2", self.s["h2"], 16, 5),
                                          ("Heading 3", self.s["h3"], 12, 4)):
            h = st[name]
            h.font.size = Pt(size)
            h.font.bold = False
            h.font.italic = False
            h.font.color.rgb = rgb(self.c.get("heading") or self.c["text"])
            set_fonts(h.element, self.fn["heading"])
            pf = h.paragraph_format
            pf.space_before, pf.space_after, pf.keep_with_next = Pt(before), Pt(after), True
            if name == "Heading 1":
                pf.page_break_before = True
        cap = st["Caption"]
        cap.font.size = Pt(self.s["caption"])
        cap.font.italic = False
        cap.font.bold = False
        cap.font.color.rgb = rgb(self.c["secondary"])
        set_fonts(cap.element, self.fn["body"])
        present = {s.name: s for s in st}
        for name, before in (("toc 1", 5), ("toc 2", 0), ("toc 3", 0), ("TOC Heading", None)):
            toc = present.get(name) or present.get(name.upper())
            if toc is None:
                continue
            set_fonts(toc.element, self.fn["body"] if before is not None else self.fn["heading"])
            toc.font.color.rgb = rgb(self.c["text"])
            if before is not None:  # a line of the contents: close together, chapters set apart a little
                toc.paragraph_format.space_before, toc.paragraph_format.space_after = Pt(before), Pt(1)
                toc.paragraph_format.line_spacing = 1.0

    # ---- text
    def runs(self, paragraph, segments, size=None):
        if isinstance(segments, str):
            segments = [(segments, "")]
        for text, style in segments:
            if style == "dot":  # text is the colour key; renders "● " in that colour
                r = paragraph.add_run("● ")
                r.font.color.rgb = rgb(self.c[text])
                r.font.size = Pt((size or self.s["body"]) * 0.8)
                continue
            r = paragraph.add_run(text if style != "tag" else f" {text} ")
            if size:
                r.font.size = Pt(size)
            if style in ("sec", "tag"):
                r.font.color.rgb = rgb(self.c["secondary"] if style == "sec" else self.c["text"])
            if style == "ref":
                r.font.color.rgb = rgb(self.c["accent"])
            if style == "mono":
                set_fonts(r._r, self.fn["mono"])
                r.font.color.rgb = rgb(self.c["secondary"])
                r.font.size = Pt((size or self.s["body"]) * 0.95)
            if style == "medium":
                set_fonts(r._r, self.fn["heading"])
            if style == "tag":
                shade(r._r.get_or_add_rPr(), self.c["field"])
                r.font.size = Pt((size or self.s["body"]) * 0.95)
            if style in ("mono", "ref"):  # IDs and references: never split at a hyphen
                no_break_hyphens(r)
        return paragraph

    def para(self, segments, size=None, after=None, before=None, align=None, style=None, keep=False):
        p = self.doc.add_paragraph(style=style) if style else self.doc.add_paragraph()
        self.runs(p, segments, size)
        if keep:
            p.paragraph_format.keep_with_next = True
        if after is not None:
            p.paragraph_format.space_after = Pt(after)
        if before is not None:
            p.paragraph_format.space_before = Pt(before)
        if align:
            p.alignment = align
        return p

    def heading(self, text, level, page_break=None):
        h = self.doc.add_heading(text, level=level)
        if page_break is False and level == 1:
            h.paragraph_format.page_break_before = False
        return h

    def page_title(self, text, after=8):
        """The title of a front-matter page: looks like a chapter heading, but stays out of the contents."""
        p = self.para([(text, "medium")], size=self.s["h1"], after=after)
        p.runs[0].font.color.rgb = rgb(self.c.get("heading") or self.c["text"])
        return p

    def lead(self, text):
        return self.para([(text, "sec")], after=10, keep=True)

    def glue_previous(self):
        """Keep the paragraph just written (a heading, label or intro) on the same page as what comes next."""
        body = self.doc.element.body
        last = body[-2] if body[-1].tag == qn("w:sectPr") and len(body) > 1 else body[-1]
        if last.tag == qn("w:p"):
            style = last.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
            if style is not None and style.get(qn("w:val")) == "Caption":
                return  # a figure's caption: don't chain figures together into blocks taller than a page
            p_pr = last.get_or_add_pPr()
            if p_pr.find(qn("w:keepNext")) is None:
                p_pr.append(OxmlElement("w:keepNext"))

    @staticmethod
    def keep_row_with_next(row):
        for c in row.cells:
            for para_ in c.paragraphs:
                para_.paragraph_format.keep_with_next = True

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---- tables: hairline style
    def table(self, header, rows, widths, group_rows=(), size=None, pad=None, center_from=None, rotate_from=None,
              header_height=None):
        """Hairline table. center_from centres columns from that index (ticks); rotate_from turns those
        header cells to read bottom-to-top, for narrow columns such as the roles in the access matrix."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE

        size = size or self.s["table"]
        look = self.f.get("tables") or {}
        fill, grid = look.get("header_fill"), look.get("borders") == "grid"
        header_text = look.get("header_text") or ("FFFFFF" if fill else self.c["secondary"])
        self.glue_previous()
        t = self.doc.add_table(rows=1, cols=len(header))
        t.alignment = WD_TABLE_ALIGNMENT.LEFT
        table_base(t, **({"pad": pad} if pad else {}))
        for i, h in enumerate(header):
            cell = t.rows[0].cells[i]
            cell.paragraphs[0].text = ""
            # Allow a line break after "/" (Build/Compiler) so words never break in the middle.
            r = cell.paragraphs[0].add_run(str(h).replace("/", "/\u200b"))
            if rotate_from is not None and i >= rotate_from:
                td = OxmlElement("w:textDirection")
                td.set(qn("w:val"), "btLr")
                cell._tc.get_or_add_tcPr().append(td)
            elif center_from is not None and i >= center_from:
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            r.font.size = Pt(self.s["table_header"])
            r.font.color.rgb = rgb(header_text)
            cell_border(cell, "bottom", self.c["line"], 6)
            if fill:
                shade(cell._tc.get_or_add_tcPr(), fill)
        repeat_header(t.rows[0])
        if rotate_from is not None:
            from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
            for c in t.rows[0].cells:
                c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
        if header_height:
            t.rows[0].height = Cm(header_height)
            t.rows[0].height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        for r_i, row in enumerate(rows):
            cells = t.add_row().cells
            keep_row_together(t.rows[-1])
            if r_i in group_rows:
                merged = cells[0].merge(cells[-1])
                merged.paragraphs[0].text = ""
                self.runs(merged.paragraphs[0], [(row[0], "medium")], size)
                cell_border(merged, "bottom", self.c["separator"])
                # A group heading row (e.g. "Approval Process") stays with the rows under it.
                merged.paragraphs[0].paragraph_format.keep_with_next = True
                continue
            for i, v in enumerate(row):
                p = cells[i].paragraphs[0]
                p.text = ""
                if isinstance(v, list):
                    self.runs(p, v, size)
                else:
                    self.runs(p, [("" if v is None else str(v), "")], size)
                p.paragraph_format.space_after = Pt(0)
                if center_from is not None and i >= center_from:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cell_border(cells[i], "bottom", self.c["separator"])
        if grid:  # a box round every cell, in place of the lines between rows
            for row in t.rows:
                done = set()
                for cell in row.cells:  # a merged cell appears once per column it spans
                    if id(cell._tc) not in done:
                        done.add(id(cell._tc))
                        box(cell, self.c["line"])
        fixed_widths(t, widths)
        # The header row and the first two rows move together, so a table never starts with a lone header
        # at the foot of a page. Short tables (up to 6 rows) are kept whole.
        keep = len(t.rows) - 1 if len(t.rows) <= 7 else min(3, len(t.rows) - 1)
        for row in t.rows[:keep]:
            self.keep_row_with_next(row)
        gap = self.doc.add_paragraph()
        gap.paragraph_format.space_after = Pt(4)
        return t

    def kv_table(self, pairs, widths):
        t = self.doc.add_table(rows=0, cols=2)
        table_base(t)
        for k, v in pairs:
            cells = t.add_row().cells
            self.runs(cells[0].paragraphs[0], [(k, "sec")], self.s["table"] + 0.5)
            self.runs(cells[1].paragraphs[0], v if isinstance(v, list) else [(str(v), "")], self.s["table"] + 0.5)
            for c in cells:
                c.paragraphs[0].paragraph_format.space_after = Pt(0)
                cell_border(c, "bottom", self.c["separator"])
        fixed_widths(t, widths)
        return t

    def signature_block(self, person, org_line, marker):
        """One signatory as a single form: a caption line, then a bordered grid of label and value rows
        (name, designation, signature, date) with the company stamp in a full-height box on the right.
        Every line and edge aligns, it is kept on one page, and it prints and scans cleanly. The marker
        lets the PDF step place a digital signature field exactly over the signature cell."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT as VA

        grid = "B4B2A9"
        label_w, stamp_w = 3.6, 4.0
        value_w = self.text_width - label_w - stamp_w
        cap = self.doc.add_paragraph()
        cap.paragraph_format.keep_with_next = True
        cap.paragraph_format.space_before = Pt(10)
        cap.paragraph_format.space_after = Pt(4)
        signing_for = person.get("signing_for")
        if signing_for and signing_for.lower() in org_line.lower().split(" · ")[0].lower():
            signing_for = None  # "Supplier · … · signing for Supplier" says the same thing twice
        self.runs(cap, [(org_line, "medium")] + ([("  \u00B7  signing for " + signing_for, "sec")] if signing_for else []),
                  self.s["table"] + 0.5)

        rows = [("Name", person.get("name") or "", 0.85),
                ("Designation", ", ".join(x for x in (person.get("designation"), person.get("department")) if x), 0.85),
                ("Signature", "", 2.3),
                ("Date", "", 0.85)]
        t = self.doc.add_table(rows=len(rows), cols=3)
        table_base(t, pad=(60, 110))
        for i, (label, value, height) in enumerate(rows):
            row = t.rows[i]
            row.height = Cm(height)
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            keep_row_together(row)
            lab, val = row.cells[0], row.cells[1]
            lab.vertical_alignment = VA.CENTER if height < 1.5 else VA.TOP
            val.vertical_alignment = VA.CENTER if height < 1.5 else VA.TOP
            self.runs(lab.paragraphs[0], [(label, "sec")], self.s["table"])
            if label == "Signature":
                r = val.paragraphs[0].add_run(marker)
                r.font.size = Pt(1)
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            elif value:
                self.runs(val.paragraphs[0], [(value, "medium" if label == "Name" else "")], self.s["table"] + 0.5)
            for c in (lab, val):
                c.paragraphs[0].paragraph_format.space_after = Pt(0)
                for side in ("top", "left", "bottom", "right"):
                    cell_border(c, side, grid, 4)
            # Keep the whole form on one page: every paragraph except the last keeps with the next.
            for c in (lab, val):
                c.paragraphs[0].paragraph_format.keep_with_next = i < len(rows) - 1
        # A vertically merged cell keeps one border set per row in Word: set them on every row's piece first.
        for i in range(len(rows)):
            piece = t.rows[i].cells[2]
            for side in ("left", "right") + (("top",) if i == 0 else ()) + (("bottom",) if i == len(rows) - 1 else ()):
                cell_border(piece, side, grid, 4)
        stamp = t.cell(0, 2).merge(t.cell(len(rows) - 1, 2))
        stamp.vertical_alignment = VA.BOTTOM
        for para in stamp.paragraphs[1:]:
            para._p.getparent().remove(para._p)
        stamp.paragraphs[0].text = ""
        self.runs(stamp.paragraphs[0], [("Company stamp", "sec")], self.s["caption"])
        stamp.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        fixed_widths(t, [label_w, value_w, stamp_w])
        gap = self.doc.add_paragraph()
        gap.paragraph_format.space_after = Pt(8)

    def cards(self, items, value_size=18):
        t = self.doc.add_table(rows=1, cols=len(items))
        table_base(t, cell_spacing=90, pad=(110, 150))
        for i, (value, label, color) in enumerate(items):
            cell = t.rows[0].cells[i]
            shade(cell._tc.get_or_add_tcPr(), self.c["ground"])
            p = cell.paragraphs[0]
            r = p.add_run(str(value))
            r.font.size = Pt(value_size)
            set_fonts(r._r, self.fn["heading"])
            if color:
                r.font.color.rgb = rgb(self.c[color])
            p.paragraph_format.space_after = Pt(0)
            self.runs(cell.add_paragraph(), [(label, "sec")], self.s["caption"])
        # Word puts a gap (the cell spacing, 0.32 cm in all) between the cards and half of one outside the
        # first and last: size the cards so the row is exactly as wide as the text, and pull the table back
        # by the outer gap so its first card starts at the margin.
        w = (self.text_width - 0.32 * (len(items) - 1)) / len(items)
        fixed_widths(t, [w] * len(items))
        ind = OxmlElement("w:tblInd")
        ind.set(qn("w:w"), "-180")
        ind.set(qn("w:type"), "dxa")
        t._tbl.tblPr.append(ind)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def gantt(self, stages, unit="Week"):
        """The project timeline as a chart: one row per activity or milestone, one narrow column per week
        (or per group of weeks on long projects), stages as shaded bands. Bars are paragraph shading on
        cells with no side margins, so neighbouring weeks join into one thin bar."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE
        from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT as VA
        from docx.enum.text import WD_LINE_SPACING

        def span(it):
            if "milestone" in it:
                w_ = int(it.get("week", it.get("start", 1)))
                return w_, w_
            return int(it["start"]), int(it.get("end", it["start"]))

        last = max((span(it)[1] for st in stages for it in st.get("items", [])), default=1)
        step = max(1, -(-last // 40))  # weeks per column: at most 40 columns
        cols = -(-last // step)
        # The label column fits the longest name on one line (rows have a fixed height), within limits.
        char_cm = (self.s["table"] - 0.5) * 0.5 / 72 * 2.54
        longest = max((len(str(it.get("name", ""))) + 5 for st in stages for it in st.get("items", [])), default=20)
        label_w = min(7.5, max(4.5, longest * char_cm + 0.4))
        col_w = (self.text_width - label_w) / cols
        size = self.s["table"] - 0.5
        n_rows = 1 + sum(1 + len(st.get("items", [])) for st in stages)
        self.glue_previous()
        t = self.doc.add_table(rows=n_rows, cols=cols + 1)
        t.alignment = WD_TABLE_ALIGNMENT.LEFT
        table_base(t, pad=(0, 0))

        def label(cell, segments, fill=None):
            p_ = cell.paragraphs[0]
            p_.paragraph_format.space_after = Pt(0)
            p_.paragraph_format.left_indent = Cm(0.1)
            self.runs(p_, segments, size)
            cell.vertical_alignment = VA.CENTER
            if fill:
                shade(cell._tc.get_or_add_tcPr(), fill)

        def bar(cell, fill):
            p_ = cell.paragraphs[0]
            p_.paragraph_format.space_after = Pt(0)
            p_.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            p_.paragraph_format.line_spacing = Pt(5)
            shade(p_._p.get_or_add_pPr(), fill)
            mark = OxmlElement("w:rPr")
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), "8")
            mark.append(sz)
            p_._p.get_or_add_pPr().append(mark)
            cell.vertical_alignment = VA.CENTER

        def diamond(cell):
            p_ = cell.paragraphs[0]
            p_.paragraph_format.space_after = Pt(0)
            p_.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p_.add_run("\u25C6")
            set_fonts(r._r, "Segoe UI Symbol")
            r.font.size = Pt(size)
            r.font.color.rgb = rgb(self.c["accent"])
            cell.vertical_alignment = VA.CENTER

        light = self.c.get("timeline_bar", "C9D8EF")
        rows = list(t.rows)
        for row in rows:
            row.height = Cm(0.5)
            row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
            keep_row_together(row)
        # header: a week number every 4 columns
        head = rows[0]
        label(head.cells[0], [(unit, "sec")])
        starts = list(range(1, cols + 1, 4))
        for c in reversed(starts):
            n = min(4, cols - c + 1)
            cell = head.cells[c].merge(head.cells[c + n - 1]) if n > 1 else head.cells[c]
            label(cell, [(str((c - 1) * step + 1), "sec")])
        for cell in head.cells:
            cell_border(cell, "bottom", self.c["line"], 6)
        repeat_header(head)
        r_i = 1
        for st in stages:
            band = rows[r_i].cells[0].merge(rows[r_i].cells[-1])
            label(band, [(st.get("name", ""), "medium")], self.c["ground"])
            r_i += 1
            for it in st.get("items", []):
                cells = rows[r_i].cells
                a, b = span(it)
                if "milestone" in it:
                    label(cells[0], [(str(it["milestone"]).ljust(4), "mono"), (it.get("name", ""), "ref")])
                    cells[0].paragraphs[0].runs[0].font.color.rgb = rgb(self.c["accent"])
                    diamond(cells[(a - 1) // step + 1])
                else:
                    ref = str(it.get("ref", ""))
                    label(cells[0], ([(ref.ljust(4), "mono")] if ref else []) + [(it.get("name", ""), "")])
                    fill = self.c["accent"] if it.get("client") else light
                    first, end = (a - 1) // step + 1, (b - 1) // step + 1
                    # One merged cell per bar, so the bar is a single unbroken shape.
                    for cell in cells:
                        cell_border(cell, "bottom", self.c["separator"])
                    span_cell = cells[first].merge(cells[end]) if end > first else cells[first]
                    bar(span_cell, fill)
                    r_i += 1
                    continue
                for cell in cells:
                    cell_border(cell, "bottom", self.c["separator"])
                r_i += 1
        fixed_widths(t, [label_w] + [col_w] * cols)
        # Keep the chart on one page when it fits; otherwise keep only the header with the first row.
        whole = n_rows <= 38
        for i, row in enumerate(rows[:-1]):
            if whole or i == 0:
                self.keep_row_with_next(row)
        gap = self.doc.add_paragraph()
        gap.paragraph_format.space_after = Pt(2)
        return t

    def figure(self, image, caption, width_cm=None):
        """A screenshot on the grey ground, like a product shot, with a quiet caption."""
        width_cm = width_cm or (self.text_width - 0.8)
        self.glue_previous()
        # Picture and caption are two rows of one table, kept together: Word does not reliably keep a table
        # with the paragraph after it, but it does keep rows of the same table together.
        t = self.doc.add_table(rows=2, cols=1)
        table_base(t, pad=(140, 200))
        cell = t.rows[0].cells[0]
        shade(cell._tc.get_or_add_tcPr(), self.c["ground"])
        cell.paragraphs[0].add_run().add_picture(str(image), width=Cm(width_cm - 0.7))
        self.pictures.append(Path(image))
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.paragraphs[0].paragraph_format.space_after = Pt(0)
        cell.paragraphs[0].paragraph_format.keep_with_next = True
        self.figures += 1
        cap_cell = t.rows[1].cells[0]
        mar = OxmlElement("w:tcMar")
        for side, wv in (("top", 70), ("left", 0), ("bottom", 0), ("right", 0)):
            m = OxmlElement(f"w:{side}")
            m.set(qn("w:w"), str(wv))
            m.set(qn("w:type"), "dxa")
            mar.append(m)
        cap_cell._tc.get_or_add_tcPr().append(mar)
        cap = cap_cell.paragraphs[0]
        cap.style = self.doc.styles["Caption"]
        cap.add_run(f"Figure {self.figures} · {caption}")
        cap.paragraph_format.space_before = Pt(0)
        cap.paragraph_format.space_after = Pt(0)
        for row in t.rows:
            keep_row_together(row)
        fixed_widths(t, [width_cm])
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

    def bullets(self, items):
        for it in items:
            p = self.doc.add_paragraph(style="List Bullet")
            self.runs(p, it if isinstance(it, list) else [(it, "")])
            p.paragraph_format.space_after = Pt(2)

    def line_list(self, items, refs=None):
        """Rows separated by hairlines, with an optional accent reference on the right."""
        self.glue_previous()
        t = self.doc.add_table(rows=0, cols=2)
        table_base(t, pad=(50, 0))
        for i, item in enumerate(items):
            cells = t.add_row().cells
            self.runs(cells[0].paragraphs[0], item if isinstance(item, list) else [(item, "")])
            ref = (refs or [None] * len(items))[i]
            if ref:
                self.runs(cells[1].paragraphs[0], [(ref, "ref")])
                cells[1].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            for c in cells:
                c.paragraphs[0].paragraph_format.space_after = Pt(0)
                if i < len(items) - 1:
                    cell_border(c, "bottom", self.c["separator"])
        fixed_widths(t, [self.text_width - 2.2, 2.2])
        for row in t.rows[:-1] if len(t.rows) <= 12 else t.rows[:3]:
            self.keep_row_with_next(row)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ---- header and footer
    def header_footer(self, left_top, right_top, left_bottom):
        for sec in self.doc.sections:
            sec.different_first_page_header_footer = True
            for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
                part.is_linked_to_previous = False
                for child in list(part._element):
                    part._element.remove(child)
                part._element.append(OxmlElement("w:p"))
            tab = sec.page_width - sec.left_margin - sec.right_margin
            for part, left, right, top in ((sec.header, left_top, right_top, True), (sec.footer, left_bottom, None, False)):
                p = part.paragraphs[0]
                p.paragraph_format.tab_stops.add_tab_stop(tab, WD_TAB_ALIGNMENT.RIGHT)
                self.runs(p, [(left, "sec"), ("\t", "")], self.s["caption"])
                if right:
                    self.runs(p, [(right, "sec")], self.s["caption"])
                else:
                    r = add_field(p, "PAGE")
                    r.font.size = Pt(self.s["caption"])
                    r.font.color.rgb = rgb(self.c["secondary"])
                if top:
                    para_border_bottom(p, self.c["separator"], 4)
                    p.paragraph_format.space_after = Pt(0)
            fp = sec.first_page_footer.paragraphs[0]
            self.runs(fp, [(left_bottom, "sec")], self.s["caption"])


# ====================================================================== building the plan
def plan_sections(spec, fmt, reg_items):
    """Decide every chapter and sub-section number before writing, so {ref:...} resolves anywhere."""
    dec = fmt.get("numbering", "plain") == "decimal"
    chap = lambda n: f"{n}.0" if dec else f"{n}"
    refs, chapters, n = {}, [], 0
    extras = [e for e in (spec.get("extra_sections") or []) if not e.get("appendix")]
    for key in fmt["chapters"]:
        if key == "signoff":
            chapters.append(("signoff", None, fmt["titles"]["signoff"]))
            continue
        if key == "extras":
            for e in extras:
                n += 1
                chapters.append(("extra", chap(n), e["title"]))
                refs[f"extra:{e['title']}"] = f"section {chap(n)}"
            continue
        if key == "by_role" and not spec.get("roles"):
            continue
        if key == "timeline" and not spec.get("timeline"):
            continue
        if key == "scope" and not spec.get("scope"):
            continue
        n += 1
        chapters.append((key, chap(n), fmt["titles"][key]))
        refs[f"section:{ {'users_access': 'users', 'scope': 'scope', 'by_role': 'by-role', 'requirements': 'requirements', 'screens': 'screens', 'nfr': 'nfr', 'timeline': 'timeline', 'decisions': 'open-issues'}[key] }"] = f"section {chap(n)}"
        if key == "decisions":
            refs["section:decisions"] = f"section {chap(n)}"
        if key == "users_access":
            sub = [("roles", True), ("access", True), ("flow", bool(spec.get("statuses"))),
                   ("integrations", bool(spec.get("integrations"))), ("notifications", bool(spec.get("notifications"))),
                   ("glossary", bool(spec.get("glossary")))]
            k = 0
            for name, present in sub:
                if present:
                    k += 1
                    refs[f"section:{name}"] = f"section {n}.{k}"
        if key == "screens":
            for i, s in enumerate(spec["screens"], 1):
                refs[f"screen:{s['id']}"] = f"section {n}.{i}"
        if key == "by_role":
            for i, r in enumerate(spec["roles"], 1):
                refs[f"role:{r['id']}"] = f"section {n}.{i}"
        if key == "requirements":
            for i, g in enumerate(spec.get("requirements", []), 1):
                refs[f"req:{g['id']}"] = g["id"]
    for i, e in enumerate([e for e in (spec.get("extra_sections") or []) if e.get("appendix")]):
        refs[f"extra:{e['title']}"] = f"Appendix {chr(65 + i)}"
    return chapters, refs


def status_is_settled(text):
    """Whether a document status reads as settled (a green dot on the cover) and not as still open (amber):
    "Signed off", "Approved", "Final" are settled; "Not approved", "Unsigned draft", "Awaiting final review"
    are not."""
    return (bool(re.search(r"\b(signed|approved|accepted|final)\b", text, re.I))
            and not re.search(r"\b(not|no|draft|pending|awaiting|review|before|until|un\w+)\b", text, re.I))


def short(ref):
    """'section 4.3' -> '4.3' for compact reference columns."""
    return ref.replace("section ", "") if ref else ""


def as_word(value):
    """A table cell from the spec as it was meant. YAML reads an unquoted No, Yes, Off or On as false or
    true; in a document table it is a word, such as "No" heading a numbering column or "Yes" in a cell."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return value


# ====================================================================== main
def build(project):
    project = Path(project)
    spec = json.loads(json.dumps(yaml.safe_load((project / "spec" / "app.yaml").read_text(encoding="utf-8")), default=str))
    import mockup  # the spec check, and whether the screenshots still show the spec
    import project as project_tool  # issued versions are locked

    issued = project_tool.is_issued(project, spec["project"].get("version", ""))
    if issued:
        sys.exit(f"v{issued['version']} was issued to {issued['to']} on {issued['date']} and is locked. "
                 "Bump project.version in the spec (e.g. to the next minor version) and generate again.")
    shots_file = project / "mockup" / "shots.json"
    if not shots_file.exists():
        sys.exit("No screenshots yet. Run: python -I tools/mockup.py screenshots " + str(project))
    errors = mockup.validate(spec)
    if errors:
        sys.exit("The spec has errors. Fix them, take the screenshots again, then generate:\n  " + "\n  ".join(errors))
    errors = document_errors(spec)
    if errors:
        sys.exit("The spec has errors in the parts the document prints. Fix them, then generate:\n  " + "\n  ".join(errors))
    shots = json.loads(shots_file.read_text(encoding="utf-8"))
    shot_dir = project / "mockup" / "screenshots"
    fmt = load_format()
    errors = format_errors(fmt)
    if errors:
        sys.exit(f"The document format has mistakes ({own_format_file() or 'templates/document-format.yaml'}):\n  "
                 + "\n  ".join(errors) + "\nSee docs/document-format.md for the settings.")
    co = workspace.company()
    bp = yaml.safe_load(workspace.asset("document-boilerplate.yaml").read_text(encoding="utf-8"))
    P = spec["project"]
    doc_title = (fmt.get("document") or {}).get("title") or "Requirements Specification"
    doc_short = (fmt.get("document") or {}).get("short") or ""
    names = {"system": P["name"], "client": P.get("client", ""), "client_short": P.get("client_short", P.get("client", "")),
             "company": co["name"], "company_short": co.get("short_name") or co["name"], "document": doc_title}
    reg_file = project / "register.json"
    items = json.loads(reg_file.read_text(encoding="utf-8"))["items"] if reg_file.exists() else []
    open_items = [it for it in items if it["audience"] == "client" and it["status"] not in ("resolved", "wont-fix")]
    made_items = [it for it in items if it["audience"] == "client" and it["status"] == "resolved" and str(it.get("answer") or "").strip()]
    chapters, refs = plan_sections(spec, fmt, items)
    labels = fmt["labels"]
    warnings = ["screenshots: " + problem for problem in mockup.screenshot_problems(project, spec)]
    notes = []  # worth knowing, but no reason to hold a version back
    roles = spec["roles"]
    role_ids = [r["id"] for r in roles]
    screens = spec["screens"]
    dialogs = {d["id"]: d for d in spec.get("dialogs", [])}
    status_text = P.get("status") or labels["default_status"]
    status_color = "ok" if status_is_settled(status_text) else "warning"
    version = P.get("version", "draft")
    num = {key: number for key, number, _ in chapters if number}

    def fill(text, where=""):
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

    doc = Document(str(workspace.asset("document-template.docx")))
    w = Writer(doc, fmt)
    w.setup_styles()
    cp = doc.core_properties
    cp.title = f"{P['name']} – {doc_title} v{version}"
    cp.author = co["name"]
    cp.keywords = doc_short
    if fmt.get("header_footer") == "generated":
        w.header_footer(f"{P['name']} · v{version}", status_text, f"{co['name']} · {labels['confidential']}")
    else:
        for sec in doc.sections:
            for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
                for t in part._element.iter(qn("w:t")):
                    if t.text and "{company}" in t.text:
                        t.text = t.text.replace("{company}", co["name"])

    # ---- requirement helpers shared by several sections
    groups = spec.get("requirements", []) or []
    has_screens = any(g.get("screens") or any(isinstance(i, dict) and i.get("screens") for i in g["items"]) for g in groups)
    has_priority = any(g.get("priority") or any(isinstance(i, dict) and i.get("priority") for i in g["items"]) for g in groups)
    reqs_for_screen = {}
    for g in groups:
        for sid in g.get("screens", []) or []:
            reqs_for_screen.setdefault(sid, []).append(g["id"])
    if has_screens:  # the spec links requirements to screens: say which screens nothing points at
        linked = set(reqs_for_screen) | {sid for g in groups for i in g["items"] if isinstance(i, dict) for sid in i.get("screens") or []}
        loose = [s["title"] for s in spec["screens"] if s.get("type") != "login" and s["id"] not in linked]
        if loose:
            notes.append(f"no requirement refers to {'this screen' if len(loose) == 1 else 'these screens'}: {', '.join(loose)}. "
                         "Link each with `screens` on a requirement, or check whether a requirement is missing")
    # A figure on a dashboard needs its meaning written down (GP-03). Strict once the spec gives any formula.
    formulas_in_use = any("formula" in stat for s in spec["screens"] for stat in s.get("stats") or [])
    figures_open = []
    TBC = [("warning", "dot"), ("To be confirmed", "")]

    def role_names(ids):
        return ", ".join(r["name"] for r in roles if r["id"] in ids) or "All users"

    def mentions(item, role):
        text = " ".join(str(item.get(k, "")) for k in ("question", "finding", "source"))
        return role["id"] in (item.get("roles") or []) or re.search(rf"\b{re.escape(role['name'])}s?\b", text, re.I)

    signers = []  # in page order, matched to the signature boxes in the PDF
    signoff = spec.get("signoff") or [
        {"name": "", "designation": "", "organisation": names["client"], "signing_for": "Business owner"},
        {"name": "", "designation": "", "organisation": co["name"], "signing_for": "Supplier"}]
    # The client signs first, on the summary page and in the sign-off chapter alike.
    signers_in_order = sorted(signoff, key=lambda s_: 0 if s_.get("organisation") in (names["client"], names["client_short"]) else 1)

    # ====================================================================== front matter
    for part in fmt["front"]:
        if part == "cover":
            logos = doc.add_table(rows=1, cols=2)
            table_base(logos, pad=(0, 0))
            logo = workspace.asset("logo.png")
            if logo:
                logos.rows[0].cells[0].paragraphs[0].add_run().add_picture(str(logo), height=Cm(1.3))
            client_logo = project / "spec" / "client-logo.png"
            if client_logo.exists():
                cell = logos.rows[0].cells[1].paragraphs[0]
                cell.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                cell.add_run().add_picture(str(client_logo), height=Cm(1.3))
            fixed_widths(logos, [w.text_width / 2] * 2)
            w.para("", before=110, after=0)
            w.para([(doc_title + (f" ({doc_short})" if doc_short else ""), "sec")], size=w.s["body"] + 1, after=2)
            title = w.para([(P["name"], "medium")], size=w.s["cover_title"], after=4)
            title.paragraph_format.keep_with_next = True
            w.para([(f"Prepared for {names['client']}", "sec")], size=w.s["body"] + 1, after=8)
            w.para([(status_color, "dot"), (status_text, "")], after=60)
            pairs = [("Version", [(version, "mono")]), ("Date", P.get("date", "")), ("Prepared by", P.get("prepared_by", "")),
                     ("Reviewed by", P.get("reviewed_by", ""))]
            if P.get("approved_by"):
                pairs.append(("Approved by", P["approved_by"]))
            pairs.append(("Platform", P.get("platform", "")))
            w.kv_table(pairs, [3.6, 6.2])
        elif part == "at_a_glance":
            w.page_break()
            w.page_title(fmt["titles"]["at_a_glance"], after=2)
            w.lead("What this document covers, and what still needs a decision before sign-off.")
            n_req = sum(len(g["items"]) for g in groups)
            n_high = sum(1 for it in open_items if it["severity"] == "high")
            w.cards([(len(roles), "User roles", None), (len(screens), "Screens", None),
                     (n_req, "Requirements", None),
                     (len(open_items), "Decisions needed" + (f", {n_high} blocking" if n_high else ""), "accent" if open_items else None)])
            w.para([("How to review it", "medium")], size=w.s["h3"], before=8, after=3)
            reading = []
            if "by_role" in num:
                reading.append(f"Business users: section {num['by_role']} (your role)" + (f" and section {num['screens']} (your screens)" if "screens" in num else "") + ".")
            later = [c[1] for c in chapters if c[0] in ("nfr", "extra") and c[1]]
            if later:
                reading.append(f"IT: section{'s' if len(later) > 1 else ''} {later[0]}{' to ' + later[-1] if len(later) > 1 else ''}.")
            if "decisions" in num:
                reading.append(f"Everyone: section {num['decisions']}, the decisions we need from you.")
            w.para(" ".join(reading), after=6)
            w.para([("Sign-off", "medium")], size=w.s["h3"], before=8, after=3)
            w.table(["Name", "Organisation", "Signing for", "Status"],
                    [[s.get("name") or "To be named", s.get("organisation", ""), s.get("signing_for", ""),
                      [("ok" if str(s.get("status", "")).lower() == "signed" else "line", "dot"), (str(s.get("status") or "Pending").capitalize(), "")]]
                     for s in signers_in_order], [4.6, 4.6, 3.6, w.text_width - 12.8])
            if P.get("history"):
                w.para([("Version history", "medium")], size=w.s["h3"], before=8, after=3)
                w.table(["Version", "Date", "Author", "Changes"],
                        [[[(str(h.get("version")), "mono")], h.get("date"), h.get("author"), fill(h.get("changes", ""))] for h in P["history"]],
                        [1.8, 2.6, 3.4, w.text_width - 7.8])
        elif part == "about":
            w.page_break()
            w.page_title(fmt["titles"]["about"])
            for title_, key in (("Disclaimer", "disclaimer"), ("Confidentiality", "confidentiality"), ("Concept acknowledgement", "concept")):
                w.para([(title_, "medium")], size=w.s["h3"], before=6, after=3)
                for line in bp[key]:
                    w.para(fill(line))
        elif part == "contents":
            w.page_break()
            w.page_title("Contents")
            p = doc.add_paragraph()
            add_field(p, 'TOC \\o "1-2" \\h \\z \\u')

    # ====================================================================== chapters
    field_header = ["Field", "Type", "Required", "Rule or source"]
    tw = w.text_width
    field_widths = [3.8, 2.7, 1.9, tw - 8.4]

    def field_rows(sections):
        rows, group = [], set()
        for sec in sections:
            if len(sections) > 1 or sec.get("title"):
                group.add(len(rows))
                rows.append([sec.get("title", "")])
            for f in sec.get("fields", []):
                t = TYPE_MAP.get(f.get("type", "text"), pretty(f.get("type", "")))
                if f.get("length"):
                    t += f", {f['length']}"
                if f.get("readonly") and f.get("type") not in ("file",):
                    t = "Calculated" if "alculat" in str(f.get("source", "")) else t + " (read-only)"
                src = f.get("source") or (f"From {pretty(f['options_from'].split('.')[0])}" if f.get("options_from")
                                          else ("Options: " + ", ".join(map(str, f["options"])) if f.get("options") else ""))
                val = f.get("validation") if f.get("validation") not in (None, "N/A") else ""
                rule = ". ".join(x for x in (src, val) if x) or "–"
                rows.append([f["label"], t, "✓" if f.get("required") else "", fill(rule, f"field {f['id']}")])
        return rows, group

    def extra_content(extra):
        for block in extra.get("content", []):
            where = f"section '{extra['title']}'"
            if "heading" in block:
                w.heading(block["heading"], 2)
            if "text" in block:
                w.para(fill(block["text"], where))
            if "bullets" in block:
                w.bullets([fill(b, where) for b in block["bullets"]])
            if "table" in block:
                hdr = [as_word(h) for h in block["table"]["header"]]
                body = [[fill(v, where) if isinstance(v, str) else as_word(v) for v in row] for row in block["table"]["rows"]]
                first = 1.3 if str(hdr[0]).lower().startswith("no") else None
                rest = (tw - (first or 0)) / (len(hdr) - (1 if first else 0))
                w.table(hdr, body, ([first] if first else []) + [rest] * (len(hdr) - (1 if first else 0)))
            if "image" in block:
                img = project / "spec" / block["image"]
                if img.exists():
                    w.figure(img, block.get("caption", extra["title"]))
                else:
                    warnings.append(f"{where}: image {block['image']} not found")

    by_screen = {}
    for s in shots:
        by_screen.setdefault(s["screen"], []).append(s)

    for key, number, title in chapters:
        # ---------------------------------------------------------------- users and access
        if key == "users_access":
            w.heading(f"{number} {title}", 1)
            for line in spec.get("overview", []) or []:
                w.para(fill(line, "overview"))
            k = 0

            def sub(t):
                nonlocal k
                k += 1
                w.heading(f"{number.split('.')[0]}.{k} {t}", 2)

            sub("User roles")
            w.table(["Role", "Responsibility", "Sees"],
                    [[[(r["name"], "medium")], fill(r.get("description", ""), f"role {r['id']}"), fill(r.get("scope", ""), f"role {r['id']}")] for r in roles],
                    [3.4, tw - 7.6, 4.2])
            sub("Access matrix")
            w.lead("A tick means the role has access; blank means no access. Built from the screens, so it always matches them.")
            rows, seen = [], set()

            def add_row(label, allowed):
                if label not in seen:
                    seen.add(label)
                    rows.append([label] + ["✓" if r in allowed else "" for r in role_ids])

            for s in screens:
                if s.get("menu"):
                    add_row(s["menu"], s.get("roles") or role_ids)
            for s in screens:
                allowed_screen = s.get("roles") or role_ids
                lst = s.get("list") or {}
                for b in (lst.get("toolbar") or []) + (lst.get("actions") or []) + (s.get("buttons") or []):
                    if b.get("example") or b.get("access") is False or b.get("label") in SKIP_ACTIONS:
                        continue
                    add_row(f"{s['title']}: {b['label'].lstrip('+ ').strip()}", b.get("roles") or allowed_screen)
            # Size role columns to their longest word, so names wrap only at spaces and after "/" and never
            # break mid-word. If the roles don't fit side by side, their names are turned on their side.
            char_cm = w.s["table_header"] * 0.56 / 72 * 2.54
            words = lambda name: re.split(r"[ /]", name.replace("/", "/ "))
            need = max(len(x) for r in roles for x in words(r["name"]) if x) * char_cm + 0.35
            first = min(5.0, max(3.6, max(len(x) for row in rows for x in str(row[0]).split()) * char_cm + 0.6))
            per = (tw - first) / len(roles)
            rotate = per < need
            if rotate:
                first = min(5.0, tw - 0.85 * len(roles))
                per = (tw - first) / len(roles)
            longest = max(len(r["name"]) for r in roles) * char_cm + 0.5
            w.table(["Menu or action"] + [r["name"] for r in roles], rows, [first] + [per] * len(roles),
                    size=w.s["table"] - 0.5, pad=(70, 60), center_from=1, rotate_from=1 if rotate else None,
                    header_height=longest if rotate else None)
            if spec.get("statuses"):
                sub("Process and statuses")
                flow = project / "spec" / "process-flow.png"
                if not flow.exists():
                    flow = shot_dir / "process-flow.png"
                if flow.exists():
                    w.figure(flow, (spec.get("process_flow") or {}).get("title") or "Process flow")
                w.table(["Status", "Meaning"], [[[(s["name"], "medium")], fill(s.get("meaning", ""), f"status {s['name']}")] for s in spec["statuses"]],
                        [3.6, tw - 3.6])
                rule_keys = [k for k, _ in STATUS_RULES] + ["next"]
                if any(k in s for s in spec["statuses"] for k in rule_keys):
                    # Who may change a record in each status, and where it can go next: the rules that are
                    # argued about after go-live when nobody wrote them down.
                    status_name = {s.get("id"): s["name"] for s in spec["statuses"]}
                    undecided = [("warning", "dot"), ("To be confirmed", "")]

                    def who(value):
                        if value is None:
                            return undecided
                        ids = role_ids if value == "all" else ([] if value == "none" else value)
                        if not ids:
                            return "Nobody"
                        return "All roles" if set(ids) >= set(role_ids) else ", ".join(r["name"] for r in roles if r["id"] in ids)

                    def moves_to(value):
                        if value is None:
                            return undecided
                        return ", ".join(status_name[x] for x in value) or "None: a final status"

                    w.para([("Status rules", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
                    w.lead("Who may change a record while it is in each status, and which statuses it can move to.")
                    rule_w = (tw - 3.0) / 4
                    w.table(["Status"] + [label_ for _, label_ in STATUS_RULES] + ["Moves to"],
                            [[[(s["name"], "medium")]] + [who(s.get(k)) for k, _ in STATUS_RULES] + [moves_to(s.get("next"))] for s in spec["statuses"]],
                            [3.0] + [rule_w] * 4)
                    open_rules = [s["name"] for s in spec["statuses"] if any(s.get(k) is None for k in rule_keys)]
                    if open_rules:
                        warnings.append(f"statuses: rules still to be confirmed for {', '.join(open_rules)} "
                                        "(set edit, cancel, delete and next on each status)")
                else:
                    notes.append("no status rules in the spec (who may edit, cancel or delete in each status, and where it "
                                 "moves next): see docs/spec-format.md")
            if spec.get("integrations"):
                sub("External systems")
                w.table(["System", "Purpose", "Direction", "Notes"],
                        [[[(x.get("system", ""), "medium")], fill(x.get("purpose", ""), f"integration {x.get('system', '')}"), x.get("direction", ""),
                          fill(x.get("notes", ""), f"integration {x.get('system', '')}")] for x in spec["integrations"]],
                        [3.6, 4.6, 2.2, tw - 10.4])
                if any(key in x for x in spec["integrations"] for key, _ in INTEGRATION_DETAILS):
                    # What starts each exchange, what goes across and what happens when it fails: the three
                    # things an integration is usually found to be missing during testing (GP-10).
                    w.para([("How each exchange works", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
                    each_w = (tw - 3.6) / 3
                    w.table(["System"] + [label_ for _, label_ in INTEGRATION_DETAILS],
                            [[[(x.get("system", ""), "medium")]]
                             + [fill(x[key], f"integration {x.get('system', '')}") if x.get(key) else TBC for key, _ in INTEGRATION_DETAILS]
                             for x in spec["integrations"]], [3.6] + [each_w] * 3)
                    undecided_ = [x.get("system", "") for x in spec["integrations"] if any(not x.get(key) for key, _ in INTEGRATION_DETAILS)]
                    if undecided_:
                        warnings.append(f"integrations: trigger, data or failure handling still to be confirmed for {', '.join(undecided_)} "
                                        "(set trigger, data and on_failure on each integration)")
                else:
                    notes.append("no integration details in the spec (for each integration: trigger, data, on_failure): "
                                 "see docs/spec-format.md")
            if spec.get("notifications"):
                sub("E-mail notifications")
                w.table(["Event", "Sent to", "Template"],
                        [[fill(n["event"], "notifications"), fill(n["recipient"], "notifications"),
                          fill(n.get("template", "To be confirmed"), "notifications")] for n in spec["notifications"]],
                        [5.4, 4.2, tw - 9.6])
            if spec.get("glossary"):
                sub("Terms")
                w.table(["Term", "Meaning"], [[[(g["term"], "mono")], fill(g["meaning"], f"glossary {g['term']}")] for g in spec["glossary"]],
                        [3.0, tw - 3.0])

        # ---------------------------------------------------------------- scope and assumptions
        elif key == "scope":
            w.heading(f"{number} {title}", 1)
            w.lead(fill(bp.get("scope_intro") or SCOPE_INTRO))
            for part, label_ in SCOPE_PARTS:
                if spec["scope"].get(part):
                    w.para([(label_, "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                    w.bullets([fill(x, f"scope, {label_.lower()}") for x in spec["scope"][part]])

        # ---------------------------------------------------------------- requirements by role
        elif key == "by_role":
            w.heading(f"{number} {title}", 1)
            w.lead("What each role sees and does. Each line points to where it is specified in full.")
            ch = number.split(".")[0]
            for i, r in enumerate(roles, 1):
                w.heading(f"{ch}.{i} {r['name']}", 2)
                mine = [s for s in screens if s["type"] != "login" and r["id"] in (s.get("roles") or role_ids)]
                if r.get("description") or r.get("scope"):
                    where = f"role {r['id']}"  # the same place as in the roles table: a bad reference is reported once
                    # Kept with the list under it: a role's heading and one line used to end a page on their own.
                    w.para([(fill(r.get("description", ""), where), ""),
                            ((" Sees: " + fill(r["scope"], where) + ".") if r.get("scope") else "", "sec")], keep=bool(mine))
                if mine:
                    w.para([("Screens", "medium")], before=4, after=2, keep=True)
                    w.line_list([s["title"] for s in mine], [short(refs.get(f"screen:{s['id']}")) for s in mine])
                can = []
                for s in mine:
                    lst = s.get("list") or {}
                    for b in (lst.get("toolbar") or []) + (lst.get("actions") or []) + (s.get("buttons") or []):
                        lab = b.get("label", "").lstrip("+ ").strip()
                        if b.get("example") or b.get("label") in SKIP_ACTIONS or (b.get("roles") and r["id"] not in b["roles"]):
                            continue
                        if lab and lab not in can:
                            can.append(lab)
                if can:
                    w.para([("Can do", "medium")], before=4, after=2, keep=True)
                    w.para(", ".join(can[:14]) + ("…" if len(can) > 14 else ""))
                mails = [fill(n["event"], "notifications") for n in spec.get("notifications", []) or []
                         if re.search(rf"\b{re.escape(r['name'])}\b", n.get("recipient", ""), re.I)]
                if mails:
                    w.para([("E-mails received", "medium")], before=4, after=2, keep=True)
                    w.para([("; ".join(mails), ""), ("  " + short(refs.get("section:notifications", "")), "ref")])
                needed = [it for it in open_items if mentions(it, r)]
                for it in needed[:6]:
                    w.para([("warning" if it["severity"] != "high" else "error", "dot"), (labels["decision_needed"] + " ", "sec"),
                            (it["id"], "mono"), (" · " + it.get("question", ""), "")], before=2, after=2)

        # ---------------------------------------------------------------- functional requirements
        elif key == "requirements":
            w.heading(f"{number} {title}", 1)
            ch = number.split(".")[0]
            for gi, g in enumerate(groups, 1):
                w.heading(f"{ch}.{gi} {fill(g['title'], g['id'])}", 2)
                w.para([(g["id"], "mono")], after=4, keep=True)
                header = ["ID", "Requirement"] + (["Priority"] if has_priority else []) + (["Screen"] if has_screens else [])
                widths = ([2.6, tw - 2.6 - (1.9 if has_priority else 0) - (1.9 if has_screens else 0)]
                          + ([1.9] if has_priority else []) + ([1.9] if has_screens else []))
                gscreens = ", ".join(short(refs.get(f"screen:{sid}")) for sid in (g.get("screens") or []) if refs.get(f"screen:{sid}"))
                rows = []
                for i, item in enumerate(g["items"], 1):
                    d = item if isinstance(item, dict) else {"text": item}
                    text = fill(d["text"], f"{g['id']}.{i}")
                    if re.search(r"mock-?up", text, re.I):
                        warnings.append(f"{g['id']}.{i}: mentions the mock-up; requirements should describe the real system")
                    cell = [(text, "")]
                    if d.get("tbc"):
                        cell += [("\n", ""), ("warning", "dot"), (labels["decision_needed"] + " ", "sec"), (d["tbc"], "mono")]
                    iscreens = ", ".join(short(refs.get(f"screen:{sid}")) for sid in (d.get("screens") or []) if refs.get(f"screen:{sid}")) or gscreens
                    row = [[(f"{g['id']}.{i}", "mono")], cell]
                    if has_priority:
                        pr = d.get("priority") or g.get("priority")
                        row.append([(pr, "tag")] if pr else "")
                    if has_screens:
                        row.append([(iscreens, "ref")])
                    rows.append(row)
                w.table(header, rows, widths)

        # ---------------------------------------------------------------- screens
        elif key == "screens":
            w.heading(f"{number} {title}", 1)
            w.lead(fill(bp["mockup_intro"]))
            ch = number.split(".")[0]
            for i, s in enumerate(screens, 1):
                h = w.heading(f"{ch}.{i} {s['title']}", 2)
                if i > 1 and (fmt.get("layout") or {}).get("screens_new_page", True):
                    h.paragraph_format.page_break_before = True
                w.para([(role_names(s.get("roles") or []), "sec")] + ([(" · " + fill(s["description"], f"screen {s['id']}"), "sec")] if s.get("description") else []), after=8, keep=True)
                if reqs_for_screen.get(s["id"]):
                    # Under the description, before the screenshot: says up front which requirements this screen
                    # covers, and can never end up alone on a page after the screen's tables.
                    w.para([("Requirements · ", "sec"), (" · ".join(reqs_for_screen[s["id"]]), "ref")],
                           size=w.s["caption"], after=8, keep=True)
                sshots = by_screen.get(s["id"], [])
                paged = [x for x in sshots if x.get("page") and not x.get("dialog") and not x.get("record")]
                for shot in sshots:
                    img = shot_dir / f"{shot['name']}.png"
                    if not img.exists():
                        continue
                    if shot.get("caption"):
                        cap = shot["caption"]
                    elif shot.get("dialog"):
                        dt = dialogs[shot["dialog"]]["title"]
                        cap = dt if dt.lower().startswith(s["title"].lower()) else f"{s['title']}, {dt.lower()} dialog"
                    elif len(paged) > 1 and shot in paged:
                        cap = f"{s['title']}, step {paged.index(shot) + 1} of {len(paged)}"
                    else:
                        cap = s.get("caption") or s["title"]
                    w.figure(img, cap)
                if s.get("stats"):
                    column_label = {c["field"]: c["label"] for c in (s.get("list") or {}).get("columns") or []}

                    def counts(stat):
                        """What a figure counts: its formula, or, for one the mock-up counts from the list, the rule in words."""
                        if stat.get("formula"):
                            return fill(stat["formula"], f"screen {s['id']}, figure {stat['label']}")
                        rule = stat.get("count")
                        if rule == "all":
                            return "The number of records in the list on this screen."
                        if isinstance(rule, dict) and rule:
                            parts = [f"{column_label.get(f, pretty(f))} is {' or '.join(str(v) for v in (vs if isinstance(vs, list) else [vs]))}"
                                     for f, vs in rule.items()]
                            return "The number of records in the list on this screen where " + " and ".join(parts) + "."
                        return None

                    missing = [stat["label"] for stat in s["stats"] if counts(stat) is None]
                    w.para([("Figures", "medium")], before=6, after=2, keep=True)
                    w.table(["Figure", "What it counts"], [[stat["label"], counts(stat) or TBC] for stat in s["stats"]], [5.0, tw - 5.0])
                    if missing and formulas_in_use:
                        warnings.append(f"screen {s['id']}: no formula for {', '.join(missing)} (add `formula` to each figure in stats)")
                    figures_open += missing
                if s.get("sections"):
                    rows, group = field_rows(s["sections"])
                    w.table(field_header, rows, field_widths, group_rows=group)
                elif s.get("list"):
                    lst = s["list"]
                    marks = {f: "Search" for f in lst.get("search") or []}
                    for f in lst.get("filters") or []:
                        marks[f] = (marks.get(f, "") + " Filter").strip()
                    w.table(["Column", "Search and filter"], [[c["label"], [(marks[c["field"]], "tag")] if c["field"] in marks else ""] for c in lst["columns"]],
                            [6.0, tw - 6.0])
                    extra_filters = [pretty(f) for f in (lst.get("filters") or []) if f not in [c["field"] for c in lst["columns"]]]
                    if extra_filters:
                        w.para([("Also filtered by ", "sec"), (", ".join(extra_filters), "")])
                    if lst.get("sort"):
                        w.para([("Sorted ", "sec"), (fill(lst["sort"], f"screen {s['id']} sort").lower() if lst["sort"][:2] == "By" else fill(lst["sort"]), "")])
                    acts = [a["label"] for a in (lst.get("toolbar") or []) + (lst.get("actions") or []) if not a.get("example")]
                    if acts:
                        w.para([("Actions ", "sec"), (", ".join(a.lstrip("+ ") for a in acts), "")])
                shown = set()
                for b in s.get("buttons", []) or []:
                    d = dialogs.get(b.get("dialog"))
                    if not d or d["id"] in shown or not d.get("fields") or d.get("doc_table", d.get("srs_table")) is False:
                        continue
                    shown.add(d["id"])
                    w.para([(d["title"], "medium")], before=6, after=2, keep=True)
                    rows, group = field_rows([{"fields": d["fields"]}])
                    w.table(field_header, rows, field_widths)

        # ---------------------------------------------------------------- non-functional requirements
        elif key == "nfr":
            w.heading(f"{number} {title}", 1)
            if spec.get("nfr"):
                w.table(["Area", "Requirement"], [[[(x["area"], "medium")], fill(x["requirement"], f"non-functional requirement {x['area']}")] for x in spec["nfr"]],
                        [4.0, tw - 4.0])
            else:
                w.para([("warning", "dot"), ("To be confirmed: number of users, performance, availability, backup, retention, security and "
                                             f"supported browsers. See {refs.get('section:open-issues', 'the decisions section')}.", "")])

        # ---------------------------------------------------------------- project timeline
        elif key == "timeline":
            tl = spec["timeline"]
            w.heading(f"{number} {title}", 1)
            w.lead(fill(tl.get("intro") or "The high-level plan for the project. Week 1 is the week of the kick-off meeting; "
                                              "calendar dates are set once the kick-off date is confirmed."))
            if tl.get("summary"):
                w.cards([(x["value"], x["label"], x.get("color")) for x in tl["summary"]], value_size=14)
            stages = tl.get("stages") or []
            w.gantt(stages, unit=tl.get("unit", "Week"))
            legend = [("\u25A0 ", ""), ("Activity", "sec"), ("      \u25A0 ", ""), ("Client involvement needed", "sec"),
                      ("      \u25C6 ", ""), ("Milestone", "sec")]
            if any(it.get("ref") for st in stages for it in st.get("items", [])):
                legend += [("      Numbers are the scope of work items", "sec")]
            lp = w.para(legend, size=w.s["caption"], after=10)
            lp.runs[0].font.color.rgb = rgb(w.c.get("timeline_bar", "C9D8EF"))
            for k in (2, 4):
                lp.runs[k].font.color.rgb = rgb(w.c["accent"])
            for k in (0, 2, 4):
                set_fonts(lp.runs[k]._r, "Segoe UI Symbol")
            ms = [it for st in stages for it in st.get("items", []) if "milestone" in it]
            if ms:
                w.para([("Milestones", "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                w.table(["ID", "Milestone", tl.get("unit", "Week"), "Client action"],
                        [[[(str(m["milestone"]), "mono")], fill(m.get("title") or m.get("name", "")),
                          str(m.get("week", m.get("start", ""))), fill(m.get("client_action") or "\u2013")] for m in ms],
                        [1.4, 6.0, 1.6, tw - 9.0])
            if tl.get("assumptions"):
                w.para([("Assumptions", "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                w.bullets([fill(a) for a in tl["assumptions"]])

        # ---------------------------------------------------------------- extra sections
        elif key == "extra":
            extra = next(e for e in spec["extra_sections"] if e["title"] == title and not e.get("appendix"))
            w.heading(f"{number} {title}", 1)
            extra_content(extra)

        # ---------------------------------------------------------------- decisions needed
        elif key == "decisions":
            w.heading(f"{number} {title}", 1)
            if open_items:
                w.lead(fill(bp["open_issues_intro"]))
                impact = {"high": ("error", labels["impact_high"]), "medium": ("warning", labels["impact_medium"]), "low": ("line", labels["impact_low"])}
                rows = []
                for it in open_items:
                    color, word = impact.get(it["severity"], ("line", it["severity"]))
                    # Point only at requirement IDs that exist in this version; free-text locations in the
                    # register may refer to an older document.
                    ids = [x for x in dict.fromkeys(re.findall(r"FR-[A-Z]+-\d{3}(?:\.\d+)?", it.get("source", "")))
                           if x.split(".")[0] in {g["id"] for g in groups}]
                    rows.append([[(it["id"], "mono")], [(it["question"], "")] + ([("  " + ", ".join(ids), "ref")] if ids else []),
                                 [(color, "dot"), (word, "")], it.get("owner") or names["client_short"], it.get("due") or "–"])
                # The three narrow columns are sized to what they hold, so an impact stays on one line and an
                # owner's name or a date never breaks in the middle of a word. The question takes the rest.
                char_cm = w.s["table"] * 0.56 / 72 * 2.54

                def fit(texts, least, most):
                    return min(most, max(least, max((len(str(t)) for t in texts), default=0) * char_cm + 0.5))

                impact_w = fit([row[2][1][0] + "  " for row in rows], 2.4, 4.2)  # the whole label, with its dot
                owner_w = fit([word for row in rows for word in str(row[3]).split()], 1.9, 3.6)
                due_w = fit([word for row in rows for word in str(row[4]).split()], 1.7, 3.2)
                w.table(["ID", "Question", "Impact", "Owner", "Due"], rows,
                        [1.6, tw - 1.6 - impact_w - owner_w - due_w, impact_w, owner_w, due_w])
            else:
                w.para([("ok", "dot"), ("There are no open decisions in this version.", "")])
            if made_items:
                # The client's answers go on record in the document they sign, not only in the register.
                w.para([(labels["decisions_made"], "medium")], size=w.s["h3"], before=10, after=3, keep=True)
                w.lead(fill(bp.get("decisions_made_intro") or DECISIONS_MADE_INTRO))
                half = (tw - 1.6 - 2.6) / 2
                w.table(["ID", "Question", "Decision", "Agreed in"],
                        [[[(it["id"], "mono")], it.get("question") or it.get("finding", ""), it["answer"], str(it.get("resolved_in") or "–")]
                         for it in made_items], [1.6, half, half, 2.6])

        # ---------------------------------------------------------------- sign-off
        elif key == "signoff":
            w.heading(title, 1)
            for line in bp["signoff"]:
                w.para(fill(line))
            excluded = (f"{len(open_items)} (section {num['decisions']})" if open_items and "decisions" in num
                        else ("None" if not open_items else str(len(open_items))))
            w.cards([(f"v{version}", f"Document, {P.get('date', '')}", None), (excluded, "Open decisions excluded", None),
                     ("By hand or in the PDF", "How to sign", None)], value_size=11)
            w.para([("Sign by hand: print this section, sign, stamp and scan it. Sign digitally: open the PDF in Adobe "
                     "Acrobat Reader and click a signature box to sign with your digital ID. Each box can be signed "
                     "separately, in any order.", "sec")], size=w.s["caption"], after=10)
            for s_ in signers_in_order:
                org = s_.get("organisation", "")
                side = "Client" if org in (names["client"], names["client_short"]) else ("Supplier" if org in (co["name"], names["company_short"]) else "")
                signers.append(s_.get("name") or s_.get("signing_for") or f"Signatory {len(signers) + 1}")
                w.signature_block(s_, f"{side} \u00B7 {org}" if side else org, f"BPSIG{len(signers)}")

    # ====================================================================== appendices
    for i, extra in enumerate([e for e in (spec.get("extra_sections") or []) if e.get("appendix")]):
        w.heading(f"Appendix {chr(65 + i)}  {extra['title']}", 1)
        extra_content(extra)

    out_dir = project / "output"
    out_dir.mkdir(exist_ok=True)
    # The name on the cover may hold characters a file name cannot (a colon, a slash): the file name is cleaned.
    out = out_dir / (project_tool.safe_name(f"{P['name']} – {doc_title} v{version}") + ".docx")
    pdf = out.with_suffix(".pdf")
    try:
        # The PDF of an earlier run goes first: if the Word step fails below, no old PDF is left beside the
        # new document for someone to send.
        pdf.unlink(missing_ok=True)
        doc.save(str(out))
    except PermissionError:
        sys.exit(f"Cannot replace the document in {out_dir}: {out.name} or its PDF is open in another program "
                 "(or is read-only). Close it and generate again.")
    shutil.copy(project / "spec" / "app.yaml", out_dir / f"spec-v{version}.yaml")
    print(f"Wrote {out}")
    print(f"  {w.figures} figures, {len(groups)} requirement groups, {len(open_items)} decisions needed, "
          f"{len(made_items)} decisions made, {len(signoff)} signatories")
    if figures_open and not formulas_in_use:
        notes.append(f"the figures {', '.join(dict.fromkeys(figures_open))} have no formula: the document shows them as to be confirmed. "
                     "Add `formula` to each figure in stats (see docs/spec-format.md)")
    for note in notes:
        print(f"  Note: {note}")
    warnings = list(dict.fromkeys(warnings))
    if warnings:
        print(f"  {len(warnings)} WARNING(S) - fix these before issuing:")
        for x in warnings:
            print("   - " + x)
    done, why = finish_in_word(out)
    if done:
        sharp = sharpen_pdf_pictures(pdf, w.pictures)
        placed = add_signature_fields(pdf, signers)
        print(f"  Table of contents updated, fonts embedded; PDF written to {pdf.name}"
              f" with {placed} of {len(signers)} signing fields"
              + (f" and {sharp} of {len(w.pictures)} pictures at full size" if w.pictures else ""))
        return out
    try:
        strip_markers(out)
    except PermissionError:
        print(f"  {out.name} is still held open by Word: close Word before opening or regenerating it.")
    if why == NO_WORD and sys.platform == "darwin":
        # Word for Mac cannot be driven the way Word for Windows can, so the last step is by hand there.
        print("  Word not available to Blueprint on a Mac: open the file in Word, click the table of contents and choose "
              "Update Table, then File > Save As and pick PDF. (The PDF's signing fields are added on Windows only.)")
    elif why == NO_WORD:
        print("  Word not available: open the file and update the table of contents (right-click > Update Field).")
    else:
        print(f"  The Word step FAILED, so there is no PDF and the table of contents is not updated: {why}")
        print("  Put that right and generate again, or open the file and update the table of contents yourself "
              "(right-click > Update Field).")
    return out


def strip_markers(docx_path):
    """Remove the invisible signature-box markers from a document (used when Word is not available)."""
    d = Document(str(docx_path))
    for t in d.element.body.iter(qn("w:t")):
        if t.text and re.fullmatch(r"BPSIG\d+", t.text):
            t.text = ""
    d.save(str(docx_path))


def sharpen_pdf_pictures(pdf_path, pictures):
    """Put the original pictures back into the PDF, in place of the reduced ones Word exported.

    Word's PDF export brings every picture down to about 200 dots per inch, whatever the document holds, so
    the small text of a screenshot went soft when zoomed. The figures are the wide pictures of the PDF, in
    reading order; each is replaced by the file it was made from. Returns how many were replaced. When the
    PDF's pictures cannot be matched one for one with the figures, nothing is changed."""
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    wide = []  # (page, picture reference, width in pixels, shape) of each figure: logos and icons are narrower
    for page in doc:
        on_page = []
        for image in page.get_images(full=True):
            rects = page.get_image_rects(image[0])
            if rects and rects[0].width > 8 / 2.54 * 72:
                on_page.append((rects[0].y0, rects[0].x0, page.number, image[0], image[2], rects[0].width / rects[0].height))
        wide += sorted(on_page)
    replaced = 0
    if len(wide) == len(pictures) and len({w[3] for w in wide}) == len(wide):
        for (_, _, page_no, xref, pixels, shape), picture in zip(wide, pictures):
            try:
                original = pymupdf.Pixmap(str(picture))
            except Exception:
                continue
            same_shape = abs(original.width / original.height - shape) < 0.03 * shape  # a wrong match would distort
            if same_shape and original.width > pixels:
                if original.alpha:  # a screenshot has nothing see-through: without it the PDF is smaller
                    original = pymupdf.Pixmap(original, 0)
                doc[page_no].replace_image(xref, pixmap=original)
                replaced += 1
    if replaced:
        tmp = pdf_path.with_suffix(".sharp.pdf")
        doc.save(str(tmp), garbage=3, deflate=True)
        doc.close()
        tmp.replace(pdf_path)
    else:
        doc.close()
    return replaced


def add_signature_fields(pdf_path, signers):
    """Put a digital signature field over each signature box in the PDF, then remove the markers.

    Each box carries an invisible marker (BPSIG1, BPSIG2 ...) in its top-left corner. The field takes the
    box's own border lines when they can be found, otherwise a rectangle of the box's known size.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    placed = 0
    for page in doc:
        hits = []
        for i, name in enumerate(signers, 1):
            for r in page.search_for(f"BPSIG{i}"):
                if page.get_textbox(r + (-1, -1, 1, 1)).strip().startswith(f"BPSIG{i}"):
                    hits.append((i, name, r))
                    break
        if not hits:
            continue
        segs = []
        for d in page.get_drawings():
            for item in d["items"]:
                if item[0] == "l":
                    segs.append(pymupdf.Rect(item[1], item[2]).normalize())
                elif item[0] == "re":
                    segs.append(pymupdf.Rect(item[1]).normalize())
        horiz = [g for g in segs if g.height < 2.5 and g.width > 60]
        vert = [g for g in segs if g.width < 2.5 and g.height > 25]
        for i, name, m in hits:
            cx = m.x0 + 1
            tops = [g.y0 for g in horiz if g.y0 <= m.y0 + 1 and g.x0 - 2 <= cx <= g.x1 + 2]
            bots = [g.y0 for g in horiz if g.y0 >= m.y1 + 25 and g.x0 - 2 <= cx <= g.x1 + 2]
            lefts = [g.x0 for g in vert if g.x0 <= m.x0 + 1 and g.y0 - 2 <= m.y1 <= g.y1 + 2]
            rights = [g.x0 for g in vert if g.x0 >= m.x1 + 60 and g.y0 - 2 <= m.y1 <= g.y1 + 2]
            if tops and bots and lefts and rights:
                rect = pymupdf.Rect(max(lefts), max(tops), min(rights), min(bots)) + (2, 2, -2, -2)
            else:
                rect = pymupdf.Rect(m.x0 - 4, m.y0 - 3, m.x0 + 250, m.y0 + 55)
            wdg = pymupdf.Widget()
            wdg.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
            wdg.field_name = f"Signature {i} - {name}"[:120]
            wdg.field_label = f"Signature: {name}"
            wdg.rect = rect
            annot = page.add_widget(wdg)
            annot.set_flags(0)  # visible on screen, but not printed: paper copies show a clean box
            page.add_redact_annot(m + (-0.5, -0.5, 0.5, 0.5))
            placed += 1
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    tmp = pdf_path.with_suffix(".signing.pdf")
    doc.save(str(tmp), garbage=3, deflate=True)
    doc.close()
    tmp.replace(pdf_path)
    return placed


NO_WORD = "Microsoft Word is not installed"  # the one reason for no PDF that is not a fault


def finish_in_word(docx_path):
    """Update fields (contents, page numbers), embed the fonts and export a PDF, if Word is installed.

    Returns (True, "") when Word wrote the PDF. Otherwise (False, why): NO_WORD on a machine without Word
    (or without PowerShell), or what went wrong in words the person generating can act on."""
    import subprocess

    if sys.platform != "win32":
        # Word is driven through Windows PowerShell and COM. A Mac may well have PowerShell installed, but
        # it has no COM there, and Word for Mac cannot be driven this way.
        return False, NO_WORD
    pdf = docx_path.with_suffix(".pdf")
    quoted = lambda path: "'" + str(path.resolve()).replace("'", "''") + "'"  # an apostrophe in a name is doubled
    script = (
        "$ErrorActionPreference='Stop';$w=$null;$d=$null;"
        "try{"
        # No alerts: a question nobody can see would leave Word waiting for ever. Not added to the recent files.
        "$w=New-Object -ComObject Word.Application;$w.Visible=$false;$w.DisplayAlerts=0;"
        f"$d=$w.Documents.Open({quoted(docx_path)},$false,$false,$false);"
        "foreach($t in $d.TablesOfContents){$t.Update()};$d.Fields.Update()|Out-Null;"
        "$d.EmbedTrueTypeFonts=$true;$d.SaveSubsetFonts=$true;"
        f"$d.Save();$d.ExportAsFixedFormat({quoted(pdf)},17);"
        "$null=$d.Content.Find.Execute('BPSIG[0-9]{1,3}',$false,$false,$true,$false,$false,$true,1,$false,'',2);"
        "$d.Save();$d.Close();$d=$null"
        "}finally{"
        # Whatever went wrong, Word is closed: left running hidden it keeps the document locked for the next run.
        "if($d){try{$d.Close([ref]0)}catch{}};if($w){try{$w.Quit([ref]0)}catch{}}"
        "}"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=240)
    except FileNotFoundError:
        return False, NO_WORD  # no PowerShell: not Windows, so no Word either
    except subprocess.TimeoutExpired:
        return False, ("Word did not finish within 4 minutes and may still be running hidden. In Task Manager, on the "
                       "Details tab, end the WINWORD.EXE you did not open yourself, then generate again")
    except Exception as e:
        return False, f"PowerShell could not be run ({e})"
    if r.returncode == 0 and pdf.exists():
        return True, ""
    try:
        said = (r.stderr or b"").decode("oem", "replace")  # what Windows PowerShell writes its errors in
    except LookupError:  # the codec exists on Windows only
        said = (r.stderr or b"").decode("utf-8", "replace")
    if "80040154" in said or "Class not registered" in said:
        return False, NO_WORD
    if r.returncode == 0:
        return False, "Word ran but wrote no PDF"
    # PowerShell wraps long messages; the reason is the text before its "At line:1 char:..." location.
    reason = " ".join(said.split("At line:")[0].split())
    if reason.rstrip(".").endswith("Command failed"):  # all Word says when it cannot save over a file in use
        reason = "Word could not save the document. It is probably open in another program: close it and generate again"
    return False, reason[:400] or f"PowerShell ended with code {r.returncode}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    build(sys.argv[1])
