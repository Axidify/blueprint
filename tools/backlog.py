"""The development backlog: user stories from the requirements, story points from the estimate, a traceability
sheet, and import files for Project Desk, Jira and Azure DevOps.

Usage:
    python -I tools/backlog.py draft  projects/<slug> [--current] [--estimate "<estimate.json>"] [--date YYYY-MM-DD] [--force]
    python -I tools/backlog.py check  projects/<slug> ["<backlog.json>"]
    python -I tools/backlog.py render projects/<slug> ["<backlog.json>"] [--ado-process agile|scrum]
    python -I tools/backlog.py scale

draft   writes projects/<slug>/backlog/<date> backlog v<version>.json from the spec, the same way every time:
        an epic for every requirement group and a user story for every requirement item, with a first guess at
        its role, title and wording, acceptance criteria drawn from the screens (status moves, required
        fields, field rules, dialogs) placed on the story they read most like, and the estimate's lines
        linked to the epic whose name they share. It works from the version issued to the client last
        (output/spec-v<version>.yaml), because the team builds what was signed; with nothing issued, or with
        --current, from spec/app.yaml. The estimate is the newest in estimates/ unless --estimate names one.
        It refuses to replace a draft of the same name unless --force.
check   checks the backlog and lists what it found: mistakes that stop render (an unknown role, screen,
        requirement or estimate line, a requirement no story covers and none excluded), what is still to
        refine (draft notes left, a story without "so that" or acceptance criteria), the story points and
        how each was worked out, and the gaps for the register.
render  checks the backlog, then writes next to it:
          "<name>.xlsx"                          internal: the backlog, how the points were worked out, a summary
          "<name> - traceability.xlsx"           for the client: each requirement with its screens, user stories,
                                                 UAT scenarios and change requests. Never story points
          "<name> - Project Desk import.xlsx"    the Tasks sheet Project Desk's import reads
          "<name> - Jira import.csv"             for Jira's CSV import
          "<name> - Azure DevOps import.csv"     for Azure DevOps' CSV import (--ado-process scrum for the Scrum
                                                 process: Product Backlog Item and Effort)
        Without a file name it takes the newest backlog in projects/<slug>/backlog/
scale   the story-point scale in knowledge/building-blocks.md, or the table to add when it is not there

Story points come from the estimate, never from a guess. Each story names the estimate lines it delivers
("lines"); a line's mandays are shared among the stories that name it (evenly, unless a story gives its
"share"), and the story's mandays (the middle of its range) become points with the scale the lead developer
sets in the "Story points" table of knowledge/building-blocks.md. A story with no line, a line with no rate,
or no scale: no points, and the reason is shown.

backlog/<date> backlog v<version>.json:
{
  "project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "short_name": "LRS",
  "spec_version": "0.1", "spec": "spec/app.yaml",
  "based_on": "the requirements v0.1, not yet issued", "date": "2026-11-07",
  "estimate": "estimates/2026-11-06 estimate from spec v0.1.json",           optional
  "epics": [ {"id": "EP-01", "title": "Apply for Leave", "group": "FR-APP-001", "description": "..."} ],
  "stories": [
    {"id": "US-001", "epic": "EP-01", "type": "Story",                      Story | Task
     "title": "Save a draft without checks",
     "role": "employee", "want": "to save my application as a draft", "so_that": "I can finish it later",
     "acceptance": ["Saving a draft does not check the required fields", "..."],
     "requirements": ["FR-APP-001.5"], "screens": ["new-application"], "priority": "Must",
     "lines": ["L01"] or [{"line": "L01", "share": 0.4}],                    the estimate lines it delivers
     "register": ["R-019"],                                                  open questions it waits on
     "notes": "...",                                                         for the team
     "source": "...", "todo": "...", "unplaced": [...]}                      draft only: for Claude
  ],
  "excluded": [ {"requirement": "FR-APP-003.2", "reason": "..."} ]         covered elsewhere, with a reason
}

A Task is technical work no requirement asks for in words (an environment, a migration): it needs no role,
"want" or requirement. The backlog is internal; only the traceability sheet goes to the client, and it never
holds story points, mandays, estimate lines or notes. See docs/backlog.md.
"""
import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import estimate as estimate_tool  # noqa: E402
import layout  # noqa: E402  (where everything is in a project folder)
import uat  # noqa: E402  (the spec model and the requirement ids, shared with the UAT scripts)

TYPES = ("Story", "Task")
PRIORITIES = ("Must", "Should", "Could")
POINTS = (1, 2, 3, 5, 8, 13)
DRAFT_ONLY = ("source", "todo", "unplaced")
CLOSED = ("resolved", "wont-fix")
INTERNAL_WORDS = uat.INTERNAL_WORDS
PRIORITY_PD = {"Must": "P2 · High", "Should": "P3 · Medium", "Could": "P4 · Low"}
PRIORITY_JIRA = {"Must": "High", "Should": "Medium", "Could": "Low"}
PRIORITY_ADO = {"Must": 1, "Should": 2, "Could": 3}
STOP = set("""a an the and or of to for in on at by with from as is are be been it its this that these those shall must
should will can may system user users when then than into not no only each every any all their his her they them
we our you your which who what where how there here also upon before after while about via per
allow allows allowed able record records screen page field fields require required requires""".split())
SUFFIXES = (("ation", ""), ("tion", "t"), ("sion", "s"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""))
SCALE_TABLE = """## Story points

How the backlog turns a story's mandays into story points. Set it with the lead developer: a story gets the
smallest number of points whose "Mandays up to" covers its mandays. A story above the last row is too big
and should be split. While a row is TBD, the backlog leaves story points blank.

| Points | Mandays up to |
|---|---|
| 1 | TBD |
| 2 | TBD |
| 3 | TBD |
| 5 | TBD |
| 8 | TBD |
| 13 | TBD |
"""


# ---------------------------------------------------------------- small helpers
as_list = uat.as_list


