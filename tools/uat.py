"""User acceptance test (UAT) scripts from the project spec: a draft, its checks, and the files for the testers.

Usage:
    python -I tools/uat.py draft   projects/<slug> [--current] [--date YYYY-MM-DD] [--force]
    python -I tools/uat.py check   projects/<slug> ["<scripts.json>"]
    python -I tools/uat.py render  projects/<slug> ["<scripts.json>"] [--force]
    python -I tools/uat.py results projects/<slug> ["<filled-in workbook.xlsx>"]
    python -I tools/uat.py defects projects/<slug>
    python -I tools/uat.py defect  projects/<slug> D-001 [D-002 ...] <status> [--note "..."] [--cr CR-004]

draft    writes <date> uat scripts v<version>.json into the project's _blueprint/uat/ (uat/ in a project not yet
         moved to the new folder layout) from the spec, the same way every time:
         the main process from start to end (each role in turn: every move made with the button that makes it,
         on its screen, by the role allowed to press it; one main process for each kind of record the statuses
         belong to, such as a plan approved on its screen and its tasks on theirs), every other status move, what each role
         may NOT do in each status, the field checks of every form and dialog, what each role may not open,
         the dashboard figures, the notifications and integrations. Each requirement goes into the scenario that
         tests it when it plainly says what it is about (a field of a form or dialog, saving a draft, sending a
         record on to a role, a button that moves a record, an e-mail when a record reaches a status, what a screen
         shows, adding or changing a list's entries), or gets a scenario written for it; one it cannot tie for
         certain gets a case of its own to refine. A process step no status rule ties to a button is made with
         the button named after it, and a record sent back to its form (a draft, a rejected application the
         status rules let its owner change) goes on with the form's own button. Every case lists its test data:
         the test accounts that sign in, the records its preconditions ask for and how to get one, the files to
         upload, and mailboxes and connections. It works from the version issued to the client last (output/spec-v<version>.yaml),
         because UAT tests what was signed; with nothing issued, or with --current, from spec/app.yaml.
         It refuses to replace a draft of the same name (refined by hand, perhaps) unless --force.
check    every requirement covered by a case or excluded with a reason, case ids unique, every case with
         steps and an expected result for each, roles and screens that exist, nothing internal
render   checks the scripts, then writes into the project's "6 UAT" folder (next to them in the old layout):
           "<name>.xlsx"  the workbook for the testers: one row per step, with Actual result, Pass/Fail,
                          Tester, Date and Defect ref to fill in, a summary of coverage and results, and the
                          Test data sheet: everything the client prepares before UAT (TD-01 ...), with Ready to mark
           "<name>.docx"  the test scripts for the client, in the company's document format, with the test data
                          list and, in each scenario, the test data it uses
         Without a file name it takes the newest scripts in the project's UAT folder.
         When the testers have already filled in steps of that workbook (a result, an actual result, a tester,
         a date or a defect), it stops, because writing it again would lose them; --force writes it anyway and
         first keeps the filled-in workbook as "<name> - results kept <date> <time>.xlsx" beside it
results  reads a workbook the testers filled in, lists the failed and blocked steps, and brings the project's
         defect log up to date: each failed step not logged yet becomes a defect (open), linked to its case,
         step and requirements; a defect fixed or sent for retest that fails again is open again, and one whose
         step now passes is closed. A workbook read before changes nothing. Writes "Defect log.xlsx" into 6 UAT.
defects  lists the defect log and writes "Defect log.xlsx" again
defect   sets the status of defects: open, fixed, retest, closed, "not a defect" (with --note saying why) or
         "change request" (a failure that is really a new wish: take it to the change-request skill, then record
         its CR with --cr). Each change is kept in the defect's history with the date and the note.

uat/<date> uat scripts v<version>.json:
{
  "project": "Leave Request System", "client": "Sample Client Sdn. Bhd.", "spec_version": "0.1",
  "spec": "output/spec-v0.1.yaml",                         the spec it was written from, in the project folder
                                                           (written the old layout's way; read in either)
  "based_on": "the requirements document v0.1, issued on 6 November 2026",
  "date": "2026-11-06",
  "cases": [
    {"id": "UAT-001", "title": "...", "type": "main process", "priority": "High", "roles": ["employee", "manager"],
     "preconditions": ["..."],
     "steps": [{"action": "Sign in as Employee", "expected": "...", "role": "employee", "screen": "login"}],
     "requirements": ["FR-APP-001.1"],
     "test_data": [{"kind": "record", "need": "A record in Draft", "how": "Fill in New Leave Application and press Save as Draft"}],
                                                           kind: account, record, file or other; how is optional
     "source": "status rules: Draft > Pending Approval > Approved",     what in the spec produced it
     "todo": "...", "related": ["UAT-004"]}                             draft only: for Claude, never printed
  ],
  "excluded": [{"requirement": "FR-APP-003.2", "reason": "..."}]       client-facing reason
}

_blueprint/uat/defects/defects.json (uat/defects/ in the old layout), the defect log:
{"project": "leave-request", "defects": [
  {"id": "D-001", "status": "open", "case": "UAT-004", "scenario": "...", "step": 6, "action": "...", "expected": "...",
   "actual": "...", "requirements": ["FR-APP-003.1"], "priority": "High", "tester": "...", "date": "2026-12-10",
   "client_ref": "the testers' Defect ref", "found_in": "<workbook>", "seen_in": ["<workbook>", ...],
   "cr": "CR-004 (when it became a change request)",
   "history": [{"date": "2026-12-10", "status": "open", "note": "Failed in <workbook>"}]}]}

Case types: main process, status change, not allowed, field checks, access, figures, notification,
integration, requirement, edge case. "source", "todo" and "related" are Blueprint's own: they never reach
the workbook or the document. Mandays, rates, cost, internal register items and platform-fit findings go in
neither.
"""
import datetime as dt
import json
import os
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402

TYPES = OrderedDict([
    ("main process", "Main process"), ("status change", "Status changes"), ("not allowed", "What may not be done"),
    ("field checks", "Field checks"), ("access", "Access"), ("figures", "Figures"), ("notification", "Notifications"),
    ("integration", "Integrations"), ("edge case", "Exceptions and edge cases"), ("requirement", "Other requirements"),
])
PRIORITIES = ("High", "Medium", "Low")
RESULTS = ("Pass", "Fail", "Blocked", "Not run")
DRAFT_ONLY = ("source", "todo", "related")
# What a scenario needs before it starts ("test_data"), by kind, in the order the test data list shows them.
DATA_KINDS = OrderedDict([("account", "Test account"), ("record", "Record"), ("file", "File"), ("other", "Other")])
DATA_SHEET = "Test data"
# A defect's status in the project's defect log, in the order a defect goes through them.
DEFECT_STATUSES = OrderedDict([
    ("open", "red"), ("fixed", "accent"), ("retest", "orange"), ("closed", "green"), ("not a defect", "grey"),
    ("change request", "grey"),
])
NEGATIVE = re.compile(r"reject|cancel|return|withdr|declin|void|fail|delet|revok|terminat|suspend|abandon|expire|lost", re.I)
INTERNAL_WORDS = re.compile(r"\bman-?days?\b|\bday rates?\b|\brate card\b|\bplatform[_ ]fit\b|\bbuilding blocks?\b|\beffort impact\b", re.I)
REF = re.compile(r"\{ref:([a-z]+):([^}]+)\}")
STEPS_SHEET = "Test steps"
STEP_COLUMNS = [  # (header, width, filled in by the testers)
    ("Case", 10, False), ("Scenario", 34, False), ("Priority", 9, False), ("Role", 16, False), ("Preconditions", 34, False),
    ("Test data", 14, False), ("Step", 6, False), ("Screen", 20, False), ("Action", 46, False), ("Expected result", 46, False),
    ("Requirements", 16, False), ("Actual result", 34, True), ("Pass/Fail", 10, True), ("Tester", 16, True),
    ("Date", 12, True), ("Defect ref", 12, True),
]


# ---------------------------------------------------------------- small helpers
def as_list(value):
    if value is None or value == "":
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def readable(date):
    """2026-11-06 as 6 November 2026; anything else as it is."""
    try:
        d = dt.date.fromisoformat(str(date)[:10])
    except ValueError:
        return str(date)
    return f"{d.day} {d:%B %Y}"


def join_words(words, last="and"):
    words = [str(w) for w in words if w]
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} {last} {words[-1]}" if words else ""


def load_yaml(path):
    import yaml

    return json.loads(json.dumps(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}, default=str))


def read_register(project):
    import layout

    path = layout.register_json(project)
    if not path.exists():
        return []
    try:
        return [it for it in json.loads(path.read_text(encoding="utf-8")).get("items", []) if isinstance(it, dict)]
    except ValueError:
        return []


def choose_spec(project, current=False):
    """(spec, path relative to the project, what it is in words): the version issued last, unless --current."""
    import layout
    import project as project_tool

    project = Path(project)
    if not current:
        for record in reversed(project_tool.load_issues(project)):
            snap = layout.snapshot(project, record.get("version"))
            if snap.exists():
                spec = load_yaml(snap)
                # Recorded the old layout's way, which tools/layout.py reads in either layout.
                return spec, f"output/spec-v{record.get('version')}.yaml", (
                    f"the requirements document v{record['version']}, issued on {readable(record.get('date', ''))}")
    path = layout.spec_file(project)
    if not path.exists():
        sys.exit(f"No spec at {path}: build the mock-up first (build-mockup), then write the UAT scripts.")
    spec = load_yaml(path)
    version = (spec.get("project") or {}).get("version", "")
    return spec, "spec/app.yaml", f"the requirements v{version}, not yet issued" if version else "the current requirements"


def requirement_ids(spec):
    """{id: (group, text, priority, tbc)} for every numbered item, and for a group without items the group."""
    out = OrderedDict()
    for g in spec.get("requirements") or []:
        if not isinstance(g, dict) or not g.get("id"):
            continue
        items = g.get("items") or []
        if not items:
            out[str(g["id"])] = (g, g.get("title", ""), g.get("priority"), None)
        for n, item in enumerate(items, 1):
            text = item.get("text", "") if isinstance(item, dict) else item
            prio = (item.get("priority") if isinstance(item, dict) else None) or g.get("priority")
            out[f"{g['id']}.{n}"] = (g, str(text or ""), prio, item.get("tbc") if isinstance(item, dict) else None)
    return out


def group_of(req_id):
    return re.sub(r"\.\d+$", "", req_id)


