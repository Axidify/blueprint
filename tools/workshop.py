"""Prepare a requirement workshop: what is still open, and the agenda as documents.

Usage:
    python -I tools/workshop.py gaps   projects/<slug>
    python -I tools/workshop.py check  projects/<slug> ["<agenda.json>"]
    python -I tools/workshop.py render projects/<slug> ["<agenda.json>"]

gaps    what a workshop for this project has to settle: the open client questions in the register, what the
        spec still lacks (status rules, integration details, formulas, scope ...), and the gap patterns of the
        knowledge base with their evidence, so the ones that already cost mandays come first
check   checks an agenda file: every reference is an open client question, every screen exists, the
        sections fit the time, and no high-severity question is left off the agenda without a reason
render  checks the agenda, then writes two Word documents into the project's "3 Workshops" folder (next to
        the agenda in a project not yet moved to the new folder layout):
          "<name> - agenda.docx"                       for the client: the questions, with room for each decision
          "<name> - facilitator notes (internal).docx" for the BA: the same, with why each question matters,
                                                       your recommendation and the questions left for later
        Without a file name it takes the newest agenda in the project's workshops folder (_blueprint/workshops/,
        or workshops/ in the old layout)

workshops/<date> <name>.json:
{
  "project": "Courier Booking System",
  "workshop": "Workshop 2: mock-up review",
  "date": "2026-11-12",
  "duration_minutes": 120,
  "goal": "Agree the approval rules and the list columns, so the requirements document can go for sign-off.",
  "attendees": [ {"role": "Business owner", "name": "", "needed_for": "decisions on approval rules"} ],
  "bring": ["A sample of the current request form"],                 optional: what the client should prepare
  "sections": [
    {"title": "Approval rules", "minutes": 30, "show": ["review-request"],     "show": mock-up screens to put up
     "items": [ {"ref": "R-012", "question": "...", "options": ["A", "B"],
                 "why": "...", "recommendation": "...", "gap_pattern": "GP-02", "effort_impact": "high"} ]}
  ],
  "parked": [ {"ref": "R-030", "question": "...", "reason": "needs the infrastructure team"} ],
  "after": ["We update the mock-up and send the requirements document within 5 working days."]
}

"why", "recommendation", "gap_pattern", "effort_impact" and "parked" are internal: they appear in the
facilitator notes only, never in the client's agenda. Mandays, rates and cost go in neither.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layout  # noqa: E402  (where everything is in a project folder)
import workspace  # noqa: E402

CLOSED = ("resolved", "wont-fix")
SEVERITY = {"high": 0, "medium": 1, "low": 2}
INTERNAL_FIELDS = ("why", "recommendation", "gap_pattern", "effort_impact")
INTERNAL_MARK = "Internal: not for the client"


# ---------------------------------------------------------------- reading the project
def read_register(project):
    path = layout.register_json(project)
    if not path.exists():
        return []
    return [it for it in json.loads(path.read_text(encoding="utf-8")).get("items", []) if isinstance(it, dict)]


def read_spec(project):
    import yaml

    path = layout.spec_file(project)
    if not path.exists():
        return None
    return json.loads(json.dumps(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, default=str))


def open_client_items(items):
    found = [it for it in items if it.get("audience") == "client" and it.get("status") not in CLOSED]
    return sorted(found, key=lambda it: (SEVERITY.get(it.get("severity"), 9), str(it.get("raised", "")), str(it.get("id", ""))))


def spec_gaps(spec):
    """What the spec does not say yet that a workshop can settle: [(topic, what is missing, gap pattern or "")]."""
    if not spec:
        return []
    gaps = []
    statuses = [s for s in spec.get("statuses") or [] if isinstance(s, dict)]
    rules = ("edit", "cancel", "delete", "next")
    without = [s.get("name", "?") for s in statuses if any(s.get(k) is None for k in rules)]
    if without:
        gaps.append(("Status rules", f"who may edit, cancel or delete, and where it moves next, is not set for: {', '.join(without)}", "GP-02"))
    integrations = [x for x in spec.get("integrations") or [] if isinstance(x, dict)]
    loose = [x.get("system", "?") for x in integrations if any(not x.get(k) for k in ("trigger", "data", "on_failure"))]
    if loose:
        gaps.append(("Integrations", f"what starts the exchange, what goes across or what happens on failure is not set for: {', '.join(loose)}", "GP-10"))
    figures = [f"{stat.get('label', '?')} ({s.get('title', s.get('id'))})" for s in spec.get("screens") or []
               for stat in s.get("stats") or [] if not stat.get("formula") and not stat.get("count")]
    if figures:
        gaps.append(("Figures", f"no formula for: {', '.join(figures)}", "GP-03"))
    if not spec.get("scope"):
        gaps.append(("Scope", "nothing says what is in scope, out of scope and assumed", ""))
    else:
        for part, label in (("in_scope", "in scope"), ("out_of_scope", "out of scope"), ("assumptions", "assumptions")):
            if not spec["scope"].get(part):
                gaps.append(("Scope", f"nothing listed as {label}", ""))
    if not spec.get("nfr"):
        gaps.append(("Non-functional requirements", "none recorded: users, performance, availability, backup, retention, security, browsers", "GP-12"))
    notifications = [n for n in spec.get("notifications") or [] if isinstance(n, dict)]
    if not notifications:
        gaps.append(("Notifications", "no e-mail or notification is listed", "GP-14"))
    else:
        open_templates = [n.get("event", "?") for n in notifications if not n.get("template") or "confirm" in str(n["template"]).lower()]
        if open_templates:
            gaps.append(("Notifications", f"the wording is to be confirmed for: {', '.join(open_templates)}", "GP-14"))
    no_scope = [r.get("name", "?") for r in spec.get("roles") or [] if isinstance(r, dict) and not r.get("scope")]
    if no_scope:
        gaps.append(("Roles", f"no data scope (what they see) for: {', '.join(no_scope)}", "GP-01"))
    groups = [g for g in spec.get("requirements") or [] if isinstance(g, dict)]
    linked = {sid for g in groups for sid in g.get("screens") or []} | {
        sid for g in groups for item in g.get("items") or [] if isinstance(item, dict) for sid in item.get("screens") or []}
    if linked:
        loose_screens = [s.get("title", s.get("id")) for s in spec.get("screens") or [] if s.get("type") != "login" and s.get("id") not in linked]
        if loose_screens:
            gaps.append(("Requirements", f"no requirement refers to: {', '.join(loose_screens)}", ""))
    return gaps


def knowledge_dir():
    """The team's knowledge base, or the starter one that comes with the app when there is none yet."""
    own = ROOT / "knowledge"
    return own if own.exists() else workspace.TEMPLATES / "knowledge"