def stem(w):
    """A rough stem, so that "reject", "rejecting" and "rejection" match (and "applications" and "application")."""
    for _ in range(2):
        for end, put in SUFFIXES:
            if w.endswith(end) and len(w) - len(end) >= 4:
                w = w[: -len(end)] + put
                break
    return w[:-1] if w.endswith("e") and len(w) > 4 else w


def words(text):
    """The words of a text that carry meaning, in any form: for matching a criterion or a line to a story."""
    out = set()
    for w in re.findall(r"[a-z][a-z\-]+", str(text or "").lower()):
        w = w.strip("-")
        if len(w) < 3 or w in STOP:
            continue
        out.add(stem(w))
    return out


def article(word):
    return "an" if str(word)[:1].lower() in "aeiou" else "a"


def capital(text):
    text = str(text or "").strip()
    return text[:1].upper() + text[1:]


def shorten(text, limit=90):
    text = re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".")
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + " …"


def num(x):
    return f"{round(x, 1):g}"


def md_range(low, high):
    return f"{num(low)} MD" if round(low, 1) == round(high, 1) else f"{num(low)} – {num(high)} MD"


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- the story-point scale
def read_scale(kdir):
    """({points: mandays up to}, problems) from the "Story points" table, or (None, []) when there is no table."""
    path = Path(kdir) / "building-blocks.md"
    if not path.exists():
        return None, []
    found, inside, scale, problems = False, False, {}, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("story points")
            found = found or inside
            continue
        if not inside or not line.startswith("|"):
            continue
        row = estimate_tool.cells(line)
        if len(row) < 2 or not row[0].isdigit():
            continue
        points = int(row[0])
        if points not in POINTS:
            problems.append(f"{points} is not a story point value ({', '.join(map(str, POINTS))})")
            continue
        rate = estimate_tool.parse_rate(row[1])
        if rate is None:
            if re.search(r"\d", row[1]):
                problems.append(f"{points} points: '{row[1]}' is not a number of mandays")
            continue
        scale[points] = rate[1]
    if not found:
        return None, []
    missing = [p for p in POINTS if p not in scale]
    if missing:
        problems.append("not set yet for " + ", ".join(map(str, missing)) + " points")
    ups = [scale[p] for p in POINTS if p in scale]
    if ups != sorted(ups):
        problems.append("the mandays must grow with the points")
    return scale, problems


def to_points(md, scale):
    """(points, note): the smallest point value whose mandays cover md; above the last, 13 and a note to split."""
    for p in POINTS:
        if md <= scale[p] + 1e-9:
            return p, ""
    return POINTS[-1], f"{num(md)} MD is above the largest value on the scale ({num(scale[POINTS[-1]])} MD): split the story"


# ---------------------------------------------------------------- the estimate
def estimate_path(project, name=None):
    folder = layout.estimates_source(project)
    if name:
        path = Path(name) if Path(name).exists() else folder / Path(name).name
        if not path.exists():
            sys.exit(f"No estimate file {path}")
        return path
    found = sorted(folder.glob("*.json"), key=estimate_tool.newest_first_key) if folder.exists() else []
    return found[-1] if found else None


def estimate_lines(project, rel, kdir):
    """({line id: line with low, high, priced, kind}, problem or None) for the lines a story can deliver: those
    counted in building blocks or given in mandays, not the work around the build."""
    if not rel:
        return {}, None
    path = Path(project) / rel
    if not path.exists():
        path = layout.resolve(project, rel)
    if not path.exists():
        return {}, f"the estimate {rel} is not there"
    try:
        est = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return {}, f"the estimate {rel} cannot be read ({e})"
    res, errors = estimate_tool.compute(est, Path(project), kdir)
    lines = OrderedDict((l["id"], l) for l in res.get("lines", []) if l.get("kind") in ("block", "md"))
    return lines, (f"the estimate {rel} has mistakes: " + "; ".join(errors[:3])) if errors else None


