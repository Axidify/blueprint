"""Change requests: check a request against what the client signed, keep the project's CR log, size each
change in building blocks, and write the client's change request note.

Usage:
    python -I tools/change_request.py scope  projects/<slug> "<what the client asked for>" [--top 8] [--version 1.0]
    python -I tools/change_request.py scope  projects/<slug> --file <requests.txt or .json> [--top 8] [--version 1.0]
    python -I tools/change_request.py add    projects/<slug> --file <cr.json>
    python -I tools/change_request.py update projects/<slug> CR-001 [CR-002 ...] --set field=value [--set field=value ...]
    python -I tools/change_request.py ask    projects/<slug> CR-002 [--check]
    python -I tools/change_request.py check  projects/<slug>
    python -I tools/change_request.py render projects/<slug>
    python -I tools/change_request.py note   projects/<slug> CR-001

scope   finds the version the client signed (the latest in output/issued.json, read from its spec snapshot
        output/spec-v<version>.yaml; --version picks another issued version) and lists what in it reads most
        like the request: requirements, screens, dialogs, status rules, scope lines, integrations,
        notifications, non-functional requirements, and from the register the decisions made (items with an
        answer) and the items left open or not to be fixed. Each with its id and section. With nothing
        issued it compares with the current spec and says so. A file holds one request per line (.txt), or a
        JSON list of texts or of {"request": ...}. The list is a lead, never a verdict: it counts shared
        words, so read each cited text before deciding.
add     adds one CR or a list to changes/crs.json: gives each the next CR id (an id in the file is ignored),
        fills raised with today and status with raised where missing, and checks the whole log. One mistake
        and nothing is written.
update  changes fields of CRs: status, sold_md and sold_by (only what the project lead gives), price, weeks,
        verdict, gap_pattern, gap_note, decided_on, notes. An empty value removes the field.
ask     for an Ambiguous CR: adds its client question to the register (the rules of register.py add, with its
        duplicate check) and links the new item to the CR. --check only checks and reports.
check   checks the CR log and sizes every CR that has building-block lines (the estimate's rules: a line
        with no rate is counted, not priced), and shows what the knowledge base's calibration notes say about
        change requests.
render  checks the log and writes "changes/CR log (internal).xlsx" for the team.
note    writes the client's note for a New CR: "changes/CR-001 <title> - change request note.docx". It never
        holds sizing, rates, building blocks or confidence; the price shows only once the project lead has
        entered the sold figure, otherwise "Quotation to follow". For an In scope CR it prints a short
        internal note instead, and for an Ambiguous one it points to ask.

The CR log is internal. changes/crs.json:
{
  "project": "Courier Booking System",
  "platform": "Joget DX",                    for sizing; the spec's platform when left out
  "crs": [
    {
      "id": "CR-001",                        given by add
      "raised": "2026-12-03",                the date the client asked
      "asked_by": "HR manager, during UAT",
      "source": "docs/2026-12-03 UAT defects.xlsx, row 14",          optional: where the request came from
      "title": "Export all applications to Excel",                    client-facing, short
      "request": "HR wants to export every application to Excel.",    client-facing: what was asked
      "stage": "uat",                        development | uat (default development)
      "verdict": "new",                      in-scope | ambiguous | new
      "basis_version": "1.0",                the signed version it was checked against
      "cited": [ {"ref": "Scope: out of scope 1", "section": "section 2", "quote": "..."} ],
                                             what the signed document says, quoted; In scope and New need one
      "reasoning": "...",                    internal: why this verdict
      "why": "...",                          client-facing: why it is a change, in one or two sentences
      "changes": ["A new Export button on My Leave Applications", "..."],   client-facing: what it would change
      "weeks": [1, 2],                       optional, client-facing: impact on the timeline in weeks, when known
      "question": "...",                     Ambiguous: the question for the client (ask puts it in the register)
      "gap_pattern": "GP-04",                a gap pattern id of knowledge/gap-patterns.md, or "new" with "gap_note"
      "lines": [ {"id": "L01", "item": "Excel export", "block": "BB-13", "count": 1, "note": "..."} ],
                                             internal: the estimate's line format (block and count, other, md, percent)
      "assumptions": ["..."],                internal: needed with lines
      "confidence": "low",                   optional: a lower level than the rules give, with "confidence_reason"
      "register": ["R-031"],                 linked register items
      "status": "raised",                    raised | quoted | approved | rejected | built
      "sold_md": 4, "sold_by": "...",        only when the project lead gives them: the mandays sold
      "price": "...",                        optional: the price as the project lead wants the client to read it
      "decided_on": "2026-12-10",            optional
      "notes": "..."                         internal
    }
  ]
}

Client-facing: title, request, asked_by, raised, cited, why, changes, weeks, price (or the sold mandays). Everything
else stays in the log and the Excel file. See docs/change-requests.md.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import estimate  # noqa: E402  (sizing: the same rules and rates as an estimate)
import project as project_tool  # noqa: E402  (what was issued)
import register  # noqa: E402  (the similarity measure, and adding a client question)
import workspace  # noqa: E402

VERDICTS = ("in-scope", "ambiguous", "new")
STATUSES = ("raised", "quoted", "approved", "rejected", "built")
SOLD = ("quoted", "approved", "built")  # a New CR in these has a figure the project lead set
STAGES = ("development", "uat")
REQUIRED = ("id", "raised", "asked_by", "title", "request", "verdict", "status")
KNOWN = set(REQUIRED) | {"source", "stage", "basis_version", "cited", "reasoning", "why", "changes", "weeks", "question",
                         "severity", "recommendation", "effort_impact", "gap_pattern", "gap_note", "lines", "assumptions",
                         "confidence", "confidence_reason", "register", "sold_md", "sold_by", "price", "decided_on", "notes"}
UPDATABLE = ("status", "sold_md", "sold_by", "price", "weeks", "verdict", "gap_pattern", "gap_note", "decided_on", "notes")
CLIENT_TEXT = ("title", "why", "changes", "question")  # written by us for the client: no internal wording in them
INTERNAL_WORDS = re.compile(r"\b(BB-\d+|OW-\d+|GP-\d+|mandays?|man-days?|MD|confidence level|day rate|building blocks?)\b", re.I)
INTERNAL_MARK = "Internal: not for the client"
LOG = Path("changes") / "crs.json"
EXCEL = "CR log (internal).xlsx"
FLOOR = 0.15  # below this a match is noise


def knowledge_dir():
    return estimate.knowledge_dir()


# ---------------------------------------------------------------- what the client signed
def read_yaml(path):
    import yaml

    return json.loads(json.dumps(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}, default=str))


def signed_basis(project, version=None):
    """The version to check a request against: {version, issued, spec, source, warnings, notes}.

    The latest version in output/issued.json, read from its spec snapshot. Without an issued version, or
    without its snapshot, the current spec, with a warning that says why."""
    p = Path(project)
    current_path = p / "spec" / "app.yaml"
    current = read_yaml(current_path) if current_path.exists() else None
    current_version = str(((current or {}).get("project") or {}).get("version") or "")
    issues = project_tool.load_issues(p)
    warnings, notes = [], []
    if version:
        record = next((i for i in issues if str(i["version"]) == str(version).lstrip("v")), None)
        if not record:
            sys.exit(f"v{str(version).lstrip('v')} was never issued. Issued: "
                     f"{', '.join('v' + str(i['version']) for i in issues) or 'nothing yet'}.")
    else:
        record = issues[-1] if issues else None
    if record:
        v = str(record["version"])
        snapshot = p / "output" / f"spec-v{v}.yaml"
        if snapshot.exists():
            spec, source = read_yaml(snapshot), f"output/spec-v{v}.yaml"
        else:
            spec, source = current, "spec/app.yaml"
            warnings.append(f"The spec snapshot of the issued v{v} (output/spec-v{v}.yaml) is missing: comparing with the "
                            f"current spec v{current_version}, which may have changed since v{v} went to the client. "
                            "Check every cited text against the issued document in output/.")
        if current_version and current_version != v:
            notes.append(f"The current spec is v{current_version}: what changed after v{v} was issued is not part of what the "
                         "client signed.")
        if len(issues) > 1 and not version:
            notes.append(f"Issued so far: {', '.join('v' + str(i['version']) for i in issues)}. Using the latest; "
                         "--version picks another.")
    else:
        v, spec, source = current_version, current, "spec/app.yaml"
        warnings.append(f"Nothing has been issued to the client yet (no output/issued.json): comparing with the current spec "
                        f"v{current_version or '?'}, which the client has not signed. Treat every verdict as provisional, and "
                        f"record the version when it goes to the client (python -I tools/project.py issue {p.name}).")
    if spec is None:
        sys.exit(f"{p.as_posix()} has no spec (spec/app.yaml) and nothing issued: there is nothing signed to compare with.")
    return {"version": v, "issued": record, "spec": spec, "source": source, "warnings": warnings, "notes": notes}


def section_numbers(spec):
    """{'screen:<id>': 'section 4.3', 'section:scope': 'section 2', ...} as the document format numbers them now."""
    try:
        import generate_requirements as gen

        return gen.plan_sections(spec, gen.load_format(), [])[1]
    except Exception:  # noqa: BLE001  (a number is a help, never a reason to stop)
        return {}


def as_text(value):
    if isinstance(value, dict):
        return value.get("text") or ""
    return "" if value is None else str(value)


def entries(spec, items, issued_on=None):
    """Everything a request can be compared with: [{kind, ref, where, text, words}]."""
    sec = section_numbers(spec)
    out = []

    def add(kind, ref, where, text, extra=""):
        text = " ".join(str(text).split())
        if text:
            out.append({"kind": kind, "ref": ref, "where": where, "text": text, "words": register.words(f"{text} {extra}")})

    screens = {s.get("id"): s for s in spec.get("screens") or [] if isinstance(s, dict)}
    roles = {r.get("id"): r.get("name", r.get("id")) for r in spec.get("roles") or [] if isinstance(r, dict)}
    status_names = {s.get("id"): s.get("name", s.get("id")) for s in spec.get("statuses") or [] if isinstance(s, dict)}
    for g in spec.get("requirements") or []:
        if not isinstance(g, dict):
            continue
        context = " ".join([str(g.get("title", ""))] + [str(screens.get(s, {}).get("title", "")) for s in g.get("screens") or []])
        where = " ".join(x for x in (sec.get("section:requirements", ""), str(g.get("id", "")), str(g.get("title", ""))) if x)
        for i, item in enumerate(g.get("items") or [], 1):
            add("requirement", f"{g.get('id')}.{i}", where, as_text(item), context)

    def labels(things, key="label"):
        return [str(t.get(key)) for t in things or [] if isinstance(t, dict) and t.get(key)]

    for sid, s in screens.items():
        fields = [f for section in s.get("sections") or [] if isinstance(section, dict) for f in section.get("fields") or []]
        lst = s.get("list") if isinstance(s.get("list"), dict) else {}
        parts = {"fields": labels(fields), "buttons": labels(s.get("buttons")), "columns": labels(lst.get("columns")),
                 "actions": labels(lst.get("actions")) + labels(lst.get("toolbar")), "figures": labels(s.get("stats"))}
        detail = "; ".join(f"{k}: {', '.join(v)}" for k, v in parts.items() if v)
        text = ". ".join(x for x in (str(s.get("title", sid)), str(s.get("description") or "").strip().rstrip("."), detail) if x)
        add("screen", f"screen {sid}", " ".join(x for x in (sec.get(f"screen:{sid}", ""), str(s.get("title", sid))) if x),
            text, " ".join(str(f.get("help", "")) for f in fields if isinstance(f, dict)))
    openers = {}
    for sid, s in screens.items():
        for b in s.get("buttons") or []:
            if isinstance(b, dict) and b.get("dialog"):
                openers.setdefault(b["dialog"], []).append(sid)
    for d in spec.get("dialogs") or []:
        if not isinstance(d, dict):
            continue
        confirm = d.get("confirm") if isinstance(d.get("confirm"), dict) else {}
        text = ". ".join(x for x in (str(d.get("title", "")), str(d.get("message") or ""),
                                     ", ".join(labels(d.get("fields"))), str(confirm.get("label") or "")) if x)
        where = ", ".join(sec.get(f"screen:{s}", "") + " " + str(screens[s].get("title", s)) for s in openers.get(d.get("id"), []))
        add("dialog", f"dialog {d.get('id')}", where.strip() or "dialogs", text)

    def who(value):
        if value is None:
            return "to be confirmed"
        if value in ("all", "none"):
            return value
        return ", ".join(roles.get(r, str(r)) for r in (value if isinstance(value, list) else [value])) or "none"

    for s in spec.get("statuses") or []:
        if not isinstance(s, dict):
            continue
        rules = "; ".join(f"{k}: {who(s.get(k))}" for k in ("edit", "cancel", "delete") if k in s)
        if "next" in s:
            rules += f"; moves to: {', '.join(status_names.get(n, str(n)) for n in s.get('next') or []) or 'nothing (final)'}"
        add("status rule", f"status {s.get('name', s.get('id'))}", sec.get("section:flow", "") + " Process and statuses",
            f"{s.get('name', '')}: {s.get('meaning', '')} {rules}".strip())
    scope = spec.get("scope") if isinstance(spec.get("scope"), dict) else {}
    for part, label in (("in_scope", "in scope"), ("out_of_scope", "out of scope"), ("assumptions", "assumption")):
        for i, line in enumerate(scope.get(part) or [], 1):
            add("scope", f"Scope: {label} {i}", sec.get("section:scope", "Scope and assumptions"), line)
    for x in spec.get("integrations") or []:
        if isinstance(x, dict):
            add("integration", f"integration {x.get('system')}", sec.get("section:integrations", "integrations"),
                ". ".join(str(x.get(k)) for k in ("system", "purpose", "direction", "notes", "trigger", "data", "on_failure") if x.get(k)))
    for n in spec.get("notifications") or []:
        if isinstance(n, dict):
            add("notification", f"notification {n.get('event')}", sec.get("section:notifications", "notifications"),
                ". ".join(str(n.get(k)) for k in ("event", "recipient", "template") if n.get(k)))
    for n in spec.get("nfr") or []:
        if isinstance(n, dict):
            add("non-functional", f"NFR {n.get('area')}", sec.get("section:nfr", "non-functional requirements"),
                f"{n.get('area', '')}: {n.get('requirement', '')}")
    for it in items:
        if not isinstance(it, dict):
            continue
        later = f", raised after the version was issued on {issued_on}" if issued_on and str(it.get("raised", "")) > str(issued_on) else ""
        status = it.get("status")
        if it.get("answer") and status in ("answered", "resolved"):
            kind, text = "decision", f"{it.get('question') or it.get('finding')} Answer: {it['answer']}"
        elif status in ("open", "asked"):
            kind, text = "open item", it.get("question") or it.get("finding")
        elif status == "wont-fix":
            kind, text = "won't fix", it.get("question") or it.get("finding")
        else:
            continue
        where = f"register, {status}" + (f", {it['resolved_in']}" if it.get("resolved_in") else "") + later
        add(kind, str(it.get("id")), where, text, it.get("finding", ""))
    return out


def score(probe, entry):
    """How much of the request an entry covers, 0 to 1: half the register's Dice measure, half the share of the
    request's words the entry has. Dice alone punishes a long screen description for its length."""
    if not probe or not entry:
        return 0.0
    return round(0.5 * register.dice(probe, entry) + 0.5 * len(probe & entry) / len(probe), 2)