def gap_patterns(kdir=None):
    """The gap patterns of the knowledge base: [{id, title, evidence: cost | review | none, questions}]."""
    path = Path(kdir or knowledge_dir()) / "gap-patterns.md"
    if not path.exists():
        return []
    patterns, current, block = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(GP-\d+)\s+(.*)$", line)
        if m:
            current = {"id": m.group(1), "title": m.group(2).strip(), "evidence": "none", "questions": 0}
            patterns.append(current)
            block = None
            continue
        if current is None:
            continue
        label = re.match(r"^\*\*([^*:]+):\*\*\s*(.*)$", line)
        if label:
            block, line = label.group(1).strip().lower(), label.group(2)
            if block == "evidence":
                text = line.strip().lower()
                current["evidence"] = ("none" if not text or text.startswith("none") else "cost" if text.startswith("cost")
                                       else "review" if text.startswith("review")
                                       else "cost" if re.search(r"\bcr\b|change request|manday|\bmd\b|overrun", text) else "review")
        # The questions are written as a list or run on after the label: either way, one per question mark.
        if block == "workshop questions":
            current["questions"] += line.count("?")
    return patterns


# ---------------------------------------------------------------- the agenda
def agenda_file(project, name=None):
    folder = layout.workshops_source(project)
    if name:
        path = Path(name) if Path(name).exists() else folder / name
        if not path.exists():
            sys.exit(f"No agenda file {path}")
        return path
    found = sorted(folder.glob("*.json")) if folder.exists() else []
    if not found:
        sys.exit(f"No agenda in {folder}. Write one first (see the top of tools/workshop.py for the format).")
    return found[-1]