# ---------------------------------------------------------------- the draft
class Draft:
    def __init__(self, spec, lines):
        self.spec = spec
        self.m = uat.Model(spec)
        self.lines = lines
        P = spec.get("project") or {}
        noun = (self.m.main or "record").replace("_", " ").replace("-", " ")
        self.noun = noun[:-1] if noun.endswith("s") else noun
        # words every requirement shares (the system's name, the record it moves) say nothing about a match
        self.noise = words(P.get("name")) | words(P.get("short_name")) | words(noun)

    def score(self, a, b):
        return len((a - self.noise) & (b - self.noise))

    # ---- wording
    def role_for(self, text):
        low = text.lower()
        names = {r["id"]: str(r.get("name") or r["id"]).lower() for r in self.m.roles}
        for rid, name in names.items():
            if re.search(rf"allows?\s+(the\s+|an?\s+)?({re.escape(name)}|{re.escape(rid)})\b", low):
                return rid
        hits = sorted((low.find(n), rid) for rid, n in names.items() if n in low)
        return hits[0][1] if hits else None

    def want_for(self, text):
        t = re.sub(r"^\s*(the\s+)?system\s+(shall|must|should|will|can)\s+", "", text.strip(), flags=re.I).rstrip(".")
        m = re.match(r"allows?\s+(the\s+|an?\s+)?[\w ]+?\s+to\s+(.+)$", t, re.I)
        if m:
            return f"to {m.group(2)}", capital(m.group(2))
        return f"the system to {t[:1].lower() + t[1:]}", capital(t)

    # ---- acceptance criteria from the screens
    def candidates(self):
        m, out = self.m, []
        for mv in m.movers():
            who = uat.join_words([m.role_name(r) for r in mv["roles"]], "or") or "a user"
            frm = f"Given {article(self.noun)} {self.noun} in {m.sname(mv['from'])}, when" if mv["from"] else "When"
            out.append((f"{frm} {who} presses {mv['label']}, it moves to {m.sname(mv['to'])}", mv["screen"]))
            dlg = mv.get("dialog") or {}
            needed = [str(f.get("label") or f.get("id")) for f in dlg.get("fields") or [] if isinstance(f, dict) and f.get("required")]
            if needed:
                out.append((f"{mv['label']} cannot be confirmed without {uat.join_words(needed)}", mv["screen"]))
        for scr in m.screens:
            if scr.get("type") not in ("form", "detail"):
                continue
            for b in scr.get("buttons") or []:
                if isinstance(b, dict) and b.get("toast") and not b.get("set_status") and not b.get("dialog"):
                    out.append((f"{b.get('label')} shows \"{m.text(b['toast'])}\"", scr["id"]))
            for f in m.form_fields(scr):
                label = m.text(f.get("label") or f.get("id"))
                if f.get("readonly") and f.get("source"):
                    out.append((f"{label} is filled in by the system ({m.text(f['source'])}) and cannot be changed", scr["id"]))
                elif f.get("required"):
                    out.append((f"{label} is required", scr["id"]))
                if f.get("validation"):
                    out.append((capital(m.text(f["validation"])), scr["id"]))
                if f.get("help") and re.search(r"\brequired\b|\bmax\b|\bonly\b", str(f["help"]), re.I):
                    out.append((f"{label}: {m.text(f['help'])}", scr["id"]))
                if f.get("options_from") and f.get("source"):
                    out.append((f"{label} offers the {m.text(f['source'])}", scr["id"]))
        for n in self.spec.get("notifications") or []:
            if isinstance(n, dict) and n.get("event"):
                out.append((f"When {m.text(n['event'])[:1].lower() + m.text(n['event'])[1:]}, "
                             f"{m.text(n.get('recipient') or 'the recipient')} is sent an e-mail", None))
        seen, unique = set(), []
        for text, sid in out:
            if text.lower() not in seen:
                seen.add(text.lower())
                unique.append((text, sid))
        return unique

    def build(self):
        epics, stories, groups = [], [], {}
        for g in self.spec.get("requirements") or []:
            if not isinstance(g, dict) or not g.get("id"):
                continue
            eid = f"EP-{len(epics) + 1:02d}"
            epics.append({"id": eid, "title": self.m.text(g.get("title") or g["id"]), "group": str(g["id"]), "description": ""})
            groups[eid] = g
            items = g.get("items") or [None]
            for n, item in enumerate(items, 1):
                text = self.m.text((item.get("text") if isinstance(item, dict) else item) or g.get("title") or "")
                rid = f"{g['id']}.{n}" if g.get("items") else str(g["id"])
                prio = (item.get("priority") if isinstance(item, dict) else None) or g.get("priority")
                want, title = self.want_for(text)
                story = {"id": f"US-{len(stories) + 1:03d}", "epic": eid, "type": "Story", "title": shorten(title),
                         "role": self.role_for(text), "want": want, "so_that": "", "acceptance": [],
                         "requirements": [rid], "screens": [s for s in as_list(g.get("screens")) if s in self.m.screen]}
                if prio in PRIORITIES:
                    story["priority"] = prio
                tbc = item.get("tbc") if isinstance(item, dict) else None
                if tbc:
                    story["register"] = as_list(tbc)
                story["source"] = f"{rid}: {text}"
                stories.append(story)
        # acceptance criteria: each on the story it reads most like. Two words in common place it; a second pass
        # lets a story's screen (known from the first pass) count as one of them.
        left = self.candidates()
        for with_screens in (False, True):
            rest = []
            for text, sid in left:
                cw, best, top = words(text), None, 1
                for s in stories:
                    sc = self.score(cw, words(s["source"]) | words(s["title"]))
                    sc += 1 if with_screens and sid and sid in s["screens"] else 0
                    if sc > top:
                        best, top = s, sc
                if best:
                    best["acceptance"].append(text)
                    if sid and sid not in best["screens"]:
                        best["screens"].append(sid)
                else:
                    rest.append((text, sid))
            left = rest
        unplaced = [{"criterion": text, "screen": sid} if sid else {"criterion": text} for text, sid in left]
        for s in stories:
            if not s["role"]:
                openers = [r for sid in s["screens"] for r in self.m.openers(sid)]
                s["role"] = openers[0] if openers else (self.m.roles[0]["id"] if self.m.roles else None)
        # the estimate's lines, by the name they share with an epic
        for lid, line in self.lines.items():
            lw = words(f"{line.get('group', '')} {line.get('item', '')}") - self.noise
            for e in epics:
                ew = words(e["title"]) - self.noise
                if ew and len(lw & ew) / len(ew) >= 0.5:
                    for s in stories:
                        if s["epic"] == e["id"]:
                            s.setdefault("lines", []).append(lid)
        for s in stories:
            todo = ["Check the role, and write 'want' and 'so that' as the user would say them"]
            if not s["acceptance"]:
                todo.append("no acceptance criteria were found on the screens: write them from the requirement and the status rules")
            if not s.get("lines") and self.lines:
                todo.append("link the estimate lines this story delivers (lines), or leave it without points")
            s["todo"] = "; ".join(todo)
        return epics, stories, unplaced


def draft(spec, spec_path, based_on, date, est_rel, lines):
    P = spec.get("project") or {}
    epics, stories, unplaced = Draft(spec, lines).build()
    out = {"project": str(P.get("name", "")), "client": str(P.get("client", "")),
           "short_name": str(P.get("short_name", "")), "spec_version": str(P.get("version", "")), "spec": spec_path,
           "based_on": based_on, "date": date}
    if est_rel:
        out["estimate"] = est_rel
    out.update(epics=epics, stories=stories, excluded=[])
    if unplaced:
        out["unplaced"] = unplaced
    return out