def lookup(project, request, top=8, version=None, basis=None):
    """(basis, [(score, entry)]) for one request, best first."""
    basis = basis or signed_basis(project, version)
    pool = entries(basis["spec"], register.load(project).get("items", []) if (Path(project) / "register.json").exists() else [],
                   (basis["issued"] or {}).get("date"))
    probe = register.words(request)
    found = [(score(probe, e["words"]), e) for e in pool]
    found = sorted([(s, e) for s, e in found if s >= FLOOR], key=lambda pair: -pair[0])
    return basis, found[:top]


def read_requests(path):
    path = Path(path)
    if not path.is_file():
        sys.exit(f"No file at {path}.")
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
        except ValueError as e:
            sys.exit(f"{path.name} is not valid JSON: {e}")
        data = data if isinstance(data, list) else [data]
        return [str(x.get("request") if isinstance(x, dict) else x).strip() for x in data if x]
    return [line.strip(" -*\t") for line in raw.splitlines() if line.strip(" -*\t")]


# ---------------------------------------------------------------- the CR log
def log_path(project):
    return Path(project) / LOG


def load_log(project):
    path = log_path(project)
    if not path.exists():
        spec_file = Path(project) / "spec" / "app.yaml"
        P = (read_yaml(spec_file).get("project") or {}) if spec_file.exists() else {}
        return {"project": P.get("name") or Path(project).name, "platform": P.get("platform", ""), "crs": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path} is not valid JSON: {e}")