# ---------------------------------------------------------------- reading the spec
class Model:
    def __init__(self, spec):
        self.spec = spec
        self.roles = [r for r in spec.get("roles") or [] if isinstance(r, dict) and r.get("id")]
        self.role = {r["id"]: r for r in self.roles}
        self.statuses = [s for s in spec.get("statuses") or [] if isinstance(s, dict) and s.get("id")]
        self.by_key = {}
        for s in self.statuses:
            self.by_key[str(s["id"]).lower()] = s
            self.by_key.setdefault(str(s.get("name") or s["id"]).lower(), s)
        self.screens = [s for s in spec.get("screens") or [] if isinstance(s, dict) and s.get("id")]
        self.screen = {s["id"]: s for s in self.screens}
        self.dialog = {d["id"]: d for d in spec.get("dialogs") or [] if isinstance(d, dict) and d.get("id")}
        self.data = spec.get("data") if isinstance(spec.get("data"), dict) else {}
        P = spec.get("project") or {}
        self.names = {"system": str(P.get("name", "")), "client": str(P.get("client", "")),
                      "client_short": str(P.get("client_short") or P.get("client", ""))}
        co = workspace.company()
        self.names.update(company=str(co.get("name", "")), company_short=str(co.get("short_name") or co.get("name", "")))
        self.main = self.main_list()
        self._movers = None
        self.made = self.new_records()
        # More than one kind of record carries the statuses (a plan and its tasks, say): each moves on its own screens.
        self.several = len({k for s in self.statuses for k in self.kinds(s["id"], fallback=False)}) > 1

    # ---- words
    def text(self, value):
        """Spec text as the client reads it: names filled in, references made plain."""
        out = str(value or "")
        for k, v in self.names.items():
            out = out.replace("{" + k + "}", v)

        def sub(m):
            kind, key = m.group(1), m.group(2)
            if kind == "screen":
                return self.title(key)
            if kind == "role":
                return self.role_name(key)
            if kind == "req":
                return key
            return "the requirements document"
        return REF.sub(sub, out)

    def role_name(self, rid):
        return str((self.role.get(rid) or {}).get("name") or rid)

    def role_id(self, value):
        """A role id from an id or a name (the process flow names roles either way), or None."""
        if value is None:
            return None
        want = str(value).strip().lower()
        return next((r["id"] for r in self.roles if want in (str(r["id"]).lower(), str(r.get("name") or "").strip().lower())), None)

    def noun(self, kind=None):
        """What a record is called in the scripts: "record", or the kind (plan, task) when there are several kinds."""
        if not self.several or not kind:
            return "record"
        word = str(kind).replace("_", " ").replace("-", " ").strip()
        if word.endswith("ies"):
            return word[:-3] + "y"
        if re.search(r"(ch|sh|ss|x)es$", word):
            return word[:-2]
        return word[:-1] if word.endswith("s") and not word.endswith("ss") else word

    def a(self, kind=None):
        """"a record", "a plan", "an application"."""
        noun = self.noun(kind)
        return f"{'an' if noun[:1].lower() in 'aeiou' else 'a'} {noun}"

    def origin(self, kind):
        """The status a record of that kind starts in: the first of its statuses no other status leads to, or None."""
        if not kind:
            return None
        targets = {n for s in self.statuses for n in self.nexts(s["id"])}
        return next((s["id"] for s in self.statuses if s["id"] not in targets and kind in self.kinds(s["id"], fallback=False)
                     and not self.negative(s["id"])), None)

    def title(self, sid):
        return self.text((self.screen.get(sid) or {}).get("title") or sid)

    def sid(self, value):
        """A status id from an id or a name, or None."""
        s = self.by_key.get(str(value).lower()) if value is not None else None
        return s["id"] if s else None

    def sname(self, status_id):
        s = self.by_key.get(str(status_id).lower())
        return str(s.get("name") or s["id"]) if s else str(status_id)

    def status(self, status_id):
        return self.by_key.get(str(status_id).lower()) or {}

    def nexts(self, status_id):
        return [self.sid(n) for n in as_list(self.status(status_id).get("next")) if self.sid(n)]

    def negative(self, status_id):
        s = self.status(status_id)
        return s.get("color") == "red" or bool(NEGATIVE.search(f"{s.get('id', '')} {s.get('name', '')}"))

    def allowed(self, status_id, rule):
        """The role ids a status rule allows, or None when the rule is not set."""
        s = self.status(status_id)
        if rule not in s or s[rule] is None:
            return None
        value = s[rule]
        if value == "all":
            return {r["id"] for r in self.roles}
        if value in ("none", "", []):
            return set()
        return {str(v) for v in as_list(value)}

    # ---- screens
    def can_open(self, rid, sid):
        roles = (self.screen.get(sid) or {}).get("roles")
        return not roles or rid in as_list(roles)

    def openers(self, sid):
        return [r["id"] for r in self.roles if self.can_open(r["id"], sid)]

    def menu(self, rid):
        return [self.text(s["menu"]) for s in self.screens if s.get("menu") and self.can_open(rid, s["id"])]

    def main_list(self):
        """The data list whose records carry the statuses: the one the workflow moves."""
        best, score = None, 0
        for name, rows in self.data.items():
            rows = [r for r in rows or [] if isinstance(r, dict)]
            hits = sum(1 for r in rows if self.sid(r.get("status")))
            if hits > score:
                best, score = name, hits
        return best

    def list_of(self, scr):
        return scr.get("data") or (scr.get("list") or {}).get("data")

    def kinds(self, status_id, fallback=True):
        """The data lists whose records can be in this status: those of the buttons that move a record into or out
        of it, and of the sample records in it. With nothing to go by, the main list (unless fallback is False)."""
        out = [x["data"] for x in self.movers() if x["data"] and status_id in (x["from"], x["to"])]
        out += [name for name, rows in self.data.items() if isinstance(rows, list)
                and any(isinstance(r, dict) and self.sid(r.get("status")) == status_id for r in rows)]
        out = list(dict.fromkeys(out))
        return out or ([self.main] if fallback and self.main else [])

    def kind_of(self, status_id, prefer=None):
        ks = self.kinds(status_id)
        return prefer if prefer in ks else (ks[0] if ks else None)

    def record(self, status_id, kind=None):
        """The id of a sample record of that kind in this status, or None."""
        for name in [kind] if kind else self.kinds(status_id):
            for r in self.data.get(name) or []:
                if isinstance(r, dict) and r and self.sid(r.get("status")) == status_id:
                    return str(next(iter(r.values())))
        return None

    def detail_for(self, rid, kind=None):
        """The screen a role opens a record of that kind (by default the main list's) on."""
        kind = kind or self.main
        for stype in ("detail", "form"):
            for s in self.screens:
                if s.get("type") == stype and s.get("data") == kind and self.can_open(rid, s["id"]) and not self.creates_on(s["id"]):
                    return s["id"]
        return None

    def creates_on(self, sid):
        """True for a form opened empty, to add a record: it never shows one."""
        return any(n["screen"] == sid for n in self.made)

    def viewers(self, kind=None):
        return [r["id"] for r in self.roles if self.detail_for(r["id"], kind)]

    def links_to(self, sid):
        """(screen, label, roles, how) of every row action ("action"), toolbar button or other button that opens this
        screen: a list with the screen's own records first, other lists next, then the rest (dashboards, forms)."""
        out = []
        target = (self.screen.get(sid) or {}).get("data")
        for s in self.screens:
            lst = s.get("list") or {}
            for b, how in ([(a, "action") for a in lst.get("actions") or []] + [(t, "toolbar") for t in lst.get("toolbar") or []]
                           + [(b, "button") for b in s.get("buttons") or []]):
                if isinstance(b, dict) and b.get("to") == sid and s["id"] != sid:
                    rank = 0 if s.get("type") == "list" and lst.get("data") == target else 1 if s.get("type") == "list" else 2
                    out.append((rank, len(out), (s["id"], str(b.get("label", "")), as_list(b.get("roles")), how)))
        return [link for _, _, link in sorted(out)]

    def open_steps(self, sid, rid, rec=None, seen=()):
        """The steps that take a role to a screen (on a record), as (action, expected, screen). A record is found in
        its list and opened with the row's action; a toolbar or screen button is just pressed."""
        scr = self.screen.get(sid) or {}
        shows = f"{self.title(sid)} opens" + (f", showing {rec}" if rec and scr.get("type") in ("detail", "form") else "")
        if scr.get("menu") and self.can_open(rid, sid):
            return [(f"Open {self.text(scr['menu'])} from the side menu", shows, sid)]
        for parent, label, roles, how in self.links_to(sid):
            if parent in seen or (roles and rid not in roles) or not self.can_open(rid, parent):
                continue
            before = self.open_steps(parent, rid, None, seen + (sid,))
            if before and before[0][0].startswith("Open ") and "side menu" in before[0][0]:
                if how == "action":
                    kind = (self.screen[parent].get("list") or {}).get("data")
                    return before + [(f"Find {rec or 'the ' + self.noun(kind)} and press {label}", shows, sid)]
                return before + [(f"Press {label}", shows, sid)]
        return [(f"Open {self.title(sid)}", shows, sid)]

    def sign_in(self, rid):
        menu = self.menu(rid)
        login = next((s["id"] for s in self.screens if s.get("type") == "login"), None)
        step = {"action": f"Sign in as {self.role_name(rid)}",
                "expected": f"Signed in. The side menu shows {join_words(menu)}" if menu else "Signed in",
                "role": rid}
        if login:
            step["screen"] = login
        return step

    # ---- what moves a record
    def new_records(self):
        """Every button that adds a record, as the mock-up finds them (tools/mockup.py new_records):
        [{screen, button, data, status}], `data` the list the record joins and `status` the status it starts in."""
        import mockup

        out = []
        for n in mockup.new_records(self.spec):
            scr = self.screen.get(n.get("screen")) or {}
            button = next((b for b in scr.get("buttons") or [] if isinstance(b, dict) and str(b.get("label", "")) == str(n.get("label", ""))), None)
            if button is not None:
                out.append({"screen": scr["id"], "button": button, "data": n.get("data"),
                            "status": self.sid(n["status"]) if n.get("status") else None})
        if not out:  # nothing ties a form to a list: a form opened empty, with a main button, still adds a record
            for s in self.screens:
                if s.get("type") != "form" or (s.get("data") and s.get("data") != self.main) or s.get("record"):
                    continue
                button = next((b for b in s.get("buttons") or [] if isinstance(b, dict) and b.get("style") == "primary"
                               and not b.get("when")), None)
                if button:
                    out.append({"screen": s["id"], "button": button, "data": s.get("data"), "status": self.sid(button.get("set_status"))
                                if isinstance(button.get("set_status"), (str, int)) else None})
                    break
        return out

    def movers(self):
        """Every button, dialog confirm or row action that moves a record: {from, to, screen, label, dialog, roles,
        toast, data, creates}. `data` is the list of the record it moves (the record kind): the screen's `data` for a
        button on a detail screen or form, the list's for a row action; `creates` is True for a button that adds a
        new record (its `from` is then None)."""
        if self._movers is not None:
            return self._movers
        creating = {(n["screen"], str(n["button"].get("label", ""))): n for n in self.made}
        out = []
        for scr in self.screens:
            lst = scr.get("list") or {}
            holds = scr.get("data") if scr.get("type") in ("detail", "form") and scr.get("data") in self.data else None
            for b, how in [(b, "button") for b in scr.get("buttons") or []] + [(a, "action") for a in lst.get("actions") or []]:
                if not isinstance(b, dict):
                    continue
                dlg = self.dialog.get(b.get("dialog")) if b.get("dialog") else None
                confirm = (dlg or {}).get("confirm") or {}
                roles = [r for r in as_list(b.get("roles")) or self.openers(scr["id"]) if self.can_open(r, scr["id"])]
                toast = confirm.get("toast") if dlg else b.get("toast")
                new = creating.get((scr["id"], str(b.get("label", "")))) if how == "button" else None
                if new:
                    if new["status"]:
                        out.append({"from": None, "to": new["status"], "screen": scr["id"], "label": str(b.get("label", "")),
                                    "dialog": dlg, "roles": roles, "toast": toast, "data": new["data"], "creates": True})
                    continue
                target = b.get("set_status") or confirm.get("set_status")
                if not target:
                    continue
                when = b.get("when") if isinstance(b.get("when"), dict) else {}
                froms = as_list(when.get("status"))
                if not froms and how == "action":
                    froms = as_list((lst.get("where") or {}).get("status"))
                froms = [self.sid(f) for f in froms if self.sid(f)] or [None]
                pairs = ([(self.sid(k), self.sid(v)) for k, v in target.items()] if isinstance(target, dict)
                         else [(f, self.sid(target)) for f in froms])
                for f, t in pairs:
                    if t:
                        out.append({"from": f, "to": t, "screen": scr["id"], "label": str(b.get("label", "")), "dialog": dlg,
                                    "roles": roles, "toast": toast, "data": lst.get("data") if how == "action" else holds,
                                    "creates": False, "row": how == "action"})
        self._movers = out
        return out

    def mover(self, frm, to, kind=None):
        """The button that moves a record (of that kind) from one status to the other: one shown in that status
        first, then one shown in any status when the status rules allow the move. Never a button that adds a record."""
        found = [x for x in self.movers() if not x["creates"] and x["to"] == to and (kind is None or x["data"] in (kind, None))]
        return (next((x for x in found if x["from"] == frm), None)
                or next((x for x in found if x["from"] is None and to in self.nexts(frm)), None))

    def path(self, frm, to, kind=None):
        """The shortest way through the buttons from one status to another, as [(from, to, mover)], without passing
        through a rejection or cancellation; [] when they are the same, None when no buttons lead there."""
        if frm == to:
            return []
        queue, seen = [(frm, [])], {frm}
        while queue:
            at, route = queue.pop(0)
            ahead = self.nexts(at) + [x["to"] for x in self.movers() if x["from"] == at and not x["creates"]]
            for nxt in dict.fromkeys(ahead):
                mv = self.mover(at, nxt, kind) if nxt not in seen else None
                if not mv:
                    continue
                if nxt == to:
                    return route + [(at, nxt, mv)]
                seen.add(nxt)
                if not self.negative(nxt):
                    queue.append((nxt, route + [(at, nxt, mv)]))
        return None

    def creation(self, kind=None, status=None):
        """{screen, button, data, status, role} of the form that adds a record (of that kind): the button that starts it
        in that status if there is one, else the form's main button; None when nothing adds one."""
        found = [n for n in self.made if kind is None or n["data"] in (kind, None)]
        pick = (next((n for n in found if status and n["status"] == status), None)
                or next((n for n in found if n["button"].get("style") == "primary"), None) or (found[0] if found else None))
        if not pick:
            return None
        roles = self.openers(pick["screen"])
        return dict(pick, role=roles[0] if roles else (self.roles[0]["id"] if self.roles else None))

    def form_fields(self, scr):
        return [f for sec in scr.get("sections") or [] if isinstance(sec, dict) for f in sec.get("fields") or [] if isinstance(f, dict)]

    def shown_fields(self, scr):
        """The fields a screen shows: its own sections, or those of the form it takes them from (fields_from)."""
        own = self.form_fields(scr)
        if own or not scr.get("fields_from"):
            return own
        return self.form_fields(self.screen.get(scr["fields_from"]) or {})

    def named_button(self, name, kind=None, rid=None):
        """The button that does a process step no status rule ties to a button: one whose label is the step's name,
        or starts it ("Approve" for "Approve and release"), on a screen of that kind of record, that the role may
        press. As a mover {screen, label, dialog, roles, toast, data, row, creates}, or None. A button that only
        goes to another screen never counts."""
        want = re.sub(r"\s+", " ", str(name or "").strip().lower())
        if not want:
            return None
        for scr in self.screens:
            if self.creates_on(scr["id"]) or (kind and scr.get("data") not in (kind, None)
                                              and (scr.get("list") or {}).get("data") not in (kind, None)):
                continue
            lst = scr.get("list") or {}
            for b, row in [(b, False) for b in scr.get("buttons") or []] + [(a, True) for a in lst.get("actions") or []]:
                if not isinstance(b, dict) or not (b.get("dialog") or b.get("toast") or b.get("set_status")):
                    continue
                label = re.sub(r"\s+", " ", str(b.get("label") or "").strip().lower())
                if not label or not (label == want or want.startswith(label + " ") or label.startswith(want + " ")):
                    continue
                roles = [r for r in as_list(b.get("roles")) or self.openers(scr["id"]) if self.can_open(r, scr["id"])]
                if rid and roles and rid not in roles:
                    continue
                dlg = self.dialog.get(b.get("dialog")) if b.get("dialog") else None
                return {"from": None, "to": None, "screen": scr["id"], "label": str(b.get("label")), "dialog": dlg, "roles": roles,
                        "toast": ((dlg or {}).get("confirm") or {}).get("toast") if dlg else b.get("toast"),
                        "data": lst.get("data") if row else scr.get("data"), "creates": False, "row": row}
        return None

    def roles_in(self, low):
        """The role ids a (lower-case) text names, in the order it names them."""
        found = []
        for r in self.roles:
            for word in (str(r.get("name") or ""), str(r["id"])):
                hit = re.search(rf"\b{re.escape(word.lower())}s?\b", low) if len(word) >= 3 else None
                if hit:
                    found.append((hit.start(), r["id"]))
                    break
        return [rid for _, rid in sorted(found)]

    def statuses_in(self, low):
        """The status ids a (lower-case) text names: by name, or by the first word of a longer name ("pending")."""
        out = []
        for s in self.statuses:
            name = str(s.get("name") or s["id"]).lower()
            words = [name] + ([name.split()[0]] if " " in name and len(name.split()[0]) >= 4 else [])
            if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
                out.append(s["id"])
        return out


