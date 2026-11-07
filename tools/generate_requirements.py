"""Generate the requirements document (Word and PDF) from a project's spec, mock-up screenshots and register.

Usage:
    python -I tools/generate_requirements.py <project_dir>

Reads  the project's spec/app.yaml, the mock-up's screenshots + shots.json (run
       `python -I tools/mockup.py screenshots <project_dir>` first), register.json (open client items
       become "Decisions needed"), optional spec/client-logo.png and spec/process-flow.png. spec/,
       register.json and the mock-up are in _blueprint/ in a project in the new folder layout
       (tools/layout.py), the screenshots in "4 Mock-up screenshots".
Uses   the company profile and branding from the workspace (see tools/workspace.py), and the document format:
       templates/document-format.yaml, overridden key by key by workspace/branding/document-format.yaml.
Writes <System> – <document title> v<version>.docx into the project's "5 Requirements document" folder
       (output/ in a project not yet moved to the new folder layout), a PDF when Microsoft Word is
       installed, and a snapshot of the spec used (spec-v<version>.yaml, in _blueprint/output/). A PDF from
       an earlier run is removed first, so the Word file and the PDF are always the same version of the content.
Warns  when the screenshots were taken before the spec's screens last changed, or one is missing, and about
       team-only text in what the client reads (the mock-up, "proposed", FB-/R- ids, requirement ids of
       another document); lists the parts still missing before issuing (NFRs, timeline, scope, signatories, and the sections the format requires,
       which it prints as To be confirmed).

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (where everything is in a project folder)
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
# Team-only words that must not reach the document the client signs (see team_notes).
MOCKUP_WORD = re.compile(r"\bmock-?ups?\b", re.I)
PROPOSED_WORD = re.compile(r"\bproposed\b(?!\s+(?:new\s+)?(?:system|solution|application|platform|portal|module)s?\b)", re.I)
FEEDBACK_ID = re.compile(r"\bFB-\d+\b")
REGISTER_ID = re.compile(r"\bR-\d{3,}\b")
REQUIREMENT_ID = re.compile(r"\b(?:N?FR|BR|UR|SR|REQ)(?:-[A-Z][A-Z0-9]*)*-\d+(?:\.\d+)*\b")
SIGNATORY_PLACEHOLDER = re.compile(r"^\s*(?:|[\[<(].*|tbc|tbd|tba|to be (?:named|confirmed|advised)|name|n/?a|x+|-+|–+|\?+)\s*$", re.I)
PROJECT_TEXT = ("timeline", "project history", "resolved_in")  # texts about the project, not the system (see team_notes)
SKIP_ACTIONS = {"Back", "Cancel", "View"}
CONTENTS_LINES = 50  # chapters and sections that fit on the contents page
# A chapter's reference key (section:<name>) by its key in the document format's `chapters`.
CHAPTER_REFS = {"users_access": "users", "scope": "scope", "by_role": "by-role", "requirements": "requirements",
                "screens": "screens", "nfr": "nfr", "timeline": "timeline", "decisions": "open-issues"}


def pretty(field):
    return str(field).replace("_", " ").capitalize()


def options_from_words(source):
    """Where a drop-down's choices come from, for the field table: "From Cars" or "From Cars where Status is Available"."""
    if isinstance(source, dict):
        where = source.get("where") if isinstance(source.get("where"), dict) else {}
        rule = " and ".join(f"{pretty(k)} is {' or '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in where.items())
        return f"From {pretty(source.get('list', ''))}" + (f" where {rule}" if rule else "")
    return f"From {pretty(str(source).split('.')[0])}"


def related_list_words(spec, screen, lst):
    """The sentence above a detail screen's related list: which records it shows."""
    link = lst.get("where_record") if isinstance(lst.get("where_record"), dict) else {}
    shown = pretty(screen.get("data") or "record").rstrip("s").lower()
    if not link:
        return f"The {pretty(lst.get('data', '')).lower()} shown with this {shown}."
    parts = " and ".join(f"{pretty(mine).lower()} is this {shown}'s {pretty(theirs).lower()}" for mine, theirs in link.items())
    return f"The {pretty(lst.get('data', '')).lower()} whose {parts}."


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


FRONT = ("cover", "at_a_glance", "about", "contents")
CHAPTERS = ("users_access", "scope", "by_role", "requirements", "screens", "nfr", "timeline", "extras", "decisions", "signoff")
STATUS_RULES = (("edit", "May edit"), ("cancel", "May cancel"), ("delete", "May delete"))  # plus `next`
SCOPE_PARTS = (("in_scope", "In scope"), ("out_of_scope", "Out of scope"), ("assumptions", "Assumptions"))


# ------------------------------------------------------------------ the scope of work's items
# The spec lists the scope of work's items (`sow: {items: [{ref, item}]}`) and each requirement group, or item,
# names the ones it specifies (`sow: "3.1"`). An end-to-end test signed off a document that covered six of the
# fourteen modules sold: nothing compared the two. Mandays never go here; they stay in the estimate.
def sow_items(spec):
    """The scope of work's items in the spec, each a dict with at least ref and item."""
    sow = spec.get("sow")
    items = sow.get("items") if isinstance(sow, dict) else None
    return [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []


def sow_refs(x):
    """The scope of work refs a requirement group or item names: `sow: "3.1"` or `sow: ["3.1", "3.2"]`."""
    value = x.get("sow") if isinstance(x, dict) else None
    if value is None:
        return []
    return [str(v).strip() for v in (value if isinstance(value, list) else [value]) if str(v).strip()]


def sow_coverage(spec):
    """Each scope of work item's ref -> the requirement ids that specify it (a group's id, or FR-XXX-001.3 for
    one item), in document order."""
    cover = {str(s.get("ref")).strip(): [] for s in sow_items(spec)}
    for g in spec.get("requirements") or []:
        if not isinstance(g, dict):
            continue
        for ref in sow_refs(g):
            cover.setdefault(ref, []).append(str(g.get("id")))
        for n, item in enumerate(g.get("items") or [], 1):
            for ref in sow_refs(item):
                if str(g.get("id")) not in cover.setdefault(ref, []):
                    cover[ref].append(f"{g.get('id')}.{n}")
    return cover
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
    for key in base["required"]:
        value = fmt["required"].get(key)
        if value is None:
            fmt["required"][key] = []
        elif not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            errors.append(f"required.{key}: must be a list of names, for example [{', '.join(base['required'][key][:2])}]")
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
    # The scope of work's items, and the requirements that name them.
    sow = spec.get("sow")
    if sow is not None:
        if not isinstance(sow, dict) or not isinstance(sow.get("items"), list):
            errors.append("sow: must have 'items', the scope of work's items as {ref, item}")
        else:
            for key in sow:
                if key not in ("source", "items"):
                    errors.append(f"sow: '{key}' is not one of source, items"
                                  + (" (the scope of work's mandays go on the timeline's activities)" if key == "mandays" else ""))
            refs = set()
            for i, s in enumerate(sow["items"], 1):
                if not need(f"sow item {i}", s, "ref", "item"):
                    continue
                for key in s:
                    if key not in ("ref", "item", "deferred", "note"):
                        errors.append(f"sow item {s['ref']}: '{key}' is not one of ref, item, deferred, note"
                                      + (" (mandays stay in the estimate and on the timeline)" if key == "mandays" else ""))
                if str(s["ref"]).strip() in refs:
                    errors.append(f"sow item {s['ref']}: the ref is used twice")
                refs.add(str(s["ref"]).strip())
            for g in spec.get("requirements") or []:
                if not isinstance(g, dict):
                    continue
                named = [(str(g.get("id")), r) for r in sow_refs(g)]
                named += [(f"{g.get('id')}.{n}", r) for n, it in enumerate(g.get("items") or [], 1) for r in sow_refs(it)]
                for where, r in named:
                    if r not in refs:
                        errors.append(f"requirement {where}: sow '{r}' is not an item of the spec's sow")
    else:
        for g in spec.get("requirements") or []:
            if isinstance(g, dict) and (sow_refs(g) or any(sow_refs(it) for it in g.get("items") or [])):
                errors.append(f"requirement group {g.get('id')}: names a scope of work item (sow), but the spec has no sow items")
                break
    for i, n in each("notifications"):
        need(f"notification {i}", n, "event", "recipient")
    for i, x in each("nfr"):
        # A row may wait on a register item (tbc: R-...) instead of its requirement: printed as To be confirmed.
        if need(f"non-functional requirement {i}", x, "area") and not x.get("tbc"):
            need(f"non-functional requirement {x['area']}", x, "requirement")
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
    for where, x in ([(f"non-functional requirement {x.get('area', i) if isinstance(x, dict) else i}", x) for i, x in each("nfr")]
                     + [(f"extra section '{x.get('title', i) if isinstance(x, dict) else i}'", x) for i, x in each("extra_sections")]):
        if not isinstance(x, dict):
            continue
        if x.get("tbc") is not None and not REGISTER_ID.fullmatch(str(x["tbc"])):
            errors.append(f"{where}: 'tbc' must be a register id, for example R-019")
        covers = x.get("covers")
        if covers is not None and not (isinstance(covers, str) or isinstance(covers, list) and all(isinstance(c, str) for c in covers)):
            errors.append(f"{where}: 'covers' must be the name of a required section, or a list of them")
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
            if "mandays" in it:
                md = it["mandays"]
                if "milestone" in it:
                    errors.append(f"{where}: a milestone has no mandays (put them on the activity)")
                elif isinstance(md, bool) or not isinstance(md, (int, float)) or md < 0:
                    errors.append(f"{where}: 'mandays' must be the scope of work's figure, a number (e.g. 12 or 7.5)")
    for key in ("rate", "rates", "cost", "price", "amount"):
        if isinstance(timeline, dict) and key in timeline:
            errors.append(f"timeline: '{key}' does not go into the requirements document (rates and cost stay internal)")
    # The timeline's own words are printed as they are: effort, rates or money in them would reach the client.
    # Only the scope of work's mandays go in, as `mandays` on each activity.
    if isinstance(timeline, dict):
        texts = [("intro", timeline.get("intro")), ("unit", timeline.get("unit"))]
        texts += [(f"summary {k}", f"{s.get('value', '')} {s.get('label', '')}") for k, s in enumerate(timeline.get("summary") or [], 1) if isinstance(s, dict)]
        texts += [("assumption", a) for a in timeline.get("assumptions") or []]
        for st in stages if isinstance(stages, list) else []:
            if isinstance(st, dict):
                texts.append((f"stage '{st.get('name', '?')}'", st.get("name")))
                texts += [(f"timeline item '{it.get('name', '?')}'", " ".join(str(it.get(x) or "") for x in ("name", "title", "client_action")))
                          for it in st.get("items") or [] if isinstance(it, dict)]
        for where, text in texts:
            m = MONEY_WORDS.search(str(text or ""))
            if m:
                errors.append(f"timeline {where}: '{m.group(0)}' does not go into the requirements document: effort, rates "
                              "and cost stay internal (the scope of work's mandays go on each activity as `mandays`)")
    return errors


# ====================================================================== low-level Word helpers
def flow_names(spec):
    """The process flow's steps with each role and status as the reader knows it, by its name: a step may give
    the id buttons use ("in-progress", "security") or the name ("Picked up", "Gate security"). Returns
    (steps, problems): a value that is neither a name nor an id is kept as written and listed as a problem."""
    roles = {str(r.get("id")): str(r.get("name")) for r in spec.get("roles") or [] if isinstance(r, dict) and r.get("id") and r.get("name")}
    statuses = {str(x.get("id")): str(x.get("name")) for x in spec.get("statuses") or [] if isinstance(x, dict) and x.get("id") and x.get("name")}
    flow = spec.get("process_flow") if isinstance(spec.get("process_flow"), dict) else {}
    steps, problems = [], []
    for step in flow.get("steps") or []:
        if not isinstance(step, dict):
            continue
        step = dict(step)
        for key, known in (("role", roles), ("status", statuses)):
            value = str(step.get(key) or "").strip()
            if not value or value in known.values():
                continue
            if value in known:
                step[key] = known[value]
            elif known and value.lower() not in {n.lower() for n in known.values()}:
                problems.append(f"process flow, step {step.get('name') or '?'}: {key} '{value}' is neither the name nor the id "
                                f"of a {key} in the spec, so the diagram does not match the {key}s the document lists "
                                f"({', '.join(known.values())})")
        steps.append(step)
    return steps, problems


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


# Effort, rates and money in words: never in the timeline's own text (its mandays go in `mandays` only).
MONEY_WORDS = re.compile(r"\b(man-?days?|mandays?|person-?days?|day rates?|rates?|costs?|costing|prices?|pricing|budget|"
                         r"quotation|RM|MYR|USD|SGD)\b|[$€£]\s?\d", re.I)


# Parts of a Word file that carry the template's own words, never wanted in a generated document.
TEMPLATE_TEXT_PARTS = ("/comments", "/commentsExtended", "/commentsIds", "/commentsExtensible", "/people",
                       "/glossaryDocument", "/custom-properties", "/extended-properties")
NOTE_KEEP = ("separator", "continuationSeparator", "continuationNotice")


def template_document(path=None):
    """The company's Word template with only what Blueprint uses from it: its styles, page set-up, header and
    footer. Its body (often an earlier client's document copied in as the template), its comments, footnotes,
    quick parts and file properties (title, subject, comments, last saved by, company) are taken out, so
    nothing of another document reaches a generated one. Every generated Word file starts here."""
    from lxml import etree

    doc = Document(str(path or workspace.asset("document-template.docx")))
    body = doc.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    for owner in (doc.part, doc.part.package):
        for rid, rel in list(owner.rels.items()):
            if not rel.is_external and rel.reltype.endswith(TEMPLATE_TEXT_PARTS):
                owner.rels.pop(rid)
    for rel in doc.part.rels.values():
        if rel.is_external or not rel.reltype.endswith(("/footnotes", "/endnotes")):
            continue
        part = rel.target_part
        root = part.element if hasattr(part, "element") else etree.fromstring(part.blob)
        for note in list(root):
            if note.get(qn("w:type")) not in NOTE_KEEP:
                root.remove(note)
        if not hasattr(part, "element"):
            part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    cp = doc.core_properties
    for name in ("title", "subject", "author", "keywords", "comments", "category", "content_status",
                 "identifier", "language", "last_modified_by", "version"):
        setattr(cp, name, "")
    now = __import__("datetime").datetime.now().replace(microsecond=0)
    cp.created = cp.modified = now
    cp.revision = 1
    return doc


# ====================================================================== the document writer
class Writer:
    """Writes styled content. Text segments are (text, style) pairs so one line can mix plain words,
    secondary text, mono IDs, accent references, tags and status dots."""

    def __init__(self, doc, fmt):
        self.doc, self.f = doc, fmt
        self.c, self.s, self.fn = fmt["colors"], fmt["sizes"], fmt["fonts"]
        self.figures = 0
        self.pictures = []  # the image file of every figure, in order: put back at full size in the PDF
        self.trimmed_dir = None  # where the pictures cut free of their empty background are kept until the PDF is done
        self.trim_cache = {}
        self.grounds = {}  # trimmed picture -> the colour of the canvas it was cut from
        self.marked = set()  # the bookmarks placed, by name: what a reference can link to
        self.target = None  # a table cell that paragraphs and tables go into instead of the body
        self.phones = set()  # the trimmed pictures that are phone screens
        sec = doc.sections[0]
        self.text_width = (sec.page_width - sec.left_margin - sec.right_margin) / 360000  # cm
        self.text_height = (sec.page_height - sec.top_margin - sec.bottom_margin) / 360000  # cm

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

    # ---- links: a reference ("5.13", "R-019", "section 7") takes the reader to what it names
    @staticmethod
    def anchor(key):
        """The bookmark name for a reference key (screen:x, req:FR-X-001, reg:R-001 ...): short, hidden (it
        starts with an underscore, so it is not listed in Word's bookmarks) and the same for the same key."""
        import hashlib

        key = {"section:decisions": "section:open-issues"}.get(key, key)
        return "_bp" + hashlib.md5(key.encode("utf-8")).hexdigest()[:12]

    def bookmark(self, paragraph, key):
        """Mark a paragraph (a heading, a requirement's or a decision's ID) as the place a reference leads to."""
        name = self.anchor(key)
        if name in self.marked:
            return
        self.marked.add(name)
        start, end = OxmlElement("w:bookmarkStart"), OxmlElement("w:bookmarkEnd")
        start.set(qn("w:id"), str(len(self.marked)))
        start.set(qn("w:name"), name)
        end.set(qn("w:id"), str(len(self.marked)))
        p_ = paragraph._p
        if p_.pPr is not None:
            p_.pPr.addnext(start)
        else:
            p_.insert(0, start)
        p_.append(end)

    def unlink_missing(self):
        """Take the link off a reference whose place is not in the document (a screen left out, an item the
        decisions chapter does not list): it stays as text rather than a link that goes nowhere."""
        for hl in list(self.doc.element.body.iter(qn("w:hyperlink"))):
            name = hl.get(qn("w:anchor"))
            if name and name.startswith("_bp") and name not in self.marked:
                for child in list(hl):
                    hl.addprevious(child)
                hl.getparent().remove(hl)

    # ---- text
    def runs(self, paragraph, segments, size=None):
        """Segments are (text, style) or (text, style, key): with a key the text links to the place
        bookmarked under it, and an ID set in the mono font takes the accent colour of a reference."""
        if isinstance(segments, str):
            segments = [(segments, "")]
        for segment in segments:
            text, style = segment[0], segment[1]
            key = segment[2] if len(segment) > 2 else None
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
            if key:
                if style == "mono":
                    r.font.color.rgb = rgb(self.c["accent"])
                link = OxmlElement("w:hyperlink")
                link.set(qn("w:anchor"), self.anchor(key))
                link.set(qn("w:history"), "1")
                r._r.addprevious(link)
                link.append(r._r)
        return paragraph

    def para(self, segments, size=None, after=None, before=None, align=None, style=None, keep=False):
        where = self.target or self.doc
        p = where.add_paragraph(style=style) if style else where.add_paragraph()
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

    def heading(self, text, level, page_break=None, key=None):
        h = self.doc.add_heading(text, level=level)
        if page_break is False and level == 1:
            h.paragraph_format.page_break_before = False
        if key:
            self.bookmark(h, key)
        return h

    def look_like_section(self, h):
        """Give a heading the look of a section heading (Heading 2) while it stays out of the contents."""
        h.paragraph_format.space_before = Pt(16)
        h.paragraph_format.space_after = Pt(5)
        for r in h.runs:
            r.font.size = Pt(self.s["h2"])
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
        if self.target is not None:
            return  # inside a cell: the row holds it together
        body = self.doc.element.body
        last = body[-2] if body[-1].tag == qn("w:sectPr") and len(body) > 1 else body[-1]
        if last.tag == qn("w:p"):
            style = last.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
            if style is not None and style.get(qn("w:val")) == "Caption":
                return  # a figure's caption: don't chain figures together into blocks taller than a page
            if not "".join(t.text or "" for t in last.iter(qn("w:t"))).strip():
                return  # the gap left after a table or figure: tied to what follows, it dragged it to a page of its own
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
              header_height=None, keep_whole=False):
        """Hairline table. center_from centres columns from that index (ticks); rotate_from turns those
        header cells to read bottom-to-top, for narrow columns such as the roles in the access matrix."""
        from docx.enum.table import WD_ROW_HEIGHT_RULE

        size = size or self.s["table"]
        look = self.f.get("tables") or {}
        fill, grid = look.get("header_fill"), look.get("borders") == "grid"
        header_text = look.get("header_text") or ("FFFFFF" if fill else self.c["secondary"])
        self.glue_previous()
        t = (self.target or self.doc).add_table(rows=1, cols=len(header))
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
        # The header row and the first two rows move together, so a table never starts with a lone header at the
        # foot of a page, and the last two rows move together, so none ends with a single row on a page of its
        # own. In between a table may run on to the next page (its header is repeated there): keeping whole
        # tables of six or seven rows together left a third of a page empty above many of them. Tables of up to
        # three rows, and those asked to (keep_whole), are kept on one page.
        n = len(t.rows)
        together = range(n - 1) if keep_whole or n <= 4 else [0, 1, n - 2]
        for i in together:
            self.keep_row_with_next(t.rows[i])
        gap = (self.target or self.doc).add_paragraph()
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
            # A label is words, or segments when part of it is a reference ("see section 7") that links.
            self.runs(cell.add_paragraph(), label if isinstance(label, list) else [(label, "sec")], self.s["caption"])
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

    # Room a figure leaves on its page: a screen's heading, description and requirements line above it, and
    # the caption and the ground's padding around it. A picture taller than the rest is made narrower.
    FIGURE_ROOM = 5.2  # cm
    PHONE_SHAPE = 1.8  # height / width at or above which a picture is a phone screen, two of which share a row

    def trimmed(self, image):
        """The picture without the empty background around it, and its shape (height / width).

        A phone screenshot is a narrow phone on a wide canvas: placed as it is, the phone was a third of the
        figure and its text too small to read. The canvas is the colour of the picture's corner; a margin of it
        is kept. A picture with no such margin (a desktop screen fills its picture) is used as it is."""
        if str(image) not in self.trim_cache:
            self.trim_cache[str(image)] = self._trim(image)
        return self.trim_cache[str(image)]

    def _trim(self, image):
        from PIL import Image, ImageChops

        with Image.open(image) as im:
            im = im.convert("RGB")
            plain = Image.new("RGB", im.size, im.getpixel((0, 0)))
            box = ImageChops.difference(im, plain).convert("L").point(lambda v: 255 if v > 14 else 0).getbbox()
            if not box:
                return Path(image), im.height / im.width
            pad = round(0.02 * im.width)
            left, top = max(0, box[0] - pad), max(0, box[1] - pad)
            right, bottom = min(im.width, box[2] + pad), min(im.height, box[3] + pad)
            if (right - left) * (bottom - top) > 0.94 * im.width * im.height:
                return Path(image), im.height / im.width
            if self.trimmed_dir is None:
                import tempfile
                self.trimmed_dir = Path(tempfile.mkdtemp(prefix="blueprint-figures-"))
            out = self.trimmed_dir / f"{len(self.trim_cache) + 1:03d}-{Path(image).name}"
            im.crop((left, top, right, bottom)).save(out)
            if (bottom - top) / (right - left) >= self.PHONE_SHAPE:
                self.phones.add(str(out))
            # The figure's ground takes the canvas colour, so the margin kept round the phone does not show
            # as a darker box on the page's lighter grey.
            self.grounds[str(out)] = "%02X%02X%02X" % im.getpixel((0, 0))
            return out, (bottom - top) / (right - left)

    def picture_width(self, shape, room_cm, max_height_cm=None, phone=False):
        """The width (cm) at which a picture fills the room it has without being taller than its page allows.
        Every phone screen is drawn at the width it has when two share a row, so all of them are at one
        scale, alone or in pairs (a short one alone at the full width looked twice the size of the rest)."""
        tallest = max_height_cm or (self.text_height - self.FIGURE_ROOM)
        if phone:
            room_cm = min(room_cm, self.phone_width)
        return min(room_cm, tallest / shape)

    @property
    def phone_width(self):
        return (self.text_width - 0.8) / 2 - 0.45

    def figure(self, image, caption, width_cm=None, max_height_cm=None):
        """A screenshot on the grey ground, like a product shot, with a quiet caption. It is sized to fit on a
        page with its caption: a picture taller than a page overflowed it, covering the footer, pushing the
        caption to the next page and leaving the page before it blank."""
        width_cm = width_cm or (self.text_width - 0.8)
        picture, shape = self.trimmed(image)
        self.glue_previous()
        # Picture and caption are two rows of one table, kept together: Word does not reliably keep a table
        # with the paragraph after it, but it does keep rows of the same table together.
        t = (self.target or self.doc).add_table(rows=2, cols=1)
        table_base(t, pad=(140, 200))
        cell = t.rows[0].cells[0]
        shade(cell._tc.get_or_add_tcPr(), self.grounds.get(str(picture), self.c["ground"]))
        cell.paragraphs[0].add_run().add_picture(
            str(picture), width=Cm(self.picture_width(shape, width_cm - 0.7, max_height_cm, phone=str(picture) in self.phones)))
        self.pictures.append(picture)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        cell.paragraphs[0].paragraph_format.space_after = Pt(0)
        cell.paragraphs[0].paragraph_format.keep_with_next = True
        self.figures += 1
        self.caption_cell(t.rows[1].cells[0], caption)
        for row in t.rows:
            keep_row_together(row)
        fixed_widths(t, [width_cm])
        spacer = (self.target or self.doc).add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

    def figure_beside(self, image, caption, render, room_cm=None):
        """A phone screen with what describes it (its field table) beside it rather than under it: the phone
        takes the width it has in a pair, and the empty half of the page next to it holds the table. A
        screen's phone and fields then share one page. render(width_cm) writes the right-hand side."""
        left_w = self.phone_width + 0.8
        gap = 0.35
        right_w = self.text_width - left_w - gap
        self.glue_previous()
        t = self.doc.add_table(rows=1, cols=2)
        table_base(t, pad=(0, 0))
        left, right = t.rows[0].cells
        mar = OxmlElement("w:tcMar")
        m = OxmlElement("w:left")
        m.set(qn("w:w"), str(round(gap * 567)))
        m.set(qn("w:type"), "dxa")
        mar.append(m)
        right._tc.get_or_add_tcPr().append(mar)
        try:
            self.target = left
            self.figure(image, caption, width_cm=left_w, max_height_cm=self.text_height - self.FIGURE_ROOM - 1.0)
            self.target = right
            render(right_w)
        finally:
            self.target = None
        for cell in (left, right):  # a cell starts with an empty paragraph, and every table leaves a gap after it
            paras = cell.paragraphs
            if len(paras) > 1 and not paras[0].text.strip() and paras[0]._p.getnext() is not None:
                paras[0]._p.getparent().remove(paras[0]._p)
            last = cell.paragraphs[-1]
            if not last.text.strip():  # the paragraph Word needs after a table in a cell: as small as it can be
                from docx.enum.text import WD_LINE_SPACING
                last.paragraph_format.space_after = Pt(0)
                last.paragraph_format.space_before = Pt(0)
                last.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
                last.paragraph_format.line_spacing = Pt(1)
        keep_row_together(t.rows[0])
        fixed_widths(t, [left_w, right_w + gap])
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

    def figure_pair(self, first, second):
        """Two phone screens side by side on one ground, each with its own caption: (image, caption) each.
        A phone screen at the full width of the page was taller than the page; two to a row are both readable
        and take half the pages."""
        width_cm = self.text_width - 0.8
        half = width_cm / 2
        pictures = [self.trimmed(image) for image, _ in (first, second)]
        self.glue_previous()
        t = self.doc.add_table(rows=2, cols=2)
        table_base(t, pad=(140, 120))
        for i, ((picture, shape), (_, caption)) in enumerate(zip(pictures, (first, second))):
            cell = t.rows[0].cells[i]
            shade(cell._tc.get_or_add_tcPr(), self.grounds.get(str(pictures[0][0]), self.c["ground"]))
            p = cell.paragraphs[0]
            p.add_run().add_picture(str(picture), width=Cm(self.picture_width(shape, self.phone_width, phone=True)))
            self.pictures.append(picture)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.keep_with_next = True
            self.figures += 1
            self.caption_cell(t.rows[1].cells[i], caption)
        for row in t.rows:
            keep_row_together(row)
        fixed_widths(t, [half, half])
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(6)

    def caption_cell(self, cap_cell, caption):
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

    def is_phone(self, image):
        """A phone screen: cut from the canvas it was drawn on, and tall. A desktop screen fills its picture
        (however long the page), so it is never one."""
        return str(self.trimmed(image)[0]) in self.phones

    def table_height(self, rows, widths, size, group_rows=()):
        """About how tall a table is (cm), from how many lines each row's longest cell wraps to."""
        char_cm = size * 0.5 / 72 * 2.54
        line = size * 1.2 / 72 * 2.54
        total = line + 0.3  # the header
        for i, row in enumerate(rows):
            if i in group_rows:
                total += line + 0.25
                continue
            texts = ["".join(x[0] for x in v) if isinstance(v, list) else str(v or "") for v in row]
            lines = max(max(1, -(-len(t) // max(1, int((w_ - 0.25) / char_cm)))) for t, w_ in zip(texts, widths))
            total += lines * line + 0.25
        return total

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
                self.runs(cells[1].paragraphs[0], [(ref[0], "ref", ref[1])] if isinstance(ref, tuple) else [(ref, "ref")])
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
        if key == "scope" and not (spec.get("scope") or sow_items(spec)):
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


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def readable_date(value):
    """A date from the spec as the document prints it: 2026-11-06 becomes 6 November 2026, the same on every
    page whatever the machine's language. Anything else (a month, "TBC") is printed as typed."""
    text = str(value or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
        return f"{int(m.group(3))} {MONTHS[int(m.group(2)) - 1]} {m.group(1)}"
    return text


def requirement_ids(spec):
    """Every requirement id this spec prints: each group's id and each numbered item under it."""
    ids = set()
    for g in spec.get("requirements") or []:
        if isinstance(g, dict) and g.get("id"):
            ids.add(str(g["id"]))
            ids.update(f"{g['id']}.{i}" for i in range(1, len(g.get("items") or []) + 1))
    return ids


def required_names(fmt):
    """What the format's `required` asks every document to have, as (non-functional areas, sections). Only what
    the document has a place for: no areas when the format leaves out the nfr chapter, no sections without extras."""
    req = fmt.get("required") if isinstance(fmt.get("required"), dict) else {}
    listed = lambda key: req.get(key) if isinstance(req.get(key), list) else []
    chapters = fmt.get("chapters") or []
    areas = [str(a).strip() for a in listed("nfr") if str(a).strip()] if "nfr" in chapters else []
    sections = [str(x).strip() for x in listed("sections") if str(x).strip()] if "extras" in chapters else []
    return areas, sections


def _names(entry, key):
    """The names a spec entry answers to: its own `area` or `title`, and whatever it `covers`."""
    covers = entry.get("covers")
    return [str(entry.get(key) or "")] + ([covers] if isinstance(covers, str) else [str(c) for c in covers or []])


def _covers(names, required, word=False):
    """Whether one of an entry's names is the required name: the same words, ignoring case, or (word=True, for
    an area) containing them as words, so "Backup and recovery" counts for Backup."""
    want = required.strip().lower()
    for name in names:
        name = name.strip().lower()
        if name == want or (word and re.search(rf"\b{re.escape(want)}\b", name)):
            return True
    return False


def section_gaps(spec, fmt):
    """The parts the requirements standard asks for (the format's `required`) that the spec leaves empty:
    [{kind: "nfr" | "section", name, tbc, present}]. `tbc` is the register id the spec links to it (or "");
    `present` says whether the spec has an entry for it at all (an empty one, or one waiting on `tbc`)."""
    spec = spec or {}
    areas, sections = required_names(fmt)
    gaps = []
    rows = [x for x in spec.get("nfr") or [] if isinstance(x, dict)]
    for area in areas:
        found = [x for x in rows if _covers(_names(x, "area"), area, word=True)]
        if not any(str(x.get("requirement") or "").strip() for x in found):
            gaps.append({"kind": "nfr", "name": area, "present": bool(found),
                         "tbc": next((str(x["tbc"]) for x in found if x.get("tbc")), "")})
    extras = [e for e in spec.get("extra_sections") or [] if isinstance(e, dict)]
    for name in sections:
        found = [e for e in extras if _covers(_names(e, "title"), name)]
        if not any(e.get("content") for e in found):
            gaps.append({"kind": "section", "name": name, "present": bool(found),
                         "tbc": next((str(e["tbc"]) for e in found if e.get("tbc")), "")})
    return gaps


def with_required_parts(spec, fmt):
    """The spec as the document prints it: every required area and section the spec has no entry for is added,
    empty, so it shows as To be confirmed instead of quietly not being there. Changes `spec` in place (the
    generator's own copy; the spec file is not touched) and returns the gaps."""
    gaps = section_gaps(spec, fmt)
    for g in gaps:
        if g["present"]:
            continue
        if g["kind"] == "nfr":
            spec.setdefault("nfr", []).append({"area": g["name"], "requirement": ""})
        else:
            spec.setdefault("extra_sections", []).append({"title": g["name"], "content": []})
    return gaps


def missing_parts(spec, fmt):
    """The parts the requirements standard asks for that the spec does not have yet, as sentences: the
    document is still generated (a draft may lack them), but a version for sign-off should not."""
    import workshop  # its spec_gaps says the same of the scope and the non-functional requirements

    chapters = fmt.get("chapters") or []
    topics = {"Scope": "scope", "Non-functional requirements": "nfr"}
    found = [f"{topic.lower()}: {what}" for topic, what, _ in workshop.spec_gaps(spec, {**fmt, "required": {}})
             if topic in topics and topics[topic] in chapters]
    if "timeline" in chapters and not ((spec.get("timeline") or {}).get("stages") if isinstance(spec.get("timeline"), dict) else None):
        found.append("timeline: none in the spec, so the document has no timeline chapter (add `timeline`, "
                     "see docs/spec-format.md)")
    gaps = section_gaps(spec, fmt)
    areas = [g["name"] for g in gaps if g["kind"] == "nfr" and not g["tbc"]]
    if areas and spec.get("nfr"):  # with no nfr at all, "none recorded" above says it for every area
        found.append(f"non-functional requirements: nothing for {', '.join(areas)}, printed as To be confirmed "
                     "(write each under `nfr`, or link the register item that settles it with `tbc: R-...`)")
    sections = [g["name"] for g in gaps if g["kind"] == "section" and not g["tbc"]]
    if sections:
        found.append(f"sections: nothing written for {', '.join(sections)}, printed as To be confirmed (write each "
                     "under `extra_sections`, or link the register item that settles it with `tbc: R-...`)")
    for g in gaps:
        if g["tbc"]:
            found.append(f"{'non-functional requirements' if g['kind'] == 'nfr' else 'sections'}: {g['name']} is printed "
                         f"as To be confirmed, waiting on {g['tbc']}")
    if "signoff" in chapters:
        signoff = [s for s in spec.get("signoff") or [] if isinstance(s, dict)]
        if not signoff:
            found.append("sign-off: nobody is named, so the forms are blank (list the signatories under `signoff`)")
        for s in signoff:
            if SIGNATORY_PLACEHOLDER.match(str(s.get("name") or "")):
                who = s.get("signing_for") or s.get("organisation") or "a signatory"
                found.append(f"sign-off: no name for {who} (set `name` under `signoff`)")
    return found


def team_notes(text, known_requirements, register=None, listed=(), system=True):
    """What in a client-visible text belongs to the team, not to the client, as short sentences: the mock-up,
    "proposed", a mock-up comment id (FB-…), a register id (R-…) the document does not list among its
    decisions needed, a requirement id that is not in this spec (often one of the client's original document).
    `register` maps register ids to items; `listed` are the ids printed under Decisions needed. `system` is
    false for texts about the project rather than the system (the timeline, the version history, where a
    decision was agreed), which may well speak of the mock-up or of a proposed date."""
    text = REF.sub("", str(text or ""))  # a {ref:...} is resolved, so it is never a stale id
    found = []

    def around(m):
        a, b = max(0, m.start() - 25), min(len(text), m.end() + 25)
        return ("..." if a else "") + text[a:b].strip() + ("..." if b < len(text) else "")

    m = MOCKUP_WORD.search(text) if system else None
    if m:
        found.append(f"mentions the mock-up ('{around(m)}'); the document should describe the real system")
    m = PROPOSED_WORD.search(text) if system else None
    if m:
        found.append(f"says 'proposed' ('{around(m)}'); write what was agreed, and keep what is still open in the register")
    for x in dict.fromkeys(FEEDBACK_ID.findall(text)):
        found.append(f"names the mock-up comment {x}, which the client cannot look up; say in words what was agreed")
    for x in dict.fromkeys(REGISTER_ID.findall(text)):
        if x in listed:
            continue
        it = (register or {}).get(x)
        if it and it.get("audience") == "internal":
            found.append(f"names {x}, an internal register item the client never sees")
        elif it and it.get("status") in ("resolved", "wont-fix"):
            found.append(f"names {x}, which is closed in the register; write the decision into the text")
        else:
            found.append(f"names {x}, which is not among the decisions needed in this document")
    for x in dict.fromkeys(REQUIREMENT_ID.findall(text)):
        if x not in known_requirements:
            found.append(f"names {x}, which is not a requirement in this spec (an id from another document?); "
                         "use {ref:req:...} or an id from this spec")
    return found


# ====================================================================== main
def build(project):
    project = Path(project)
    spec_file = layout.spec_file(project)
    if not project.is_dir():
        sys.exit(f"No project at {project}. Give the project's folder, for example projects/<slug>.")
    if not spec_file.exists():
        sys.exit(f"No spec at {spec_file}: this project has no spec yet. Build a mock-up first (it writes the spec), "
                 "then take its screenshots and generate the document.")
    spec = json.loads(json.dumps(yaml.safe_load(spec_file.read_text(encoding="utf-8")), default=str))
    import mockup  # the spec check, and whether the screenshots still show the spec
    import project as project_tool  # issued versions are locked

    project_tool.version_of(spec.get("project") or {})  # 1.10 written without quotes would be named and locked as 1.1
    issued = project_tool.is_issued(project, spec["project"].get("version", ""))
    if issued:
        sys.exit(f"v{issued['version']} was issued to {issued['to']} on {issued['date']} and is locked. "
                 "Bump project.version in the spec (e.g. to the next minor version) and generate again.")
    shots_file = layout.shots_plan(project)
    if not shots_file.exists():
        sys.exit("No screenshots yet. Run: python -I tools/mockup.py screenshots " + str(project))
    errors = mockup.validate(spec)
    if errors:
        sys.exit("The spec has errors. Fix them, take the screenshots again, then generate:\n  " + "\n  ".join(errors))
    errors = document_errors(spec)
    if errors:
        sys.exit("The spec has errors in the parts the document prints. Fix them, then generate:\n  " + "\n  ".join(errors))
    shots = json.loads(shots_file.read_text(encoding="utf-8"))
    shot_dir = layout.screenshots_dir(project)
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
    reg_file = layout.register_json(project)
    items = json.loads(reg_file.read_text(encoding="utf-8"))["items"] if reg_file.exists() else []
    open_items = [it for it in items if it["audience"] == "client" and it["status"] not in ("resolved", "wont-fix")]
    made_items = [it for it in items if it["audience"] == "client" and it["status"] == "resolved"
                  and (str(it.get("answer") or "").strip() or str(it.get("decision") or "").strip())]
    parts_missing = missing_parts(spec, fmt)  # of the spec as written, before the required parts are added
    with_required_parts(spec, fmt)
    chapters, refs = plan_sections(spec, fmt, items)
    labels = fmt["labels"]
    warnings = ["screenshots: " + problem for problem in mockup.screenshot_problems(project, spec)]
    warnings += flow_names(spec)[1]
    raw = [it["id"] for it in made_items if not str(it.get("decision") or "").strip()]
    if raw and "decisions" in [k for k, *_ in chapters]:
        warnings.append(f"Decisions made prints the client's own answer for {', '.join(raw)}: write each one's agreed decision "
                        "in one line (register.py update ... --set decision=\"...\"), as it is what the client signs")
    cover = sow_coverage(spec)
    bare = [f"{x['ref']} {x['item']}" for x in sow_items(spec) if not cover.get(str(x["ref"]).strip()) and not x.get("deferred")]
    if bare:
        warnings.append(f"Scope of work items with no requirement: {'; '.join(bare)}. Write their requirements (sow: on the "
                        "group), or record that they are left out of this version (deferred:) once the client agrees")
    notes = []  # worth knowing, but no reason to hold a version back
    roles = spec["roles"]
    role_ids = [r["id"] for r in roles]
    screens = spec["screens"]
    dialogs = {d["id"]: d for d in spec.get("dialogs", [])}
    status_text = P.get("status") or labels["default_status"]
    status_color = "ok" if status_is_settled(status_text) else "warning"
    version = P.get("version", "draft")
    num = {key: number for key, number, _ in chapters if number}
    known_reqs = requirement_ids(spec)
    register = {it.get("id"): it for it in items}
    listed = {it["id"] for it in open_items} if "decisions" in num else set()

    def team_check(text, where):
        """Warn about team-only words in a text the client will read, saying where it is in the spec."""
        if isinstance(text, str) and text.strip():
            system = not (where.startswith(PROJECT_TEXT) or where.endswith(PROJECT_TEXT))
            warnings.extend(f"{where}: {x}" for x in team_notes(text, known_reqs, register, listed, system))

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
        if where:
            team_check(text, where)
        return out

    # The short texts the document prints as they are (names, titles, labels, captions), checked the same way
    # as the longer ones that go through fill().
    team_check(P.get("name"), "project")
    team_check(P.get("status"), "project status")
    for r in roles:
        team_check(r.get("name"), f"role {r['id']}")
    for s in spec.get("statuses") or []:
        team_check(s.get("name"), f"status {s.get('name')}")
    for s in screens:
        where = f"screen {s['id']}"
        for text in (s.get("title"), s.get("caption")):
            team_check(text, where)
        for sec in s.get("sections") or []:
            team_check(sec.get("title"), where)
            for f in sec.get("fields") or []:
                team_check(f.get("label"), f"field {f['id']}")
        lst = s.get("list") or {}
        for c in lst.get("columns") or []:
            team_check(c.get("label"), where)
        for b in (lst.get("toolbar") or []) + (lst.get("actions") or []) + (s.get("buttons") or []):
            if not b.get("example"):
                team_check(b.get("label"), where)
        for stat in s.get("stats") or []:
            team_check(stat.get("label"), where)
    for d in spec.get("dialogs") or []:
        team_check(d.get("title"), f"dialog {d['id']}")
        for f in d.get("fields") or []:
            team_check(f.get("label"), f"dialog {d['id']}, field {f['id']}")
    for shot in shots:
        team_check(shot.get("caption"), f"screenshots, {shot['name']}")
    for x in spec.get("glossary") or []:
        team_check(x.get("term"), f"glossary {x.get('term')}")
    for x in spec.get("nfr") or []:
        team_check(x.get("area"), f"non-functional requirement {x.get('area')}")
    for x in spec.get("integrations") or []:
        team_check(x.get("system"), f"integration {x.get('system')}")
        team_check(x.get("direction"), f"integration {x.get('system')}")
    for e in spec.get("extra_sections") or []:
        team_check(e.get("title"), f"section '{e.get('title')}'")
        for block in e.get("content") or []:
            team_check(block.get("heading"), f"section '{e.get('title')}'")
            team_check(block.get("caption"), f"section '{e.get('title')}'")
    for st in (spec.get("timeline") or {}).get("stages") or []:
        team_check(st.get("name"), "timeline")
        for it in st.get("items") or []:
            team_check(it.get("name"), "timeline")
    # What the register puts in the document: its questions and answers, and where each was agreed.
    for it in open_items + made_items:
        for key in ("question", "answer", "resolved_in") + (("finding",) if not it.get("question") else ()):
            if it in open_items and key in ("answer", "resolved_in"):
                continue
            team_check(str(it.get(key) or ""), f"register {it['id']}, {key}")

    doc = template_document()
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
    # Where in this document each decision needed applies: the requirements that carry it as `tbc`, otherwise
    # the requirement ids its register `source` names, if this spec has them. A source says where the item was
    # found, often in the client's original document, whose ids are not this document's: printed as they are,
    # they pointed the client at the wrong requirement or at none.
    where_asked, elsewhere = {}, []
    for g in groups:
        for i, item in enumerate(g["items"], 1):
            for x in REGISTER_ID.findall(str(item.get("tbc") or "") if isinstance(item, dict) else ""):
                where_asked.setdefault(x, []).append(f"{g['id']}.{i}")
    for it in open_items:
        if it["id"] in where_asked:
            continue
        named = list(dict.fromkeys(REQUIREMENT_ID.findall(str(it.get("source") or ""))))
        if [x for x in named if x in known_reqs]:
            where_asked[it["id"]] = [x for x in named if x in known_reqs]
        if [x for x in named if x not in known_reqs]:
            elsewhere.append(f"{it['id']} ({', '.join(x for x in named if x not in known_reqs)})")
    if elsewhere and "decisions" in num:
        notes.append(f"the register's source for {', '.join(elsewhere)} names requirement ids that are not in this spec "
                     "(probably those of the document the question was found in), so Decisions needed does not show them. "
                     "Put `tbc: R-xxx` on the requirement each question is about, and the document points at it")
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
            client_logo = layout.spec_dir(project) / "client-logo.png"
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
            pairs = [("Version", [(version, "mono")]), ("Date", readable_date(P.get("date"))), ("Prepared by", P.get("prepared_by", "")),
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
            # Each section it names is a link to that section.
            reading = []
            if "by_role" in num:
                reading += [("Business users: ", ""), (f"section {num['by_role']}", "ref", "section:by-role"), (" (your role)", "")]
                if "screens" in num:
                    reading += [(" and ", ""), (f"section {num['screens']}", "ref", "section:screens"), (" (your screens)", "")]
                reading.append((". ", ""))
            later = [(c[1], f"extra:{c[2]}" if c[0] == "extra" else "section:nfr") for c in chapters if c[0] in ("nfr", "extra") and c[1]]
            if later:
                reading += [("IT: ", "")]
                if len(later) > 1:
                    reading += [("sections ", ""), (later[0][0], "ref", later[0][1]), (" to ", ""), (later[-1][0], "ref", later[-1][1])]
                else:
                    reading += [(f"section {later[0][0]}", "ref", later[0][1])]
                reading.append((". ", ""))
            if "decisions" in num:
                reading += [("Everyone: ", ""), (f"section {num['decisions']}", "ref", "section:open-issues"), (", the decisions we need from you.", "")]
            if reading and reading[-1][0] == ". ":
                reading[-1] = (".", "")
            w.para(reading, after=6)
            w.para([("Sign-off", "medium")], size=w.s["h3"], before=8, after=3)
            w.table(["Name", "Organisation", "Signing for", "Status"],
                    [[s.get("name") or "To be named", s.get("organisation", ""), s.get("signing_for", ""),
                      [("ok" if str(s.get("status", "")).lower() == "signed" else "line", "dot"), (str(s.get("status") or "Pending").capitalize(), "")]]
                     for s in signers_in_order], [4.6, 4.6, 3.6, w.text_width - 12.8])
            if P.get("history"):
                w.para([("Version history", "medium")], size=w.s["h3"], before=8, after=3)
                w.table(["Version", "Date", "Author", "Changes"],
                        [[[(str(h.get("version")), "mono")], readable_date(h.get("date")), h.get("author"), fill(h.get("changes", ""), f"project history v{h.get('version')}")] for h in P["history"]],
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

    def side_table_rows(rows, group):
        """A field table beside a phone screen has three columns: a required field carries an asterisk, as it
        does on the screen beside it, in place of the Required column there is no room for."""
        return [r if i in group else [r[0] + (" *" if r[2] else ""), r[1], r[3]] for i, r in enumerate(rows)]

    def side_field_widths(width, rows=()):
        """Field, Type, Rule: the Field column as wide as its longest word ("Acknowledgement" broke in two)."""
        size = w.s["table"] - 0.5
        longest = max((len(word) for r in rows for word in str(r[0]).split()), default=10)
        field_w = min(3.4, max(2.5, longest * size * 0.56 / 72 * 2.54 + 0.35))
        type_w = 2.1
        return [field_w, type_w, width - field_w - type_w]

    def side_fields(rows, group, width, size):
        shown = side_table_rows(rows, group)
        w.table(["Field", "Type", "Rule or source"], shown, side_field_widths(width, shown), group_rows=group,
                size=size, pad=(60, 60))
        if any(r[2] for i, r in enumerate(rows) if i not in group):
            w.para([("* Required", "sec")], size=w.s["caption"], after=0)

    def list_tables(lst, width, size=None, screen=None):
        """A list's columns with what can be searched and filtered, then its other filters, sort and actions."""
        where = f"screen {screen['id']} sort" if screen else ""
        marks = {f: "Search" for f in lst.get("search") or []}
        for f in lst.get("filters") or []:
            marks[f] = (marks.get(f, "") + " Filter").strip()
        first = min(6.0, width * 0.55)
        t = w.table(["Column", "Search and filter"], [[c["label"], [(marks[c["field"]], "tag")] if c["field"] in marks else ""] for c in lst["columns"]],
                    [first, width - first], size=size, keep_whole=len(lst["columns"]) <= 15)  # a list's columns are read as one
        lines = []
        extra_filters = [pretty(f) for f in (lst.get("filters") or []) if f not in [c["field"] for c in lst["columns"]]]
        if extra_filters:
            lines.append([("Also filtered by ", "sec"), (", ".join(extra_filters), "")])
        if lst.get("sort"):
            lines.append([("Sorted ", "sec"), (fill(lst["sort"], where).lower() if lst["sort"][:2] == "By" else fill(lst["sort"]), "")])
        acts = [a["label"] for a in (lst.get("toolbar") or []) + (lst.get("actions") or []) if not a.get("example")]
        if acts:
            lines.append([("Actions ", "sec"), (", ".join(a.lstrip("+ ") for a in acts), "")])
        if lines:  # the lines under the table stay with its last rows: "Actions" alone on a page said nothing
            w.keep_row_with_next(t.rows[-1])
            gap = t._tbl.getnext()
            if gap is not None and gap.tag == qn("w:p"):
                gap.get_or_add_pPr().append(OxmlElement("w:keepNext"))
        for k, line in enumerate(lines):
            w.para(line, size=size, keep=k < len(lines) - 1)

    def field_widths(rows):
        """Field, Type, Required, Rule: the Type column wide enough for "Text (read-only)" on one line."""
        longest = max((len(str(r[1])) for r in rows if len(r) > 1), default=10)
        type_w = min(3.6, max(2.7, longest * w.s["table"] * 0.52 / 72 * 2.54 + 0.5))
        return [3.8, type_w, 1.8, tw - 5.6 - type_w]

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
                src = f.get("source") or (options_from_words(f["options_from"]) if f.get("options_from")
                                          else ("Options: " + ", ".join(map(str, f["options"])) if f.get("options") else ""))
                val = f.get("validation") if f.get("validation") not in (None, "N/A") else ""
                rule = ". ".join(x for x in (src, val) if x) or "–"
                rows.append([f["label"], t, "✓" if f.get("required") else "", fill(rule, f"field {f['id']}")])
        return rows, group

    def to_be_confirmed(entry):
        """A required part with nothing written yet: To be confirmed, and the decision it waits on when the
        document lists that decision."""
        tbc = str(entry.get("tbc") or "")
        if tbc in listed:
            return [("warning", "dot"), (f"To be confirmed: decision needed {tbc}, see ", ""),
                    (refs.get("section:open-issues", "the decisions section"), "ref", "section:open-issues"), (".", "")]
        return [("warning", "dot"), ("To be confirmed.", "")]

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
                img = layout.spec_dir(project) / block["image"]
                if img.exists():
                    w.figure(img, block.get("caption", extra["title"]))
                else:
                    warnings.append(f"{where}: image {block['image']} not found")

    captions = {}  # of the screens' figures, with the screen and shot of each: two alike and the reader cannot tell the pictures apart

    def caption_advice(cap, s, shot, first):
        """How to tell two figures with one caption apart, as a fix that cannot make it worse: a `caption` for the
        extra shot that says what differs (its record, role, page or dialog), never the screen's own `caption`,
        which every figure of the screen takes. Two screens that share a title each get their own `caption`."""
        other_screen, other = first
        if other_screen != s["id"]:
            return (f"screen {other_screen} has a figure with it too: give one of the two screens its own `caption` "
                    "that says what it is for")
        names = {r["id"]: r["name"] for r in roles}
        differs = []
        if shot.get("record") and shot.get("record") != other.get("record"):
            differs.append(f"showing record {shot['record']}")
        if shot.get("role") and shot.get("role") != other.get("role"):
            differs.append(f"as seen by {names.get(shot['role'], shot['role'])}")
        if shot.get("page") and shot.get("page") != other.get("page"):
            differs.append(f"page {shot['page']}")
        if shot.get("dialog") and shot.get("dialog") != other.get("dialog") and shot["dialog"] in dialogs:
            differs.append(f"with the {dialogs[shot['dialog']]['title'].lower()} dialog")
        if "dialog" not in shot:  # the screen's own figure: the extra one is the other
            return (f"give the extra one a `caption` in `screenshots`, name {other.get('name')}, that says what it shows "
                    "differently (not the screen's `caption`: both figures take it)")
        if not differs:
            return (f"`screenshots` entry {shot['name']} shows the same screen, role and record as {other.get('name')}: "
                    "take it out, or set the `record` or `role` it should show")
        return (f"give `screenshots` entry {shot['name']} its own `caption`, for example \"{cap}, {' and '.join(differs)}\" "
                "(not the screen's `caption`: both figures take it)")
    by_screen = {}
    for s in shots:
        by_screen.setdefault(s["screen"], []).append(s)

    def chapter_key(key, title):
        """The reference key of a chapter, the one plan_sections gave its number under."""
        if key == "extra":
            return f"extra:{title}"
        return f"section:{CHAPTER_REFS[key]}" if key in CHAPTER_REFS else None

    def link_list(keys, style="ref", sep=", "):
        """Segments for several references, each a link: [("5.1", "ref", "screen:login"), (", ", "ref") ...]."""
        out = []
        for i, (text, key) in enumerate(keys):
            out += ([(sep, "ref" if style == "ref" else "")] if i else []) + [(text, style, key)]
        return out

    group_ids = {g["id"] for g in groups}

    def requirement_key(x):
        return f"req:{x}" if x in group_ids else f"reqitem:{x}"

    for key, number, title in chapters:
        # ---------------------------------------------------------------- users and access
        if key == "users_access":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            for line in spec.get("overview", []) or []:
                w.para(fill(line, "overview"))
            k = 0

            def sub(t, name):
                nonlocal k
                k += 1
                w.heading(f"{number.split('.')[0]}.{k} {t}", 2, key=f"section:{name}")

            sub("User roles", "roles")
            w.table(["Role", "Responsibility", "Sees"],
                    [[[(r["name"], "medium")], fill(r.get("description", ""), f"role {r['id']}"), fill(r.get("scope", ""), f"role {r['id']}")] for r in roles],
                    [3.4, tw - 7.6, 4.2])
            sub("Access matrix", "access")
            w.lead("A tick means the role has access; blank means no access. Built from the screens, so it always matches them.")
            rows, seen = [], set()

            def add_row(label, allowed):
                if label not in seen:
                    seen.add(label)
                    rows.append([label] + ["✓" if r in allowed else "" for r in role_ids])

            for s in screens:
                if s.get("menu"):
                    add_row(s["menu"], s.get("roles") or role_ids)
            # A screen's actions open to the same roles share one row ("Job Details: Navigate, Call Customer,
            # Accept Job"): a row per button made the matrix three pages of mostly empty rows.
            for s in screens:
                allowed_screen = s.get("roles") or role_ids
                lst = s.get("list") or {}
                same = {}  # the roles allowed -> the actions they may do, in screen order
                for b in (lst.get("toolbar") or []) + (lst.get("actions") or []) + (s.get("buttons") or []):
                    if b.get("example") or b.get("access") is False or b.get("label") in SKIP_ACTIONS:
                        continue
                    allowed = tuple(r for r in role_ids if r in (b.get("roles") or allowed_screen))
                    label_ = b["label"].lstrip("+ ").strip()
                    if label_ not in same.setdefault(allowed, []):
                        same[allowed].append(label_)
                for allowed, labels_ in same.items():
                    add_row(f"{s['title']}: {', '.join(labels_)}", allowed)
            # Size role columns to their longest word, so names wrap only at spaces and after "/" and never
            # break mid-word. If the roles don't fit side by side, their names are turned on their side.
            char_cm = w.s["table_header"] * 0.56 / 72 * 2.54
            words = lambda name: re.split(r"[ /]", name.replace("/", "/ "))
            need = max(len(x) for r in roles for x in words(r["name"]) if x) * char_cm + 0.35
            first = min(5.0, max(3.6, max(len(x) for row in rows for x in str(row[0]).split()) * char_cm + 0.6))
            per = (tw - first) / len(roles)
            rotate = per < need
            if rotate:  # narrow role columns leave room for the actions, which share a row per screen
                first = max(min(5.0, tw - 0.85 * len(roles)), min(7.0, tw - 1.5 * len(roles)))
                per = (tw - first) / len(roles)
            longest = max(len(r["name"]) for r in roles) * char_cm + 0.5
            # Kept on one page when it fits on one: it is read across, role by role.
            w.table(["Menu or action"] + [r["name"] for r in roles], rows, [first] + [per] * len(roles),
                    size=w.s["table"] - 0.5, pad=(70, 60), center_from=1, rotate_from=1 if rotate else None,
                    header_height=longest if rotate else None, keep_whole=len(rows) <= 28)
            if spec.get("statuses"):
                sub("Process and statuses", "flow")
                flow = layout.spec_dir(project) / "process-flow.png"
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

                    def moves_to(value, auto=()):
                        """The statuses it moves to; those the system moves it to on its own (`auto`) say so."""
                        if value is None:
                            return undecided
                        return ", ".join(status_name[x] + (" (automatic)" if x in auto else "") for x in value) or "None: a final status"

                    w.para([("Status rules", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
                    w.lead("Who may change a record while it is in each status, and which statuses it can move to.")
                    rule_w = (tw - 3.0) / 4
                    w.table(["Status"] + [label_ for _, label_ in STATUS_RULES] + ["Moves to"],
                            [[[(s["name"], "medium")]] + [who(s.get(k)) for k, _ in STATUS_RULES]
                             + [moves_to(s.get("next"), s.get("auto") or ())] for s in spec["statuses"]],
                            [3.0] + [rule_w] * 4)
                    open_rules = [s["name"] for s in spec["statuses"] if any(s.get(k) is None for k in rule_keys)]
                    if open_rules:
                        warnings.append(f"statuses: rules still to be confirmed for {', '.join(open_rules)} "
                                        "(set edit, cancel, delete and next on each status)")
                else:
                    notes.append("no status rules in the spec (who may edit, cancel or delete in each status, and where it "
                                 "moves next): see docs/spec-format.md")
            if spec.get("integrations"):
                sub("External systems", "integrations")
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
                sub("E-mail notifications", "notifications")
                w.table(["Event", "Sent to", "Template"],
                        [[fill(n["event"], "notifications"), fill(n["recipient"], "notifications"),
                          fill(n.get("template", "To be confirmed"), "notifications")] for n in spec["notifications"]],
                        [5.4, 4.2, tw - 9.6])
            if spec.get("glossary"):
                sub("Terms", "glossary")
                w.table(["Term", "Meaning"], [[[(g["term"], "medium")], fill(g["meaning"], f"glossary {g['term']}")] for g in spec["glossary"]],
                        [3.0, tw - 3.0])

        # ---------------------------------------------------------------- scope and assumptions
        elif key == "scope":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            w.lead(fill(bp.get("scope_intro") or SCOPE_INTRO))
            for part, label_ in SCOPE_PARTS:
                if (spec.get("scope") or {}).get(part):
                    w.para([(label_, "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                    w.bullets([fill(x, f"scope, {label_.lower()}") for x in spec["scope"][part]])
            if sow_items(spec):
                # Where each item of the scope of work is specified, so the client can check nothing sold is missing.
                cover = sow_coverage(spec)
                w.para([("Scope of work items", "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                rows = []
                for x in sow_items(spec):
                    ids = cover.get(str(x["ref"]).strip()) or []
                    if ids:
                        where_ = link_list([(i, requirement_key(i)) for i in ids])
                    elif x.get("deferred"):
                        where_ = "Not in this version: " + fill(str(x["deferred"]), f"sow item {x['ref']}")
                    else:
                        where_ = [("Not specified yet", "tag")]
                    rows.append([str(x["ref"]), fill(str(x["item"]), f"sow item {x['ref']}"), where_])
                w.table(["Ref", "Scope of work item", "Specified in"], rows, [1.6, tw * 0.5 - 1.6, tw * 0.5])

        # ---------------------------------------------------------------- requirements by role
        elif key == "by_role":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            w.lead("What each role sees and does. Each line points to where it is specified in full.")
            ch = number.split(".")[0]
            for i, r in enumerate(roles, 1):
                w.heading(f"{ch}.{i} {r['name']}", 2, key=f"role:{r['id']}")
                mine = [s for s in screens if s["type"] != "login" and r["id"] in (s.get("roles") or role_ids)]
                if r.get("description") or r.get("scope"):
                    where = f"role {r['id']}"  # the same place as in the roles table: a bad reference is reported once
                    # Kept with the list under it: a role's heading and one line used to end a page on their own.
                    w.para([(fill(r.get("description", ""), where), ""),
                            ((" Sees: " + fill(r["scope"], where) + ".") if r.get("scope") else "", "sec")], keep=bool(mine))
                if mine:
                    w.para([("Screens", "medium")], before=4, after=2, keep=True)
                    w.line_list([s["title"] for s in mine], [(short(refs.get(f"screen:{s['id']}")), f"screen:{s['id']}") for s in mine])
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
                    w.para([("; ".join(mails), ""), ("  ", ""), (short(refs.get("section:notifications", "")), "ref", "section:notifications")])
                # The decisions that concern the role, by number: written out under every role they named, the same
                # questions came back two, three and four times in this chapter. They are in full in the decisions
                # chapter, which the line points to.
                needed = [it for it in open_items if mentions(it, r)]
                if needed:
                    blocking = any(it["severity"] == "high" for it in needed)
                    ids = []
                    for k_, it in enumerate(needed):
                        ids += ([(", ", "")] if k_ else []) + [(it["id"], "mono", f"reg:{it['id']}")]
                    w.para([("error" if blocking else "warning", "dot"),
                            (labels["decision_needed" if len(needed) == 1 else "decisions_needed"] + " ", "sec")] + ids
                           + ([("  \u00B7  ", "sec"), (refs["section:open-issues"], "ref", "section:open-issues")] if refs.get("section:open-issues") else []),
                           before=4, after=2)

        # ---------------------------------------------------------------- functional requirements
        elif key == "requirements":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            ch = number.split(".")[0]
            # The ID column fits the longest ID on one line: a narrow one broke "FR-AUTH-001.1" after the dot.
            longest_id = max((len(f"{g['id']}.{len(g['items'])}") for g in groups), default=8)
            id_w = max(2.2, longest_id * w.s["table"] * 0.95 * 0.6 / 72 * 2.54 + 0.6)
            items_all = [i for g in groups for i in g["items"]]
            with_priority = sum(1 for g in groups for i in g["items"] if (isinstance(i, dict) and i.get("priority")) or g.get("priority"))
            priority_column = has_priority and with_priority * 2 >= len(items_all)
            order = {sc["id"]: n for n, sc in enumerate(spec["screens"])}
            screen_order = lambda sid: order.get(sid, len(order))
            # A group that lists many screens and none on its items printed every screen on every item: the
            # reader could not tell which screen an item is about.
            broad = [g["id"] for g in groups if len(g.get("screens") or []) > 2
                     and len(g["items"]) > 1 and not any(isinstance(i, dict) and i.get("screens") for i in g["items"])]
            if broad and has_screens:
                notes.append(f"{', '.join(broad)} list{'s' if len(broad) == 1 else ''} several screens and none of {'its' if len(broad) == 1 else 'their'} "
                             "items says which it is about, so every item shows all of them: give an item its own `screens` "
                             "(`{text, screens: [id]}`) to show only the screens it is about")
            for gi, g in enumerate(groups, 1):
                w.heading(f"{ch}.{gi} {fill(g['title'], g['id'])}", 2, key=f"req:{g['id']}")
                w.para([(g["id"], "mono")], after=4, keep=True)
                header = ["ID", "Requirement"] + (["Priority"] if priority_column else []) + (["Screen"] if has_screens else [])
                widths = ([id_w, tw - id_w - (1.9 if priority_column else 0) - (1.9 if has_screens else 0)]
                          + ([1.9] if priority_column else []) + ([1.9] if has_screens else []))
                rows = []
                for i, item in enumerate(g["items"], 1):
                    d = item if isinstance(item, dict) else {"text": item}
                    text = fill(d["text"], f"{g['id']}.{i}")  # also warns when it mentions the mock-up
                    cell = [(text, "")]
                    if d.get("tbc"):
                        tbc = str(d["tbc"]).strip()
                        cell += [("\n", ""), ("warning", "dot"), (labels["decision_needed"] + " ", "sec"),
                                 (tbc, "mono", f"reg:{tbc}") if REGISTER_ID.fullmatch(tbc) else (tbc, "mono")]
                    # In the order the screens come in the document, each once: an item's own `screens` when it
                    # has them, else its group's.
                    iscreens = [(short(refs.get(f"screen:{sid}")), f"screen:{sid}")
                                for sid in sorted(dict.fromkeys(d.get("screens") or g.get("screens") or []), key=screen_order)
                                if refs.get(f"screen:{sid}")]
                    row = [[(f"{g['id']}.{i}", "mono")], cell]
                    pr = d.get("priority") or g.get("priority")
                    if priority_column:
                        row.append([(pr, "tag")] if pr else "")
                    elif pr:  # a column for one or two priorities was a column of blanks: shown after the text
                        cell[1:1] = [(" ", ""), (pr, "tag")]
                    if has_screens:
                        row.append(link_list(iscreens))
                    rows.append(row)
                t = w.table(header, rows, widths)
                for i in range(1, len(g["items"]) + 1):  # each requirement is a place a decision can point to
                    w.bookmark(t.rows[i].cells[0].paragraphs[0], f"reqitem:{g['id']}.{i}")

        # ---------------------------------------------------------------- screens
        elif key == "screens":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            w.lead(fill(bp["mockup_intro"]))
            ch = number.split(".")[0]
            # The contents list chapters and sections on one page. With many screens they ran on to a second page
            # for a few lines: then the screens are listed under their chapter only (each still starts a page,
            # and the requirements by role point to each by number). Their headings look the same either way.
            entries = len(chapters) + len(roles) + len(groups) + len(screens) + 6
            screen_level = 3 if entries > CONTENTS_LINES else 2
            for i, s in enumerate(screens, 1):
                h = w.heading(f"{ch}.{i} {s['title']}", screen_level, key=f"screen:{s['id']}")
                if screen_level == 3:
                    w.look_like_section(h)
                if i > 1 and (fmt.get("layout") or {}).get("screens_new_page", True):
                    h.paragraph_format.page_break_before = True
                w.para([(role_names(s.get("roles") or []), "sec")] + ([(" · " + fill(s["description"], f"screen {s['id']}"), "sec")] if s.get("description") else []), after=8, keep=True)
                if reqs_for_screen.get(s["id"]):
                    # Under the description, before the screenshot: says up front which requirements this screen
                    # covers, and can never end up alone on a page after the screen's tables.
                    w.para([("Requirements · ", "sec")] + link_list([(x, f"req:{x}") for x in reqs_for_screen[s["id"]]], sep=" · "),
                           size=w.s["caption"], after=8, keep=True)
                sshots = by_screen.get(s["id"], [])
                paged = [x for x in sshots if x.get("page") and not x.get("dialog") and not x.get("record")]
                main_role = sshots[0].get("role") if sshots else None
                pending = []
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
                        if "dialog" in shot:  # an extra screenshot from the spec's `screenshots`: say how it differs
                            seen_by = next((r["name"] for r in roles if r["id"] == shot.get("role")), None)
                            parts = ([f"as seen by {seen_by}"] if seen_by and shot.get("role") != main_role else []) + \
                                    ([f"showing record {shot['record']}"] if shot.get("record") else [])
                            cap += (", " + " and ".join(parts)) if parts else ""
                    if cap in captions:
                        warnings.append(f"screen {s['id']}: two figures have the caption '{cap}' "
                                        f"({caption_advice(cap, s, shot, captions[cap])})")
                    captions.setdefault(cap, (s["id"], shot))
                    pending.append((img, cap))
                # Two phone screens in a row share one figure row; anything else has a row of its own.
                placed = []
                while pending:
                    if len(pending) > 1 and w.is_phone(pending[0][0]) and w.is_phone(pending[1][0]):
                        placed.append([pending.pop(0), pending.pop(0)])
                    else:
                        placed.append([pending.pop(0)])
                # A phone on its own leaves half the page empty beside it: its field table, or the columns of its
                # list, go there, so the screen and what describes it share a page. Only when the table is no
                # taller than the page allows; otherwise it goes under the picture as usual.
                beside = None
                last = placed[-1] if placed else None
                side_size = w.s["table"] - 0.5
                side_w = tw - (w.phone_width + 0.8) - 0.35
                side_rows = None
                if last and len(last) == 1 and w.is_phone(last[0][0]) and not s.get("stats"):
                    if s.get("sections"):
                        side_rows = field_rows(s["sections"])
                if side_rows is not None:
                    rows_, group_ = side_rows
                    tallest = w.text_height - w.FIGURE_ROOM
                    if w.table_height(side_table_rows(rows_, group_), side_field_widths(side_w, side_table_rows(rows_, group_)), side_size, group_) <= tallest:
                        beside = lambda width, r_=rows_, g_=group_: side_fields(r_, g_, width, side_size)
                elif last and len(last) == 1 and w.is_phone(last[0][0]) and not s.get("stats") and s.get("list") and s.get("type") != "detail":
                    beside = lambda width: list_tables(s["list"], width, side_size, screen=s)
                for group_ in placed:
                    if len(group_) == 2:
                        w.figure_pair(*group_)
                    elif group_ is last and beside:
                        w.figure_beside(group_[0][0], group_[0][1], beside)
                    else:
                        w.figure(*group_[0])
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
                if s.get("sections") and not beside:
                    rows, group = field_rows(s["sections"])
                    w.table(field_header, rows, field_widths(rows), group_rows=group)
                if s.get("list") and (s.get("type") == "detail" or not s.get("sections")) and not beside:
                    lst = s["list"]
                    if s.get("type") == "detail":
                        w.para([(lst.get("title") or "Related records", "medium")], before=6, after=2, keep=True)
                        w.lead(related_list_words(spec, s, lst))
                    list_tables(lst, tw, screen=s)
                shown = set()
                for b in s.get("buttons", []) or []:
                    d = dialogs.get(b.get("dialog"))
                    if not d or d["id"] in shown or not d.get("fields") or d.get("doc_table", d.get("srs_table")) is False:
                        continue
                    shown.add(d["id"])
                    w.para([(d["title"], "medium")], before=6, after=2, keep=True)
                    rows, group = field_rows([{"fields": d["fields"]}])
                    w.table(field_header, rows, field_widths(rows))

        # ---------------------------------------------------------------- non-functional requirements
        elif key == "nfr":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            if spec.get("nfr"):
                w.table(["Area", "Requirement"], [[[(x["area"], "medium")],
                                                    fill(x["requirement"], f"non-functional requirement {x['area']}")
                                                    if str(x.get("requirement") or "").strip() else to_be_confirmed(x)]
                                                   for x in spec["nfr"]],
                        [4.0, tw - 4.0])
            else:
                w.para([("warning", "dot"), ("To be confirmed: number of users, performance, availability, backup, retention, security and "
                                             f"supported browsers. See {refs.get('section:open-issues', 'the decisions section')}.", "")])

        # ---------------------------------------------------------------- project timeline
        elif key == "timeline":
            tl = spec["timeline"]
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            w.lead(fill(tl.get("intro") or "The high-level plan for the project. Week 1 is the week of the kick-off meeting; "
                                              "calendar dates are set once the kick-off date is confirmed.", "timeline"))
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
            # The scope of work's mandays, line by line: what the client agreed, never the internal estimate.
            # Rates and cost never appear here.
            effort = [it for st in stages for it in st.get("items", []) if "milestone" not in it and "mandays" in it]
            if effort:
                def md(n):
                    return f"{n:g}"
                w.para([(labels["sow_mandays"], "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                total = sum(it["mandays"] for it in effort)
                w.table(["Item", "Activity", "Mandays"],
                        [[[(str(it.get("ref", "")), "mono")], fill(it.get("name", ""), "timeline"), md(it["mandays"])] for it in effort]
                        + [["", [("Total", "medium")], [(md(total), "medium")]]],
                        [1.4, tw - 4.0, 2.6], keep_whole=len(effort) <= 20)
            ms = [it for st in stages for it in st.get("items", []) if "milestone" in it]
            if ms:
                w.para([("Milestones", "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                w.table(["ID", "Milestone", tl.get("unit", "Week"), "Client action"],
                        [[[(str(m["milestone"]), "mono")], fill(m.get("title") or m.get("name", ""), "timeline"),
                          str(m.get("week", m.get("start", ""))), fill(m.get("client_action") or "\u2013", "timeline")] for m in ms],
                        [1.4, 6.0, 1.6, tw - 9.0])
            if tl.get("assumptions"):
                w.para([("Assumptions", "medium")], size=w.s["h3"], before=6, after=3, keep=True)
                w.bullets([fill(a, "timeline, assumptions") for a in tl["assumptions"]])

        # ---------------------------------------------------------------- extra sections
        elif key == "extra":
            extra = next(e for e in spec["extra_sections"] if e["title"] == title and not e.get("appendix"))
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            extra_content(extra)
            if not extra.get("content"):
                w.para(to_be_confirmed(extra))

        # ---------------------------------------------------------------- decisions needed
        elif key == "decisions":
            w.heading(f"{number} {title}", 1, key=chapter_key(key, title))
            if open_items:
                w.lead(fill(bp["open_issues_intro"]))
                impact = {"high": ("error", labels["impact_high"]), "medium": ("warning", labels["impact_medium"]), "low": ("line", labels["impact_low"])}
                rows = []
                for it in open_items:
                    color, word = impact.get(it["severity"], ("line", it["severity"]))
                    ids = where_asked.get(it["id"], [])
                    rows.append([[(it["id"], "mono")], [(it["question"], "")] + ([("  ", "")] + link_list([(x, requirement_key(x)) for x in ids]) if ids else []),
                                 [(color, "dot"), (word, "")], it.get("owner") or names["client_short"], it.get("due") or "–"])
                # The three narrow columns are sized to what they hold, so an impact stays on one line and an
                # owner's name or a date never breaks in the middle of a word. The question takes the rest.
                char_cm = w.s["table"] * 0.56 / 72 * 2.54

                def fit(texts, least, most):
                    return min(most, max(least, max((len(str(t)) for t in texts), default=0) * char_cm + 0.5))

                impact_w = fit([row[2][1][0] + "  " for row in rows], 2.4, 4.2)  # the whole label, with its dot
                owner_w = fit([word for row in rows for word in str(row[3]).split()], 1.9, 3.6)
                due_w = fit([word for row in rows for word in str(row[4]).split()], 1.7, 3.2)
                t = w.table(["ID", "Question", "Impact", "Owner", "Due"], rows,
                            [1.6, tw - 1.6 - impact_w - owner_w - due_w, impact_w, owner_w, due_w])
                for row_, it in zip(t.rows[1:], open_items):
                    w.bookmark(row_.cells[0].paragraphs[0], f"reg:{it['id']}")
            else:
                w.para([("ok", "dot"), ("There are no open decisions in this version.", "")])
            if made_items:
                # The client's answers go on record in the document they sign, not only in the register.
                w.para([(labels["decisions_made"], "medium")], size=w.s["h3"], before=10, after=3, keep=True)
                w.lead(fill(bp.get("decisions_made_intro") or DECISIONS_MADE_INTRO))
                half = (tw - 1.6 - 2.6) / 2
                w.table(["ID", "Question", "Decision", "Agreed in"],
                        [[[(it["id"], "mono")], it.get("question") or it.get("finding", ""),
                          str(it.get("decision") or "").strip() or it["answer"], str(it.get("resolved_in") or "–")]
                         for it in made_items], [1.6, half, half, 2.6])

        # ---------------------------------------------------------------- sign-off
        elif key == "signoff":
            w.heading(title, 1)
            for line in bp["signoff"]:
                w.para(fill(line))
            # What is signed and what is not, in words a client reads without help: the version and its date,
            # the decisions still open (left out of this approval), and how to sign.
            dated = readable_date(P.get("date")).replace(" ", " ")  # the date stays on one line in the card
            n_open = len(open_items)
            still_open = (f"{n_open} decision{'s' if n_open != 1 else ''} still open" if n_open else "No open decisions")
            left_out = (([(labels["not_signed"] + ": see ", "sec"), (f"section {num['decisions']}", "ref", "section:open-issues")]
                         if "decisions" in num else labels["not_signed"]) if n_open else labels["nothing_left_out"])
            w.cards([(f"Version {version}", labels["signing"] + (f" · {dated}" if dated else ""), None),
                     (still_open, left_out, None),
                     ("By hand or digitally", labels["how_to_sign"], None)], value_size=11)
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
        w.heading(f"Appendix {chr(65 + i)}  {extra['title']}", 1, key=f"extra:{extra['title']}")
        extra_content(extra)
        if not extra.get("content"):
            w.para(to_be_confirmed(extra))

    w.unlink_missing()
    out_dir = layout.output_dir(project)
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
    layout.snapshots_dir(project).mkdir(parents=True, exist_ok=True)
    shutil.copy(spec_file, layout.snapshot(project, version))
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
    if parts_missing:
        print(f"  {len(parts_missing)} PART(S) MISSING - add these to the spec before issuing:")
        for x in parts_missing:
            print("   - " + x)
    done, why = finish_in_word(out)
    try:
        return finish(out, pdf, w, signers, done, why)
    finally:
        if w.trimmed_dir:
            shutil.rmtree(w.trimmed_dir, ignore_errors=True)


def finish(out, pdf, w, signers, done, why):
    """The PDF's full-size pictures and signing fields, or what to do by hand when Word could not make it."""
    if done:
        sharp, unsharp = sharpen_pdf_pictures(pdf, w.pictures)
        placed = add_signature_fields(pdf, signers)
        print(f"  Table of contents updated, fonts embedded; PDF written to {pdf.name}"
              f" with {placed} of {len(signers)} signing fields"
              + (f" and {sharp} of {len(w.pictures)} pictures at full size" if w.pictures else ""))
        if unsharp:
            print(f"  Pictures: {unsharp}.")
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


def drop_picture_entry(doc, page, name):
    """Remove a picture's entry from a page's resources (the picture itself goes when the file is saved)."""
    holder, path = page.xref, "Resources"
    kind, value = doc.xref_get_key(holder, path)
    if kind == "xref":  # the resources are an object of their own
        holder, path = int(value.split()[0]), ""
    path = f"{path}/XObject" if path else "XObject"
    kind, value = doc.xref_get_key(holder, path)
    if kind == "xref":
        holder, path = int(value.split()[0]), ""
    doc.xref_set_key(holder, f"{path}/{name}" if path else name, "null")


def sharpen_pdf_pictures(pdf_path, pictures):
    """Put the original pictures back into the PDF, in place of the reduced ones Word exported.

    Word's PDF export brings every picture down to about 200 dots per inch, whatever the document holds, so
    the small text of a screenshot went soft when zoomed. The figures are the wide pictures of the PDF, in
    reading order; each is replaced by the file it was made from. Word keeps two identical pictures once, so
    one picture of the PDF may stand for several figures: it is replaced once, when their files are the same.

    Returns (how many figures now have their full-size picture, why the others do not: "" when all do).
    When the PDF's pictures cannot be matched one for one with the figures, nothing is changed."""
    import hashlib

    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    wide = []  # (page, picture reference, width in pixels, shape) of each figure: logos and icons are smaller
    # By area: a phone screen two to a row is narrower than a wide logo, but far larger.
    is_wide = lambda rect: rect.width * rect.height > 25 * (72 / 2.54) ** 2
    for page in doc:
        # The places of a picture are found by its content, so pictures with the same content (one stored
        # twice, or once and used twice) all report every place: each place is taken once, by one of them.
        alike = {}  # places -> the pictures that report them
        for image in page.get_images(full=True):
            rects = sorted((r for r in page.get_image_rects(image[0]) if is_wide(r)), key=lambda r: (r.y0, r.x0))
            if rects:
                alike.setdefault(tuple((round(r.y0, 1), round(r.x0, 1)) for r in rects), (rects, []))[1].append(image)
        on_page = []
        for rects, images in alike.values():
            for i, rect in enumerate(rects):
                image = images[i % len(images)]
                on_page.append((round(rect.y0 / 4), rect.x0, page.number, image[0], image[2], rect.width / rect.height))
        wide += sorted(on_page)
    unmatched = "the pictures could not be matched to the figures, so the PDF keeps Word's reduced pictures"
    if len(wide) != len(pictures):
        doc.close()
        return 0, f"the PDF has {len(wide)} wide pictures for {len(pictures)} figures: {unmatched}"
    uses = {}  # picture reference -> [(page, width in pixels, shape, figure file)], in reading order
    for (_, _, page_no, xref, pixels, shape), picture in zip(wide, pictures):
        uses.setdefault(xref, []).append((page_no, pixels, shape, Path(picture)))

    def content(path):
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return str(path)

    if any(len({content(p) for *_, p in used}) > 1 for used in uses.values()):
        doc.close()  # one picture in the PDF for figures that differ: the order is not the figures' order
        return 0, unmatched
    replaced, other_shape, not_larger, unreadable = 0, 0, 0, 0
    for xref, used in uses.items():
        page_no, pixels, shape, picture = used[0]
        try:
            original = pymupdf.Pixmap(str(picture))
        except Exception:
            unreadable += len(used)
            continue
        if abs(original.width / original.height - shape) >= 0.03 * shape:  # a wrong match would distort
            other_shape += len(used)
            continue
        if original.width <= pixels:
            not_larger += len(used)
            continue
        if original.alpha:  # a screenshot has nothing see-through: without it the PDF is smaller
            original = pymupdf.Pixmap(original, 0)
        page = doc[page_no]
        names_before = {image[7] for image in page.get_images(full=True)}
        page.replace_image(xref, pixmap=original)  # every place that shows this picture gets the new one
        # The library adds the new picture to the page under a name of its own and copies it over the
        # old one, leaving that extra entry behind: every picture would be in the file twice.
        for image in page.get_images(full=True):
            if image[7] not in names_before:
                drop_picture_entry(doc, page, image[7])
        replaced += len(used)
    pictures_ = lambda n: f"{n} picture{'s' if n != 1 else ''}"
    why = "; ".join(x for x in (
        f"{pictures_(other_shape)} did not match the shape of {'its' if other_shape == 1 else 'their'} figure, "
        "so the PDF keeps Word's reduced version" if other_shape else "",
        f"{pictures_(not_larger)} {'was' if not_larger == 1 else 'were'} already as sharp as the original" if not_larger else "",
        f"{pictures_(unreadable)} could not be read from the screenshots folder" if unreadable else "") if x)
    if replaced:
        tmp = pdf_path.with_suffix(".sharp.pdf")
        doc.save(str(tmp), garbage=3, deflate=True)
        doc.close()
        tmp.replace(pdf_path)
    else:
        doc.close()
    return replaced, why


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


def utf8_console():
    """Print "●", "–" and every other character as they are: a Windows console or pipe may otherwise use an
    old code page, where they stop the run or come out as "?" or "�". Messages to stderr (sys.exit) as well."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    utf8_console()
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(sys.argv[1])
    except Exception:
        pass
