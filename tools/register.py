"""Project register: add and update items, validate register.json and render register.xlsx for the BA.

Usage:
    python -I tools/register.py add      projects/<slug> --file <items.json> [--check]
    python -I tools/register.py add      projects/<slug> [--check]  < items.json   (items on standard input)
    python -I tools/register.py similar  projects/<slug> "<question or finding>" [--top 5]
    python -I tools/register.py update   projects/<slug> R-001 [R-002 ...] --set field=value [--set field=value ...]
    python -I tools/register.py render   projects/<slug> [--overwrite] [--from "<returned register.xlsx>"]
    python -I tools/register.py validate projects/<slug>
    python -I tools/register.py next-id  projects/<slug>

register.json is in the project's _blueprint folder and register.xlsx is "Questions and fixes register.xlsx" at
the top of the project (in a project not yet moved to the new folder layout: register.json and register.xlsx
at the top). Below, both are called by their short names.

add takes one item or a list of items (JSON, UTF-8) from a file or standard input. It gives each the next
free id (an id in the input is ignored: ids are never chosen by hand), fills raised with today and status
with open where they are missing, and checks every item with the same rules as validate. One bad item
stops the whole batch and nothing is written. Before writing it lists the existing items each new one
may duplicate (by the words of its question and finding); it still writes them, unless --check is given:
then it only checks and reports, and writes nothing. It prints the ids given.

similar lists the existing items closest to a question or finding, to check a candidate before adding it.

update changes fields of existing items: --set status=resolved --set answer="..." --set resolved_in="...".
Unknown fields and values not allowed are refused, and nothing is written. An empty value (--set owner=)
removes an optional field. An answer on an open or asked item moves it to answered, as in Excel, unless
--set status is given too.

add and update write register.json only. Run render afterwards for the Excel file.

render writes register.xlsx from register.json, and beside it "Questions for the client.xlsx": the client
items alone, the only register file to send (register.xlsx has internal sheets). First it takes over what was typed into the existing
register.xlsx since it was written: a client's answer (Client response, Answer / decision) or a changed
Status. Those go into register.json, so they are not lost when the Excel file is written again. When
Excel and register.json both changed the same thing, it stops and says so; --overwrite writes the file
from register.json regardless and drops what was typed in Excel.

--from also takes over a copy of the register that came back from the client (the file sent to them, with
their answers in Client response or a Status changed), after the project's own register.xlsx and by the
same rules: what the client changed since that copy was written goes into register.json, and an item that
was also changed here since then stops it, naming both values. The returned file is only read; keep it
(file it into the client documents with project.py file). A copy without the hidden note of what it held (made by an older
Blueprint, or pasted into a new workbook) gives only the answers to items that have none yet.

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
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout  # noqa: E402  (where everything is in a project folder)

TYPES = {"question", "gap", "contradiction", "assumption", "decision", "fix"}
AUDIENCES = {"client", "internal"}
SEVERITIES = {"high", "medium", "low"}
STATUSES = {"open", "asked", "answered", "resolved", "wont-fix"}
STAGES = {"sow", "workshop-1", "mockup", "workshop-2", "requirements-draft", "requirements-final", "development", "uat",
          "srs-draft", "srs-final"}  # the last two are the names used before 0.4.0
REQUIRED = ["id", "type", "audience", "severity", "category", "stage", "source", "finding", "status", "raised"]
FIELDS = ["id", "type", "audience", "severity", "category", "stage", "source", "finding", "question", "recommendation",
          "effort_impact", "status", "answer", "raised", "resolved_in", "owner", "due"]  # every field, in the order written
EFFORTS = {"none", "low", "medium", "high"}
DUPLICATE = 0.5  # similarity from which add names an existing item as a likely duplicate
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
RENDERED = "_rendered"  # a hidden sheet: the status and answer of every item as the file was written
EDITABLE = {"Status": "status", "Client response": "answer", "Answer / decision": "answer"}  # column -> field
# The team's words: never in what a client item says (render warns before the client's file is sent).
INTERNAL_WORDS = re.compile(r"\b(man-?days?|day rates?|rate card|building blocks?|BB-\d+|effort impact|internal fix(es)?)\b", re.I)


def text(value):
    return "" if value is None else str(value).strip()


# ---------------------------------------------------------------- readable references
# An item's `source` is the reviewer's note of where something was found, in shorthand: "SRS v1.0 §2.1/§2.2
# Loan Request Form; 4.3.1 (p31); Figure 5 (p30)". The Excel file shows it as the document, said once, and
# each place on a line of its own in plain words: "Section 2.1, Section 2.2 Loan Request Form", "Section
# 4.3.1 · page 31". register.json keeps the note as written; a note in a style these rules do not know is
# shown as it is.
DOC_NAME = re.compile(r"^((?:[A-Za-z][\w&\- ]{0,30}?\s)?v\d+(?:\.\d+)*)(?=[\s,;:]|$)")


def readable_place(part):
    p = part.strip().strip(",")
    p = re.sub(r"\(\s*pp?\.?\s*(\d+)\s*[-–]\s*(\d+)\s*\)", r"· pages \1–\2", p)
    p = re.sub(r"\(\s*pp?\.?\s*(\d+)\s*\)", r"· page \1", p)
    p = re.sub(r"\bpp?\.?\s?(\d+)\s*[-–]\s*(\d+)\b", r"pages \1–\2", p)
    p = re.sub(r"\bp\.?\s?(\d+)\b", r"page \1", p)
    p = re.sub(r"\(([^()]*?),\s*page (\d+)\)", r"(\1) · page \2", p)
    p = re.sub(r"§\s*", "Section ", p)
    p = re.sub(r"\bsection\b", "Section", p)
    p = re.sub(r"\s*/\s*(?=Section )", ", ", p)
    p = re.sub(r"^(\d+(?:\.\d+)+[a-z]?)\b", r"Section \1", p)
    p = re.sub(r"(?<!comment )(?<!comments )(?<!, )(?<!and )\b(FB-\d+)\b", r"comment \1", p)
    p = re.sub(r"'([^']{30})[^']{8,}'", r"'\1…'", p)
    return re.sub(r"\s{2,}", " ", p).strip()


def readable_reference(source):
    """(document, places on separate lines) for the Excel file, from an item's `source` note."""
    src = text(source)
    m = DOC_NAME.match(src)
    doc, rest = (m.group(1).strip(), src[m.end():]) if m else ("", src)
    places = [readable_place(x) for x in re.split(r"\s*;\s*", rest) if x.strip(" ,")]
    return doc, "\n".join(places)