def save_log(project, log):
    """Write crs.json whole or not at all."""
    path = log_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".crs-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(log, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except PermissionError:
        Path(tmp).unlink(missing_ok=True)
        sys.exit(f"Cannot write {path}: another program has it open. Close it and run this again.")
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def next_id(log):
    nums = [int(m.group(1)) for cr in log.get("crs", []) if isinstance(cr, dict) and (m := re.fullmatch(r"CR-(\d+)", str(cr.get("id", ""))))]
    return f"CR-{(max(nums) if nums else 0) + 1:03d}"


def platform_of(project, log):
    if log.get("platform"):
        return log["platform"]
    spec_file = Path(project) / "spec" / "app.yaml"
    return ((read_yaml(spec_file).get("project") or {}).get("platform") or "") if spec_file.exists() else ""


def weeks_pair(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (float(value), float(value)) if value >= 0 else None
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return (float(value[0]), float(value[1])) if 0 <= value[0] <= value[1] else None
    return None


def weeks_text(weeks):
    low, high = weeks
    return estimate.rng(low, high, unit=" week" if round(high, 1) == 1 else " weeks")


def size(cr, project, platform, kdir):
    """The CR's lines worked out by the estimate's rules: (result or None, errors)."""
    if not cr.get("lines"):
        return None, []
    est = {"project": f"{cr.get('id')} {cr.get('title', '')}", "platform": platform, "date": cr.get("raised"),
           "basis": f"{cr.get('id')} against v{cr.get('basis_version', '?')}", "basis_kind": "requirements-document",
           "lines": cr["lines"], "assumptions": cr.get("assumptions") or []}
    for key in ("confidence", "confidence_reason"):
        if cr.get(key):
            est[key] = cr[key]
    # compute() lowers the confidence for open high-severity register items of the project; those belong to the
    # project's estimate, not to one change. Point it at the changes folder, which has no register.
    res, errors = estimate.compute(est, Path(project) / "changes", kdir)
    errors = [e.replace("missing assumptions", "assumptions are needed with lines").replace("missing platform",
              "no platform: set it at the top of crs.json or in the spec") for e in errors]
    return (None if errors else res), errors


def calibration_notes(kdir):
    """(every calibration note in building-blocks.md, the ones about change requests or small changes)."""
    path = Path(kdir) / "building-blocks.md"
    if not path.exists():
        return [], []
    lines, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("calibration")
            continue
        text = line.strip().lstrip("-* ").strip()
        if inside and text and not re.fullmatch(r"none( yet)?\.?", text, re.I):
            lines.append(text)
    return lines, [l for l in lines if re.search(r"\bCRs?\b|change requests?|\bsmall\b", l, re.I)]


def gap_pattern_ids(kdir):
    path = Path(kdir) / "gap-patterns.md"
    if not path.exists():
        return None
    return set(re.findall(r"^##\s+(GP-\d+)\b", path.read_text(encoding="utf-8"), re.M))


def check_log(log, project, kdir=None):
    """(errors, warnings, sizing {CR id: result}) for the whole log."""
    kdir = kdir or knowledge_dir()
    errors, warnings, sizing = [], [], {}
    crs = log.get("crs")
    if not isinstance(crs, list):
        return ["crs must be a list"], [], {}
    reg_ids = {it.get("id") for it in (register.load(project).get("items", []) if (Path(project) / "register.json").exists() else [])}
    patterns = gap_pattern_ids(kdir)
    issues = project_tool.load_issues(Path(project))
    latest = str(issues[-1]["version"]) if issues else None
    platform = platform_of(project, log)
    seen = set()
    for n, cr in enumerate(crs, 1):
        if not isinstance(cr, dict):
            errors.append(f"CR #{n}: not a CR")
            continue
        where = cr.get("id") or f"CR #{n}"
        for key in REQUIRED:
            if cr.get(key) in (None, "", []):
                errors.append(f"{where}: missing {key}")
        unknown = sorted(set(cr) - KNOWN)
        if unknown:
            errors.append(f"{where}: unknown field{'s' * (len(unknown) > 1)} {', '.join(unknown)}")
        if cr.get("id") and not re.fullmatch(r"CR-\d{3,}", str(cr["id"])):
            errors.append(f"{where}: an id is CR-001, CR-002 ...")
        if cr.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(cr.get("id"))
        for key in ("raised", "decided_on"):
            if cr.get(key) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(cr[key])):
                errors.append(f"{where}: {key} '{cr[key]}' is not a date (YYYY-MM-DD)")
        verdict, status = cr.get("verdict"), cr.get("status")
        if verdict and verdict not in VERDICTS:
            errors.append(f"{where}: verdict '{verdict}' not in {list(VERDICTS)}")
        if status and status not in STATUSES:
            errors.append(f"{where}: status '{status}' not in {list(STATUSES)}")
        if cr.get("stage") and cr["stage"] not in STAGES:
            errors.append(f"{where}: stage '{cr['stage']}' not in {list(STAGES)}")
        cited = cr.get("cited")
        if cited is not None and (not isinstance(cited, list) or not all(isinstance(c, dict) and c.get("ref") and c.get("quote") for c in cited)):
            errors.append(f"{where}: cited is a list of {{ref, section, quote}}, each with a ref and the quoted text")
            cited = []
        if verdict in ("in-scope", "new") and not cited:
            errors.append(f"{where}: {verdict} needs what the signed document says (cited: ref and quote), read in the "
                          "document itself, not taken from a similarity score")
        if verdict == "new":
            for key, what in (("why", "why it is a change, for the client"), ("changes", "what it would change (a list)")):
                if not cr.get(key):
                    errors.append(f"{where}: a New CR needs {key}: {what}")
            if cr.get("changes") is not None and (not isinstance(cr["changes"], list) or not all(isinstance(c, str) and c.strip() for c in cr["changes"])):
                errors.append(f"{where}: changes is a list of sentences")
            if not cr.get("gap_pattern"):
                errors.append(f"{where}: a New CR needs a gap_pattern (a GP id, or \"new\" with gap_note): close-project learns from it")
        if verdict == "ambiguous":
            if not cr.get("question"):
                errors.append(f"{where}: an Ambiguous CR needs the question for the client")
            if status != "raised":
                errors.append(f"{where}: an Ambiguous CR stays raised until the client answers; then set its verdict to in-scope or new")
            if not cr.get("register"):
                warnings.append(f"{where}: its question is not in the register yet: python -I tools/change_request.py ask {Path(project).as_posix()} {where}")
        if status in ("quoted", "approved") and verdict != "new":
            errors.append(f"{where}: only a New CR is {status}")
        gp = cr.get("gap_pattern")
        if gp:
            if gp == "new":
                if not cr.get("gap_note"):
                    errors.append(f"{where}: gap_pattern \"new\" needs gap_note: the gap in general terms, without client content")
            elif not re.fullmatch(r"GP-\d+", str(gp)):
                errors.append(f"{where}: gap_pattern '{gp}' is a GP id or \"new\"")
            elif patterns is not None and gp not in patterns:
                errors.append(f"{where}: {gp} is not in knowledge/gap-patterns.md")
        for rid in cr.get("register") or []:
            if rid not in reg_ids:
                errors.append(f"{where}: {rid} is not in the register")
        sold = cr.get("sold_md")
        if sold is not None and (isinstance(sold, bool) or not isinstance(sold, (int, float)) or sold <= 0):
            errors.append(f"{where}: sold_md is the number of mandays sold, above 0")
        if sold is not None and not cr.get("sold_by"):
            errors.append(f"{where}: sold_md needs sold_by: the project lead who set it (a figure is never made up)")
        if verdict == "new" and status in SOLD and sold is None:
            errors.append(f"{where}: a {status} CR needs sold_md and sold_by from the project lead")
        if sold is not None and verdict != "new":
            errors.append(f"{where}: only a New CR is sold")
        if cr.get("weeks") is not None and not weeks_pair(cr["weeks"]):
            errors.append(f"{where}: weeks is a number or [low, high] weeks")
        for key in CLIENT_TEXT:
            values = cr.get(key) if isinstance(cr.get(key), list) else [cr.get(key)]
            for value in values:
                m = INTERNAL_WORDS.search(str(value or ""))
                if m:
                    errors.append(f"{where}: {key} mentions '{m.group(0)}': it goes to the client, who never sees effort, "
                                  "rates, building blocks, gap patterns or confidence")
                    break
        if latest and cr.get("basis_version") and str(cr["basis_version"]) != latest and status == "raised":
            warnings.append(f"{where}: checked against v{cr['basis_version']}, but v{latest} is the latest issued: check it again")
        if verdict == "new" and not cr.get("lines"):
            warnings.append(f"{where}: not sized yet (no building-block lines)")
        res, problems = size(cr, project, platform, kdir)
        errors += [f"{where}: {e}" for e in problems]
        if res:
            sizing[cr.get("id")] = res
    return errors, warnings, sizing