def check(agenda, project):
    """Mistakes in an agenda, as sentences; empty when it is in order."""
    errors = []
    for key in ("project", "workshop", "date", "duration_minutes", "goal", "sections"):
        if not agenda.get(key):
            errors.append(f"missing {key}")
    duration = agenda.get("duration_minutes")
    if duration and (isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0):
        errors.append("duration_minutes must be a number of minutes, for example 120")
        duration = None
    if agenda.get("sections") and not isinstance(agenda["sections"], list):
        return errors + ["sections must be a list"]
    items = read_register(project)
    by_id = {it.get("id"): it for it in items}
    spec = read_spec(project)
    screens = {s.get("id") for s in (spec or {}).get("screens") or []}
    seen, total = {}, 0
    for n, section in enumerate(agenda.get("sections") or [], 1):
        where = f"section {n} ({section.get('title', 'untitled')})" if isinstance(section, dict) else f"section {n}"
        if not isinstance(section, dict) or not section.get("title") or not section.get("items"):
            errors.append(f"{where}: needs a title and at least one item")
            continue
        minutes = section.get("minutes")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0:
            errors.append(f"{where}: minutes must be a number above 0")
        else:
            total += minutes
        for screen in section.get("show") or []:
            if spec is not None and screen not in screens:
                errors.append(f"{where}: '{screen}' is not a screen of the mock-up")
        for k, item in enumerate(section["items"], 1):
            if not isinstance(item, dict) or not str(item.get("question") or "").strip():
                errors.append(f"{where}, item {k}: needs a question")
                continue
            ref = item.get("ref")
            if ref:
                if ref in seen:
                    errors.append(f"{where}: {ref} is already in {seen[ref]}")
                seen[ref] = where
                known = by_id.get(ref)
                if not known:
                    errors.append(f"{where}: {ref} is not in the register: add the question there first, so its answer has somewhere to go")
                elif known and known.get("audience") != "client":
                    errors.append(f"{where}: {ref} is an internal item: it is your team's to fix, not a question for the client")
                elif known and known.get("status") in CLOSED:
                    errors.append(f"{where}: {ref} is already {known['status']}")
    if duration and total > duration:
        errors.append(f"the sections add up to {total:g} minutes, the workshop is {duration:g}: move items to parked or shorten sections")
    parked = {}
    for k, item in enumerate(agenda.get("parked") or [], 1):
        if not isinstance(item, dict) or not (item.get("ref") or item.get("question")) or not item.get("reason"):
            errors.append(f"parked item {k}: needs a ref or a question, and the reason it waits")
            continue
        if item.get("ref"):
            parked[item["ref"]] = item
            if item["ref"] in seen:
                errors.append(f"{item['ref']} is both on the agenda and parked")
    for it in open_client_items(items):
        if it.get("severity") == "high" and it.get("id") not in seen and it.get("id") not in parked:
            errors.append(f"{it.get('id')} (high) is open and not on the agenda: add it to a section, or to parked with the reason it waits")
    return errors


def clock(minutes):
    return f"{int(minutes) // 60}:{int(minutes) % 60:02d}"