# What the client reads in the Where column: the places as above, without the team's own references. A mock-up
# comment's id (FB-009) means nothing to the client, and a spec id ("dialog pickup-dialog") names a part of the
# spec they never see: it becomes the title the mock-up shows ("Pick up dialog").
COMMENT_IDS = re.compile(r"\b(?:mock-up\s+)?(comments?)\s+FB-\d+(?:(?:\s*,\s*|\s+and\s+)(?:comment\s+)?FB-\d+)*", re.I)
SPEC_ID = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+"  # how spec ids are written: lower-case words joined by hyphens
# References of the team's own that should never reach the client (render warns about a client item whose Where
# still has one): mock-up comments, building blocks, gap patterns, other work and estimate lines; and the ids
# of the spec (spec_ids), which these cannot tell from words like "e-mail".
INTERNAL_REFS = re.compile(r"\b(?:FB|BB|GP|OW)-\d+\b|\bL\d{2,}\b")


def load_spec(project):
    try:
        import yaml

        spec = yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8")) or {}
    except Exception:  # no spec yet, or one that cannot be read: the ids are shown as written
        return {}
    return spec if isinstance(spec, dict) else {}


def spec_titles(spec):
    """{spec id: (kind, title)} for a spec's screens and dialogs."""
    out = {}
    for kind, key in (("screen", "screens"), ("dialog", "dialogs")):
        for part in spec.get(key) or []:
            if isinstance(part, dict) and part.get("id") and part.get("title"):
                out[str(part["id"])] = (kind, str(part["title"]).strip())
    return out


def spec_ids(node, out=None):
    """Every id in a spec written the way spec ids are (screens, dialogs, roles, statuses, fields ...)."""
    out = set() if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("id"), str) and re.fullmatch(SPEC_ID, node["id"]):
            out.add(node["id"])
        for value in node.values():
            spec_ids(value, out)
    elif isinstance(node, list):
        for value in node:
            spec_ids(value, out)
    return out