# ---------------------------------------------------------------- the draft
class Draft:
    def __init__(self, spec):
        self.m = Model(spec)
        self.cases = []
        self.records = {}  # precondition text -> (status id, record kind): the records the test data list asks for

    def add(self, title, kind, roles, steps, source, priority="Medium", preconditions=(), requirements=(), todo=None, keys=(),
            moves=(), needs=()):
        """A case. `moves` are the (from, to, button label) it makes, so a requirement about that move can be linked
        to it; `needs` is test data the steps do not show (a mailbox, a connection, a record about to fall due)."""
        if any(c["title"].lower() == title.lower() for c in self.cases) or not steps:
            return None
        case = {"id": "", "title": title, "type": kind, "priority": priority, "roles": [r for r in dict.fromkeys(roles) if r],
                "preconditions": list(dict.fromkeys(preconditions)), "steps": steps, "requirements": list(requirements), "source": source}
        if todo:
            case["todo"] = todo
        case["_keys"] = {str(k).lower() for k in keys if k and len(str(k)) >= 4}
        case["_moves"] = list(moves)
        case["_needs"] = list(needs)
        self.cases.append(case)
        return case

    def titled(self, title):
        return next((c for c in self.cases if c["title"].lower() == title.lower()), None)

    @staticmethod
    def link(case, rid):
        if rid not in case["requirements"]:
            case["requirements"].append(rid)

    @staticmethod
    def step(action, expected, screen=None, role=None):
        s = {"action": action, "expected": expected}
        if screen:
            s["screen"] = screen
        if role:
            s["role"] = role
        return s

    def open(self, sid, rid, rec=None):
        return [self.step(a, e, s) for a, e, s in self.m.open_steps(sid, rid, rec)]

    def press(self, mover, to, rec=None, fill_note=True):
        """Steps that press a moving button, through its dialog when it has one; a row action on the record's row."""
        m = self.m
        after = (f'A message like "{m.text(mover["toast"])}" appears. ' if mover.get("toast") else "") + f"The status is now {m.sname(to)}."
        dlg = mover.get("dialog")
        action = (f"Find {rec or 'the ' + m.noun(mover.get('data'))} and press {mover['label']}" if mover.get("row")
                  else f"Press {mover['label']}")
        if not dlg:
            return [self.step(action, after, mover["screen"])]
        steps = [self.step(action, f"The {m.text(dlg.get('title') or 'confirmation')} window opens", mover["screen"])]
        required = [m.text(f.get("label") or f.get("id")) for f in dlg.get("fields") or [] if isinstance(f, dict) and f.get("required")]
        optional = [m.text(f.get("label") or f.get("id")) for f in dlg.get("fields") or [] if isinstance(f, dict) and not f.get("required")]
        if fill_note and (required or optional):
            steps.append(self.step(f"Fill in {join_words(required or optional)}", "The text is accepted", mover["screen"]))
        steps.append(self.step(f"Press {m.text((dlg.get('confirm') or {}).get('label') or 'OK')}", after, mover["screen"]))
        return steps

    def precondition(self, status_id, kind=None):
        m = self.m
        kind = kind or m.kind_of(status_id)
        rec = m.record(status_id, kind)
        if rec:
            text = f"{m.a(kind).capitalize()} in {m.sname(status_id)}, for example {rec}"
        else:
            made = self.creation_note(status_id, kind)
            text = f"{m.a(kind).capitalize()} in {m.sname(status_id)}" + (f" ({made})" if made else "")
        self.records[text] = (status_id, kind)
        return text

    def creation_note(self, status_id, kind=None):
        m = self.m
        made = m.creation(kind, status_id)
        if not made:
            return ""
        if made["status"] == status_id:
            return f"fill in {m.title(made['screen'])} and press {made['button'].get('label')}"
        draft = next((b for b in m.screen[made["screen"]].get("buttons") or [] if isinstance(b, dict)
                      and "draft" in str(b.get("label", "")).lower()), None)
        if draft and "draft" in f"{status_id} {m.sname(status_id)}".lower():
            return f"fill in {m.title(made['screen'])} and press {draft['label']}"
        return ""

    # ---- (a) the main process
    def stages(self):
        """[(status id or None, role id or None, step name)] of the main process, the first being where a record starts."""
        m = self.m
        flow = m.spec.get("process_flow") if isinstance(m.spec.get("process_flow"), dict) else {}
        steps = [s for s in flow.get("steps") or [] if isinstance(s, dict)]
        if steps:
            return [(m.sid(s.get("status")), m.role_id(s.get("role")), s.get("name")) for s in steps]
        if not m.statuses:
            return []
        targets = {n for s in m.statuses for n in m.nexts(s["id"])}
        start = next((s["id"] for s in m.statuses if s["id"] not in targets), m.statuses[0]["id"])
        path = [start]
        while True:
            forward = [n for n in m.nexts(path[-1]) if not m.negative(n) and n not in path]
            if not forward:
                break
            path.append(forward[0])
        if len(path) > 1 and "draft" in f"{start} {m.sname(start)}".lower():
            path = path[1:]  # the main button sends a new record straight on; saving a draft is a case of its own
        return [(p, None, None) for p in path]

    def chains(self, stages):
        """The stages split by the kind of record they move: [(data list or None, stages)], in the order each kind
        first comes up. A plan approved on its screen and its tasks done on theirs are two processes."""
        m = self.m
        chains, current = OrderedDict(), None
        for stage in stages:
            st = stage[0]
            ks = m.kinds(st) if st else []
            if ks and current is None and None in chains:
                chains[ks[0]] = chains.pop(None)
                current = ks[0]
            elif ks and current not in ks:
                current = next((k for k in ks if k in chains), ks[0])
            chains.setdefault(current, []).append(stage)
        return list(chains.items())

    def main_process(self):
        stages = self.stages()
        if not stages:
            return set()
        chains = self.chains(stages)
        moves = set()
        for n, (kind, chain) in enumerate(chains):
            moves |= self.process(kind, chain, n == 0, [k for k, _ in chains[:n]])
        return moves

    def process(self, kind, chain, first, before):
        """One main process: a record of one kind from where it starts to the end, each move made with the button
        that makes it, on its own screen, by the role allowed to press it."""
        m = self.m
        noun = m.noun(kind)
        steps, roles, keys, todo, moves, pre, made_moves = [], [], [], [], set(), [], []
        start, start_role, _ = chain[0]
        made = m.creation(kind, start)
        begin = made["status"] if made and made["status"] else m.origin(kind)
        if start and begin and begin != start and m.path(begin, start, kind):
            chain = [(begin, None, None)] + list(chain)  # it starts in an earlier status and is moved on from there
            start = begin
        if made and start and made["status"] and made["status"] != start:
            made = None
        if not first:
            made = None  # a record of a later kind is picked up where the first one's process leaves it
        creator = start_role or (made["role"] if made else None)
        actor, rec = None, None
        if made:
            form, button = made["screen"], made["button"]
            fields = m.form_fields(m.screen[form])
            required = [m.text(f.get("label")) for f in fields if f.get("required") and not f.get("readonly")]
            filled = [m.text(f.get("label")) for f in fields if f.get("readonly") and (f.get("default") or f.get("source"))]
            steps += [self.step(**m.sign_in(creator))] + self.open(form, creator)
            steps.append(self.step(f"Fill in every required field with valid data: {join_words(required)}" if required
                                   else "Fill in the form with valid data",
                                   "Each value is accepted" + (f". {join_words(filled)} {'is' if len(filled) == 1 else 'are'} filled in already" if filled else ""),
                                   form))
            after = (f'A message like "{m.text(button["toast"])}" appears. ' if button.get("toast") else "")
            saved = made["status"] or start
            after += f"The {noun} is saved with status {m.sname(saved)}" if saved else f"The {noun} is saved"
            steps.append(self.step(f"Press {button.get('label', 'Submit')}", after, form))
            keys += [button.get("label"), m.title(form)]
            actor = creator
        elif start:
            pre.append(self.precondition(start, kind))
            rec = m.record(start, kind)
            if before:
                todo.append(f"this {noun} moves on its own screens, apart from the {join_words([m.noun(k) for k in before])}: "
                            f"say in the preconditions what that must be in for the {noun} to start")
        roles.append(creator)
        visited = [s for s in [start] if s]  # every status the record passes through, the ones in between too
        for (frm, _, _), (to, hint, name) in zip(chain, chain[1:]):
            route = m.path(frm, to, kind) if frm and to else None
            if route:
                for n, (a, b, mv) in enumerate(route):
                    allowed = mv["roles"]
                    if n == len(route) - 1 and hint and (not allowed or hint in allowed):
                        rid = hint
                    else:
                        rid = (allowed[0] if allowed else None) or hint or self.rule_role(a, b)
                    if rid != actor or not rid:
                        steps.append(self.step(**m.sign_in(rid)) if rid else self.step("Sign in as the person who does the next step", "Signed in"))
                        actor = rid
                    steps += self.open(mv["screen"], rid, rec) + self.press(mv, b, rec)
                    keys.append(mv["label"])
                    roles.append(rid)
                    moves.add((a, b))
                    made_moves.append((a, b, mv["label"]))
                    visited.append(b)
                continue
            rid = hint or self.rule_role(frm, to)
            named = m.named_button(name, kind, rid) if name and to else None
            if named:  # a button named after the step does it, though no status rule ties it to the move
                rid = rid or (named["roles"][0] if named["roles"] else None)
                roles.append(rid)
                if rid != actor or not rid:
                    steps.append(self.step(**m.sign_in(rid)) if rid else self.step("Sign in as the person who does the next step", "Signed in"))
                    actor = rid
                steps += self.open(named["screen"], rid, rec) + self.press(named, to, rec)
                keys.append(named["label"])
                if frm:
                    moves.add((frm, to))
                    made_moves.append((frm, to, named["label"]))
                visited.append(to)
                continue
            roles.append(rid)
            if rid != actor or not rid:
                steps.append(self.step(**m.sign_in(rid)) if rid else self.step("Sign in as the person who does the next step", "Signed in"))
                actor = rid
            where = m.detail_for(rid, kind) if rid else None
            if where:
                steps += self.open(where, rid, rec)
            steps.append(self.step(f"Complete the step '{name}'" if name else f"Send the {noun} on to {m.sname(to)}",
                                   f"The status is now {m.sname(to)}" if to else "The step is recorded", where))
            elsewhere = [x for x in m.movers() if to and x["to"] == to and not x["creates"] and (kind is None or x["data"] in (kind, None))]
            if frm and elsewhere:
                froms = join_words([m.sname(x["from"]) for x in elsewhere if x["from"]], "or") or "another status"
                todo.append(f"no button in the mock-up moves {m.a(kind)} from {m.sname(frm)} to {m.sname(to)} "
                            f"({elsewhere[0]['label']} on {m.title(elsewhere[0]['screen'])} does it from {froms}): write how it is done")
            else:
                todo.append(f"no button in the mock-up does '{name or m.sname(to)}': write how it is done")
            if frm and to:
                moves.add((frm, to))
            if to:
                visited.append(to)
        last = chain[-1][0]
        looker = creator or next((r for r in roles if r), None)
        if looker and last and len(chain) > 1:
            look = m.detail_for(looker, kind)
            if looker != actor:
                steps.append(self.step(**m.sign_in(looker)))
            if look:
                steps += self.open(look, looker, rec)
                history = " Its history shows each step, who did it and when." if (m.screen[look].get("timeline")) else ""
                steps[-1]["expected"] += f". Its status is {m.sname(last)}.{history}"
            else:
                steps[-1]["expected"] += f". The {noun} is listed with status {m.sname(last)}"
        path = [m.sname(s) for s in visited]
        span = f"from {m.sname(chain[0][0]) if chain[0][0] else 'start'} to {m.sname(last) if last else 'end'}"
        self.add(f"Main process: the {noun}, {span}" if m.several and kind else f"Main process: {span}",
                 "main process", roles, steps, "status rules: " + " > ".join(path) if path else "process flow", "High", pre,
                 todo="; ".join(todo) or None, keys=keys + path, moves=made_moves)
        return moves

    def rule_role(self, frm, to):
        m = self.m
        rules = (["cancel"] if m.negative(to) and "cancel" in f"{to} {m.sname(to)}".lower() else []) + ["edit"]
        for rule in rules:
            allowed = m.allowed(frm, rule) if frm else None
            if allowed:
                return next((r["id"] for r in m.roles if r["id"] in allowed), None)
        return None

    # ---- (b) the other status moves and the status rules
    def status_moves(self, done):
        m = self.m
        for s in m.statuses:
            frm = s["id"]
            for to in m.nexts(frm):
                if (frm, to) in done:
                    continue
                kind = next((k for k in m.kinds(frm) if k in m.kinds(to)), m.kind_of(frm))
                noun = m.noun(kind)
                if to in [m.sid(a) for a in as_list(s.get("auto"))]:  # the system moves it on its own
                    steps = [self.step(f"Wait for the condition that moves {m.a(kind)} from {m.sname(frm)} to {m.sname(to)}",
                                       f"The system moves it to {m.sname(to)} on its own, without anyone pressing a button"),
                             self.step(f"Open the {noun}", f"The status is {m.sname(to)}")]
                    self.add(f"Automatic: from {m.sname(frm)} to {m.sname(to)}", "status change", [], steps,
                             f"status rules: {m.sname(frm)} moves to {m.sname(to)} automatically", "High", [self.precondition(frm, kind)],
                             todo=f"write the condition from the requirements (a date or event), and how the tester brings it about",
                             keys=[m.sname(frm), m.sname(to), "automatic"], moves=[(frm, to, None)],
                             needs=[{"kind": "record", "need": f"{m.a(kind).capitalize()} in {m.sname(frm)} that will meet the condition "
                                     f"for {m.sname(to)} during UAT",
                                     "how": "prepare it before UAT so the condition falls on a test day (a date due then, or the event "
                                            "staged), or agree with the team how the testers bring the condition about"}])
                    continue
                mover = m.mover(frm, to, kind)
                rid = (mover["roles"][0] if mover and mover["roles"] else None) or self.rule_role(frm, to)
                rec = m.record(frm, kind)
                steps = [self.step(**m.sign_in(rid))] if rid else []
                todo = None
                again = None if mover else self.resubmit(frm, to, kind)
                if mover:
                    steps += self.open(mover["screen"], rid, rec) + self.press(mover, to, rec)
                    title = f"{mover['label']}: from {m.sname(frm)} to {m.sname(to)}"
                elif again:
                    rid, form, button = again
                    steps = [self.step(**m.sign_in(rid))]
                    where = m.detail_for(rid, kind)
                    if where:
                        steps += self.open(where, rid, rec)
                    steps.append(self.step(f"Open {rec or 'the ' + noun} to change it", f"{m.title(form)} opens with its details filled in", form))
                    steps.append(self.step(f"Press {button}", f"The status is now {m.sname(to)}", form))
                    title = f"{button}: from {m.sname(frm)} to {m.sname(to)}"
                    mover = {"label": button}
                else:
                    where = m.detail_for(rid, kind) if rid else None
                    if where:
                        steps += self.open(where, rid, rec)
                    steps.append(self.step(f"Move the {noun} on to {m.sname(to)}", f"The status is now {m.sname(to)}", where))
                    title = f"From {m.sname(frm)} to {m.sname(to)}"
                    todo = f"no button in the mock-up moves {m.a(kind)} from {m.sname(frm)} to {m.sname(to)}: write the steps from the requirements"
                    if not rid:
                        todo += ", and who does it"
                self.add(title, "status change", [rid], steps, f"status rules: {m.sname(frm)} next {m.sname(to)}", "High",
                         [self.precondition(frm, kind)], todo=todo, keys=[m.sname(frm), m.sname(to), (mover or {}).get("label")],
                         moves=[(frm, to, (mover or {}).get("label"))])

    def resubmit(self, frm, to, kind):
        """(role, form, button) when a record in `frm` goes on to `to` by being changed on the form that adds it and
        sent with that form's button: the form's records start in `to`, and the status rules let the role change
        the record in `frm` (a draft sent on, a rejected application corrected and sent again). Else None."""
        m = self.m
        made = m.creation(kind, to)
        if not made or made["status"] != to:
            return None
        allowed = m.allowed(frm, "edit") or set()
        rid = next((r for r in m.openers(made["screen"]) if r in allowed), None)
        return (rid, made["screen"], str(made["button"].get("label") or "Submit")) if rid else None

    def allowed_actions(self):
        """A case for each status where a role may change or delete a record without moving it."""
        m = self.m
        for s in m.statuses:
            frm = s["id"]
            kind = m.kind_of(frm)
            made = m.creation(kind)
            field = None
            if made:
                field = next((m.text(f.get("label")) for f in m.form_fields(m.screen[made["screen"]]) if not f.get("readonly")), None)
            for rule, action, expected in (
                    ("edit", f"Change {field or 'a field'} and save", f"The change is kept and the status stays {m.sname(frm)}"),
                    ("delete", f"Delete the {m.noun(kind)}", f"The {m.noun(kind)} is removed and no longer listed")):
                allowed = m.allowed(frm, rule) or set()
                if not allowed:
                    continue
                rid = next((r["id"] for r in m.roles if r["id"] in allowed), None)
                if not rid:
                    continue
                where = m.detail_for(rid, kind)
                steps = [self.step(**m.sign_in(rid))] + (self.open(where, rid, m.record(frm, kind)) if where else [])
                steps.append(self.step(action, expected, where))
                verb = "changes" if rule == "edit" else "deletes"
                self.add(f"{m.role_name(rid)} {verb} {m.a(kind)} in {m.sname(frm)}", "status change", [rid], steps,
                         f"status rules: {m.sname(frm)} {rule} {join_words(sorted(allowed))}", "High", [self.precondition(frm, kind)],
                         keys=[m.sname(frm), rule])

    def not_allowed(self):
        m = self.m
        verbs = {"edit": "change", "cancel": "cancel", "delete": "delete"}
        for s in m.statuses:
            frm = s["id"]
            kind = m.kind_of(frm)
            rec = m.record(frm, kind)
            steps, roles = [], []
            for rid in m.viewers(kind):
                barred = [verbs[rule] for rule in verbs if m.allowed(frm, rule) is not None and rid not in m.allowed(frm, rule)]
                if not barred:
                    continue
                where = m.detail_for(rid, kind)
                route = m.open_steps(where, rid, rec)
                via = f" from {route[0][0][5:].replace(' from the side menu', '')}" if len(route) > 1 else ""
                steps.append(self.step(f"Sign in as {m.role_name(rid)} and open {rec or m.a(kind) + ' in ' + m.sname(frm)}{via}",
                                       f"It shows status {m.sname(frm)}. There is no way to {join_words(barred, 'or')} it", where, rid))
                roles.append(rid)
            if steps:
                self.add(f"{m.sname(frm)}: what each role may not do", "not allowed", roles, steps,
                         f"status rules of {m.sname(frm)}: edit, cancel, delete", "High", [self.precondition(frm, kind)],
                         keys=[m.sname(frm), "cancel", "delete"])

    # ---- (c) field checks
    def field_steps(self, fields, button, screen):
        m = self.m
        required, rules = [], []
        for f in fields:
            label = m.text(f.get("label") or f.get("id"))
            if f.get("readonly"):
                if f.get("source") or f.get("default"):
                    rules.append(self.step(f"Look at {label}", f"It is filled in ({m.text(f.get('source') or 'by the system')}) and cannot be changed", screen))
                continue
            if f.get("required"):
                required.append(self.step(f"Leave {label} empty and press {button}",
                                          f"The form is not sent: {label} is pointed out as required", screen))
            if f.get("options_from") or f.get("options"):
                values = f.get("options") or []
                src, only = f.get("options_from"), ""
                if isinstance(src, dict):  # {list, field, where}: only the records the filter lets through
                    lst, col, where = src.get("list"), src.get("field"), src.get("where") or {}
                    rows = [r for r in m.data.get(lst) or [] if isinstance(r, dict) and r.get(col) and all(
                        str(r.get(k)) in [str(v) for v in as_list(want)] for k, want in where.items())]
                    values = [r.get(col) for r in rows]
                    if where:
                        only = " only, " + join_words([f"{str(k).replace('_', ' ')} {join_words([str(v) for v in as_list(want)])}"
                                                       for k, want in where.items()])
                elif src and "." in str(src):
                    lst, col = str(src).split(".", 1)
                    values = [r.get(col) for r in m.data.get(lst) or [] if isinstance(r, dict) and r.get(col)]
                values = [str(v.get("label") or v.get("value")) if isinstance(v, dict) else str(v) for v in values]
                source = m.text(f.get("source")) if f.get("source") else ""
                rules.append(self.step(f"Open the choices of {label}", (f"It offers {source}" if source else "It offers the agreed values")
                                       + only + (f", such as {join_words(values[:4])}" if values else ""), screen))
            if f.get("length"):
                rules.append(self.step(f"Type more than {f['length']} characters into {label}",
                                       f"No more than {f['length']} characters are taken, or a message says so", screen))
            if f.get("format"):
                rules.append(self.step(f"Enter {label} in another format than {m.text(f['format'])}",
                                       "It is refused with a message", screen))
            if f.get("validation"):
                rules.append(self.step(f"Enter a value of {label} that breaks its rule",
                                       f"It is refused: {m.text(f['validation'])}", screen))
            if f.get("type") in ("number", "date", "datetime") and not f.get("validation"):
                kind = "a number" if f["type"] == "number" else "a valid date"
                rules.append(self.step(f"Type letters into {label}", f"Only {kind} is accepted", screen))
        return required, rules

    def field_checks(self):
        m = self.m
        for scr in m.screens:
            if scr.get("type") != "form" or not scr.get("sections"):
                continue
            button = next((b for b in scr.get("buttons") or [] if isinstance(b, dict) and b.get("style") == "primary"), None)
            label = (button or {}).get("label", "Submit")
            openers = m.openers(scr["id"])
            if not openers:
                continue
            rid = openers[0]
            fields = m.form_fields(scr)
            required, rules = self.field_steps(fields, label, scr["id"])
            lead = [self.step(**m.sign_in(rid))] + self.open(scr["id"], rid, m.text(scr.get("record")) if scr.get("record") else None)
            labels = [m.text(f.get("label")) for f in fields]
            if required:
                self.add(f"{m.title(scr['id'])}: required fields", "field checks", [rid], lead + required,
                         f"fields of {scr['id']}: required", preconditions=[], keys=labels + [m.title(scr["id"])])
            if rules:
                self.add(f"{m.title(scr['id'])}: field rules", "field checks", [rid], lead + rules,
                         f"fields of {scr['id']}: rules, lengths, choices", keys=labels + [m.title(scr["id"])])
        for did, dlg in m.dialog.items():
            fields = [f for f in dlg.get("fields") or [] if isinstance(f, dict)]
            opener = next(((s, b) for s in m.screens for b in s.get("buttons") or []
                           if isinstance(b, dict) and b.get("dialog") == did and not b.get("example")), None)
            if not fields or not opener:
                continue
            scr, b = opener
            rid = next((r for r in as_list(b.get("roles")) or m.openers(scr["id"]) if m.can_open(r, scr["id"])), None)
            if not rid:
                continue
            when = as_list((b.get("when") or {}).get("status")) if isinstance(b.get("when"), dict) else []
            status_id = m.sid(when[0]) if when else None
            rec = m.record(status_id) if status_id else None
            confirm = m.text((dlg.get("confirm") or {}).get("label") or "OK")
            required, rules = self.field_steps(fields, confirm, scr["id"])
            lead = [self.step(**m.sign_in(rid))] + self.open(scr["id"], rid, rec) + [
                self.step(f"Press {b.get('label')}", f"The {m.text(dlg.get('title') or 'confirmation')} window opens", scr["id"])]
            title = m.text(dlg.get("title") or did)
            pre = [self.precondition(status_id)] if status_id else []
            keys = [m.text(f.get("label")) for f in fields] + [b.get("label"), title]
            if required:
                self.add(f"{title}: required fields", "field checks", [rid], lead + required, f"fields of dialog {did}: required",
                         preconditions=pre, keys=keys)
            if rules:
                self.add(f"{title}: field rules", "field checks", [rid], lead + rules, f"fields of dialog {did}: rules",
                         preconditions=pre, keys=keys)

    # ---- (d) access
    def access(self):
        m = self.m
        if len(m.roles) < 2:
            return
        for r in m.roles:
            rid = r["id"]
            barred = [s for s in m.screens if s.get("type") != "login" and not m.can_open(rid, s["id"])]
            steps = [self.step(**m.sign_in(rid))]
            hidden = [m.text(s["menu"]) for s in barred if s.get("menu")]
            if hidden:
                steps.append(self.step("Look at the side menu", f"{join_words(hidden)} {'is' if len(hidden) == 1 else 'are'} not in it"))
            for s in barred:
                steps.append(self.step(f"Open {m.title(s['id'])} directly, by its address", "Access is refused", s["id"]))
            if r.get("scope"):
                listing = next((s for s in m.screens if (s.get("list") or {}).get("data") == m.main and m.can_open(rid, s["id"])), None)
                if listing:
                    steps += self.open(listing["id"], rid)
                    steps[-1]["expected"] += f". It lists {m.text(r['scope']).lower()}, nothing else"
            if len(steps) > 1:
                self.add(f"{m.role_name(rid)}: only their own screens and records", "access", [rid], steps,
                         f"roles of the screens; scope of {rid}", "High", keys=[m.role_name(rid)] + hidden)

    # ---- figures on dashboards
    def figures(self):
        m = self.m
        for scr in m.screens:
            stats = [s for s in scr.get("stats") or [] if isinstance(s, dict)]
            openers = m.openers(scr["id"])
            if not stats or not openers:
                continue
            rid = openers[0]
            steps = [self.step(**m.sign_in(rid))] + self.open(scr["id"], rid)
            todo = []
            for st in stats:
                label = m.text(st.get("label"))
                count = st.get("count")
                if count == "all":
                    expected = "It equals the number of records listed on the screen"
                elif isinstance(count, dict):
                    parts = [f"{k} {join_words(as_list(v), 'or')}" for k, v in count.items()]
                    expected = f"It equals the number of records listed with {join_words(parts)}"
                elif st.get("formula"):
                    expected = f"It shows {m.text(st['formula'])[:1].lower()}{m.text(st['formula'])[1:]}"
                else:
                    expected = "It shows the figure as specified"
                    todo.append(f"no formula for {label}")
                steps.append(self.step(f"Check {label}", expected, scr["id"]))
            self.add(f"{m.title(scr['id'])}: figures", "figures", [rid], steps, f"stats of {scr['id']}",
                     todo="; ".join(todo) or None, keys=[m.text(s.get("label")) for s in stats])

    # ---- (f) notifications and integrations
    def notifications(self):
        m = self.m
        for n in m.spec.get("notifications") or []:
            if not isinstance(n, dict) or not n.get("event"):
                continue
            reqs = [key for kind, key in REF.findall(str(n.get("template", ""))) if kind == "req"]
            template = m.text(n.get("template")) if n.get("template") else ""
            self.add(f"Notification: {m.text(n['event'])}", "notification", [],
                     [self.step(f"Make this happen: {m.text(n['event'])}",
                                f"{m.text(n.get('recipient') or 'The recipient')} receives the notification as specified"
                                + (f" ({template})" if template else ""))],
                     f"notifications: {n['event']}", requirements=[r for r in reqs if r in requirement_ids(m.spec)],
                     todo=None if template else "the wording of this notification is not in the spec", keys=[n["event"], "e-mail"],
                     needs=[{"kind": "other", "need": f"A mailbox the testers can read for {m.text(n.get('recipient') or 'the recipient')}"}])

    def integrations(self):
        m = self.m
        for x in m.spec.get("integrations") or []:
            if not isinstance(x, dict) or not x.get("system"):
                continue
            system = m.text(x["system"])
            trigger = m.text(x.get("trigger")) if x.get("trigger") else ""
            steps = [self.step(f"Do what starts the exchange: {trigger}" if trigger else f"Use the system so that it exchanges data with {system}",
                               f"The exchange with {system} works as specified" + (f": {m.text(x['data'])}" if x.get("data") else ""))]
            if x.get("on_failure"):
                steps.append(self.step(f"With {system} unavailable, do the same again", f"As specified: {m.text(x['on_failure'])}"))
            missing = [k for k in ("trigger", "on_failure") if not x.get(k)]
            self.add(f"Integration: {system}" + (f" ({m.text(x['purpose'])})" if x.get("purpose") else ""), "integration", [], steps,
                     f"integrations: {x['system']}", todo=f"not in the spec for this exchange: {', '.join(missing)}" if missing else None,
                     keys=[system], needs=[{"kind": "other", "need": f"{system} connected to the test system, with test data for the exchange"
                                            + (f" ({m.text(x['data'])})" if x.get("data") else "")}]
                     + ([{"kind": "other", "need": f"A way to make {system} unavailable during the test, agreed with its owner"}] if x.get("on_failure") else []))

    # ---- (e) requirements tied to the scenario that tests them
    def link_requirements(self):
        """Put each requirement into the scenario that tests it, or write the scenario that does, when the
        requirement says plainly what it is about: a field of a form (filled in, its choices, required, required
        for one choice), a field of a dialog that must be filled in, saving a draft, sending a record on to a role,
        a button that moves a record, an e-mail when a record reaches a status, what a screen shows, adding or
        changing a list's entries. What it cannot tie for certain is left to requirements(), as a case to refine.
        A requirement waiting for an open decision (tbc) is never tied."""
        covered = {r for c in self.cases for r in c["requirements"]}
        rules = (self.by_notification, self.by_dialog_field, self.by_field, self.by_draft, self.by_route, self.by_move,
                 self.by_screen, self.by_maintain)
        for rid, (group, text, priority, tbc) in requirement_ids(self.m.spec).items():
            if rid in covered or tbc:
                continue
            plain = self.m.text(text)
            item = next((it for it in group.get("items") or [] if isinstance(it, dict) and self.m.text(it.get("text")) == plain), None)
            screens = [s for s in as_list((item or {}).get("screens")) or as_list(group.get("screens")) if s in self.m.screen]
            screens += [k for kind, k in REF.findall(str(text)) if kind == "screen" and k in self.m.screen and k not in screens]
            prio = {"must": "High", "should": "Medium", "could": "Low"}.get(str(priority or "").lower(), "Medium")
            for rule in rules:
                if rule(rid, plain, plain.lower(), prio, screens):
                    break

    def by_notification(self, rid, plain, low, prio, screens):
        """"e-mail the employee when the application is approved or rejected": for each status, a case that moves a
        record there and checks the recipient's e-mail."""
        m = self.m
        if not re.search(r"e-?mail|notif|\binform|\balert|\bsms\b", low):
            return False
        who = m.roles_in(low)
        targets = [s for s in m.statuses_in(low) if any(x["to"] == s and not x["creates"] for x in m.movers())]
        if not who or not targets:
            return False
        name = m.role_name(who[0])
        for to in targets:
            mv = next(x for x in m.movers() if x["to"] == to and not x["creates"])
            frm = mv["from"] or next((s["id"] for s in m.statuses if to in m.nexts(s["id"])), None)
            kind = mv["data"] or m.kind_of(to)
            actor = (mv["roles"] or [None])[0]
            if not frm or not actor:
                return False
            rec = m.record(frm, kind)
            steps = [self.step(**m.sign_in(actor))] + self.open(mv["screen"], actor, rec) + self.press(mv, to, rec)
            steps.append(self.step(f"Open the mailbox of the {name} test account",
                                   f"An e-mail has come telling them that {rec or 'the ' + m.noun(kind)} is now {m.sname(to)}"))
            case = self.add(f"E-mail to the {name}: {m.sname(to)}", "notification", [actor, who[0]], steps, f"requirement {rid}", prio,
                            [self.precondition(frm, kind)], [rid], moves=[(frm, to, mv["label"])],
                            needs=[{"kind": "other", "need": f"A mailbox the testers can read for the {name} test account"}])
            if case is None:
                self.link(self.titled(f"E-mail to the {name}: {m.sname(to)}"), rid)
        return True

    def form_screens(self):
        return [s for s in self.m.screens if s.get("type") == "form" and s.get("sections")]

    def by_field(self, rid, plain, low, prio, screens):
        """A field of a form named in the requirement: filled in by the system, its choices, required, or required
        only for one choice of another field (that case gets the step that proves it)."""
        m = self.m
        for scr in self.form_screens():
            fields = m.form_fields(scr)
            named = [f for f in fields if f.get("label") and re.search(rf"\b{re.escape(m.text(f['label']).lower())}", low)]
            rules = self.titled(f"{m.title(scr['id'])}: field rules")
            required = self.titled(f"{m.title(scr['id'])}: required fields")
            for f in named:
                label = m.text(f["label"])
                if f.get("readonly") and (f.get("source") or f.get("default")) and rules \
                        and re.search(r"pre-?fill|read-?only|calculat|filled in|automatic", low):
                    self.link(rules, rid)
                    return True
                if (f.get("options") or f.get("options_from")) and rules and re.search(r"\boffer|\bchoos|\bchoice|\bselect|\bpick|\blist", low):
                    self.link(rules, rid)
                    return True
            if not re.search(r"\brequire|\bmandatory|\bmust be (filled|given|attached)", low):
                continue
            button = next((b.get("label") for b in scr.get("buttons") or [] if isinstance(b, dict) and b.get("style") == "primary"), "Submit")
            for f in named:
                label = m.text(f["label"])
                if f.get("required") and required and not f.get("readonly"):
                    self.link(required, rid)
                    return True
                for other in fields:  # "required for Medical Leave": a value of another field's choices
                    if other is f:
                        continue
                    for value in self.choices(other):
                        if value and re.search(rf"\b{re.escape(value.lower())}\b", low):
                            case = required or rules
                            step = self.step(f"Choose {value} in {m.text(other.get('label'))}, leave {label} empty and press {button}",
                                             f"The form is not sent: {label} is pointed out as required for {value}", scr["id"])
                            if case is None:
                                return False
                            case["steps"].append(step)
                            self.link(case, rid)
                            return True
        return False

    def choices(self, f):
        """The values a choice field offers, from its options or the list they come from."""
        m = self.m
        values = list(f.get("options") or [])
        src = f.get("options_from")
        if isinstance(src, dict):
            values = [r.get(src.get("field")) for r in m.data.get(src.get("list")) or [] if isinstance(r, dict)]
        elif src and "." in str(src):
            lst, col = str(src).split(".", 1)
            values = [r.get(col) for r in m.data.get(lst) or [] if isinstance(r, dict)]
        return [str(v.get("label") or v.get("value")) if isinstance(v, dict) else str(v) for v in values if v]

    def by_dialog_field(self, rid, plain, low, prio, screens):
        """"require a reason when rejecting": a required field of the dialog that the named button opens."""
        m = self.m
        if not re.search(r"\brequire|\bmandatory", low):
            return False
        for did, dlg in m.dialog.items():
            case = self.titled(f"{m.text(dlg.get('title') or did)}: required fields")
            if not case:
                continue
            openers = [str(b.get("label") or "") for s in m.screens for b in s.get("buttons") or [] if isinstance(b, dict) and b.get("dialog") == did]
            stems = [w.lower().rstrip("e") for w in (o.split()[0] for o in openers if o.split()) if len(w) >= 4]
            words = {w for f in dlg.get("fields") or [] if isinstance(f, dict) and f.get("required")
                     for w in re.findall(r"[a-z]{4,}", m.text(f.get("label") or f.get("id")).lower())}
            if any(re.search(rf"\b{re.escape(st)}", low) for st in stems) and any(re.search(rf"\b{w}\b", low) for w in words):
                self.link(case, rid)
                return True
        return False

    def by_draft(self, rid, plain, low, prio, screens):
        """"save a draft without validation": a case that saves one with the form's draft button."""
        m = self.m
        if "draft" not in low:
            return False
        status = next((s["id"] for s in m.statuses if "draft" in f"{s['id']} {s.get('name', '')}".lower()), None)
        for scr in self.form_screens():
            button = next((b for b in scr.get("buttons") or [] if isinstance(b, dict) and "draft" in str(b.get("label", "")).lower()), None)
            who = [r for r in m.openers(scr["id"]) if r in m.roles_in(low)] or m.openers(scr["id"])
            if not button or not who or not m.creates_on(scr["id"]):
                continue
            kind = scr.get("data") or m.main
            loose = re.search(r"without (validation|checks|all)|incomplete|partial|unfinished|not complete", low)
            saved = (f'A message like "{m.text(button["toast"])}" appears. ' if button.get("toast") else "") + \
                    (f"The {m.noun(kind)} is saved with status {m.sname(status)}" if status else f"The {m.noun(kind)} is saved")
            steps = [self.step(**m.sign_in(who[0]))] + self.open(scr["id"], who[0])
            if loose:
                steps.append(self.step(f"Fill in one field only, leave the required fields empty and press {button['label']}", saved, scr["id"]))
            else:
                steps.append(self.step(f"Fill in some of the fields and press {button['label']}", saved, scr["id"]))
            self.add(f"{button['label']}: an unfinished {m.noun(kind)}", "status change", [who[0]], steps, f"requirement {rid}", prio,
                     requirements=[rid], moves=[(None, status, button["label"])])
            return True
        return False

    def by_route(self, rid, plain, low, prio, screens):
        """"route a submitted application to the employee's line manager": the main process, where that role finds it."""
        m = self.m
        if not re.search(r"\brout|\bsent to|\bsend\b.*\bto\b|\bassign|\bforward", low) or " to " not in low:
            return False
        who = m.roles_in(low.split(" to ", 1)[1])
        if not who:
            return False
        target = who[-1]
        for case in (c for c in self.cases if c["type"] == "main process"):
            at = next((n for n, s in enumerate(case["steps"]) if s.get("role") == target and s["action"].startswith("Sign in")), None)
            if at is None:
                continue
            after = case["steps"][at + 1:]
            look = next((s for s in after if s["action"].startswith("Find")), None) or next((s for s in after if s["action"].startswith("Open")), None)
            if look is not None and "sent to them as the" not in look["expected"]:
                look["expected"] += f". The {m.noun()} is there, sent to them as the {m.role_name(target)}"
            self.link(case, rid)
            return True
        return False

    def by_move(self, rid, plain, low, prio, screens):
        """A requirement about a button that moves a record ("cancel a Pending or Approved application"): the cases
        that press it, those from the statuses it names when it names any, by the roles it names."""
        m = self.m
        if re.search(r"e-?mail|notif|\binform\b", low):
            return False
        found = []
        status_words = {str(s.get("name") or s["id"]).lower() for s in m.statuses}
        for x in m.movers():
            word = (x["label"].split() or [""])[0].lower()
            stem = word.rstrip("e") if len(word) > 4 else word
            # "an approved batch" names a status, not the button: only other words from the stem count
            if len(stem) >= 4 and any(w not in status_words for w in re.findall(rf"\b{re.escape(stem)}[a-z]*", low)):
                found.append(x)
        who = m.roles_in(low)
        found = [x for x in found if not who or not x["roles"] or set(who) & set(x["roles"])]
        if not found:
            return False
        named = m.statuses_in(low)
        found = [x for x in found if x["from"] in named or x["to"] in named] or found
        cases = [c for c in self.cases for x in found if any(mv[2] == x["label"] and (x["from"] in (None, mv[0])) and mv[1] == x["to"]
                                                          for mv in c["_moves"])]
        for case in dict.fromkeys(map(id, cases)):
            self.link(next(c for c in cases if id(c) == case), rid)
        return bool(cases)

    def by_screen(self, rid, plain, low, prio, screens):
        """"show the booking as specified in Booking Details": a case that opens the screen and checks its fields."""
        m = self.m
        if not re.search(r"\bshow|\bdisplay|\bview|\bsee\b", low):
            return False
        for sid in screens:
            scr = m.screen[sid]
            labels = [m.text(f.get("label")) for f in m.shown_fields(scr) if f.get("label")]
            labels = labels or [m.text(c.get("label")) for c in (scr.get("list") or {}).get("columns") or [] if isinstance(c, dict) and c.get("label")]
            who = [r for r in m.roles_in(low) if m.can_open(r, sid)] or m.openers(sid)
            if not labels or not who:
                continue
            kind = scr.get("data") or (scr.get("list") or {}).get("data")
            rec = m.text(scr.get("record")) if scr.get("record") else None
            steps = [self.step(**m.sign_in(who[0]))] + self.open(sid, who[0], rec)
            steps.append(self.step("Look at what the screen shows", f"It shows {join_words(labels)}, each with the {m.noun(kind)}'s own value", sid))
            self.add(f"{m.title(sid)}: what it shows", "requirement", [who[0]], steps, f"requirement {rid}", prio,
                     [self.precondition(m.sid((next((r for r in m.data.get(kind) or [] if isinstance(r, dict)), {})).get("status")), kind)]
                     if kind and m.statuses and any(isinstance(r, dict) and m.sid(r.get("status")) for r in m.data.get(kind) or []) else [],
                     [rid])
            return True
        return False

    def by_maintain(self, rid, plain, low, prio, screens):
        """"allow the Administrator to add and edit equipment": the list's add and edit buttons, each tried."""
        m = self.m
        verbs = [v for v in ("add", "edit", "delete") if re.search(rf"\b{v}", low)]
        if not verbs:
            return False
        for sid in screens or [s["id"] for s in m.screens]:
            scr = m.screen[sid]
            lst = scr.get("list") or {}
            if scr.get("type") != "list" or not (screens or (lst.get("data") and re.search(rf"\b{re.escape(str(lst['data']).rstrip('s').replace('_', ' '))}", low))):
                continue
            buttons = [(b, "toolbar") for b in lst.get("toolbar") or [] if isinstance(b, dict)] + \
                      [(b, "action") for b in lst.get("actions") or [] if isinstance(b, dict)]
            pick = {v: next(((b, how) for b, how in buttons if re.search(rf"\b{v}", str(b.get("label", "")).lower())), None) for v in verbs}
            who = [r for r in m.roles_in(low) if m.can_open(r, sid)] or m.openers(sid)
            if not all(pick.values()) or not who:
                continue
            thing = m.noun(lst.get("data")) if m.several else str(lst.get("data") or "entry").replace("_", " ").rstrip("s")
            steps = [self.step(**m.sign_in(who[0]))] + self.open(sid, who[0])
            for v in verbs:
                b, how = pick[v]
                action = f"Press {b['label']}" if how == "toolbar" else f"Find {('an' if thing[:1] in 'aeiou' else 'a')} {thing} and press {b['label']}"
                expected = {"add": f"A new {thing} can be filled in and saved; it is then listed",
                            "edit": f"Its details can be changed and saved; the list shows the change",
                            "delete": f"After confirming, the {thing} is no longer listed"}[v]
                steps.append(self.step(action, expected, sid))
            self.add(f"{m.title(sid)}: {join_words(verbs)}", "requirement", [who[0]], steps, f"requirement {rid}", prio, requirements=[rid])
            return True
        return False

    # ---- (f) every requirement covered
    def requirements(self):
        m = self.m
        covered = {r for c in self.cases for r in c["requirements"]}
        prio = {"must": "High", "should": "Medium", "could": "Low"}
        for rid, (group, text, priority, tbc) in requirement_ids(m.spec).items():
            if rid in covered:
                continue
            plain = m.text(text)
            low = plain.lower()
            role = next((r["id"] for r in m.roles if re.search(rf"\b{re.escape(str(r.get('name', '')).lower())}\b", low)
                         or re.search(rf"\b{re.escape(r['id'].lower())}\b", low)), None)
            screens = [s for s in as_list(group.get("screens")) if s in m.screen]
            item = next((it for it in group.get("items") or [] if isinstance(it, dict) and m.text(it.get("text")) == plain), None)
            screens = [s for s in as_list((item or {}).get("screens")) if s in m.screen] or screens
            role = role or (m.openers(screens[0])[0] if screens and m.openers(screens[0]) else None)
            steps = [self.step(**m.sign_in(role))] if role else []
            if screens and role:
                steps += self.open(screens[0], role)
            steps.append(self.step(f"Check that it works as required: {plain}", f"It works as stated in {rid}",
                                   screens[0] if screens else None))
            pre = [f"The open decision {tbc} has been made"] if tbc else []
            hits = [(sum(1 for k in c["_keys"] if k in low), n, c) for n, c in enumerate(self.cases) if c["type"] != "requirement"]
            related = [c for score, _, c in sorted(hits, key=lambda h: (-h[0], h[1])) if score][:3]
            case = self.add(f"{rid}: {plain[:90].rstrip()}{'...' if len(plain) > 90 else ''}", "requirement", [role], steps,
                            f"requirement {rid}", prio.get(str(priority or "").lower(), "Medium"), pre, [rid],
                            todo=f"write real steps for {rid}, or add {rid} to the scenario that already tests it and remove this case",
                            keys=())
            if case is not None and related:
                case["_related"] = related

    # ---- what each case needs before it starts
    def test_data(self, case):
        """[{kind, need, how?}]: the test accounts that sign in, the records the preconditions ask for (and how to
        get one), the files the steps upload, and what the case asked for itself (a mailbox, a connection)."""
        m = self.m
        out = []
        signed = [s.get("role") for s in case["steps"] if s.get("role")] + [r for r in case["roles"] if r]
        for rid in dict.fromkeys(signed):
            if rid not in m.role:
                continue
            scope = m.text(m.role[rid].get("scope") or "")
            out.append({"kind": "account", "need": f"A test account for {m.role_name(rid)}"
                        + (f" (what it sees: {scope[:1].lower()}{scope[1:]}; set it up so the test records are among them)" if scope else "")})
        for pre in case["preconditions"]:
            if pre not in self.records:
                continue
            status, kind = self.records[pre]
            need = {"kind": "record", "need": f"{m.a(kind).capitalize()} in {m.sname(status)}"}
            made = m.creation(kind, status)
            start = (made or {}).get("status") or m.origin(kind)
            how = self.creation_note(status, kind)
            route = m.path(start, status, kind) if start and start != status else None
            first = f"fill in {m.title(made['screen'])} and press {made['button'].get('label')}" if made and made.get("status") == start else ""
            if not how and route:
                presses = [f"{mv['label']} (as {m.role_name(mv['roles'][0])})" if mv["roles"] else mv["label"] for _, _, mv in route]
                how = (f"{first}, then " if first else f"from {m.sname(start)}, press ") + ", then ".join(presses)
            elif not how and start == status and first:
                how = first
            if how:
                need["how"] = how[:1].upper() + how[1:]
            out.append(need)
        for step in case["steps"]:
            scr = m.screen.get(step.get("screen")) or {}
            for f in m.form_fields(scr) if scr.get("type") == "form" else []:
                label = m.text(f.get("label") or f.get("id"))
                if f.get("type") != "file" or "empty" in step["action"] or not (
                        label.lower() in step["action"].lower() or (f.get("required") and step["action"].startswith("Fill in every required"))):
                    continue
                need = f"A file to upload as {label}" + (f" ({m.text(f['help'])})" if f.get("help") else "")
                if "breaks its rule" in step["action"] and f.get("validation"):
                    need = f"A file for {label} that breaks its rule: {m.text(f['validation'])}"
                out.append({"kind": "file", "need": need})
        out += case.get("_needs") or []
        return list({d["need"]: d for d in out}.values())

    def build(self):
        done = self.main_process()
        self.status_moves(done)
        self.allowed_actions()
        self.not_allowed()
        self.field_checks()
        self.access()
        self.figures()
        self.notifications()
        self.integrations()
        self.link_requirements()
        self.requirements()
        for n, c in enumerate(self.cases, 1):
            c["id"] = f"UAT-{n:03d}"
        for c in self.cases:
            related = c.pop("_related", [])
            if related:
                c["related"] = [r["id"] for r in related]
            c["test_data"] = self.test_data(c)
            for key in ("_keys", "_moves", "_needs"):
                c.pop(key, None)
        return self.cases