def render(agenda, project, path):
    """Write the client's agenda and the facilitator notes next to the agenda file. Returns the two paths."""

    import generate_requirements as gen

    fmt = gen.load_format()
    problems = gen.format_errors(fmt)
    if problems:
        sys.exit("The document format has mistakes:\n  " + "\n  ".join(problems))
    co = workspace.company()
    spec = read_spec(project) or {}
    titles = {s.get("id"): s.get("title", s.get("id")) for s in spec.get("screens") or []}
    by_id = {it.get("id"): it for it in read_register(project)}
    outputs = []
    for internal in (False, True):
        doc = gen.template_document()
        w = gen.Writer(doc, fmt)
        w.setup_styles()
        w.header_footer(f"{agenda['project']} · {agenda['workshop']}", INTERNAL_MARK if internal else str(agenda["date"]),
                        f"{co['name']} · {fmt['labels']['confidential']}")
        tw = w.text_width
        w.para([("Facilitator notes" if internal else "Workshop agenda", "sec")], size=w.s["body"] + 1, after=2)
        w.page_title(str(agenda["workshop"]), after=4)
        w.para([(str(agenda["project"]), "sec")], size=w.s["body"] + 1, after=10)
        if internal:
            w.para([("error", "dot"), (INTERNAL_MARK + ". It holds your reasons and recommendations; give the client the agenda.", "")], after=10)
        total = sum(s["minutes"] for s in agenda["sections"])
        n_items = sum(len(s["items"]) for s in agenda["sections"])
        w.cards([(str(agenda["date"]), "Date", None), (f"{agenda['duration_minutes']:g} min", "Duration", None),
                 (n_items, "Questions to settle", "accent")], value_size=14)
        w.para([("Goal", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
        w.para(str(agenda["goal"]), after=6)
        if agenda.get("attendees"):
            w.para([("Who should be there", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
            w.table(["Role", "Name", "Needed for"],
                    [[[(a.get("role", ""), "medium")], a.get("name", ""), a.get("needed_for", "")] for a in agenda["attendees"]],
                    [4.4, 4.4, tw - 8.8])
        if agenda.get("bring"):
            w.para([("Please bring", "medium")], size=w.s["h3"], before=8, after=3, keep=True)
            w.bullets([str(b) for b in agenda["bring"]])
        start = 0
        for n, section in enumerate(agenda["sections"], 1):
            w.heading(f"{n}  {section['title']}", 2)
            timing = f"{section['minutes']:g} minutes" + (f"  ·  {clock(start)} to {clock(start + section['minutes'])}" if internal else "")
            shown = [titles.get(s, s) for s in section.get("show") or []]
            w.para([(timing, "sec")] + ([("  ·  On screen: ", "sec"), (", ".join(shown), "")] if shown else []), after=6, keep=True)
            start += section["minutes"]
            rows = []
            for k, item in enumerate(section["items"], 1):
                question = [(str(item["question"]), "")]
                if item.get("options"):
                    question += [("\n", "")] + [(f"Options: {'  /  '.join(str(o) for o in item['options'])}", "sec")]
                number = [(f"{n}.{k}", "mono")]
                if internal:
                    known = by_id.get(item.get("ref")) or {}
                    notes = []
                    for label, key in (("Why", "why"), ("We recommend", "recommendation")):
                        if item.get(key):
                            notes += ([("\n", "")] if notes else []) + [(f"{label}: ", "sec"), (str(item[key]), "")]
                    facts = [x for x in (item.get("ref"), item.get("gap_pattern"),
                                         f"{known['severity']} severity" if known.get("severity") else "",
                                         f"{item['effort_impact']} effort impact" if item.get("effort_impact") else "") if x]
                    rows.append([number, question, notes or "–", [(" · ".join(facts), "mono")] if facts else "–"])
                else:
                    rows.append([number, question, ""])
            if internal:
                w.table(["No", "Question", "Notes for you", "Ref"], rows, [1.2, (tw - 4.6) * 0.45, (tw - 4.6) * 0.55, 3.4])
            else:
                w.table(["No", "Question", "Decision"], rows, [1.2, (tw - 1.2) * 0.58, (tw - 1.2) * 0.42])
        if internal:
            w.para([(f"Planned: {total:g} of {agenda['duration_minutes']:g} minutes"
                     + (f", {agenda['duration_minutes'] - total:g} spare" if agenda["duration_minutes"] > total else ""), "sec")], before=6, after=6)
            if agenda.get("parked"):
                w.heading("Left for later", 2)
                w.lead("Not for this session. Each has the reason it waits.")
                w.table(["Ref", "Question", "Why it waits"],
                        [[[(str(p.get("ref") or "–"), "mono")], str(p.get("question") or (by_id.get(p.get("ref")) or {}).get("question", "")),
                          str(p["reason"])] for p in agenda["parked"]], [1.8, (tw - 1.8) * 0.55, (tw - 1.8) * 0.45])
        if agenda.get("after"):
            w.heading("After the session", 2)
            w.bullets([str(a) for a in agenda["after"]])
        client_doc, notes_doc = layout.workshop_documents(project, path)
        if path.parent.resolve() != layout.workshops_source(project).resolve():  # an agenda kept elsewhere: beside it
            client_doc, notes_doc = (path.with_name(x.name) for x in (client_doc, notes_doc))
        out = notes_doc if internal else client_doc
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            doc.save(str(out))
        except PermissionError:
            sys.exit(f"Cannot write {out.name}: close it in Word and run this again.")
        outputs.append(out)
    return outputs


# ---------------------------------------------------------------- commands
def cmd_gaps(project):
    items = read_register(project)
    still = open_client_items(items)
    internal = [it for it in items if it.get("audience") == "internal" and it.get("status") not in CLOSED]
    print(f"What a workshop for {Path(project).as_posix()} has to settle")
    print(f"\nOpen questions for the client: {len(still)} "
          f"({sum(1 for it in still if it.get('severity') == 'high')} high, {sum(1 for it in still if it.get('severity') == 'medium')} medium, "
          f"{sum(1 for it in still if it.get('severity') == 'low')} low)")
    for it in still:
        extra = ", ".join(x for x in (it.get("category", ""), f"{it['effort_impact']} effort impact" if it.get("effort_impact") else "",
                                      f"owner {it['owner']}" if it.get("owner") else "", f"due {it['due']}" if it.get("due") else "",
                                      it.get("status", "")) if x)
        print(f"  {it.get('id')} [{it.get('severity')}; {extra}] {str(it.get('question') or it.get('finding', ''))[:200]}")
    if internal:
        print(f"\nInternal items still open: {len(internal)} (your team's to fix before the session; they never go on the agenda)")
    spec = read_spec(project)
    if spec is None:
        print("\nNo spec yet: the workshop works from the brief and the gap patterns below.")
    else:
        gaps = spec_gaps(spec)
        print(f"\nWhat the spec does not say yet: {len(gaps)}")
        for topic, detail, pattern in gaps:
            print(f"  {topic}: {detail}" + (f"  [{pattern}]" if pattern else ""))
    patterns = gap_patterns()
    order = {"cost": 0, "review": 1, "none": 2}
    print(f"\nGap patterns in the knowledge base: {len(patterns)} (those that already cost mandays come first in every workshop)")
    for p in sorted(patterns, key=lambda p: (order[p["evidence"]], p["id"])):
        evidence = {"cost": "has cost mandays", "review": "found in reviews", "none": "no evidence yet"}[p["evidence"]]
        print(f"  {p['id']} {p['title']} [{evidence}; {p['questions']} workshop question{'s' if p['questions'] != 1 else ''}]")
    earlier = sorted(layout.workshops_source(project).glob("*.json")) if layout.workshops_source(project).exists() else []
    if earlier:
        print(f"\nEarlier agendas: {', '.join(x.name for x in earlier)}")


def load(project, name):
    path = agenda_file(project, name)
    try:
        agenda = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path.name} is not valid JSON: {e}")
    errors = check(agenda, project)
    if errors:
        print(f"{path.name} needs fixing:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    return path, agenda


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if len(args) not in (2, 3) or args[0] not in ("gaps", "check", "render") or (args[0] == "gaps" and len(args) != 2):
        sys.exit(__doc__)
    command, project = args[0], args[1]
    if not Path(project).is_dir():
        sys.exit(f"No project folder {project}")
    if command == "gaps":
        return cmd_gaps(project)
    path, agenda = load(project, args[2] if len(args) == 3 else None)
    sections = agenda["sections"]
    summary = (f"{len(sections)} sections, {sum(len(s['items']) for s in sections)} questions, "
               f"{sum(s['minutes'] for s in sections):g} of {agenda['duration_minutes']:g} minutes, {len(agenda.get('parked') or [])} left for later")
    if command == "check":
        print(f"OK: {path.name}: {summary}")
        return
    client, internal = render(agenda, project, path)
    print(f"Workshop pack for {agenda['project']}: {summary}")
    print(f"  For the client:  {client}")
    print(f"  For you only:    {internal}")
    print("  The facilitator notes are internal: send the agenda, keep the notes.")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