def internal_ref(where, ids):
    """The first reference of the team's own left in a client item's Where, or None."""
    m = INTERNAL_REFS.search(where)
    if m:
        return m.group(0)
    return next((x for x in re.findall(rf"(?<![\w-]){SPEC_ID}(?![\w-])", where) if x in ids), None)


def client_place(place, titles):
    """One place of an item's Where as the client reads it (see COMMENT_IDS)."""
    p = COMMENT_IDS.sub(lambda m: "mock-up " + m.group(1).lower(), place)
    p = re.sub(r"\bFB-\d+\b", "mock-up comment", p)
    p = re.sub(r"\b(?:mock-up\s+)+mock-up\b", "mock-up", p, flags=re.I)

    def title(sid):
        kind, name = titles[sid]
        return name if name.lower().endswith(kind) else f"{name} {kind}"
    p = re.sub(r"\b(?:screen|dialog)\s+([a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])",
               lambda m: title(m.group(1)) if m.group(1) in titles else m.group(0), p)
    p = re.sub(rf"(?<![\w-])({SPEC_ID})(?![\w-])", lambda m: title(m.group(1)) if m.group(1) in titles else m.group(0), p)
    return re.sub(r"\s{2,}", " ", p).strip()


def client_where(source, titles):
    """The Where column of the client's sheets, from an item's `source` note."""
    return "\n".join(client_place(x, titles) for x in readable_reference(source)[1].split("\n"))


def excel_edits(project, reg, path=None):
    """What was typed into register.xlsx (or the returned copy at `path`) since it was written:
    ({(id, field): value}, conflicts).

    The hidden sheet says what each cell held when the file was written, so an edit made in Excel can be
    told from a change made in register.json since. A file written by an older Blueprint has no such
    sheet; there the one safe sign of an edit is an answer in Excel where the register has none."""
    from openpyxl import load_workbook

    returned = path is not None
    path = Path(path) if returned else layout.register_xlsx(project)
    if not path.exists():
        if returned:
            sys.exit(f"No file at {path}. Nothing was written.")
        return {}, []
    try:
        wb = load_workbook(path)
    except Exception as e:
        if returned:
            sys.exit(f"Cannot read {path} as an Excel register ({type(e).__name__}). Nothing was written.")
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
    save(project, reg)
    return done