def draft(spec, spec_path, based_on, date):
    P = spec.get("project") or {}
    return {"project": str(P.get("name", "")), "client": str(P.get("client", "")), "spec_version": str(P.get("version", "")),
            "spec": spec_path, "based_on": based_on, "date": date, "cases": Draft(spec).build(), "excluded": []}


# ---------------------------------------------------------------- checks
def scripts_file(project, name=None):
    import layout

    folder = layout.uat_source(project)
    if name:
        path = Path(name) if Path(name).exists() else folder / name
        if not path.exists():
            sys.exit(f"No UAT scripts file {path}")
        return path
    found = sorted(folder.glob("*.json")) if folder.exists() else []
    if not found:
        sys.exit(f"No UAT scripts in {folder}. Write a draft first: python -I tools/uat.py draft {Path(project).as_posix()}")
    return found[-1]


def texts(case):
    yield case.get("title")
    yield from case.get("preconditions") or []
    for d in case.get("test_data") or []:
        if isinstance(d, dict):
            yield d.get("need")
            yield d.get("how")
    for s in case.get("steps") or []:
        if isinstance(s, dict):
            yield s.get("action")
            yield s.get("expected")


def coverage(scripts, spec):
    """(all requirement ids, {id: [case ids]}, {id: reason})."""
    reqs = requirement_ids(spec)
    by = {r: [] for r in reqs}
    for c in scripts.get("cases") or []:
        if isinstance(c, dict):
            for r in c.get("requirements") or []:
                if r in by:
                    by[r].append(c.get("id"))
    excluded = {str(e.get("requirement")): str(e.get("reason") or "") for e in scripts.get("excluded") or [] if isinstance(e, dict)}
    return reqs, by, excluded