# ---------------------------------------------------------------- reading a backlog
def backlog_file(project, name=None):
    folder = layout.backlog_source(project)
    if name:
        path = Path(name) if Path(name).exists() else folder / name
        if not path.exists():
            sys.exit(f"No backlog file {path}")
        return path
    found = sorted((f for f in folder.glob("*.json")), key=estimate_tool.newest_first_key) if folder.exists() else []
    if not found:
        sys.exit(f"No backlog in {folder}. Write a draft first: python -I tools/backlog.py draft {Path(project).as_posix()}")
    return found[-1]


def spec_of(project, backlog):
    path = layout.resolve(project, backlog.get("spec") or "spec/app.yaml")
    if not path.exists():
        sys.exit(f"The backlog was written from {backlog.get('spec')}, which is not in the project any more.")
    return uat.load_yaml(path)


def line_refs(story):
    """[(line id, share or None)] of a story."""
    out = []
    for x in as_list(story.get("lines")):
        if isinstance(x, dict):
            out.append((str(x.get("line") or ""), x.get("share")))
        else:
            out.append((str(x), None))
    return out


def work_out_points(backlog, lines, scale, scale_problems):
    """{story id: {"low", "high", "points", "why", "parts": [(line id, share)]}}."""
    shares = {}  # line id -> [(story id, share or None)]
    for s in backlog.get("stories") or []:
        for lid, share in line_refs(s):
            shares.setdefault(lid, []).append((s.get("id"), share))
    portion = {}
    for lid, takers in shares.items():
        given = sum(sh for _, sh in takers if isinstance(sh, (int, float)))
        rest = [sid for sid, sh in takers if not isinstance(sh, (int, float))]
        for sid, sh in takers:
            portion[(sid, lid)] = sh if isinstance(sh, (int, float)) else max(0.0, 1 - given) / len(rest)
    scale_ready = scale is not None and not scale_problems
    out = {}
    for s in backlog.get("stories") or []:
        sid, refs = s.get("id"), line_refs(s)
        r = {"low": None, "high": None, "points": None, "why": "", "parts": [(lid, portion.get((sid, lid), 0)) for lid, _ in refs]}
        out[sid] = r
        if not refs:
            r["why"] = "no estimate line: link the line it delivers"
            continue
        if any(lid not in lines for lid, _ in refs):
            r["why"] = "an estimate line it names is not in the estimate"
            continue
        unpriced = [lid for lid, _ in refs if not lines[lid].get("priced")]
        if unpriced:
            r["why"] = f"{uat.join_words(unpriced)} {'has' if len(unpriced) == 1 else 'have'} no rate in the knowledge base yet"
            continue
        r["low"] = sum(lines[lid]["low"] * portion.get((sid, lid), 0) for lid, _ in refs)
        r["high"] = sum(lines[lid]["high"] * portion.get((sid, lid), 0) for lid, _ in refs)
        if scale is None:
            r["why"] = "no story-point scale in the knowledge base yet (python -I tools/backlog.py scale)"
        elif scale_problems:
            r["why"] = "the story-point scale is " + "; ".join(scale_problems)
        if scale_ready:
            r["points"], r["why"] = to_points((r["low"] + r["high"]) / 2, scale)
    return out


def register_items(project):
    return {str(it.get("id")): it for it in uat.read_register(project) if it.get("id")}