def sized_text(res):
    if not res:
        return "not sized"
    lines, unpriced = res["lines"], res["unpriced"]
    if len(unpriced) == len(lines):
        return f"counted, not priced ({len(lines)} line{'s' * (len(lines) != 1)})"
    text = estimate.rng(*res["total"])
    if unpriced:
        text = (f"priced so far {text}, {len(unpriced)} of {len(lines)} lines not priced" if res["build_unpriced"]
                else f"{text} for the priced lines, {len(unpriced)} not priced")
    return f"{text}, {res['confidence']} confidence"


# ---------------------------------------------------------------- Excel
def render_xlsx(log, sizing, out):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    fill = PatternFill("solid", fgColor="1F3864")
    wrap = Alignment(wrap_text=True, vertical="top")

    def table(ws, columns, rows):
        for c, (name, width) in enumerate(columns, 1):
            cell = ws.cell(row=1, column=c, value=name)
            cell.font, cell.fill, cell.alignment = Font(bold=True, color="FFFFFF"), fill, wrap
            ws.column_dimensions[get_column_letter(c)].width = width
        for r, row in enumerate(rows, 2):
            for c, value in enumerate(row, 1):
                ws.cell(row=r, column=c, value=round(value, 2) if isinstance(value, float) else value).alignment = wrap
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
        ws.oddHeader.center.text = INTERNAL_MARK

    crs = [cr for cr in log.get("crs", []) if isinstance(cr, dict)]
    wb = Workbook()
    ws = wb.active
    ws.title = "CR log"
    rows = []
    for cr in crs:
        res = sizing.get(cr.get("id"))
        weeks = weeks_pair(cr.get("weeks"))
        rows.append([cr.get("id"), cr.get("raised"), cr.get("asked_by"), cr.get("title"), cr.get("request"),
                     {"in-scope": "In scope", "ambiguous": "Ambiguous", "new": "New"}.get(cr.get("verdict"), cr.get("verdict")),
                     "\n".join(f"{c.get('ref')}{' (' + c['section'] + ')' if c.get('section') else ''}: \"{c.get('quote')}\""
                               for c in cr.get("cited") or [] if isinstance(c, dict)),
                     cr.get("reasoning", ""), cr.get("gap_pattern", "") + (f": {cr['gap_note']}" if cr.get("gap_note") else ""),
                     cr.get("status"), res["total"][0] if res and len(res["unpriced"]) < len(res["lines"]) else None,
                     res["total"][1] if res and len(res["unpriced"]) < len(res["lines"]) else None, sized_text(res) if cr.get("lines") else "",
                     cr.get("sold_md"), cr.get("sold_by", ""), cr.get("price", ""),
                     weeks_text(weeks) if weeks else "", ", ".join(cr.get("register") or []),
                     f"v{cr['basis_version']}" if cr.get("basis_version") else "", cr.get("notes", "")])
    table(ws, [("ID", 9), ("Raised", 11), ("Asked by", 18), ("Title", 28), ("Request", 45), ("Verdict", 11),
               ("Signed document says", 50), ("Reasoning", 40), ("Gap pattern", 14), ("Status", 10), ("Sized low (MD)", 10),
               ("Sized high (MD)", 10), ("Sizing", 34), ("Sold (MD)", 9), ("Sold by", 16), ("Price", 14), ("Timeline", 12),
               ("Register", 12), ("Checked against", 11), ("Notes", 36)], rows)

    s = wb.create_sheet("Sizing")
    rows = []
    for cr in crs:
        res = sizing.get(cr.get("id"))
        for l in (res or {}).get("lines", []):
            what = l.get("block") or l.get("other") or ("lead developer's figure" if l["kind"] == "md" else "share")
            rows.append([cr.get("id"), l["id"], l["item"], what, l.get("block_name", ""), l.get("count"),
                         estimate.rng(l["rate_low"], l["rate_high"], "") if l.get("rate_low") is not None else "",
                         l["rate_from"], l["low"] if l["priced"] else None, l["high"] if l["priced"] else None, l.get("note", "")])
        if res:
            rows.append([cr.get("id"), "", "Confidence: " + res["confidence"], "", "", None, "", " ".join(res["reasons"]), None, None,
                         "; ".join(cr.get("assumptions") or [])])
    table(s, [("CR", 9), ("Line", 7), ("Item", 30), ("Block", 10), ("Building block", 26), ("Count", 7), ("Rate (MD)", 10),
              ("Rate from", 30), ("Low (MD)", 9), ("High (MD)", 9), ("Note / assumptions", 50)], rows)

    t = wb.create_sheet("Summary")
    t.column_dimensions["A"].width = 40
    t.column_dimensions["B"].width = 14
    co = workspace.company()
    sold = sum(cr.get("sold_md") or 0 for cr in crs if cr.get("status") in ("approved", "built"))
    summary = [(f"Change requests: {log.get('project', '')}", ""), (INTERNAL_MARK, ""), ("", ""), ("Requests logged", len(crs))]
    for label, key, names in (("By verdict", "verdict", VERDICTS), ("By status", "status", STATUSES)):
        counts = Counter(cr.get(key) for cr in crs)
        summary += [("", ""), (label, "")] + [(name, counts.get(name, 0)) for name in names]
    summary += [("", ""), ("By gap pattern (New and Ambiguous)", "")]
    summary += sorted(Counter(cr.get("gap_pattern") or "not mapped" for cr in crs if cr.get("verdict") != "in-scope").items())
    summary += [("", ""), ("Mandays sold, approved or built", sold)]
    if co.get("day_rate") and sold:
        summary.append((f"Value at {(co.get('currency') or '').strip()} {co['day_rate']:,} a day".replace("  ", " "), sold * co["day_rate"]))
    for r, (a, b) in enumerate(summary, 1):
        t.cell(row=r, column=1, value=a).font = Font(bold=(b == "" and a != ""))
        t.cell(row=r, column=2, value=b)
    t.oddHeader.center.text = INTERNAL_MARK
    try:
        wb.save(out)
    except PermissionError:
        sys.exit(f"Cannot write {out}: close it in Excel and run this again.")
    return out