def check(scripts, project):
    """(mistakes, warnings) as sentences; no mistakes means the scripts can be rendered."""
    errors, warnings = [], []
    for key in ("project", "spec_version", "spec", "date", "cases"):
        if not scripts.get(key):
            errors.append(f"missing {key}")
    if scripts.get("cases") and not isinstance(scripts["cases"], list):
        return errors + ["cases must be a list"], warnings
    import layout

    spec_path = layout.resolve(project, str(scripts.get("spec") or "spec/app.yaml"))
    if not spec_path.exists():
        return errors + [f"the spec it was written from, {scripts.get('spec')}, is not in the project"], warnings
    spec = load_yaml(spec_path)
    m = Model(spec)
    reqs = requirement_ids(spec)
    internal_ids = {str(it.get("id")) for it in read_register(project) if it.get("audience") != "client"}  # only client items are the client's
    seen = set()
    for n, c in enumerate(scripts.get("cases") or [], 1):
        if not isinstance(c, dict):
            errors.append(f"case {n}: not a case")
            continue
        cid = str(c.get("id") or f"case {n}")
        if not re.fullmatch(r"UAT-\d{3,}", str(c.get("id") or "")):
            errors.append(f"{cid}: the id must be UAT- and a number, for example UAT-001")
        if cid in seen:
            errors.append(f"{cid} is used twice")
        seen.add(cid)
        if not str(c.get("title") or "").strip():
            errors.append(f"{cid}: needs a title")
        if c.get("priority") not in PRIORITIES:
            errors.append(f"{cid}: priority must be High, Medium or Low")
        if c.get("type") and c["type"] not in TYPES:
            warnings.append(f"{cid}: type '{c['type']}' is not one of {', '.join(TYPES)}: it is listed under Other requirements")
        for rid in as_list(c.get("roles")):
            if rid not in m.role:
                errors.append(f"{cid}: '{rid}' is not a role of the spec")
        steps = c.get("steps")
        if not steps or not isinstance(steps, list):
            errors.append(f"{cid}: needs steps")
            steps = []
        for k, s in enumerate(steps, 1):
            if not isinstance(s, dict) or not str(s.get("action") or "").strip():
                errors.append(f"{cid}, step {k}: needs an action")
                continue
            if not str(s.get("expected") or "").strip():
                errors.append(f"{cid}, step {k}: needs an expected result")
            if s.get("screen") and s["screen"] not in m.screen:
                errors.append(f"{cid}, step {k}: '{s['screen']}' is not a screen of the mock-up")
            if s.get("role") and s["role"] not in m.role:
                errors.append(f"{cid}, step {k}: '{s['role']}' is not a role of the spec")
        for r in as_list(c.get("requirements")):
            if r not in reqs and r not in {str(g.get("id")) for g in spec.get("requirements") or [] if isinstance(g, dict)}:
                errors.append(f"{cid}: {r} is not a requirement of spec v{scripts.get('spec_version')}")
        for t in texts(c):
            t = str(t or "")
            if INTERNAL_WORDS.search(t):
                errors.append(f"{cid}: '{INTERNAL_WORDS.search(t).group(0)}' is internal and must not reach the client's testers")
            for rid in re.findall(r"\bR-\d+\b", t):
                if rid in internal_ids:
                    errors.append(f"{cid}: {rid} is an internal register item")
        data = c.get("test_data")
        if data is None:
            warnings.append(f"{cid}: no test data listed: say what it needs before it starts (test accounts, records in "
                            "their status, files to upload), or write \"test_data\": [] when it needs nothing")
        elif not isinstance(data, list) or not all(isinstance(d, dict) and d.get("kind") in DATA_KINDS and str(d.get("need") or "").strip()
                                                    for d in data):
            errors.append(f"{cid}: each test_data entry needs a kind ({', '.join(DATA_KINDS)}) and what is needed (need)")
        if c.get("todo"):
            warnings.append(f"{cid}: still to do: {c['todo']}")
    _, by, excluded = coverage(scripts, spec)
    for e in scripts.get("excluded") or []:
        if not isinstance(e, dict) or not e.get("requirement") or not str(e.get("reason") or "").strip():
            errors.append("each excluded requirement needs its id and the reason it is not tested")
        elif e["requirement"] not in reqs:
            errors.append(f"excluded {e['requirement']} is not a requirement of spec v{scripts.get('spec_version')}")
        elif by.get(e["requirement"]):
            warnings.append(f"{e['requirement']} is excluded but {', '.join(by[e['requirement']])} test{'s' if len(by[e['requirement']]) == 1 else ''} it")
        if isinstance(e, dict) and INTERNAL_WORDS.search(str(e.get("reason") or "")):
            errors.append(f"excluded {e.get('requirement')}: the reason holds internal words")
    for r, cases in by.items():
        if not cases and r not in excluded:
            errors.append(f"{r} is not covered: add it to a case that tests it, or to excluded with the reason")
    return errors, warnings