def check(backlog, spec, project, lines, line_problem):
    """(errors that stop render, things still to refine, gaps for the register)."""
    m = uat.Model(spec)
    errors, refine, gaps = [], [], []
    for key in ("project", "date", "epics", "stories"):
        if not backlog.get(key):
            errors.append(f"missing {key}")
    reqs = uat.requirement_ids(spec)
    reg = register_items(project)
    epic_ids = []
    for i, e in enumerate(backlog.get("epics") or []):
        where = e.get("id") or f"epic #{i + 1}"
        if not e.get("id") or not e.get("title"):
            errors.append(f"{where}: an epic needs id and title")
        if e.get("id") in epic_ids:
            errors.append(f"{where}: duplicate id")
        epic_ids.append(e.get("id"))
        if e.get("group") and e["group"] not in {g.get("id") for g in spec.get("requirements") or [] if isinstance(g, dict)}:
            errors.append(f"{where}: group {e['group']} is not a requirement group of the spec")
        if INTERNAL_WORDS.search(str(e.get("title") or "")):
            errors.append(f"{where}: the title goes to the client on the traceability sheet: keep mandays, rates and building blocks out of it")
    seen, covered, used_lines, used_screens = set(), {}, set(), set()
    for i, s in enumerate(backlog.get("stories") or []):
        where = s.get("id") or f"story #{i + 1}"
        if not s.get("id") or not s.get("title"):
            errors.append(f"{where}: a story needs id and title")
        if s.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(s.get("id"))
        if s.get("epic") not in epic_ids:
            errors.append(f"{where}: epic {s.get('epic')} is not in the backlog")
        kind = s.get("type") or "Story"
        if kind not in TYPES:
            errors.append(f"{where}: type '{kind}' is not one of {', '.join(TYPES)}")
        if kind == "Story":
            if s.get("role") not in m.role:
                errors.append(f"{where}: role '{s.get('role')}' is not a role of the spec ({', '.join(m.role)})")
            if not str(s.get("want") or "").strip():
                errors.append(f"{where}: a story needs 'want'")
            if not str(s.get("so_that") or "").strip() and not s.get("todo"):
                refine.append(f"{where}: no 'so that' yet")
            if not s.get("requirements"):
                errors.append(f"{where}: a story needs the requirements it delivers (a Task does not)")
        if INTERNAL_WORDS.search(str(s.get("title") or "")):
            errors.append(f"{where}: the title goes to the client on the traceability sheet: keep mandays, rates and building blocks out of it")
        if not isinstance(s.get("acceptance", []), list) or any(not isinstance(a, str) or not a.strip() for a in s.get("acceptance") or []):
            errors.append(f"{where}: acceptance must be a list of sentences")
        elif not s.get("acceptance") and not s.get("todo"):
            refine.append(f"{where}: no acceptance criteria yet")
        if s.get("priority") and s["priority"] not in PRIORITIES:
            errors.append(f"{where}: priority '{s['priority']}' is not one of {', '.join(PRIORITIES)}")
        for r in as_list(s.get("requirements")):
            if r not in reqs:
                errors.append(f"{where}: {r} is not a requirement of the spec")
            else:
                covered.setdefault(r, []).append(s.get("id"))
        for sid in as_list(s.get("screens")):
            if sid not in m.screen:
                errors.append(f"{where}: screen '{sid}' is not in the spec")
            used_screens.add(sid)
        for x in as_list(s.get("lines")):
            lid, share = (x.get("line"), x.get("share")) if isinstance(x, dict) else (x, None)
            if share is not None and (not isinstance(share, (int, float)) or isinstance(share, bool) or not 0 < share <= 1):
                errors.append(f"{where}: the share of {lid} must be a number above 0 and up to 1")
            if lines and lid not in lines:
                errors.append(f"{where}: {lid} is not a building-block or manday line of the estimate")
            elif not lines and not line_problem:
                errors.append(f"{where}: names estimate line {lid}, but the backlog has no estimate")
            used_lines.add(lid)
        for rid in as_list(s.get("register")):
            if rid not in reg:
                errors.append(f"{where}: {rid} is not in the register")
            elif reg[rid].get("status") not in CLOSED:
                gaps.append(f"{where} waits on {rid}, still open: not ready to build until the client answers")
        if s.get("todo"):
            refine.append(f"{where}: draft note left: {s['todo']}")
        if s.get("unplaced"):
            refine.append(f"{where}: criteria still to place")
    totals = {}
    for s in backlog.get("stories") or []:
        for lid, share in line_refs(s):
            if isinstance(share, (int, float)):
                totals[lid] = totals.get(lid, 0) + share
    for lid, total in totals.items():
        if total > 1.0001:
            errors.append(f"the shares of {lid} add up to {num(total * 100)}%: more than the whole line")
    excluded = {}
    for e in backlog.get("excluded") or []:
        r = str((e or {}).get("requirement") or "")
        if r not in reqs:
            errors.append(f"excluded: {r or '(no id)'} is not a requirement of the spec")
        elif not str(e.get("reason") or "").strip():
            errors.append(f"excluded: {r} needs a reason")
        elif r in covered:
            errors.append(f"excluded: {r} is also delivered by {', '.join(covered[r])}")
        excluded[r] = e
    for r in reqs:
        if r not in covered and r not in excluded:
            errors.append(f"{r} is in no story: add one, or exclude it with a reason")
    if backlog.get("unplaced"):
        refine.append(f"{len(backlog['unplaced'])} acceptance criteria from the screens are not on a story yet ('unplaced')")
    for lid, line in lines.items():
        if lid not in used_lines:
            gaps.append(f"estimate line {lid} ({line.get('item')}) is in no story: work no requirement asks for, "
                        "or a requirement missing from the spec")
    for scr in m.screens:
        if scr["id"] not in used_screens and scr.get("type") not in ("login",):
            gaps.append(f"screen '{m.title(scr['id'])}' is in no story: is it needed, and which requirement asks for it?")
    if line_problem:
        errors.append(line_problem)
    return errors, refine, gaps


def load(project, name, kdir):
    path = backlog_file(project, name)
    try:
        backlog = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path.name} is not valid JSON: {e}")
    spec = spec_of(project, backlog)
    lines, problem = estimate_lines(project, backlog.get("estimate"), kdir)
    return path, backlog, spec, lines, problem


# ---------------------------------------------------------------- what the files show
def user_story(story, m):
    if (story.get("type") or "Story") != "Story":
        return str(story.get("want") or "")
    role = m.role_name(story.get("role"))
    article = "an" if role[:1].lower() in "aeiou" else "a"
    text = f"As {article} {role}, I want {story.get('want', '').strip()}"
    if story.get("so_that"):
        text += f", so that {story['so_that'].strip()}"
    return text + "."


def ordered(backlog):
    """[(epic, [stories])] in the backlog's order."""
    by = OrderedDict((e["id"], (e, [])) for e in backlog.get("epics") or [])
    for s in backlog.get("stories") or []:
        if s.get("epic") in by:
            by[s["epic"]][1].append(s)
    return list(by.values())


def screens_of(story, m):
    return [m.title(x) for x in as_list(story.get("screens")) if x in m.screen]


def open_questions(story, reg):
    return [rid for rid in as_list(story.get("register")) if (reg.get(rid) or {}).get("status") not in CLOSED]