# ---------------------------------------------------------------- the client's note
def find_cr(log, cid):
    cr = next((c for c in log.get("crs", []) if isinstance(c, dict) and c.get("id") == cid), None)
    if not cr:
        sys.exit(f"No {cid} in the CR log. CRs: {', '.join(str(c.get('id')) for c in log.get('crs', []) if isinstance(c, dict)) or 'none'}")
    return cr


def price_text(cr):
    """What the client's note says about the price: only what the project lead entered."""
    if cr.get("price"):
        return str(cr["price"])
    if cr.get("sold_md") and cr.get("sold_by"):
        return f"{estimate.num(cr['sold_md'])} mandays"
    return "Quotation to follow"


def write_note(project, log, cr):
    """The client's change request note, in the company's document format. Returns its path."""
    from docx import Document

    import generate_requirements as gen

    fmt = gen.load_format()
    problems = gen.format_errors(fmt)
    if problems:
        sys.exit("The document format has mistakes:\n  " + "\n  ".join(problems))
    co = workspace.company()
    basis = signed_basis(project, cr.get("basis_version") if cr.get("basis_version") and project_tool.is_issued(Path(project), cr["basis_version"]) else None)
    P = basis["spec"].get("project") or {}
    system = P.get("name") or log.get("project", "")
    doc = Document(str(workspace.asset("document-template.docx")))
    w = gen.Writer(doc, fmt)
    w.setup_styles()
    w.header_footer(f"{system} · Change request {cr['id']}", gen.readable_date(cr["raised"]), f"{co['name']} · {fmt['labels']['confidential']}")
    tw = w.text_width
    w.para([("Change request", "sec")], size=w.s["body"] + 1, after=2)
    w.page_title(str(cr["title"]), after=4)
    w.para([(system, "sec")] + ([(f"  ·  {P['client']}", "sec")] if P.get("client") else []), size=w.s["body"] + 1, after=10)
    weeks = weeks_pair(cr.get("weeks"))
    w.cards([(cr["id"], "Reference", None), (gen.readable_date(cr["raised"]), "Raised", None),
             (weeks_text(weeks) if weeks else "To be confirmed", "Timeline impact", None),
             (price_text(cr), "Price", "accent")], value_size=12)

    w.heading("What was asked", 2)
    w.para(str(cr["request"]), after=4)
    w.para([("Asked by ", "sec"), (str(cr["asked_by"]), ""), (f" on {gen.readable_date(cr['raised'])}", "sec")], after=6)

    w.heading("Why this is a change", 2)
    w.para(str(cr["why"]), after=6)
    issued = basis["issued"]
    signed = (f"The requirements document v{basis['version']}" + (f", issued on {gen.readable_date(issued['date'])}," if issued else "")
              + " says:")
    w.lead(signed)
    w.table(["Reference", "Section", "What it says"],
            [[[(str(c["ref"]), "mono")], str(c.get("section") or "–"), f"“{c['quote']}”"] for c in cr["cited"]],
            [3.6, 2.6, tw - 6.2])

    w.heading("What it would change", 2)
    w.bullets([str(c) for c in cr["changes"]])

    w.heading("Impact on the timeline and price", 2)
    w.kv_table([("Timeline", f"About {weeks_text(weeks)} added to the plan" if weeks else "To be confirmed with the quotation"),
                ("Price", price_text(cr))], [4.4, tw - 4.4])

    w.heading("Your decision", 2)
    w.lead("Please confirm whether we should go ahead with this change. Work on it starts once it is approved; "
           "until then the system is built as the signed document describes.")
    w.table(["", "Name", "Signature", "Date"], [[[("Approved by", "sec")], "", "", ""], [[("For", "sec")], "", "", ""]],
            [3.0, (tw - 3.0) * 0.4, (tw - 3.0) * 0.35, (tw - 3.0) * 0.25])

    out = log_path(project).parent / f"{cr['id']} {project_tool.safe_name(cr['title'])} - change request note.docx"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        doc.save(str(out))
    except PermissionError:
        sys.exit(f"Cannot write {out.name}: close it in Word and run this again.")
    return out