def load(project, name):
    path = scripts_file(project, name)
    try:
        scripts = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{path.name} is not valid JSON: {e}")
    errors, warnings = check(scripts, project)
    if warnings:
        print(f"{path.name}: to look at")
        print("\n".join(f"  - {w}" for w in warnings))
    if errors:
        print(f"{path.name} needs fixing:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    import layout

    return path, scripts, load_yaml(layout.resolve(project, scripts["spec"]))


def summary(scripts, spec):
    reqs, by, excluded = coverage(scripts, spec)
    cases = scripts["cases"]
    covered = sum(1 for r in reqs if by[r])
    return {"cases": len(cases), "steps": sum(len(c["steps"]) for c in cases), "requirements": len(reqs), "covered": covered,
            "excluded": len([r for r in reqs if r in excluded and not by[r]]),
            "by_type": Counter(c.get("type") if c.get("type") in TYPES else "requirement" for c in cases),
            "by_priority": Counter(c["priority"] for c in cases), "test_data": len(test_data_list(scripts))}


def test_data_list(scripts):
    """Every distinct thing the scenarios need before UAT starts, numbered TD-01 ...: [{ref, kind, need, how, cases}],
    test accounts first, then records, files and the rest, each in the order the scenarios first ask for it."""
    found = OrderedDict()
    for c in scripts.get("cases") or []:
        for d in c.get("test_data") or [] if isinstance(c, dict) else []:
            if not isinstance(d, dict) or not str(d.get("need") or "").strip():
                continue
            kind = d.get("kind") if d.get("kind") in DATA_KINDS else "other"
            item = found.setdefault((kind, str(d["need"]).strip()), {"kind": kind, "need": str(d["need"]).strip(), "how": "", "cases": []})
            item["how"] = item["how"] or str(d.get("how") or "").strip()
            if c.get("id") not in item["cases"]:
                item["cases"].append(c.get("id"))
    order = list(DATA_KINDS)
    items = sorted(found.values(), key=lambda d: order.index(d["kind"]))
    for n, d in enumerate(items, 1):
        d["ref"] = f"TD-{n:02d}"
    return items


def data_refs(scripts):
    """{case id: [TD refs]}."""
    out = {}
    for d in test_data_list(scripts):
        for cid in d["cases"]:
            out.setdefault(cid, []).append(d["ref"])
    return out


# ---------------------------------------------------------------- render
def step_rows(scripts, m):
    """One row per step: the case, the role acting at that step, the screen's title."""
    for c in scripts["cases"]:
        role = (as_list(c.get("roles")) or [None])[0]
        for k, s in enumerate(c["steps"], 1):
            role = s.get("role") or role
            yield c, k, s, m.role_name(role) if role else ""


def group_rows(scripts, spec):
    reqs, by, excluded = coverage(scripts, spec)
    rows = OrderedDict()
    for rid, (g, _, _, _) in reqs.items():
        key = str(g.get("id"))
        row = rows.setdefault(key, {"id": key, "title": str(g.get("title", "")), "total": 0, "covered": 0, "excluded": 0, "cases": []})
        row["total"] += 1
        row["covered"] += 1 if by[rid] else 0
        row["excluded"] += 1 if not by[rid] and rid in excluded else 0
        row["cases"] += [c for c in by[rid] if c not in row["cases"]]
    return list(rows.values())


def render_xlsx(scripts, spec, out):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    import sheets

    m = Model(spec)
    wb = Workbook()
    s = wb.active
    s.title = "Summary"
    ws = sheets.setup(wb.create_sheet(STEPS_SHEET), [width for _, width, _ in STEP_COLUMNS], freeze="C2")
    tester_cols = [c for c, (_, _, by_tester) in enumerate(STEP_COLUMNS, 1) if by_tester]
    for c, (name, width, _) in enumerate(STEP_COLUMNS, 1):
        ws.cell(row=1, column=c, value=name)
    refs = data_refs(scripts)
    date_col = [name for name, _, _ in STEP_COLUMNS].index("Date") + 1
    r = 1
    for case, k, step, role in step_rows(scripts, m):
        r += 1
        values = [case["id"], case["title"], case["priority"], role, "\n".join(case.get("preconditions") or []) if k == 1 else "",
                  ", ".join(refs.get(case["id"], [])) if k == 1 else "",
                  k, m.title(step["screen"]) if step.get("screen") else "", step["action"], step["expected"],
                  ", ".join(case.get("requirements") or []), "", "", "", None, ""]
        for c, value in enumerate(values, 1):
            ws.cell(row=r, column=c, value=value)
        ws.cell(row=r, column=date_col).number_format = "d mmm yyyy"
    sheets.header(ws, 1, len(STEP_COLUMNS), fill_in=tester_cols)
    sheets.rows(ws, 2, r, len(STEP_COLUMNS), fill_in=tester_cols)
    col = {name: get_column_letter(i) for i, (name, _, _) in enumerate(STEP_COLUMNS, 1)}
    if r > 1:
        # A result as a dot and a coloured word, following what the tester picks.
        sheets.status(ws, f"{col['Pass/Fail']}2:{col['Pass/Fail']}{r}", {"Pass": "green", "Fail": "red", "Blocked": "orange", "Not run": "grey"})
        ws.auto_filter.ref = f"A1:{get_column_letter(len(STEP_COLUMNS))}{r}"
        dv = DataValidation(type="list", formula1='"' + ",".join(RESULTS) + '"', allow_blank=True,
                            showErrorMessage=True, errorTitle="Pass/Fail", error="Choose Pass, Fail, Blocked or Not run")
        ws.add_data_validation(dv)
        dv.add(f"{col['Pass/Fail']}2:{col['Pass/Fail']}{r}")
        dates = DataValidation(type="date", operator="greaterThan", formula1="1", allow_blank=True,
                               showErrorMessage=True, errorTitle="Date", error="Type a date, for example 12 Jan 2027")
        ws.add_data_validation(dates)
        dates.add(f"{col['Date']}2:{col['Date']}{r}")

    sm = summary(scripts, spec)
    sheets.setup(s, [22, 44, 13, 13, 13, 13, 40], titles=None)
    sheets.title(s, "A1", f"{scripts['project']}: user acceptance test",
                 f"Written from {scripts.get('based_on') or 'v' + scripts['spec_version']} · {readable(scripts['date'])}")
    rows = [("Scenarios", sm["cases"]), ("Steps", sm["steps"]), ("Test data to prepare", f"{sm['test_data']} items, see {DATA_SHEET}"),
            ("Requirements covered", f"{sm['covered']} of {sm['requirements']}" + (f" ({sm['excluded']} not tested, see below)" if sm["excluded"] else ""))]
    rng = f"'{STEPS_SHEET}'!{col['Pass/Fail']}2:{col['Pass/Fail']}{max(r, 2)}"
    rows += [("Steps passed", f'=COUNTIF({rng},"Pass")'), ("Steps failed", f'=COUNTIF({rng},"Fail")'),
             ("Steps blocked", f'=COUNTIF({rng},"Blocked")'),
             ("Steps not run yet", f'={sm["steps"]}-COUNTIF({rng},"Pass")-COUNTIF({rng},"Fail")-COUNTIF({rng},"Blocked")')]
    line = 4
    for label, value in rows:
        sheets.label(s.cell(row=line, column=1, value=label))
        sheets.value(s.cell(row=line, column=2, value=value), bold=label == "Scenarios")
        line += 1
    line += 1
    sheets.section(s.cell(row=line, column=1, value="Coverage by requirement group"))
    line += 1
    head = line
    for c, name in enumerate(["Group", "Title", "Requirements", "Covered", "Not tested", "Scenarios", "Scenario ids"], 1):
        s.cell(row=line, column=c, value=name)
    for g in group_rows(scripts, spec):
        line += 1
        for c, value in enumerate([g["id"], g["title"], g["total"], g["covered"], g["excluded"], len(g["cases"]), ", ".join(g["cases"])], 1):
            s.cell(row=line, column=c, value=value)
    sheets.header(s, head, 7)
    sheets.rows(s, head + 1, line, 7)
    line += 2
    sheets.section(s.cell(row=line, column=1, value="Scenarios by kind"))
    for kind, label in TYPES.items():
        if sm["by_type"].get(kind):
            line += 1
            sheets.label(s.cell(row=line, column=1, value=label))
            sheets.value(s.cell(row=line, column=3, value=sm["by_type"][kind]))
    data = test_data_list(scripts)
    t = sheets.setup(wb.create_sheet(DATA_SHEET, 1), [9, 14, 54, 44, 22, 18, 9, 30], freeze="C2")
    data_cols = ("Ref", "Kind", "What is needed", "How to get it", "Scenarios", "Prepared by", "Ready", "Notes")
    for c, name in enumerate(data_cols, 1):
        t.cell(row=1, column=c, value=name)
    for n, d in enumerate(data, 2):
        for c, value in enumerate((d["ref"], DATA_KINDS[d["kind"]], d["need"], d["how"], ", ".join(d["cases"]), "", "", ""), 1):
            t.cell(row=n, column=c, value=value)
    sheets.header(t, 1, len(data_cols), fill_in=(6, 7, 8))
    sheets.rows(t, 2, max(len(data) + 1, 2), len(data_cols), fill_in=(6, 7, 8))
    if data:
        ready = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
        t.add_data_validation(ready)
        ready.add(f"G2:G{len(data) + 1}")
        sheets.status(t, f"G2:G{len(data) + 1}", {"Yes": "green", "No": "red"})
    reqs, by, excluded = coverage(scripts, spec)
    left_out = [(rid, reqs[rid][1], excluded[rid]) for rid in reqs if not by[rid] and rid in excluded]
    if left_out:
        x = sheets.setup(wb.create_sheet("Not tested"), [16, 60, 60], freeze="A2")
        for c, name in enumerate(("Requirement", "Text", "Why it is not tested"), 1):
            x.cell(row=1, column=c, value=name)
        for n, (rid, text, reason) in enumerate(left_out, 2):
            for c, value in enumerate((rid, m.text(text), reason), 1):
                x.cell(row=n, column=c, value=value)
        sheets.header(x, 1, 3)
        sheets.rows(x, 2, len(left_out) + 1, 3)
    wb.active = wb.sheetnames.index(STEPS_SHEET)
    try:
        wb.save(str(out))
    except PermissionError:
        sys.exit(f"Cannot write {out.name}: close it in Excel and run this again.")
    return out


def render_docx(scripts, spec, out):

    import generate_requirements as gen

    fmt = gen.load_format()
    problems = gen.format_errors(fmt)
    if problems:
        sys.exit("The document format has mistakes:\n  " + "\n  ".join(problems))
    co = workspace.company()
    m = Model(spec)
    sm = summary(scripts, spec)
    system, client = scripts["project"], scripts.get("client") or m.names["client"] or "the client"
    doc = gen.template_document()
    w = gen.Writer(doc, fmt)
    w.setup_styles()
    w.header_footer(f"{system} · User acceptance test", f"v{scripts['spec_version']} · {readable(scripts['date'])}",
                    f"{co['name']} · {fmt['labels']['confidential']}")
    tw = w.text_width
    w.para([("User acceptance test scripts", "sec")], size=w.s["body"] + 1, after=2)
    w.page_title(system, after=4)
    w.para([(f"Written from {scripts.get('based_on') or 'v' + scripts['spec_version']} · {readable(scripts['date'])}", "sec")],
           size=w.s["body"] + 1, after=10)
    w.cards([(sm["cases"], "Test scenarios", None), (sm["steps"], "Steps", None),
             (f"{sm['covered']} of {sm['requirements']}", "Requirements covered", "accent")], value_size=14)
    w.heading("Purpose", 2)
    w.para(f"These scripts let {client}'s testers check that {system} does what was agreed in "
           f"{scripts.get('based_on') or 'the requirements'}. Each scenario says who carries it out, what must be in place "
           "first, the steps, and the result to expect at each step. Testing against what was agreed keeps the "
           "discussion about each result short: the expected result is the agreement.", after=6)
    w.heading("How to record results", 2)
    w.bullets([
        "Record the results in the workbook that comes with this document: one row per step.",
        "Pass: what happened matches the expected result. Fail: it does not; write what happened under Actual result.",
        "Blocked: the step could not be carried out (an earlier step failed, test data or access is missing). Say why.",
        "Give each failure a defect reference and fill in Tester and Date for every step you run.",
        "Where the system does what the expected result says, but you would like it to work differently, mark the step "
        "Pass and note the wish under Actual result: it is a change request, handled apart from defects.",
        "Use test accounts and test data, never live personal data.",
    ])
    data = test_data_list(scripts)
    refs = {d["ref"]: d for d in data}
    by_case = data_refs(scripts)
    if data:
        w.heading("Test data to prepare before UAT", 2)
        w.para(f"{client} prepares these before the testers start, so no scenario is held up for want of an account, a record "
               "in the right status or a file. Each scenario lists the items it uses. The workbook's Test data sheet has a "
               "column to mark each one ready.", after=4)
        w.table(["Ref", "What is needed", "How to get it", "Scenarios"],
                [[[(d["ref"], "mono")], d["need"], d["how"] or "–", ", ".join(d["cases"])] for d in data],
                [1.6, (tw - 4.6) * 0.45, (tw - 4.6) * 0.35, 3.0 + (tw - 4.6) * 0.2])
    groups = group_rows(scripts, spec)
    if groups:
        w.heading("What the scenarios cover", 2)
        w.table(["Group", "Requirement", "Covered", "Scenarios"],
                [[[(g["id"], "mono")], g["title"], f"{g['covered']} of {g['total']}", ", ".join(g["cases"]) or "–"] for g in groups],
                [3.0, (tw - 6.0) * 0.5, 3.0, (tw - 6.0) * 0.5])
    by_kind = OrderedDict((k, []) for k in TYPES)
    for c in scripts["cases"]:
        by_kind[c.get("type") if c.get("type") in TYPES else "requirement"].append(c)
    w.heading("Test scenarios", 1)
    for kind, cases in by_kind.items():
        if not cases:
            continue
        w.heading(TYPES[kind], 2)
        for c in cases:
            w.heading(f"{c['id']}  {c['title']}", 3)
            facts = [("Who: ", "sec"), (join_words([m.role_name(r) for r in as_list(c.get("roles"))]) or "As each step says", ""),
                     ("   ·   Priority: ", "sec"), (c["priority"], "")]
            if c.get("requirements"):
                facts += [("   ·   Requirements: ", "sec"), (", ".join(c["requirements"]), "mono")]
            w.para(facts, after=4, keep=True)
            if c.get("preconditions"):
                w.para([("Before you start", "medium")], after=2, keep=True)
                w.bullets([str(p) for p in c["preconditions"]])
            if by_case.get(c["id"]):
                w.para([("Test data: ", "medium"), ("  ".join(f"{ref} {refs[ref]['need']}." for ref in by_case[c["id"]]), "")],
                       after=4, keep=True)
            w.table(["No", "Step", "Expected result", "Result"],
                    [[[(str(k), "mono")], s["action"], s["expected"], ""] for k, s in enumerate(c["steps"], 1)],
                    [1.0, (tw - 3.2) * 0.5, (tw - 3.2) * 0.5, 2.2])
    reqs, by, excluded = coverage(scripts, spec)
    left_out = [(rid, reqs[rid][1], excluded[rid]) for rid in reqs if not by[rid] and rid in excluded]
    if left_out:
        w.heading("Requirements not tested in UAT", 2)
        w.table(["Requirement", "Text", "Why"], [[[(rid, "mono")], m.text(text), reason] for rid, text, reason in left_out],
                [3.0, (tw - 3.0) * 0.55, (tw - 3.0) * 0.45])
    w.heading("Acceptance", 2)
    w.para(f"Signed for {client} when the scenarios have been run and the results agreed.", after=6)
    w.table(["Name", "Designation", "Signature", "Date"], [["", "", "", ""], ["", "", "", ""]],
            [tw * 0.3, tw * 0.3, tw * 0.25, tw * 0.15])
    try:
        doc.save(str(out))
    except PermissionError:
        sys.exit(f"Cannot write {out.name}: close it in Word and run this again.")
    return out


# ---------------------------------------------------------------- results
def read_results(path):
    """The steps of a filled-in workbook: [{case, scenario, step, expected, actual, result, tester, date, defect, requirements}]."""
    from openpyxl import load_workbook

    wb = load_workbook(str(path), data_only=True)
    if STEPS_SHEET not in wb.sheetnames:
        sys.exit(f"{Path(path).name} has no '{STEPS_SHEET}' sheet: it is not a UAT workbook made by Blueprint.")
    ws = wb[STEPS_SHEET]
    head = [str(c.value or "").strip() for c in ws[1]]
    need = {"Case": "case", "Scenario": "scenario", "Step": "step", "Action": "action", "Expected result": "expected",
            "Actual result": "actual", "Pass/Fail": "result", "Tester": "tester", "Date": "date", "Defect ref": "defect",
            "Requirements": "requirements"}
    index = {key: head.index(name) for name, key in need.items() if name in head}
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not any(row):
            continue
        item = {key: row[i] if i < len(row) else None for key, i in index.items()}
        item["result"] = str(item.get("result") or "").strip().capitalize() or "Not run"
        if item["result"] == "Not run" and not item.get("case"):
            continue
        rows.append(item)
    return rows


def filled_in(path):
    """How many steps of a workbook the testers have filled in (anything typed in their columns)."""
    try:
        rows = read_results(path)
    except SystemExit:
        return 0
    return sum(1 for r in rows if r["result"] != "Not run"
               or any(str(r.get(k) or "").strip() for k in ("actual", "tester", "date", "defect")))


def keep_results(workbook, force):
    """Before the testers' workbook is written again: stop if they filled any of it in, or with `force` keep
    their copy beside it first. Their results are never lost to a new render."""
    workbook = Path(workbook)
    if not workbook.exists():
        return None
    try:
        steps = filled_in(workbook)
    except Exception as e:  # open in Excel, or not a workbook: do not write over what cannot be read
        sys.exit(f"Cannot read {workbook.name} to see whether the testers filled it in ({type(e).__name__}). "
                 "Close it in Excel and run this again. Nothing was written.")
    if not steps:
        return None
    if not force:
        sys.exit(f"The testers have filled in {steps} step{'s' if steps != 1 else ''} of {workbook.name}: writing it again "
                 "would lose their results. Nothing was written. Read them first (uat.py results), or add --force to "
                 "write it anyway: the filled-in workbook is then kept beside it under a new name.")
    kept = workbook.with_name(f"{workbook.stem} - results kept {dt.datetime.now().strftime('%Y-%m-%d %H%M')}.xlsx")
    if kept.exists():
        sys.exit(f"{kept.name} exists already: run this again in a minute. Nothing was written.")
    try:
        os.replace(workbook, kept)
    except PermissionError:
        sys.exit(f"Cannot move {workbook.name} aside: close it in Excel and run this again. Nothing was written.")
    print(f"  The testers' filled-in workbook is kept as {kept.name}")
    return kept


def cmd_results(project, name):
    import layout

    folder = layout.uat_output(project)
    if name:
        path = Path(name) if Path(name).exists() else folder / name
    else:
        found = sorted(f for f in folder.glob("*.xlsx") if f.name != layout.DEFECT_LOG) if folder.exists() else []
        path = found[-1] if found else None
    if not path or not path.exists():
        sys.exit("No filled-in UAT workbook found: name the file.")
    rows = read_results(path)
    counts = Counter(r["result"] for r in rows)
    print(f"UAT results in {path.name}: {len(rows)} steps; " + ", ".join(f"{counts.get(k, 0)} {k.lower()}" for k in RESULTS))
    other = sorted(k for k in counts if k not in RESULTS)
    if other:
        print(f"  Results not understood: {', '.join(other)}")
    for kind in ("Fail", "Blocked"):
        listed = [r for r in rows if r["result"] == kind]
        if listed:
            print(f"\n{'Failed' if kind == 'Fail' else 'Blocked'}: {len(listed)}")
        for r in listed:
            when = r.get("date")
            when = readable(when.date().isoformat() if hasattr(when, "date") else when) if when else ""
            print(f"  {r.get('case')} step {r.get('step')}: {r.get('scenario')}"
                  + (f" [{r['requirements']}]" if r.get("requirements") else "")
                  + (f" defect {r['defect']}" if r.get("defect") else ""))
            print(f"    expected: {r.get('expected')}")
            print(f"    actual:   {r.get('actual') or '(not written)'}" + (f"  ({r.get('tester') or ''} {when})".rstrip(" ()") + ")" if r.get("tester") or when else ""))
    if counts.get("Blocked"):
        print("\n  A blocked step usually lacks test data or access: check the scripts' Test data list with the client.")
    log, changed = record_defects(project, rows, path.name, scripts_for(project, path))
    if any(changed.values()):
        save_defects(project, log)
    print(f"\nDefect log ({layout.shown(project, layout.defect_log(project))}): "
          + "; ".join(f"{len(ids)} {what}: {', '.join(ids)}" for what, ids in changed.items() if ids) if any(changed.values())
          else "\nDefect log: nothing new from this workbook.")
    print_defects(log, only_active=True)
    write_defects_xlsx(project, log)


# ---------------------------------------------------------------- the defect log
def scripts_for(project, workbook):
    """The UAT scripts a workbook was written from: the one of the same name, else the newest; {} when none."""
    import layout

    folder = layout.uat_source(project)
    same = folder / Path(workbook).with_suffix(".json").name
    found = [same] if same.exists() else sorted(folder.glob("* uat scripts *.json")) if folder.exists() else []
    try:
        return json.loads(found[-1].read_text(encoding="utf-8")) if found else {}
    except ValueError:
        return {}


def load_defects(project):
    import layout

    path = layout.defect_log(project)
    if not path.exists():
        return {"project": Path(project).name, "defects": []}
    try:
        log = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        sys.exit(f"{layout.shown(project, path)} is not valid JSON: {e}")
    log.setdefault("defects", [])
    return log


def defect_errors(log):
    errors, seen = [], set()
    for n, d in enumerate(log.get("defects") or [], 1):
        if not isinstance(d, dict):
            errors.append(f"defect {n}: not a defect")
            continue
        did = str(d.get("id") or f"defect {n}")
        if not re.fullmatch(r"D-\d{3,}", str(d.get("id") or "")):
            errors.append(f"{did}: the id must be D- and a number, for example D-001")
        if did in seen:
            errors.append(f"{did} is used twice")
        seen.add(did)
        if d.get("status") not in DEFECT_STATUSES:
            errors.append(f"{did}: status must be one of {', '.join(DEFECT_STATUSES)}")
        if not d.get("case"):
            errors.append(f"{did}: needs the UAT case it was found in")
    return errors


def save_defects(project, log):
    import layout

    errors = defect_errors(log)
    if errors:
        sys.exit("The defect log has mistakes; nothing was written:\n  " + "\n  ".join(errors))
    path = layout.defect_log(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def as_date(value):
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value or "")[:10]


def record_defects(project, rows, source, scripts, today=None):
    """Bring the defect log up to date with a filled-in workbook (`source`, its file name): a failed step not in the
    log yet becomes a defect (open), one fixed or sent for retest that fails again is open again, and one fixed or
    sent for retest whose step now passes is closed. A workbook read before changes nothing.
    Returns (log, {"new": [ids], "open again": [ids], "closed": [ids]})."""
    today = today or dt.date.today().isoformat()
    log = load_defects(project)
    cases = {str(c.get("id")): c for c in scripts.get("cases") or [] if isinstance(c, dict)}
    by_step = {(str(d.get("case")), str(d.get("step"))): d for d in log["defects"]}
    changed = OrderedDict([("new", []), ("open again", []), ("closed", [])])
    numbers = [int(d["id"][2:]) for d in log["defects"] if re.fullmatch(r"D-\d+", str(d.get("id") or ""))]
    for r in rows:
        if r["result"] not in ("Fail", "Pass") or not r.get("case"):
            continue
        key = (str(r["case"]), str(r.get("step")))
        d = by_step.get(key)
        if d is not None and source in d.get("seen_in", []):
            continue
        if r["result"] == "Pass":
            if d is not None and d["status"] in ("fixed", "retest"):
                d["status"] = "closed"
                d["history"].append({"date": today, "status": "closed", "note": f"Passed in {source}"})
                d.setdefault("seen_in", []).append(source)
                changed["closed"].append(d["id"])
            continue
        case = cases.get(str(r["case"])) or {}
        reqs = [x.strip() for x in str(r.get("requirements") or "").split(",") if x.strip()] or list(case.get("requirements") or [])
        found = {"actual": str(r.get("actual") or ""), "tester": str(r.get("tester") or ""), "date": as_date(r.get("date")),
                 "client_ref": str(r.get("defect") or "")}
        if d is None:
            numbers.append(max(numbers, default=0) + 1)
            d = {"id": f"D-{numbers[-1]:03d}", **found, "case": str(r["case"]), "scenario": str(r.get("scenario") or case.get("title") or ""),
                 "step": r.get("step"), "action": str(r.get("action") or ""), "expected": str(r.get("expected") or ""),
                 "requirements": reqs, "priority": case.get("priority") or "", "found_in": source, "seen_in": [source],
                 "status": "open", "history": [{"date": today, "status": "open", "note": f"Failed in {source}"}]}
            log["defects"].append(d)
            by_step[key] = d
            changed["new"].append(d["id"])
            continue
        d.setdefault("seen_in", []).append(source)
        if d["status"] in ("fixed", "retest", "closed"):
            d.update({k: v for k, v in found.items() if v})
            d["status"] = "open"
            d["history"].append({"date": today, "status": "open", "note": f"Failed again in {source}"})
            changed["open again"].append(d["id"])
    return log, changed


def set_defects(project, ids, status, note="", cr="", today=None):
    """Change the status of defects in the log, with a note in each one's history. Returns the log."""
    if status not in DEFECT_STATUSES:
        sys.exit(f"'{status}' is not a defect status: use one of {', '.join(DEFECT_STATUSES)}")
    if status == "not a defect" and not note:
        sys.exit('Say why it is not a defect: --note "<why>" (the system does what was signed, for example).')
    log = load_defects(project)
    by_id = {d.get("id"): d for d in log["defects"]}
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"Not in the defect log: {', '.join(missing)}. Nothing was changed.")
    for i in ids:
        d = by_id[i]
        d["status"] = status
        if cr:
            d["cr"] = cr
        d.setdefault("history", []).append({"date": today or dt.date.today().isoformat(), "status": status, "note": note})
    save_defects(project, log)
    return log