def load(project):
    path = layout.register_json(project)
    if not path.exists():
        sys.exit(f"No register at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save(project, reg):
    """Write register.json whole or not at all: into a temporary file next to it, then put in its place."""
    path = layout.register_json(project)
    fd, tmp = tempfile.mkstemp(prefix=".register-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except PermissionError:
        Path(tmp).unlink(missing_ok=True)
        sys.exit(f"Cannot write {path}: another program has it open. Close it and run this again.")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def register_bytes(project):
    """register.json as it is now (None when there is none), for put_back after a step that failed half-way."""
    path = layout.register_json(project)
    return path.read_bytes() if path.exists() else None


def put_back(project, before):
    """Put register.json back as register_bytes found it, in one step."""
    path = layout.register_json(project)
    if before is None:
        path.unlink(missing_ok=True)
        return
    fd, tmp = tempfile.mkstemp(prefix=".register-", suffix=".tmp", dir=path.parent)
    with os.fdopen(fd, "wb") as f:
        f.write(before)
    os.replace(tmp, path)


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


def field_errors(it, where, keys=None):
    """The rules add and update apply on top of validate: known fields, text values, effort and dates."""
    errors = []
    for key in (it if keys is None else keys):
        if key not in FIELDS:
            errors.append(f"{where}: unknown field '{key}' (fields: {', '.join(FIELDS)})")
        elif it.get(key) is not None and not isinstance(it[key], str):
            errors.append(f"{where}: {key} must be text, not {json.dumps(it[key], ensure_ascii=False)}")
    effort = it.get("effort_impact")
    if isinstance(effort, str) and effort and effort not in EFFORTS and (keys is None or "effort_impact" in keys):
        errors.append(f"{where}: effort_impact '{effort}' not in {sorted(EFFORTS)}")
    for key in ("raised", "due"):
        value = it.get(key)
        if isinstance(value, str) and value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) and (keys is None or key in keys):
            errors.append(f"{where}: {key} '{value}' is not a date (YYYY-MM-DD)")
    return errors


def put(it, key, value):
    """Set a field; a new one goes in its documented place among the fields the item already has."""
    if key in it:
        it[key] = value
        return
    rank, out = FIELDS.index(key), {}
    for k, v in it.items():
        if key not in out and k in FIELDS and FIELDS.index(k) > rank:
            out[key] = value
        out[k] = v
    out.setdefault(key, value)
    it.clear()
    it.update(out)


# ---------------------------------------------------------------------- likely duplicates
STOP = set("""a an the and or nor of to in on for by with at from as is are was were be been being it its this that
these those which what when who whom whose how why where there their they them we our us you your he she his her not no
do does did can could should would will shall may might must has have had if then than so such any all each every other
only also about into per via up out over under more most less very just same""".split())


def stem(word):
    for _ in range(2):
        for suffix in ("ing", "ed", "es", "s", "e"):
            if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= 3:
                word = word[:-len(suffix)]
                break
        else:
            break
    return word


def words(value):
    """The words that carry meaning: lower case, hyphens joined (e-mail, email), common words dropped, crude stems."""
    flat = re.sub(r"(?<=\w)[-'’](?=\w)", "", text(value).lower())
    return {stem(w) for w in re.findall(r"[a-z0-9]+", flat) if len(w) > 1 and w not in STOP}


def dice(a, b):
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def similarity(one, other):
    """How alike two items read, 0 to 1: the best of question against question, finding against finding, and
    both together. A field of fewer than three words is too short to compare on its own."""
    def both(it):
        return words(f"{text(it.get('question'))} {text(it.get('finding'))}")
    scores = [dice(both(one), both(other))]
    for key in ("question", "finding"):
        a, b = words(one.get(key)), words(other.get(key))
        if len(a) >= 3 and len(b) >= 3:
            scores.append(dice(a, b))
    return round(max(scores), 2)


def closest(items, probe, top=5, floor=0.0):
    """The items most like `probe`, best first: [(score, item)], each at least `floor`."""
    scored = [(similarity(probe, it), it) for it in items if isinstance(it, dict)]
    scored = [(s, it) for s, it in scored if s > 0 and s >= floor]
    return sorted(scored, key=lambda pair: (-pair[0], text(pair[1].get("id"))))[:top]


def short(it, width=90):
    line = " ".join((text(it.get("question")) or text(it.get("finding"))).split())
    return line if len(line) <= width else line[:width - 3] + "..."


# ---------------------------------------------------------------------- add and update
def read_items(source):
    """The items to add, from a file, or from standard input when `source` is None or '-'."""
    if source in (None, "-"):
        if sys.stdin is None or sys.stdin.isatty():
            sys.exit("Give the items with --file <items.json>, or on standard input. Nothing was added.")
        raw, where = sys.stdin.buffer.read(), "standard input"
    else:
        path = Path(source)
        if not path.is_file():
            sys.exit(f"No file at {path}. Nothing was added.")
        raw, where = path.read_bytes(), str(path)
    try:
        content = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        sys.exit(f"{where} is not UTF-8 text. Save it as UTF-8 and run this again. Nothing was added.")
    if not content.strip():
        sys.exit(f"{where} is empty. Nothing was added.")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        sys.exit(f"{where} is not valid JSON (line {e.lineno}, column {e.colno}: {e.msg}). Nothing was added.")
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        data = data["items"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        sys.exit("Give one item ({...}) or a list of items ([{...}, ...]). Nothing was added.")
    return data


def prepare(reg, batch, today=None):
    """The batch as add would write it: (items, notes, errors). Each item gets the next free id (an id it
    carries is ignored), and raised and status where missing. Nothing may be written while there are errors."""
    today = today or date.today().isoformat()
    first = int(next_id(reg)[2:])
    new, notes, errors = [], [], []
    for n, given in enumerate(batch, 1):
        if not isinstance(given, dict):
            errors.append(f"item {n}: not an item (an item is {{\"type\": ..., \"finding\": ..., ...}})")
            continue
        rid = f"R-{first + len(new):03d}"
        if given.get("id") and given["id"] != rid:
            notes.append(f"item {n}: the id {given['id']} it carried is not used; it is {rid} (add gives the ids)")
        it = {"id": rid}
        for key in sorted((k for k in given if k != "id"), key=lambda k: FIELDS.index(k) if k in FIELDS else len(FIELDS)):
            it[key] = given[key]
        for key, value in (("status", "open"), ("raised", today)):
            if not it.get(key):
                put(it, key, value)
        new.append(it)
        where = f"item {n} ({rid})"
        errors += [where + e[len(rid):] for e in validate({"items": [it]})]
        errors += field_errors(it, where)
    return new, notes, errors


def likely_duplicates(reg, new, floor=DUPLICATE):
    """[(new id, existing item, score)] for each new item that reads like one already in the register, or
    like one earlier in the same batch."""
    pool, found = [it for it in reg.get("items", []) if isinstance(it, dict)], []
    for it in new:
        found += [(it["id"], old, score) for score, old in closest(pool, it, top=3, floor=floor)]
        pool.append(it)
    return found


def update(reg, ids, sets):
    """Apply `field=value` changes to the items `ids`: (changes, errors). Nothing is changed when there are errors."""
    errors, values = [], {}
    for s in sets:
        key, sep, value = s.partition("=")
        key = key.strip()
        if not sep or not key:
            errors.append(f"--set {s}: write it as field=value")
        elif key == "id":
            errors.append("id cannot be changed: ids are never reused")
        elif key not in FIELDS:
            errors.append(f"unknown field '{key}' (fields: {', '.join(f for f in FIELDS if f != 'id')})")
        else:
            values[key] = value.strip()
    items = {it.get("id"): it for it in reg.get("items", []) if isinstance(it, dict)}
    missing = [f"{rid}: no such item in the register" for rid in ids if rid not in items]
    if missing:
        return [], errors + missing
    changed, changes = {rid: json.loads(json.dumps(items[rid])) for rid in ids}, []
    for rid, it in changed.items():
        for key, value in values.items():
            before = text(it.get(key))
            if value:
                put(it, key, value)
            else:
                it.pop(key, None)
            if before != value:
                changes.append(f"{rid} {key}: {before or '(empty)'} -> {value or '(removed)'}")
        if values.get("answer") and "status" not in values and it.get("status") in ("open", "asked"):
            changes.append(f"{rid} status: {it['status']} -> answered (it has an answer now)")
            it["status"] = "answered"
        errors += validate({"items": [it]}) + field_errors(it, rid, keys=values)
    if not errors:
        for rid, it in changed.items():
            items[rid].clear()
            items[rid].update(it)
    return changes, errors


def render(project, reg, overwrite=False, returned=None):
    """Write register.xlsx. Unless `overwrite`, what was typed into the existing file is taken into the
    register first (and register.json saved), so writing the file again never loses it. This happens here,
    not in the command around it, so that no caller can write the file without it. `returned` is a copy
    that came back from the client: what was typed into it is taken next, by the same rules."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    if not overwrite:
        edits, conflicts = excel_edits(project, reg)
        own = layout.register_xlsx(project).name
        if conflicts:
            print(f"{own} and register.json disagree. Nothing was written:")
            print("\n".join(f"  - {c}" for c in conflicts))
            print("Put the value you want into register.json, then run this again with --overwrite.")
            sys.exit(1)
        if edits:
            print(f"Taken from {own} into register.json:")
            print("\n".join(f"  - {line}" for line in take_excel_edits(project, reg, edits)))
    if returned:
        name = Path(returned).name
        edits, conflicts = excel_edits(project, reg, returned)
        if conflicts:
            print(f"{name} and register.json disagree. {layout.register_xlsx(project).name} was not written:")
            print("\n".join(f"  - {c.replace('Excel has', 'the returned file has')}" for c in conflicts))
            print("Settle each with the BA: record the right value with register.py update (or leave register.json "
                  "as it is), then run this again; a value register.json already holds is not taken again.")
            sys.exit(1)
        if edits:
            print(f"Taken from {name} into register.json:")
            print("\n".join(f"  - {line}" for line in take_excel_edits(project, reg, edits)))
        else:
            print(f"Nothing new in {name}: no answer or status differs from what it held when it was written.")

    import sheets

    # Severity and status as a dot and a coloured word (docs/design-language.md, Spreadsheets): high blocks
    # sign-off, an answered item needs us, an asked one waits on the client.
    sev_tones = {"High": "red", "Medium": "orange", "Low": "grey"}
    status_tones = {"open": "grey", "asked": "accent", "answered": "orange", "resolved": "green", "wont-fix": "grey"}
    internal = "Internal: not for the client"
    items = sorted(reg["items"], key=lambda it: (it["status"] in ("resolved", "wont-fix"),
                                                 SEV_ORDER.get(it["severity"], 9), it["id"]))

    def sheet(ws, columns, rows, fill_in=(), mark=None):
        sheets.setup(ws, [width for _, width, _ in columns], freeze="B2", internal=mark)
        fill_cols = [c for c, (name, _, _) in enumerate(columns, 1) if name in fill_in]
        for c, (name, width, _) in enumerate(columns, 1):
            ws.cell(row=1, column=c, value=name)
        for r, it in enumerate(rows, 2):
            for c, (name, _, key) in enumerate(columns, 1):
                value = key(it) if callable(key) else it.get(key, "")
                ws.cell(row=r, column=c, value=value)
        sheets.header(ws, 1, len(columns), fill_in=fill_cols)
        sheets.rows(ws, 2, len(rows) + 1, len(columns), fill_in=fill_cols)
        for name, tones in (("Severity", sev_tones), ("Status", status_tones)):
            col = get_column_letter(next(i for i, c in enumerate(columns, 1) if c[0] == name))
            if rows:
                sheets.status(ws, f"{col}2:{col}{len(rows) + 1}", tones)
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
            col = next(i for i, c in enumerate(columns, 1) if c[0] == "Status")
            dv = DataValidation(type="list", formula1='"' + ",".join(sorted(STATUSES)) + '"', allow_blank=False)
            ws.add_data_validation(dv)
            dv.add(f"{get_column_letter(col)}2:{get_column_letter(col)}{len(rows) + 1}")

    cap = lambda k: (lambda it: (it.get(k) or "").capitalize())
    doc_of = lambda it: readable_reference(it.get("source"))[0]
    where_of = lambda it: readable_reference(it.get("source"))[1]
    spec = load_spec(project)
    titles, ids = spec_titles(spec), spec_ids(spec)
    client_where_of = lambda it: client_where(it.get("source"), titles)
    client_cols = [
        ("ID", 8, "id"), ("Severity", 10, cap("severity")), ("Document", 12, doc_of), ("Where", 34, client_where_of),
        ("Observation", 55, "finding"), ("Question for client", 55, "question"),
        ("Our recommendation", 40, "recommendation"), ("Client response", 45, "answer"),
        ("Status", 12, "status"), ("Raised", 12, "raised"),
    ]
    internal_cols = [
        ("ID", 8, "id"), ("Severity", 10, cap("severity")), ("Type", 13, "type"), ("Category", 12, "category"),
        ("Document", 12, doc_of), ("Where", 34, where_of), ("Finding", 60, "finding"),
        ("Fix / recommendation", 50, "recommendation"), ("Effort impact", 12, "effort_impact"), ("Status", 12, "status"),
        ("Raised", 12, "raised"),
    ]
    finding_at = next(i for i, c in enumerate(internal_cols) if c[0] == "Finding")
    all_cols = internal_cols[:finding_at] + [("Audience", 11, "audience"), ("Stage", 12, "stage")] +         internal_cols[finding_at:finding_at + 1] + [("Question for client", 50, "question")] +         internal_cols[finding_at + 1:] + [("Answer / decision", 40, "answer"), ("Resolved in", 16, "resolved_in")]

    wb = Workbook()
    ws = wb.active
    ws.title = "For client"
    sheet(ws, client_cols, [it for it in items if it["audience"] == "client"], fill_in=("Client response",))
    sheet(wb.create_sheet("Internal fixes"), internal_cols, [it for it in items if it["audience"] == "internal"], mark=internal)
    sheet(wb.create_sheet("All items"), all_cols, items, fill_in=("Answer / decision",), mark=internal)

    s = sheets.setup(wb.create_sheet("Summary"), [28, 12], internal=internal, landscape=False, titles=None)
    rows = [(reg.get("project", ""), ""), ("Client: " + reg.get("client", ""), ""), ("", ""), ("Total items", len(items))]
    for label, field in (("By status", "status"), ("By severity", "severity"), ("By audience", "audience"),
                         ("By category", "category")):
        rows += [("", ""), (label, "")]
        rows += sorted(Counter(it[field] for it in items).items())
    for r, (a, b) in enumerate(rows, 1):
        left, right = s.cell(row=r, column=1, value=a), s.cell(row=r, column=2, value=b)
        if r == 1:
            sheets.title(s, "A1", a)
        elif r == 2:
            sheets.label(left)
        elif b == "" and a != "":
            sheets.section(left)
        else:
            sheets.label(left)
            sheets.value(right, bold=a == "Total items")

    # What each item held as this file is written, so the next render can tell what was typed in Excel since.
    kept = wb.create_sheet(RENDERED)
    kept.append(["id", "status", "answer"])
    for it in items:
        kept.append([it["id"], it["status"], it.get("answer") or ""])
    kept.sheet_state = "veryHidden"

    out = layout.register_xlsx(project)
    try:
        wb.save(out)
    except PermissionError:
        sys.exit(f"Cannot write {out}: close it in Excel and run this again.")

    # A client item's own words reach the client as they are: effort, rates and building blocks never should.
    for it in items:
        if it["audience"] != "client":
            continue
        for key in ("finding", "question", "recommendation"):
            m = INTERNAL_WORDS.search(str(it.get(key) or ""))
            if m:
                print(f"  Check {it['id']} before sending: its {key} says '{m.group(0)}', and it goes to the client. "
                      f"Reword it with register.py update {it['id']} --set {key}=\"...\" and render again.")
                break
        ref = internal_ref(client_where_of(it), ids)
        if ref:
            print(f"  Check {it['id']} before sending: its Where says '{ref}', a reference of the team's that the "
                  f"client will not know. Say it in the client's words (a screen's title, a section of the document) "
                  f"with register.py update {it['id']} --set source=\"...\" and render again.")

    # The file to send: the client's items and nothing else, in no sheet, hidden or not. Its hidden note holds
    # only those items, so a copy the client sends back is taken in with --from like the BA's file.
    for_client = [it for it in items if it["audience"] == "client"]
    cwb = Workbook()
    sheet(cwb.active, client_cols, for_client, fill_in=("Client response",))
    cwb.active.title = "For client"
    note = cwb.create_sheet(RENDERED)
    note.append(["id", "status", "answer"])
    for it in for_client:
        note.append([it["id"], it["status"], it.get("answer") or ""])
    note.sheet_state = "veryHidden"
    client_out = layout.client_register_xlsx(project)
    try:
        cwb.save(client_out)
    except PermissionError:
        sys.exit(f"Wrote {out.name}, but cannot write {client_out}: close it in Excel and run this again.")
    return out


COMMANDS = {  # command: (switches, options that take a value, (fewest, most) plain arguments)
    "add": ({"--check"}, {"--file"}, (1, 1)),
    "similar": (set(), {"--top"}, (2, None)),
    "update": (set(), {"--set"}, (2, None)),
    "render": ({"--overwrite"}, {"--from"}, (1, 1)),
    "validate": (set(), set(), (1, 1)),
    "next-id": (set(), set(), (1, 1)),
}


def parse(argv):
    """(command, plain arguments, {option: True or [values]}); the usage for anything else."""
    if not argv or argv[0] not in COMMANDS:
        sys.exit(__doc__)
    cmd, (switches, valued, (fewest, most)) = argv[0], COMMANDS[argv[0]]
    args, opts, rest = [], {}, list(argv[1:])
    while rest:
        a = rest.pop(0)
        name, eq, inline = a.partition("=")
        if a in switches:
            opts[a] = True
        elif a in valued or (eq and name in valued):
            if not eq and not rest:
                sys.exit(__doc__)
            opts.setdefault(name, []).append(inline if eq else rest.pop(0))
        elif a.startswith("--"):
            sys.exit(__doc__)
        else:
            args.append(a)
    if len(args) < fewest or (most is not None and len(args) > most) or (cmd == "update" and "--set" not in opts):
        sys.exit(__doc__)
    return cmd, args, opts


def cmd_add(project, reg, opts):
    files = opts.get("--file", [])
    if len(files) > 1:
        sys.exit("Give one --file. Nothing was added.")
    new, notes, errors = prepare(reg, read_items(files[0] if files else None))
    for line in notes:
        print(f"Note: {line}")
    if errors:
        print("Nothing was added. Fix these and run it again:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    dupes = likely_duplicates(reg, new)
    ids = f"{new[0]['id']}" if len(new) == 1 else f"{new[0]['id']} to {new[-1]['id']}"
    if "--check" in opts:
        print(f"Checked, nothing written: {len(new)} item{'s' * (len(new) != 1)} would be added as {ids}.")
    else:
        reg.setdefault("items", []).extend(new)
        save(project, reg)
        print(f"Added {len(new)} item{'s' * (len(new) != 1)} to register.json: {ids}")
    for it in new:
        print(f"  {it['id']}  {it['audience']:<8} {it['severity']:<6} {short(it, 80)}")
    if dupes:
        print("Possible duplicates: check each, and merge or drop the new item if it is one.")
        for rid, old, score in dupes:
            print(f"  {rid} may be a duplicate of {old.get('id')} (similarity {score:.2f}, {old.get('status')}): {short(old, 70)}")
    existing = validate(reg)
    if existing and "--check" not in opts:
        print("Note: register.json has problems render will refuse; fix them first:")
        print("\n".join(f"  - {e}" for e in existing))
    if "--check" not in opts:
        print(f"Next: python -I tools/register.py render {project}")


def cmd_similar(reg, args, opts):
    probe = " ".join(args)
    try:
        top = int((opts.get("--top") or ["5"])[-1])
    except ValueError:
        sys.exit("--top takes a number, e.g. --top 10")
    found = closest(reg.get("items", []), {"question": probe, "finding": probe}, top=top, floor=0.2)
    if not found:
        print("No existing item reads like it (similarity below 0.20).")
        return
    print(f"Closest items (similarity from 0 to 1; from {DUPLICATE:.2f} up it is likely the same thing):")
    for score, it in found:
        print(f"  {it.get('id')}  {score:.2f}  {text(it.get('status')):<9} {text(it.get('audience')):<8} {short(it)}")


def cmd_update(project, reg, args, opts):
    changes, errors = update(reg, args, opts["--set"])
    if errors:
        print("Nothing was changed:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    if not changes:
        print("Nothing to change: the items already hold those values.")
        return
    save(project, reg)
    print("Changed in register.json:")
    print("\n".join(f"  - {c if len(c) <= 110 else c[:107] + '...'}" for c in changes))
    print(f"Next: python -I tools/register.py render {project}")


def main():
    cmd, args, opts = parse(sys.argv[1:])
    project = args[0]
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
    reg = load(project)
    if cmd == "next-id":
        print(next_id(reg))
        return
    if cmd == "add":
        cmd_add(project, reg, opts)
        return refresh_overview(project)
    if cmd == "similar":
        return cmd_similar(reg, args[1:], opts)
    if cmd == "update":
        cmd_update(project, reg, args[1:], opts)
        return refresh_overview(project)
    errors = validate(reg)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    if cmd == "validate":
        print(f"OK: {len(reg['items'])} items")
        return
    returned = opts.get("--from", [])
    if len(returned) > 1:
        sys.exit("Give one --from file. Nothing was written.")
    out = render(project, reg, overwrite="--overwrite" in opts, returned=returned[0] if returned else None)
    c = Counter(it["audience"] for it in reg["items"])
    print(f"Wrote {out}: {c['client']} client items, {c['internal']} internal fixes (for the team)")
    print(f"Wrote {layout.client_register_xlsx(project)}: the {c['client']} client items alone. Send this one to the client, "
          "never the register itself.")
    refresh_overview(project)


def refresh_overview(project):
    try:  # the project's overview page follows what was just written; it never stops this command
        sys.path.insert(0, str(Path(__file__).resolve().parent)); import overview; overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