def in_scope_note(cr, basis):
    cited = "; ".join(f"{c.get('ref')}{' (' + c['section'] + ')' if c.get('section') else ''}: “{c.get('quote')}”"
                      for c in cr.get("cited") or [])
    return (f"{cr['id']} {cr['title']}: in scope ({INTERNAL_MARK.lower()}).\n"
            f"  Asked by {cr['asked_by']} on {cr['raised']}: {cr['request']}\n"
            f"  The signed document v{cr.get('basis_version') or basis['version']} already covers it: {cited}\n"
            + (f"  Why: {cr['reasoning']}\n" if cr.get("reasoning") else "")
            + "  Build or fix it as part of the project, at no charge. To answer the client, cite the reference above.")


# ---------------------------------------------------------------- commands
def refresh(project):
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(project)
    except Exception:
        pass


def checked(project, log):
    errors, warnings, sizing = check_log(log, project)
    if errors:
        print("The CR log needs fixing. Nothing was written:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    return warnings, sizing


def cmd_scope(a):
    requests = read_requests(a.file) if a.file else [" ".join(a.request)]
    if not requests or not requests[0]:
        sys.exit("Give the request in quotes, or a file of requests with --file.")
    basis = signed_basis(a.project, a.version)
    issued = basis["issued"]
    print(f"Checked against v{basis['version']}" + (f", issued to {issued['to']} on {issued['date']}" if issued else ", not issued")
          + f" ({basis['source']})")
    for line in basis["warnings"]:
        print(f"Warning: {line}")
    for line in basis["notes"]:
        print(f"Note: {line}")
    for n, request in enumerate(requests, 1):
        _, found = lookup(a.project, request, a.top, basis=basis)
        print(f"\nRequest {n}: {request}")
        if not found:
            print("  Nothing in the signed version reads like it: it may be new, or worded differently. Search the document "
                  "itself before deciding.")
        for s, e in found:
            text = e["text"] if len(e["text"]) <= 240 else e["text"][:237] + "..."
            print(f"  {s:.2f}  {e['kind']:<14} {e['ref']}  [{e['where']}]")
            print(f"        “{text}”")
    print("\nThe score counts shared words; it does not decide scope. Read each cited text in the signed document, then "
          "decide In scope (quote it), Ambiguous (it is silent or left open) or New.")


def cmd_add(a):
    log = load_log(a.project)
    try:
        data = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        sys.exit(f"Cannot read {a.file}: {e}. Nothing was added.")
    batch = data if isinstance(data, list) else [data]
    added = []
    for given in batch:
        if not isinstance(given, dict):
            sys.exit("Give one CR ({...}) or a list of them. Nothing was added.")
        cr = {"id": next_id(log), **{k: v for k, v in given.items() if k != "id"}}
        cr.setdefault("raised", dt.date.today().isoformat())
        cr.setdefault("status", "raised")
        log.setdefault("crs", []).append(cr)
        added.append(cr)
    warnings, sizing = checked(a.project, log)
    save_log(a.project, log)
    print(f"Added to {LOG.as_posix()}: " + ", ".join(f"{cr['id']} ({cr['verdict']}) {cr['title']}" for cr in added))
    for cr in added:
        if cr["id"] in sizing:
            print(f"  {cr['id']} sized: {sized_text(sizing[cr['id']])} (internal)")
    for line in warnings:
        print(f"Note: {line}")
    refresh(a.project)


def parse_value(key, value):
    if value == "":
        return None
    if key == "sold_md":
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            sys.exit(f"sold_md takes a number of mandays, not '{value}'. Nothing was changed.")
    if key == "weeks":
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*", value)
        if not m:
            sys.exit(f"weeks takes a number or a range such as 1-2, not '{value}'. Nothing was changed.")
        low = float(m.group(1))
        return [low, float(m.group(2))] if m.group(2) else low
    return value


def cmd_update(a):
    log = load_log(a.project)
    sets = {}
    for s in a.set:
        key, sep, value = s.partition("=")
        if not sep or key.strip() not in UPDATABLE:
            sys.exit(f"--set {s}: one of {', '.join(UPDATABLE)} as field=value. Nothing was changed.")
        sets[key.strip()] = parse_value(key.strip(), value.strip())
    changes = []
    for cid in a.ids:
        cr = find_cr(log, cid)
        for key, value in sets.items():
            before = cr.get(key)
            if value is None:
                cr.pop(key, None)
            else:
                cr[key] = value
            if before != value:
                changes.append(f"{cid} {key}: {before if before is not None else '(empty)'} -> {value if value is not None else '(removed)'}")
    warnings, _ = checked(a.project, log)
    if not changes:
        print("Nothing to change: the CRs already hold those values.")
        return
    save_log(a.project, log)
    print("Changed in the CR log:")
    print("\n".join(f"  - {c}" for c in changes))
    for line in warnings:
        print(f"Note: {line}")
    refresh(a.project)


def cmd_ask(a):
    log = load_log(a.project)
    cr = find_cr(log, a.id)
    if cr.get("verdict") != "ambiguous":
        sys.exit(f"{a.id} is {cr.get('verdict')}: only an Ambiguous CR becomes a question for the client.")
    if cr.get("register"):
        sys.exit(f"{a.id} is already in the register as {', '.join(cr['register'])}.")
    if not cr.get("question"):
        sys.exit(f"{a.id} has no question for the client: add one first.")
    if not (Path(a.project) / "register.json").exists():
        sys.exit(f"No register.json in {a.project}.")
    reg = register.load(a.project)
    cited = "; ".join(str(c.get("ref")) for c in cr.get("cited") or [] if isinstance(c, dict))
    item = {"type": "question", "audience": "client", "severity": cr.get("severity") or "medium",
            "category": cr.get("gap_pattern") if str(cr.get("gap_pattern", "")).startswith("GP-") else "scope",
            "stage": cr.get("stage") or "development",
            "source": f"{cr['id']} (change request log)" + (f"; signed v{cr.get('basis_version')}: {cited}" if cited else ""),
            "finding": f"Asked by {cr['asked_by']} on {cr['raised']}: {cr['request']} The signed document"
                       + (f" v{cr['basis_version']}" if cr.get("basis_version") else "") + " does not settle whether this is included.",
            "question": cr["question"], "recommendation": cr.get("recommendation"), "effort_impact": cr.get("effort_impact")}
    item = {k: v for k, v in item.items() if v}
    new, notes, errors = register.prepare(reg, [item])
    if errors:
        print("Nothing was added. Fix these in the CR and run it again:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    dupes = register.likely_duplicates(reg, new)
    rid = new[0]["id"]
    if a.check:
        print(f"Checked, nothing written: {a.id}'s question would be added to the register as {rid}.")
    else:
        reg.setdefault("items", []).extend(new)
        register.save(a.project, reg)
        cr["register"] = [rid]
        save_log(a.project, log)
        print(f"Added {a.id}'s question to the register as {rid}, and linked it to {a.id}.")
    print(f"  {rid}  client {item['severity']:<6} {register.short(new[0], 80)}")
    if dupes:
        print("Possible duplicates: check each; if it is one, link that item to the CR instead (\"register\" in crs.json).")
        for _, old, s in dupes:
            print(f"  may be a duplicate of {old.get('id')} (similarity {s:.2f}, {old.get('status')}): {register.short(old, 70)}")
    if not a.check:
        print(f"Next: python -I tools/register.py render {Path(a.project).as_posix()}")
        refresh(a.project)


def cmd_check(a, render=False):
    log = load_log(a.project)
    if not log_path(a.project).exists():
        sys.exit(f"No CR log yet ({LOG.as_posix()}): add the first CR with add.")
    warnings, sizing = checked(a.project, log)
    crs = [cr for cr in log.get("crs", []) if isinstance(cr, dict)]
    counts = Counter(cr.get("verdict") for cr in crs)
    print(f"CR log for {log.get('project', '')}: {len(crs)} request{'s' * (len(crs) != 1)} ({counts.get('new', 0)} new, "
          f"{counts.get('ambiguous', 0)} ambiguous, {counts.get('in-scope', 0)} in scope)")
    for cr in crs:
        extra = [x for x in (cr.get("gap_pattern"), sized_text(sizing.get(cr["id"])) if cr.get("lines") else "",
                             f"sold {estimate.num(cr['sold_md'])} MD by {cr['sold_by']}" if cr.get("sold_md") else "",
                             ", ".join(cr.get("register") or [])) if x]
        print(f"  {cr['id']}  {cr['verdict']:<9} {cr['status']:<8} {cr['title']}" + (f"  [{'; '.join(extra)}]" if extra else ""))
    _, about_crs = calibration_notes(knowledge_dir())
    if about_crs:
        print("What the knowledge base's calibration notes say about change requests (use them only as written there):")
        print("\n".join(f"  - {line}" for line in about_crs))
    else:
        print("The knowledge base has no calibration note about change requests: size each from the building-block rates alone.")
    for line in warnings:
        print(f"Note: {line}")
    if render:
        out = render_xlsx(log, sizing, log_path(a.project).parent / EXCEL)
        print(f"Wrote {out}")
        print("Internal: not for the client.")
        refresh(a.project)


def cmd_note(a):
    log = load_log(a.project)
    warnings, _ = checked(a.project, log)
    cr = find_cr(log, a.id)
    if cr["verdict"] == "in-scope":
        print(in_scope_note(cr, signed_basis(a.project)))
        print("No client note: an In scope request is not a change request.")
        return
    if cr["verdict"] == "ambiguous":
        sys.exit(f"{a.id} is Ambiguous: it is a question for the client, not a change yet. "
                 f"python -I tools/change_request.py ask {Path(a.project).as_posix()} {a.id}")
    for line in signed_basis(a.project, cr.get("basis_version") if project_tool.is_issued(Path(a.project), cr.get("basis_version") or "") else None)["warnings"]:
        print(f"Warning: {line}")
    out = write_note(a.project, log, cr)
    print(f"Wrote {out}")
    print(f"For the client. Price shown: {price_text(cr)}" + ("" if cr.get("sold_md") or cr.get("price") else
          " (the project lead has not entered the sold figure)"))
    refresh(a.project)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scope"); s.add_argument("project"); s.add_argument("request", nargs="*"); s.add_argument("--file")
    s.add_argument("--top", type=int, default=8); s.add_argument("--version")
    s = sub.add_parser("add"); s.add_argument("project"); s.add_argument("--file", required=True)
    s = sub.add_parser("update"); s.add_argument("project"); s.add_argument("ids", nargs="+"); s.add_argument("--set", action="append", required=True)
    s = sub.add_parser("ask"); s.add_argument("project"); s.add_argument("id"); s.add_argument("--check", action="store_true")
    for name in ("check", "render"):
        s = sub.add_parser(name); s.add_argument("project")
    s = sub.add_parser("note"); s.add_argument("project"); s.add_argument("id")
    a = ap.parse_args()
    if not Path(a.project).is_dir():
        sys.exit(f"No project folder {a.project}")
    {"scope": cmd_scope, "add": cmd_add, "update": cmd_update, "ask": cmd_ask, "check": cmd_check,
     "render": lambda a: cmd_check(a, render=True), "note": cmd_note}[a.cmd](a)


if __name__ == "__main__":
    main()