def trace(backlog, spec, project):
    """[(requirement id, text, priority, screens, stories, UAT scenarios, change requests, excluded reason)]."""
    m = uat.Model(spec)
    reqs = uat.requirement_ids(spec)
    stories = {}
    for s in backlog.get("stories") or []:
        for r in as_list(s.get("requirements")):
            stories.setdefault(r, []).append(s)
    cases = {}
    folder = layout.uat_source(project)
    found = sorted(folder.glob("*.json")) if folder.exists() else []
    if found:
        try:
            scripts = json.loads(found[-1].read_text(encoding="utf-8"))
        except ValueError:
            scripts = {}
        for c in scripts.get("cases") or []:
            for r in as_list((c or {}).get("requirements")):
                cases.setdefault(r, []).append(c.get("id"))
    crs = {}
    try:
        log = json.loads(layout.cr_log(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = {}
    for cr in log.get("crs") or [] if isinstance(log, dict) else []:
        cited = " ".join(str((c or {}).get("ref") or "") for c in cr.get("cited") or [] if isinstance(c, dict))
        for r in reqs:
            group = uat.group_of(r)
            if re.search(rf"(?<![\w.-]){re.escape(r)}(?![\d])", cited) or re.search(rf"(?<![\w.-]){re.escape(group)}(?![\w.])", cited):
                crs.setdefault(r, []).append(f"{cr.get('id')} {cr.get('title') or ''}".strip())
    excluded = {str(e.get("requirement")): str(e.get("reason") or "") for e in backlog.get("excluded") or [] if isinstance(e, dict)}
    rows = []
    for r, (g, text, prio, _) in reqs.items():
        st = stories.get(r, [])
        screens = []
        for s in st:
            screens += [x for x in screens_of(s, m) if x not in screens]
        rows.append((r, m.text(text), prio or "", screens, [f"{s['id']} {s.get('title', '')}" for s in st],
                     cases.get(r, []), crs.get(r, []), excluded.get(r, "")))
    return rows


# ---------------------------------------------------------------- Excel
INK, GREY = estimate_tool.INK, estimate_tool.GREY
HEAD_FILL, ROW_LINE, ORANGE = estimate_tool.HEAD_FILL, estimate_tool.ROW_LINE, estimate_tool.ORANGE
XL_FONT = estimate_tool.XL_FONT


def sheet_writer():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    line = Border(bottom=Side(style="thin", color=ROW_LINE))

    def put(ws, r, c, value, color=INK, bold=False, size=11, wrap=True, fill=None, border=True):
        cell = ws.cell(row=r, column=c, value=value)
        cell.font = Font(name=XL_FONT, size=size, bold=bold, color=color)
        cell.alignment = Alignment(wrap_text=wrap, vertical="top")
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        if border:
            cell.border = line
        return cell

    def header(ws, r, columns):
        from openpyxl.utils import get_column_letter

        for c, (name, width) in enumerate(columns, 1):
            put(ws, r, c, name, color=GREY, bold=True, size=10, fill=HEAD_FILL)
            ws.column_dimensions[get_column_letter(c)].width = width
    return put, header


def save(wb, out):
    try:
        wb.save(str(out))
    except PermissionError:
        sys.exit(f"Cannot write {out.name}: close it in Excel and run this again.")
    return out


def render_internal(backlog, spec, project, pts, gaps, lines, out):
    from openpyxl import Workbook

    m = uat.Model(spec)
    reg = register_items(project)
    put, header = sheet_writer()
    wb = Workbook()
    s = wb.active
    s.title = "Summary"
    s.sheet_view.showGridLines = False
    s.column_dimensions["A"].width = 30
    s.column_dimensions["B"].width = 90
    put(s, 1, 1, f"{backlog['project']}: development backlog", bold=True, size=16, border=False)
    put(s, 2, 1, f"Written from {backlog.get('based_on') or 'v' + str(backlog.get('spec_version'))} · "
                 f"{uat.readable(backlog.get('date'))} · Internal: not for the client", color=GREY, border=False, wrap=False)
    stories = backlog.get("stories") or []
    sized = [x for x in stories if pts[x["id"]]["points"]]
    total = sum(pts[x["id"]]["points"] for x in sized)
    rows = [("Epics", len(backlog.get("epics") or [])), ("User stories", sum(1 for x in stories if (x.get("type") or "Story") == "Story")),
            ("Tasks", sum(1 for x in stories if x.get("type") == "Task")),
            ("Story points", f"{total} on {len(sized)} of {len(stories)} items" if sized else "None yet: see the Points sheet"),
            ("Estimate", backlog.get("estimate") or "None: no story points"),
            ("Gaps for the register", len(gaps))]
    r = 4
    for label, value in rows:
        put(s, r, 1, label, bold=True)
        put(s, r, 2, value)
        r += 1
    if gaps:
        r += 1
        put(s, r, 1, "Gaps found while writing the backlog", bold=True, size=13, border=False)
        for g in gaps:
            r += 1
            put(s, r, 1, "")
            put(s, r, 2, g)

    b = wb.create_sheet("Backlog")
    b.sheet_view.showGridLines = False
    header(b, 1, [("#", 6), ("Type", 8), ("ID", 9), ("Title", 36), ("User story", 50), ("Acceptance criteria", 60),
                  ("Priority", 9), ("Points", 8), ("Requirements", 16), ("Screens", 24), ("Open questions", 14)])
    r = 1
    for n, (epic, members) in enumerate(ordered(backlog), 1):
        r += 1
        points = sum(pts[x["id"]]["points"] or 0 for x in members)
        for c, v in enumerate([str(n), "Epic", epic["id"], epic["title"], epic.get("description") or "", "", "",
                               points or None, epic.get("group") or "", "", ""], 1):
            put(b, r, c, v, bold=c == 4, fill=HEAD_FILL)
        for k, x in enumerate(members, 1):
            r += 1
            values = [f"{n}.{k}", x.get("type") or "Story", x["id"], x.get("title"), user_story(x, m),
                      "\n".join(f"{i}. {a}" for i, a in enumerate(x.get("acceptance") or [], 1)), x.get("priority") or "",
                      pts[x["id"]]["points"], ", ".join(as_list(x.get("requirements"))), ", ".join(screens_of(x, m)),
                      ", ".join(open_questions(x, reg))]
            for c, v in enumerate(values, 1):
                put(b, r, c, v, color=ORANGE if c == 11 and v else INK)
    b.freeze_panes = "D2"
    b.auto_filter.ref = f"A1:K{max(r, 2)}"

    p = wb.create_sheet("Points")
    p.sheet_view.showGridLines = False
    header(p, 1, [("ID", 9), ("Title", 40), ("Estimate lines and share", 50), ("Mandays", 14), ("Points", 8), ("Note", 60)])
    for r, x in enumerate(stories, 2):
        res = pts[x["id"]]
        parts = "\n".join(f"{lid} {(lines.get(lid) or {}).get('item', '')}: {num(share * 100)}%" for lid, share in res["parts"])
        md = md_range(res["low"], res["high"]) if res["low"] is not None else "—"
        for c, v in enumerate([x["id"], x.get("title"), parts, md, res["points"], res["why"]], 1):
            put(p, r, c, v, color=GREY if c == 6 else INK)
    p.freeze_panes = "C2"
    wb.active = 1
    return save(wb, out)


def render_trace(backlog, spec, project, out):
    from openpyxl import Workbook

    put, header = sheet_writer()
    wb = Workbook()
    t = wb.active
    t.title = "Traceability"
    t.sheet_view.showGridLines = False
    put(t, 1, 1, f"{backlog['project']}: requirements traceability", bold=True, size=16, border=False, wrap=False)
    put(t, 2, 1, f"From {backlog.get('based_on') or 'v' + str(backlog.get('spec_version'))} · {uat.readable(backlog.get('date'))}",
        color=GREY, border=False, wrap=False)
    header(t, 4, [("Requirement", 14), ("What it says", 56), ("Priority", 9), ("Screens", 26), ("User stories", 40),
                  ("UAT scenarios", 16), ("Change requests", 30)])
    r = 4
    for rid, text, prio, screens, stories, cases, crs, reason in trace(backlog, spec, project):
        r += 1
        built = "\n".join(stories) or (f"Not built as a story: {reason}" if reason else "")
        for c, v in enumerate([rid, text, prio, "\n".join(screens), built, ", ".join(cases), "\n".join(crs)], 1):
            put(t, r, c, v, color=GREY if c == 5 and not stories else INK)
    t.freeze_panes = "B5"
    t.auto_filter.ref = f"A4:G{max(r, 5)}"
    return save(wb, out)


def render_project_desk(backlog, spec, project, pts, out):
    """The Tasks sheet of Project Desk's task import: columns matched by their header."""
    from openpyxl import Workbook

    m = uat.Model(spec)
    reg = register_items(project)
    put, header = sheet_writer()
    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    header(ws, 1, [("#", 7), ("Title", 44), ("Type", 8), ("Status", 10), ("Priority", 13), ("Story Points", 12),
                   ("Description", 60), ("Acceptance Criteria", 60)])
    r = 1
    for n, (epic, members) in enumerate(ordered(backlog), 1):
        r += 1
        desc = "\n".join(x for x in (epic.get("description") or "", f"Requirements: {epic['group']}" if epic.get("group") else "") if x)
        for c, v in enumerate([str(n), epic["title"], "Epic", "To do", "P3 · Medium", None, desc, None], 1):
            put(ws, r, c, v, border=False)
        for k, x in enumerate(members, 1):
            r += 1
            for c, v in enumerate([f"{n}.{k}", x.get("title"), x.get("type") or "Story", "To do",
                                   PRIORITY_PD.get(x.get("priority"), "P3 · Medium"), pts[x["id"]]["points"],
                                   description(x, m, reg), "\n".join(x.get("acceptance") or []) or None], 1):
                put(ws, r, c, v, border=False)
    return save(wb, out)


def description(story, m, reg, acceptance=False):
    parts = [user_story(story, m)]
    if acceptance and story.get("acceptance"):
        parts.append("Acceptance criteria:\n" + "\n".join(f"{i}. {a}" for i, a in enumerate(story["acceptance"], 1)))
    refs = [f"Requirements: {', '.join(as_list(story.get('requirements')))}" if story.get("requirements") else "",
            f"Screens: {', '.join(screens_of(story, m))}" if story.get("screens") else "",
            f"Waiting on: {', '.join(open_questions(story, reg))}" if open_questions(story, reg) else "",
            f"Story id in Blueprint: {story['id']}"]
    parts.append("\n".join(x for x in refs if x))
    if story.get("notes"):
        parts.append(str(story["notes"]))
    return "\n\n".join(p for p in parts if p)


def render_jira(backlog, spec, project, pts, out):
    m = uat.Model(spec)
    reg = register_items(project)
    label = re.sub(r"\s+", "-", backlog.get("short_name") or "") or None
    rows, n = [], 0
    for epic, members in ordered(backlog):
        n += 1
        parent = n
        rows.append([n, "", "Epic", epic["title"], "\n".join(x for x in (epic.get("description") or "",
                     f"Requirements: {epic['group']}" if epic.get("group") else "") if x), "", "", label or ""])
        for x in members:
            n += 1
            rows.append([n, parent, x.get("type") or "Story", x.get("title"), description(x, m, reg, acceptance=True),
                         PRIORITY_JIRA.get(x.get("priority"), ""), pts[x["id"]]["points"] or "", label or ""])
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Issue ID", "Parent", "Issue Type", "Summary", "Description", "Priority", "Story Points", "Labels"])
        w.writerows(rows)
    return out


def html_text(text):
    return "".join(f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in str(text).split("\n\n") if p.strip())


def render_ado(backlog, spec, project, pts, out, process="agile"):
    """Azure DevOps: a Feature for each epic with its stories under it (Title 1, Title 2); HTML in the text fields."""
    m = uat.Model(spec)
    reg = register_items(project)
    scrum = process == "scrum"
    item_type = "Product Backlog Item" if scrum else "User Story"
    tags = backlog.get("short_name") or ""
    head = ["Work Item Type", "Title 1", "Title 2", "Description"] + (["Acceptance Criteria"] if scrum else []) + \
        ["Effort" if scrum else "Story Points", "Priority", "Tags"]
    rows = []
    for epic, members in ordered(backlog):
        desc = html_text("\n\n".join(x for x in (epic.get("description") or "", f"Requirements: {epic['group']}" if epic.get("group") else "") if x))
        rows.append(["Feature", epic["title"], "", desc] + ([""] if scrum else []) + ["", 2, tags])
        for x in members:
            kind = item_type if (x.get("type") or "Story") == "Story" else "Task"
            criteria = "<ol>" + "".join(f"<li>{html.escape(a)}</li>" for a in x.get("acceptance") or []) + "</ol>" if x.get("acceptance") else ""
            body = html_text(description(x, m, reg))
            if not scrum and criteria:
                body += "<p><b>Acceptance criteria</b></p>" + criteria
            rows.append([kind, "", x.get("title"), body] + ([criteria] if scrum else []) +
                        [pts[x["id"]]["points"] or "", PRIORITY_ADO.get(x.get("priority"), 2), tags])
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(rows)
    return out


# ---------------------------------------------------------------- commands
def report(path, backlog, pts, errors, refine, gaps):
    stories = backlog.get("stories") or []
    sized = [s for s in stories if pts[s["id"]]["points"]]
    print(f"{path.name}: {len(backlog.get('epics') or [])} epics, {len(stories)} stories, "
          f"story points on {len(sized)} ({sum(pts[s['id']]['points'] for s in sized)} in all)")
    why = OrderedDict()
    for s in stories:
        if not pts[s["id"]]["points"]:
            why.setdefault(pts[s["id"]]["why"], []).append(s["id"])
    for reason, ids in why.items():
        print(f"  No points for {', '.join(ids)}: {reason}")
    for s in stories:
        if pts[s["id"]]["points"] and pts[s["id"]]["why"]:
            print(f"  {s['id']}: {pts[s['id']]['why']}")
    if errors:
        print(f"\nTo fix before render ({len(errors)}):")
        print("\n".join(f"  - {e}" for e in errors))
    if refine:
        print(f"\nStill to refine ({len(refine)}):")
        print("\n".join(f"  - {e}" for e in refine))
    if gaps:
        print(f"\nGaps for the register ({len(gaps)}):")
        print("\n".join(f"  - {g}" for g in gaps))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, usage=argparse.SUPPRESS, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft")
    d.add_argument("project")
    d.add_argument("--current", action="store_true")
    d.add_argument("--estimate")
    d.add_argument("--date")
    d.add_argument("--force", action="store_true")
    for name in ("check", "render"):
        c = sub.add_parser(name)
        c.add_argument("project")
        c.add_argument("file", nargs="?")
        if name == "render":
            c.add_argument("--ado-process", choices=("agile", "scrum"), default="agile")
    sub.add_parser("scale")
    for p in sub.choices.values():
        p.add_argument("--knowledge", help=argparse.SUPPRESS)
    a = ap.parse_args()
    kdir = estimate_tool.knowledge_dir(a.knowledge)

    if a.command == "scale":
        scale, problems = read_scale(kdir)
        if scale is None:
            print(f"There is no story-point scale in {kdir / 'building-blocks.md'} yet. Agree the figures with the lead\n"
                  "developer, then add this section to the file (after the Other work table):\n")
            print(SCALE_TABLE)
            return
        print("Story points (mandays up to): " + ", ".join(f"{p}: {num(scale[p])}" if p in scale else f"{p}: TBD" for p in POINTS))
        for problem in problems:
            print(f"  - {problem}")
        return

    project = Path(a.project)
    if not project.is_dir():
        sys.exit(f"No project folder {project}")

    if a.command == "draft":
        try:
            date = dt.date.fromisoformat(a.date).isoformat() if a.date else dt.date.today().isoformat()
        except ValueError:
            sys.exit(f"--date {a.date} is not a date: write it as YYYY-MM-DD")
        if not layout.spec_file(project).exists():
            sys.exit(f"No spec at {layout.spec_file(project)}: build the mock-up first (build-mockup), then the backlog.")
        spec, rel, based_on = uat.choose_spec(project, a.current)
        est = estimate_path(project, a.estimate)
        est_rel = est.resolve().relative_to(project.resolve()).as_posix() if est and project.resolve() in est.resolve().parents else (str(est) if est else None)
        lines, problem = estimate_lines(project, est_rel, kdir)
        backlog = draft(spec, rel, based_on, date, est_rel, lines)
        folder = layout.backlog_source(project)
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{date} backlog v{backlog['spec_version']}.json"
        if out.exists() and not a.force:
            sys.exit(f"{out.name} exists already (it may have been refined since): pass --force to replace it, or refine that one.")
        write_json(out, backlog)
        stories = backlog["stories"]
        print(f"Backlog draft for {backlog['project']}, written from {based_on} ({rel})")
        print(f"  {len(backlog['epics'])} epics, {len(stories)} stories; acceptance criteria from the screens on "
              f"{sum(1 for s in stories if s['acceptance'])} of them, {len(backlog.get('unplaced') or [])} still to place")
        if est_rel:
            linked = {lid for s in stories for lid in s.get('lines', [])}
            print(f"  Estimate: {est_rel}: {len(linked)} of {len(lines)} building-block lines linked by name")
        else:
            print("  No estimate in estimates/: the stories get no story points until one is made ('estimate this project')")
        if problem:
            print(f"  Note: {problem}")
        print(f"  {out}")
        return

    path, backlog, spec, lines, problem = load(project, a.file, kdir)
    errors, refine, gaps = check(backlog, spec, project, lines, problem)
    scale, scale_problems = read_scale(kdir)
    pts = work_out_points(backlog, lines, scale, scale_problems)
    report(path, backlog, pts, errors, refine, gaps)
    if a.command == "check":
        if errors:
            sys.exit(1)
        return
    if errors:
        sys.exit("\nNothing was written: fix the mistakes above first.")
    outs = layout.backlog_outputs(project, path)
    for target in outs.values():
        target.parent.mkdir(parents=True, exist_ok=True)
    made = [("Backlog for the team (internal)", render_internal(backlog, spec, project, pts, gaps, lines, outs["internal"])),
            ("Traceability, for the client", render_trace(backlog, spec, project, outs["traceability"])),
            ("Project Desk import", render_project_desk(backlog, spec, project, pts, outs["project_desk"])),
            ("Jira import", render_jira(backlog, spec, project, pts, outs["jira"])),
            ("Azure DevOps import" + (" (Scrum)" if a.ado_process == "scrum" else ""),
             render_ado(backlog, spec, project, pts, outs["ado"], a.ado_process))]
    print()
    for label, out in made:
        print(f"  {label + ':':34} {out}")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview
        overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