def print_defects(log, only_active=False):
    defects = log.get("defects") or []
    counts = Counter(d.get("status") for d in defects)
    if not defects:
        return
    print(f"  {len(defects)} defect{'s' if len(defects) != 1 else ''}: " + ", ".join(f"{counts[s]} {s}" for s in DEFECT_STATUSES if counts.get(s)))
    for d in defects:
        if only_active and d.get("status") in ("closed", "not a defect", "change request"):
            continue
        reqs = ", ".join(d.get("requirements") or [])
        print(f"  {d['id']} [{d.get('status')}] {d.get('case')} step {d.get('step')}: {d.get('scenario')}"
              + (f" ({reqs})" if reqs else "") + (f" client ref {d['client_ref']}" if d.get("client_ref") else "")
              + (f" -> {d['cr']}" if d.get("cr") else ""))


def write_defects_xlsx(project, log):
    """"Defect log.xlsx" in the project's 6 UAT folder: one row per defect, for the team and the client's UAT lead."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    import layout
    import sheets

    defects = log.get("defects") or []
    if not defects:
        return None
    out = layout.defect_log_xlsx(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = [("Defect", 9), ("Status", 14), ("Priority", 9), ("Case", 10), ("Scenario", 34), ("Step", 6), ("Requirements", 18),
               ("Expected result", 44), ("Actual result", 44), ("Tester", 16), ("Found on", 12), ("Client ref", 10),
               ("Change request", 12), ("Last change", 40)]
    wb = Workbook()
    ws = sheets.setup(wb.active, [w for _, w in columns], freeze="C2")
    ws.title = "Defects"
    for c, (name, _) in enumerate(columns, 1):
        ws.cell(row=1, column=c, value=name)
    for r, d in enumerate(defects, 2):
        last = (d.get("history") or [{}])[-1]
        when = readable(last.get("date", "")) if last.get("date") else ""
        values = [d.get("id"), d.get("status"), d.get("priority"), d.get("case"), d.get("scenario"), d.get("step"),
                  ", ".join(d.get("requirements") or []), d.get("expected"), d.get("actual"), d.get("tester"),
                  readable(d["date"]) if d.get("date") else "", d.get("client_ref"), d.get("cr", ""),
                  f"{when}: {last.get('status', '')}" + (f", {last['note']}" if last.get("note") else "")]
        for c, value in enumerate(values, 1):
            ws.cell(row=r, column=c, value=value)
    last_row = len(defects) + 1
    sheets.header(ws, 1, len(columns))
    sheets.rows(ws, 2, last_row, len(columns))
    sheets.status(ws, f"B2:B{last_row}", dict(DEFECT_STATUSES))
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last_row}"
    try:
        wb.save(str(out))
    except PermissionError:
        print(f"  Cannot write {out.name}: close it in Excel and run uat.py defects again. The log itself is saved.")
        return None
    print(f"  {layout.shown(project, out)}")
    return out


def cmd_defects(project):
    import layout

    log = load_defects(project)
    errors = defect_errors(log)
    if errors:
        sys.exit("The defect log has mistakes:\n  " + "\n  ".join(errors))
    if not log["defects"]:
        print("No defects logged yet: they come from the testers' workbook (uat.py results).")
        return
    print(f"Defect log ({layout.shown(project, layout.defect_log(project))}):")
    print_defects(log)
    write_defects_xlsx(project, log)


def cmd_defect(project, ids, status, note, cr):
    log = set_defects(project, ids, status, note, cr)
    print(f"{', '.join(ids)}: {status}" + (f" ({note})" if note else ""))
    if status == "change request" and not cr:
        d = next(x for x in log["defects"] if x["id"] == ids[0])
        print("  Take it to the change-request skill, which checks it against the signed version, for example:\n"
              f'    python -I tools/change_request.py scope {Path(project).as_posix()} "{d.get("actual") or d.get("scenario")}"\n'
              f"  Then record the CR on the defect: uat.py defect {Path(project).as_posix()} {ids[0]} \"change request\" --cr CR-00x")
    write_defects_xlsx(project, log)


# ---------------------------------------------------------------- commands
def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    values = {}
    for key in ("--date", "--note", "--cr"):
        if key in args:
            i = args.index(key)
            if i + 1 >= len(args):
                sys.exit(f"{key} needs a value, for example " + {"--date": "--date 2026-11-12", "--note": '--note "fixed in build 14"',
                                                                 "--cr": "--cr CR-004"}[key])
            values[key] = args[i + 1]
            del args[i:i + 2]
    date = values.get("--date")
    flags = {a for a in args if a.startswith("--")}
    args = [a for a in args if a not in flags]
    if args[:1] == ["defect"]:
        if len(args) < 4 or flags or "--date" in values:
            sys.exit(__doc__)
        if not Path(args[1]).is_dir():
            sys.exit(f"No project folder {args[1]}")
        return cmd_defect(args[1], args[2:-1], args[-1], values.get("--note", ""), values.get("--cr", ""))
    if len(args) not in (2, 3) or args[0] not in ("draft", "check", "render", "results", "defects") \
            or (args[0] in ("draft", "defects") and len(args) != 2) or set(values) - {"--date"} \
            or flags - {"--current", "--force"} or (args[0] not in ("draft", "render") and flags) \
            or (args[0] == "render" and flags - {"--force"}):
        sys.exit(__doc__)
    command, project = args[0], args[1]
    if not Path(project).is_dir():
        sys.exit(f"No project folder {project}")
    if command == "defects":
        return cmd_defects(project)
    if command == "draft":
        try:
            date = dt.date.fromisoformat(date).isoformat() if date else dt.date.today().isoformat()
        except ValueError:
            sys.exit(f"--date {date} is not a date: write it as YYYY-MM-DD")
        spec, rel, based_on = choose_spec(project, "--current" in flags)
        scripts = draft(spec, rel, based_on, date)
        import layout

        folder = layout.uat_source(project)
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{date} uat scripts v{scripts['spec_version']}.json"
        if out.exists() and "--force" not in flags:
            sys.exit(f"{out.name} exists already (it may have been refined since): pass --force to replace it, or refine that one.")
        out.write_text(json.dumps(scripts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        current = (load_yaml(layout.spec_file(project)).get("project") or {}).get("version") if rel != "spec/app.yaml" else None
        sm = summary(scripts, spec)
        todo = sum(1 for c in scripts["cases"] if c.get("todo"))
        print(f"UAT draft for {scripts['project']}, written from {based_on} ({rel})")
        if current is not None and str(current) != scripts["spec_version"]:
            print(f"  The spec has moved on to v{current} since: UAT tests what was signed. Use --current for the current spec.")
        print(f"  {sm['cases']} scenarios, {sm['steps']} steps: " + ", ".join(f"{n} {k}" for k, n in sm["by_type"].items()))
        print(f"  Requirements covered: {sm['covered']} of {sm['requirements']} (each one not in a scenario has a case of its own to merge)")
        print(f"  Cases still to refine: {todo}")
        print(f"  {out}")
        return
    if command == "results":
        return cmd_results(project, args[2] if len(args) == 3 else None)
    path, scripts, spec = load(project, args[2] if len(args) == 3 else None)
    sm = summary(scripts, spec)
    line = (f"{sm['cases']} scenarios, {sm['steps']} steps, requirements covered {sm['covered']} of {sm['requirements']}"
            + (f", {sm['excluded']} not tested with a reason" if sm["excluded"] else ""))
    if command == "check":
        print(f"OK: {path.name}: {line}")
        return
    import layout

    out = layout.uat_output(project) if path.parent.resolve() == layout.uat_source(project).resolve() else path.parent
    out.mkdir(parents=True, exist_ok=True)
    for name in (path.with_suffix(".xlsx").name, path.with_suffix(".docx").name):
        target = out / name
        try:  # both files or neither: one open in Excel or Word stops it before anything is written
            if target.exists():
                open(target, "r+b").close()
        except PermissionError:
            sys.exit(f"Cannot write {name}: close it in Excel or Word and run this again. Nothing was written.")
    keep_results(out / path.with_suffix(".xlsx").name, "--force" in flags)
    xlsx = render_xlsx(scripts, spec, out / path.with_suffix(".xlsx").name)
    docx = render_docx(scripts, spec, out / path.with_suffix(".docx").name)
    print(f"UAT scripts for {scripts['project']}: {line}")
    print(f"  Workbook for the testers:   {xlsx}")
    print(f"  Test scripts for the client: {docx}")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
