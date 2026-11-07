"""Find requirements that contradict each other: everything a spec (or a client's document) says about the same
subject, side by side, with the clear clashes found mechanically.

Usage:
    python -I tools/contradictions.py projects/<slug> [--out <folder>] [--json] [--strict]
    python -I tools/contradictions.py --text <review>/extract/text.md [--out <folder>] [--json]

With a project, the spec (`_blueprint/spec/app.yaml`) is read; the pack is written to
`_blueprint/reviews/spec-v<version>-contradictions/` (pack.md and pack.json) unless --out names a folder.
With --text, an extracted document (`extract.py`'s text.md) is read and the pack written next to it (or to --out).

The pack has three parts, and says which is which:

1. Clashes (mechanical). Found from the spec's own structure; each one is a real contradiction unless the spec
   is wrong about something else. Spec mode only:
   - status-rule      a sentence (requirement, status meaning, scope, note …) says a role may, or may not,
                      cancel, edit or delete a record in a status, and the status rules say the opposite;
   - button-rule      a button that moves a record to a cancelled status is shown to a role the status's
                      cancel rule leaves out;
   - rule-move        a status lets someone cancel but cannot move to a cancelled status, or moves to one
                      (not automatically) while nobody may cancel;
   - out-of-scope     an integration in the spec is named under out_of_scope;
   - field-limit      one field is given two different limits (characters, KB, MB, GB);
   - field-optional   a required field is called optional.
   A negative sentence with a condition ("may not cancel after the leave starts") is a refinement, not a clash:
   it is listed under Look here instead.
2. Look here (word cues, for judgement). Pairs of statements about the same subject where one reads
   all-or-nothing and the other partial ("imports nothing" / "skips the bad rows"), one forbids what the other
   allows (shared action and a shared word), or they give different numbers of the same unit. Many are fine;
   each needs reading.
3. Everything said about each subject: each screen, dialog, status, field, integration and role, and themes
   (uploads and imports, cancelling, deleting, notifications, deadlines …), with every statement's location
   and text, for the reader to compare. A document (--text) has themes only.

What it cannot do: understand meaning. Two sentences that disagree in different words, about different
subjects, or by what one leaves out are found only by reading the pack. A sentence about cancelling, editing
or deleting is checked against the status rules only when it names the role before the action and the status
after it (or is a status's own meaning), and only when the rule is written.

--json prints the result as JSON instead of the summary. --strict exits with 1 when there is a clash.
"""
import argparse
import itertools
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layout  # noqa: E402

ACTIONS = {"cancel": "cancel", "withdraw": "cancel", "edit": "edit", "amend": "edit", "delete": "delete", "remove": "delete"}
PASSIVE = {"cancelled": "cancel", "canceled": "cancel", "withdrawn": "cancel", "edited": "edit", "amended": "edit",
           "deleted": "delete", "removed": "delete"}
NEGATION = re.compile(r"\b(not|cannot|can't|never|no longer|no one|nobody)\b", re.I)
# a negation close before the verb: "shall not be able to change", "cannot cancel"
NEAR_NEGATION = re.compile(r"\b(?:not|cannot|can't|never|no longer)\s+(?:[\w-]+\s+){0,4}$", re.I)
CONDITION = re.compile(r"\b(after|before|once|when|whenever|unless|if|within|until|while|except)\b", re.I)
CLAUSE_SPLIT = re.compile(r"[.;:!?]\s+|\s+(?:and then|but|whereas)\s+", re.I)
CANCEL_LIKE = re.compile(r"cancel|withdr", re.I)

THEMES = {
    "Uploads and imports": r"upload\w*|import\w*|bulk|csv|spreadsheet|template file",
    "Files and attachments": r"attach\w*|files?|pdf|jpe?g|png|\d+\s*[mkg]b",
    "Cancelling and withdrawing": r"cancel\w*|withdr\w*",
    "Deleting": r"delet\w*|purg\w*|removed?",
    "Editing after saving or submitting": r"edit\w*|amend\w*|modif\w*|resubmit\w*|re-submit\w*|reopen\w*|re-open\w*",
    "Approving and rejecting": r"approv\w*|reject\w*|send back|sent back|return(?:ed)? to",
    "Notifications": r"e-?mails?|e-?mailed|notif\w*|inform\w*|alerts?|sms|reminders?",
    "Deadlines and time limits": r"deadlines?|expir\w*|overdue|sla|within\s+\d+|\d+\s+(?:working\s+)?(?:days?|hours?|minutes?)",
    "Access and visibility": r"access\w*|visib\w*|permission\w*|can see|cannot see|only see|view only|read-only",
    "Numbering and references": r"running number|reference number|ref no|prefix\w*|numbering",
    "Duplicates": r"duplicat\w*|already exists?|unique\w*",
    "Errors and failures": r"invalid|errors?|fail\w*|retr(?:y|ies|ied)|rolled back|roll back",
    "Retention and archiving": r"retention|retain\w*|archiv\w*|kept for",
}
THEME_RE = {name: re.compile(rf"\b(?:{pattern})\b", re.I) for name, pattern in THEMES.items()}

ALL_OR_NOTHING = re.compile(
    r"\b(nothing|none of|no (?:records?|rows?|data|lines?) (?:is|are)|whole (?:file|batch|upload|list)|"
    r"entire (?:file|batch|upload|list)|all[- ]or[- ]nothing|rolled back|roll(?:s|ed)? back|"
    r"reject(?:s|ed)? the (?:whole|entire|file|batch|upload)|is rejected in full)\b", re.I)
PARTIAL = re.compile(
    r"\b(skip(?:s|ped|ping)?|(?:valid|good|correct|remaining|other) (?:rows?|records?|lines?)|rest of the|"
    r"partially|row by row|each valid|only the valid)\b", re.I)
# all-or-nothing against partial is only read between statements about loading or processing data
DATA_THEMES = {"theme:Uploads and imports", "theme:Errors and failures", "theme:Files and attachments"}
VERBS = ("cancel", "edit", "delete", "approve", "reject", "import", "upload", "submit", "resubmit", "reopen", "view",
         "see", "download", "export", "notify", "e-mail", "email", "send", "attach", "change", "amend", "withdraw",
         "assign", "override", "create", "add", "close")
VERB_RE = {v: re.compile(rf"\b{re.escape(v)}\b", re.I) for v in VERBS}
NUMBER_UNIT = re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s*(working days?|days?|hours?|minutes?|mb|kb|gb|characters?|chars|times|attempts?|retries|%)",
                         re.I)
LIMIT_UNITS = {"mb", "kb", "gb", "character"}
STOP = set("""a an the and or of to in on for by with from at as is are be been being was were this that these those it its
shall should must may can will would could system user users record records application applications when if then than
not no only any all each every their his her they them which who whom what where after before once also into out
upon via per has have had do does done able allow allowed allows""".split())


# ------------------------------------------------------------------ statements
class Statement:
    """One thing the spec or document says: where it is, its text, and the subjects it belongs to by structure."""

    def __init__(self, loc, text, owners=(), kind="text", status=None, field=None):
        self.loc, self.text, self.kind = loc, " ".join(str(text).split()), kind
        self.owners = set(owners)  # subject keys it belongs to by where it is in the spec
        self.status = status       # the status id, for a status's own meaning
        self.field = field         # (screen or dialog key, field dict), for a field's own texts
        self.subjects = set(self.owners)

    def quote(self, limit=300):
        return self.text if len(self.text) <= limit else self.text[: limit - 1] + "…"

    def as_dict(self):
        return {"loc": self.loc, "text": self.text}


def _text(value):
    return "" if value is None else str(value).strip()


def _list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _alias_re(aliases):
    aliases = sorted({a.strip() for a in aliases if a and len(a.strip()) >= 2}, key=len, reverse=True)
    if not aliases:
        return None
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(a) for a in aliases) + r")(?:s|es)?(?![\w-])", re.I)


class Spec:
    """The spec's names, resolved once: roles, statuses, screens, dialogs, fields and integrations."""

    def __init__(self, spec):
        self.spec = spec or {}
        self.roles = {r["id"]: r for r in _list(self.spec.get("roles")) if isinstance(r, dict) and r.get("id")}
        self.statuses = {s["id"]: s for s in _list(self.spec.get("statuses")) if isinstance(s, dict) and s.get("id")}
        self.screens = {s["id"]: s for s in _list(self.spec.get("screens")) if isinstance(s, dict) and s.get("id")}
        self.dialogs = {d["id"]: d for d in _list(self.spec.get("dialogs")) if isinstance(d, dict) and d.get("id")}
        self.integrations = [i for i in _list(self.spec.get("integrations")) if isinstance(i, dict) and i.get("system")]
        self.role_re = {rid: _alias_re([r.get("name"), rid.replace("-", " ").replace("_", " ")]) for rid, r in self.roles.items()}
        firsts = {}
        for sid, s in self.statuses.items():
            words = _text(s.get("name")).split()
            if len(words) > 1 and len(words[0]) >= 4:
                firsts.setdefault(words[0].lower(), []).append(sid)
        self.status_re = {}
        for sid, s in self.statuses.items():
            aliases = [s.get("name"), sid.replace("-", " ").replace("_", " ")]
            words = _text(s.get("name")).split()
            if len(words) > 1 and len(firsts.get(words[0].lower(), [])) == 1:
                aliases.append(words[0])
            self.status_re[sid] = _alias_re(aliases)

    def status_id(self, ref):
        ref = _text(ref)
        if ref in self.statuses:
            return ref
        for sid, s in self.statuses.items():
            if _text(s.get("name")).lower() == ref.lower():
                return sid
        return None

    def status_name(self, sid):
        return _text(self.statuses.get(sid, {}).get("name")) or sid

    def role_name(self, rid):
        return _text(self.roles.get(rid, {}).get("name")) or rid

    def rule(self, sid, action):
        """The roles a status rule allows for an action: a set of role ids, or None when the rule is not written."""
        status = self.statuses.get(sid, {})
        if action not in status:
            return None
        value = status.get(action)
        if value is None:
            return None
        allowed = set()
        for item in _list(value):
            item = _text(item)
            if item.lower() == "all":
                return set(self.roles)
            if item.lower() in ("none", ""):
                continue
            rid = item if item in self.roles else next((r for r, d in self.roles.items() if _text(d.get("name")).lower() == item.lower()), item)
            allowed.add(rid)
        return allowed

    def mentions(self, regexes, text):
        return [key for key, rx in regexes.items() if rx is not None and rx.search(text)]

    def title(self, kind, key):
        if kind == "screen":
            return _text(self.screens.get(key, {}).get("title")) or key
        if kind == "dialog":
            return _text(self.dialogs.get(key, {}).get("title")) or key
        return key


def _rules_text(sp, sid):
    s = sp.statuses[sid]
    parts = []
    for action in ("edit", "cancel", "delete"):
        allowed = sp.rule(sid, action)
        if allowed is not None:
            parts.append(f"{action.title()}: {', '.join(sp.role_name(r) for r in sorted(allowed)) or 'none'}")
    if "next" in s:
        nxt = [sp.status_name(sp.status_id(n) or n) for n in _list(s.get("next"))]
        parts.append(f"Next: {', '.join(nxt) or 'none (final)'}")
    if s.get("auto"):
        parts.append(f"Automatic: {', '.join(sp.status_name(sp.status_id(n) or n) for n in _list(s.get('auto')))}")
    return ". ".join(parts)


def _target_status(sp, button):
    """The status a button (or the dialog it opens) moves its record to, as an id, or None."""
    ref = button.get("set_status")
    if ref is None and button.get("dialog") in sp.dialogs:
        ref = (sp.dialogs[button["dialog"]].get("confirm") or {}).get("set_status")
    if ref is None or isinstance(ref, dict):
        return None
    return sp.status_id(ref)


def _field_statements(out, where_key, where_title, field, prefix):
    label = _text(field.get("label")) or _text(field.get("id"))
    loc = f"{prefix} {where_title}: field {label}"
    own = {where_key, f"field:{label.lower()}"}
    for key, word in (("help", "help"), ("validation", "rule"), ("source", "source"), ("placeholder", "placeholder")):
        if _text(field.get(key)):
            out.append(Statement(f"{loc} ({word})", field[key], own, "field", field=(where_key, field)))
    facts = []
    if field.get("required"):
        facts.append("required")
    if field.get("readonly"):
        facts.append("read-only")
    if field.get("length"):
        facts.append(f"up to {field['length']} characters")
    if facts:
        out.append(Statement(f"{loc} (settings)", f"{label}: {', '.join(facts)}.", own, "field-settings", field=(where_key, field)))


def spec_statements(spec):
    """Every statement in a spec, each with its location and the subjects it belongs to by structure."""
    sp = spec if isinstance(spec, Spec) else Spec(spec)
    s = sp.spec
    out = []
    for i, para in enumerate(_list(s.get("overview")), 1):
        out.append(Statement(f"Overview, paragraph {i}", para, kind="overview"))
    scope = s.get("scope") or {}
    for key, words in (("in_scope", "in scope"), ("out_of_scope", "out of scope"), ("assumptions", "assumption")):
        for i, line in enumerate(_list(scope.get(key)), 1):
            out.append(Statement(f"Scope: {words} {i}", line, {"scope"}, f"scope:{key}"))
    for rid, r in sp.roles.items():
        for key in ("description", "scope"):
            if _text(r.get(key)):
                out.append(Statement(f"Role {sp.role_name(rid)}: {key}", r[key], {f"role:{rid}"}, "role"))
    for sid, st in sp.statuses.items():
        if _text(st.get("meaning")):
            out.append(Statement(f"Status {sp.status_name(sid)}: meaning", st["meaning"], {f"status:{sid}"}, "status-meaning", status=sid))
        rules = _rules_text(sp, sid)
        if rules:
            out.append(Statement(f"Status {sp.status_name(sid)}: rules", rules, {f"status:{sid}"}, "status-rules", status=sid))
    for scr_id, scr in sp.screens.items():
        key, title = f"screen:{scr_id}", sp.title("screen", scr_id)
        if _text(scr.get("description")):
            out.append(Statement(f"Screen {title}: description", scr["description"], {key}, "screen"))
        for sec in _list(scr.get("sections")):
            if not isinstance(sec, dict):
                continue
            if _text(sec.get("note")):
                out.append(Statement(f"Screen {title}: section {_text(sec.get('title'))} (note)", sec["note"], {key}, "screen"))
            for field in _list(sec.get("fields")):
                if isinstance(field, dict):
                    _field_statements(out, key, title, field, "Screen")
        for stat in _list(scr.get("stats")):
            if isinstance(stat, dict) and _text(stat.get("formula")):
                out.append(Statement(f"Screen {title}: figure {_text(stat.get('label'))}", stat["formula"], {key}, "screen"))
        lst = scr.get("list") if isinstance(scr.get("list"), dict) else {}
        buttons = [(b, "button") for b in _list(scr.get("buttons"))] + [(b, "row action") for b in _list(lst.get("actions"))] + \
                  [(b, "toolbar button") for b in _list(lst.get("toolbar"))]
        for b, what in buttons:
            if not isinstance(b, dict) or not (b.get("dialog") or b.get("set_status") or _text(b.get("toast")) or b.get("roles")):
                continue  # a button that only opens another screen says nothing
            owners = {key}
            if b.get("dialog") in sp.dialogs:
                owners.add(f"dialog:{b['dialog']}")
            target = _target_status(sp, b)
            parts = [f"{what.capitalize()} '{_text(b.get('label'))}'"]
            if b.get("roles"):
                parts.append(f"for {', '.join(sp.role_name(r) for r in _list(b['roles']))}")
            when = (b.get("when") or {}).get("status") if isinstance(b.get("when"), dict) else None
            if when:
                parts.append(f"when {' or '.join(_text(w) for w in _list(when))}")
            if target:
                parts.append(f"moves the record to {sp.status_name(target)}")
                owners.add(f"status:{target}")
            if _text(b.get("toast")):
                parts.append(f"says \"{_text(b['toast'])}\"")
            out.append(Statement(f"Screen {title}: {what} {_text(b.get('label'))}", " ".join(parts) + ".", owners, "button"))
    opened_from = {}
    for scr_id, scr in sp.screens.items():
        lst = scr.get("list") if isinstance(scr.get("list"), dict) else {}
        for b in _list(scr.get("buttons")) + _list(lst.get("actions")):
            if isinstance(b, dict) and b.get("dialog"):
                opened_from.setdefault(b["dialog"], set()).add(f"screen:{scr_id}")
    for did, d in sp.dialogs.items():
        key, title = f"dialog:{did}", sp.title("dialog", did)
        owners = {key} | opened_from.get(did, set())
        if _text(d.get("message")):
            out.append(Statement(f"Dialog {title}: message", d["message"], owners, "dialog"))
        for field in _list(d.get("fields")):
            if isinstance(field, dict):
                before = len(out)
                _field_statements(out, key, title, field, "Dialog")
                for st in out[before:]:
                    st.owners |= owners
                    st.subjects |= owners
        confirm = d.get("confirm") if isinstance(d.get("confirm"), dict) else {}
        if _text(confirm.get("toast")):
            out.append(Statement(f"Dialog {title}: confirm message", confirm["toast"], owners, "dialog"))
    for group in _list(s.get("requirements")):
        if not isinstance(group, dict):
            continue
        gid = _text(group.get("id"))
        gscreens = {f"screen:{x}" for x in _list(group.get("screens"))}
        for n, item in enumerate(_list(group.get("items")), 1):
            text, iscreens, note = item, set(), None
            if isinstance(item, dict):
                text, note = item.get("text"), item.get("note")
                iscreens = {f"screen:{x}" for x in _list(item.get("screens"))}
            owners = iscreens or gscreens
            if _text(text):
                out.append(Statement(f"{gid}.{n}", text, owners, "requirement"))
            if _text(note):
                out.append(Statement(f"{gid}.{n} (internal note)", note, owners, "note"))
    for n in _list(s.get("notifications")):
        if isinstance(n, dict):
            text = f"{_text(n.get('event'))}: to {_text(n.get('recipient'))}. {_text(n.get('template'))}".strip()
            out.append(Statement(f"Notification '{_text(n.get('event'))}'", text, set(), "notification"))
    for integ in sp.integrations:
        key = f"integration:{_text(integ['system']).lower()}"
        for part, words in (("purpose", "purpose"), ("notes", "notes"), ("trigger", "trigger"), ("data", "data"), ("on_failure", "on failure")):
            if _text(integ.get(part)):
                out.append(Statement(f"Integration {_text(integ['system'])}: {words}", integ[part], {key}, "integration"))
    for item in _list(s.get("nfr")):
        if isinstance(item, dict) and _text(item.get("requirement")):
            out.append(Statement(f"NFR {_text(item.get('area'))}", item["requirement"], set(), "nfr"))
    for item in _list(s.get("glossary")):
        if isinstance(item, dict) and _text(item.get("meaning")):
            out.append(Statement(f"Glossary {_text(item.get('term'))}", item["meaning"], set(), "glossary"))
    flow = s.get("process_flow") if isinstance(s.get("process_flow"), dict) else {}
    for i, note in enumerate(_list(flow.get("notes")), 1):
        out.append(Statement(f"Process flow: note {i}", note, set(), "flow"))
    for sec in _list(s.get("extra_sections")):
        if not isinstance(sec, dict):
            continue
        title = _text(sec.get("title"))
        for i, block in enumerate(_list(sec.get("content")), 1):
            if not isinstance(block, dict):
                continue
            if _text(block.get("text")):
                out.append(Statement(f"{title}: paragraph {i}", block["text"], set(), "extra"))
            for j, bullet in enumerate(_list(block.get("bullets")), 1):
                out.append(Statement(f"{title}: block {i}, bullet {j}", bullet, set(), "extra"))
            table = block.get("table") if isinstance(block.get("table"), dict) else {}
            for j, row in enumerate(_list(table.get("rows")), 1):
                out.append(Statement(f"{title}: table row {j}", " | ".join(_text(c) for c in _list(row)), set(), "extra"))
    return [st for st in out if st.text]


def link_subjects(sp, statements):
    """Add to each statement the subjects it names: screens, dialogs, statuses, roles, integrations, fields, themes."""
    screen_re = {f"screen:{k}": _alias_re([_text(v.get("title"))]) for k, v in sp.screens.items()}
    dialog_re = {f"dialog:{k}": _alias_re([_text(v.get("title"))]) for k, v in sp.dialogs.items()}
    status_re = {f"status:{k}": v for k, v in sp.status_re.items()}
    role_re = {f"role:{k}": v for k, v in sp.role_re.items()}
    integ_re = {f"integration:{_text(i['system']).lower()}": _alias_re([_text(i["system"])]) for i in sp.integrations}
    labels = set()
    for st in statements:
        if st.field:
            labels.add(_text(st.field[1].get("label")).lower())
    field_re = {f"field:{lab}": _alias_re([lab]) for lab in labels if len(lab) >= 4}
    for st in statements:
        for regexes in (screen_re, dialog_re, status_re, role_re, integ_re, field_re):
            st.subjects.update(sp.mentions(regexes, st.text))
        st.subjects.update(f"theme:{name}" for name, rx in THEME_RE.items() if rx.search(st.text))
    return statements


# ------------------------------------------------------------------ mechanical clashes
def _clauses(text):
    return [c for c in CLAUSE_SPLIT.split(text) if c and c.strip()]


def _role_hits(sp, text):
    """[(start, end, role id)] for each role named in a text, the longer name winning where two overlap."""
    hits = []
    for rid, rx in sp.role_re.items():
        if rx is None:
            continue
        hits += [(m.start(), m.end(), rid) for m in rx.finditer(text)]
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    kept = []
    for h in hits:
        if kept and h[0] < kept[-1][1]:
            continue
        kept.append(h)
    return kept


def _status_hits(sp, text):
    return [sid for sid, rx in sp.status_re.items() if rx is not None and rx.search(text)]


def _claims(sp, st):
    """What a sentence says about who may cancel, edit or delete in which status: [(action, roles, statuses, allowed,
    conditional)]. Only the plain shapes: '<role> … <action> … <status>', '<status> … be <done> by <role>', and a
    status's own meaning naming a role and an action."""
    claims = []
    for clause in _clauses(st.text):
        for m in re.finditer(r"\b(" + "|".join(ACTIONS) + r")\b", clause, re.I):
            action = ACTIONS[m.group(1).lower()]
            before, after = clause[: m.start()], clause[m.end():]
            roles = [rid for _, _, rid in _role_hits(sp, before)]
            if not roles:
                continue
            cond = CONDITION.search(after)
            if st.status:
                statuses = [st.status]
            else:  # a status named inside a condition ("until it is picked up") is not the one acted on
                statuses = _status_hits(sp, after[: cond.start()] if cond else after)
                if not statuses:
                    continue
            claims.append((action, roles[-1:] if " or " not in before[-40:] else roles, statuses,
                           not NEGATION.search(before), bool(CONDITION.search(clause))))
        for m in re.finditer(r"\bbe\s+(" + "|".join(PASSIVE) + r")\s+by\b", clause, re.I):
            action = PASSIVE[m.group(1).lower()]
            before, after = clause[: m.start()], clause[m.end():]
            roles = [rid for _, _, rid in _role_hits(sp, after)]
            statuses = [st.status] if st.status else _status_hits(sp, before)
            if roles and statuses:
                claims.append((action, roles, statuses, not NEGATION.search(before), bool(CONDITION.search(clause))))
    return claims


def _clash(rule, subject, a, b, why):
    return {"rule": rule, "subject": subject, "a": a.as_dict() if isinstance(a, Statement) else a,
            "b": b.as_dict() if isinstance(b, Statement) else b, "why": why}


def clashes(sp, statements):
    found, looks = [], []
    rules = {sid: st for st in statements if st.kind == "status-rules" for sid in [st.status]}
    # status-rule: a sentence against the status rules
    for st in statements:
        if st.kind in ("status-rules", "button", "field-settings"):
            continue
        for action, roles, statuses, allowed, conditional in _claims(sp, st):
            for sid in statuses:
                rule = sp.rule(sid, action)
                if rule is None or sid not in rules:
                    continue
                for rid in roles:
                    if allowed == (rid in rule):
                        continue
                    who = ", ".join(sp.role_name(r) for r in sorted(rule)) or "nobody"
                    if allowed:
                        why = (f"It lets {sp.role_name(rid)} {action} a record in {sp.status_name(sid)}; the status rules "
                               f"allow {who} to {action} there.")
                    else:
                        why = (f"It says {sp.role_name(rid)} may not {action} a record in {sp.status_name(sid)}; the status "
                               f"rules allow {who} to {action} there.")
                    item = _clash("status-rule", f"status:{sid}", st, rules[sid], why)
                    if conditional and (not allowed or st.status):
                        item["why"] += " The sentence has a condition, so it may be about another case: read both."
                        looks.append(item)
                    else:
                        found.append(item)
    # button-rule: a cancelling button shown to a role the cancel rule leaves out
    for scr_id, scr in sp.screens.items():
        lst = scr.get("list") if isinstance(scr.get("list"), dict) else {}
        for b, what, where in [(b, "button", None) for b in _list(scr.get("buttons"))] + \
                               [(b, "row action", lst.get("where")) for b in _list(lst.get("actions"))]:
            if not isinstance(b, dict):
                continue
            target = _target_status(sp, b)
            if not target or not CANCEL_LIKE.search(target + " " + sp.status_name(target)):
                continue
            when = b.get("when") if isinstance(b.get("when"), dict) else {}
            froms = when.get("status") or (where.get("status") if isinstance(where, dict) else None)
            from_ids = [sp.status_id(x) for x in _list(froms)]
            roles = _list(b.get("roles")) or _list(scr.get("roles")) or list(sp.roles)
            label = _text(b.get("label"))
            bst = next((x for x in statements if x.kind == "button" and x.loc.endswith(f"{what} {label}")
                        and x.loc.startswith(f"Screen {sp.title('screen', scr_id)}:")), None)
            for sid in filter(None, from_ids):
                rule = sp.rule(sid, "cancel")
                if rule is None or sid not in rules:
                    continue
                for rid in roles:
                    if rid in sp.roles and rid not in rule:
                        found.append(_clash("button-rule", f"status:{sid}", bst, rules[sid],
                                            f"{sp.role_name(rid)} sees '{label}' on {sp.title('screen', scr_id)}, which cancels a "
                                            f"record in {sp.status_name(sid)}; the status rules allow "
                                            f"{', '.join(sp.role_name(r) for r in sorted(rule)) or 'nobody'} to cancel there."))
    # rule-move: the cancel rule against where the status can go
    cancel_ids = [sid for sid in sp.statuses if CANCEL_LIKE.search(sid + " " + sp.status_name(sid))]
    if cancel_ids:
        for sid, s in sp.statuses.items():
            if sid in cancel_ids or "next" not in s or sid not in rules:
                continue
            rule = sp.rule(sid, "cancel")
            nxt = {sp.status_id(n) for n in _list(s.get("next"))}
            auto = {sp.status_id(n) for n in _list(s.get("auto"))}
            to_cancel = [c for c in cancel_ids if c in nxt and c not in auto]
            if rule and not (set(cancel_ids) & nxt):
                found.append(_clash("rule-move", f"status:{sid}", rules[sid], rules[sid],
                                    f"{', '.join(sp.role_name(r) for r in sorted(rule))} may cancel in {sp.status_name(sid)}, "
                                    f"but it cannot move to {sp.status_name(cancel_ids[0])}."))
            elif rule is not None and not rule and to_cancel:
                found.append(_clash("rule-move", f"status:{sid}", rules[sid], rules[sid],
                                    f"{sp.status_name(sid)} moves to {sp.status_name(to_cancel[0])}, but nobody may cancel there."))
    # out-of-scope: an integration named as out of scope
    for st in statements:
        if st.kind != "scope:out_of_scope":
            continue
        for integ in sp.integrations:
            rx = _alias_re([_text(integ["system"])])
            if rx and rx.search(st.text):
                own = next((x for x in statements if x.kind == "integration" and x.loc.startswith(f"Integration {_text(integ['system'])}:")),
                           {"loc": f"Integration {_text(integ['system'])}", "text": _text(integ.get("purpose"))})
                looks.append(_clash("out-of-scope", f"integration:{_text(integ['system']).lower()}", st, own,
                                    f"{_text(integ['system'])} is an integration of this spec and is named under out of scope: "
                                    f"either one is wrong, or the exclusion should say which part is left out."))
    # field-limit and field-optional
    seen = set()
    for st in statements:
        if not st.field or id(st.field[1]) in seen:
            continue
        field = st.field[1]
        seen.add(id(field))
        label = _text(field.get("label"))
        own = [x for x in statements if x.field and x.field[1] is field]
        rx = _alias_re([label]) if len(label) >= 4 else None
        where = {st.field[0]} | (st.owners - {f"field:{label.lower()}"})
        unique = sum(1 for x in statements if x.kind == "field-settings" and x.field and
                     _text(x.field[1].get("label")).lower() == label.lower()) <= 1
        # another statement counts for this field when it names the label and belongs to the field's screen or
        # dialog, or belongs to no screen while the label is used once in the spec
        others = [x for x in statements if not x.field and x.kind not in ("button",) and rx and rx.search(x.text)
                  and ((x.owners & where) or (not x.owners and unique))]
        limits = {}
        for x in own + [o for o in others if any(rx.search(c) and NUMBER_UNIT.search(c) for c in _clauses(o.text))]:
            texts = _clauses(x.text) if x in others else [x.text]
            for clause in texts:
                if x in others and not rx.search(clause):
                    continue
                for m in NUMBER_UNIT.finditer(clause):
                    unit = _unit(m.group(2))
                    if unit in LIMIT_UNITS:
                        limits.setdefault(unit, {}).setdefault(_num(m.group(1)), x)
        for unit, by_value in limits.items():
            if len(by_value) > 1:
                (va, sa), (vb, sb) = list(by_value.items())[:2]
                found.append(_clash("field-limit", f"field:{label.lower()}", sa, sb,
                                    f"{label} is given two limits: {_fmt(va)} and {_fmt(vb)} {_unit_name(unit)}."))
        if field.get("required"):
            settings = next((x for x in own if x.kind == "field-settings"), st)
            for x in own + others:
                near = (rf"(?:{re.escape(label)}\W+(?:(?:is|are|field|remains|stays|becomes|left)\W+){{0,2}}\(?optional"
                        rf"|optional\W+{re.escape(label)})")
                if any(re.search(r"\boptional\b", c, re.I) if x in own else re.search(near, c, re.I) for c in _clauses(x.text)):
                    found.append(_clash("field-optional", f"field:{label.lower()}", x, settings,
                                        f"{label} is required on the form but called optional here."))
    return _dedupe(found), _dedupe(looks)


def _unit(u):
    u = u.lower()
    if u.startswith("char"):
        return "character"
    if u.startswith("working day"):
        return "working day"
    for base in ("day", "hour", "minute", "attempt"):
        if u.startswith(base):
            return base
    return u


def _unit_name(unit, plural=True):
    if unit in ("mb", "kb", "gb"):
        return unit.upper()
    if unit == "%":
        return "per cent"
    return unit + ("s" if plural and not unit.endswith("s") else "")


def _num(text):
    value = float(text.replace(",", ""))
    return int(value) if value.is_integer() else value


def _fmt(value):
    return f"{value:,}" if isinstance(value, int) else str(value)


def _dedupe(items):
    out, keys = [], set()
    for item in items:
        key = (item["rule"], item["a"]["loc"], item["b"]["loc"], item["why"])
        if key not in keys:
            keys.add(key)
            out.append(item)
    return out


# ------------------------------------------------------------------ look here (word cues)
UNIT_WORDS = {"days", "hours", "minutes", "working", "characters", "chars", "times", "attempts", "retries", "hour", "minute"}


def _content(text):
    return {w for w in re.findall(r"[a-z][a-z-]{3,}", text.lower()) if w not in STOP and w not in UNIT_WORDS}


def _polarity(text):
    """{verb: True (allowed) | False (forbidden)} for the actions a statement names."""
    out = {}
    for clause in _clauses(text):
        for verb, rx in VERB_RE.items():
            m = rx.search(clause)
            if m:
                out[verb] = not NEAR_NEGATION.search(clause[: m.start()])
    return out


def _numbers(text):
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
        return {}
    out = {}
    for m in NUMBER_UNIT.finditer(text):
        out.setdefault(_unit(m.group(2)), set()).add(_num(m.group(1)))
    return out


def look_here(subjects, skip=()):
    """Pairs of statements about the same subject whose words suggest they disagree. For a reader to judge."""
    out, seen = [], set(skip)
    for key, sts in subjects.items():
        for a, b in itertools.combinations(sts, 2):
            if a.loc == b.loc or (a.loc, b.loc) in seen or (b.loc, a.loc) in seen:
                continue
            why = None
            shared = (_content(a.text) & _content(b.text)) - set(VERBS)
            if (a.subjects & b.subjects & DATA_THEMES) and (
                    (ALL_OR_NOTHING.search(a.text) and PARTIAL.search(b.text)) or (PARTIAL.search(a.text) and ALL_OR_NOTHING.search(b.text))):
                why = "One reads all-or-nothing, the other partial."
            # the overview describes today's problems ("cannot see where each job stands"), not the system
            # status rules and buttons are checked mechanically above; their words ("Delete: none") are not prose
            prose = not ({a.kind, b.kind} & {"overview", "status-rules", "button"})
            if not why and prose and len(shared) >= 2:
                pa, pb = _polarity(a.text), _polarity(b.text)
                for verb in sorted(set(pa) & set(pb)):
                    if pa[verb] != pb[verb]:
                        why = f"One allows '{verb}', the other forbids it (both about: {', '.join(sorted(shared)[:3])})."
                        break
            other_fields = a.field and b.field and a.field[1] is not b.field[1]
            same_table = a.loc.split(":")[0] == b.loc.split(":")[0] and "table row" in a.loc and "table row" in b.loc
            if not why and not other_fields and not same_table and len(shared) >= 2:
                na, nb = _numbers(a.text), _numbers(b.text)
                for unit in sorted(set(na) & set(nb)):
                    if na[unit] != nb[unit]:
                        why = (f"Different numbers of {_unit_name(unit)}: {', '.join(_fmt(v) for v in sorted(na[unit]))} and "
                               f"{', '.join(_fmt(v) for v in sorted(nb[unit]))}.")
                        break
            if why:
                seen.add((a.loc, b.loc))
                out.append({"rule": "look-here", "subject": key, "a": a.as_dict(), "b": b.as_dict(), "why": why})
    return out


# ------------------------------------------------------------------ the pack
def subject_title(sp, key, labels=None):
    kind, _, name = key.partition(":")
    if kind == "screen":
        return f"Screen: {sp.title('screen', name)}"
    if kind == "dialog":
        return f"Dialog: {sp.title('dialog', name)}"
    if kind == "status":
        return f"Status: {sp.status_name(name)}"
    if kind == "role":
        return f"Role: {sp.role_name(name)}"
    if kind == "field":
        return f"Field: {(labels or {}).get(name, name)}"
    if kind == "integration":
        system = next((_text(i["system"]) for i in sp.integrations if _text(i["system"]).lower() == name), name)
        return f"Integration: {system}"
    if kind == "theme":
        return f"Theme: {name}"
    return key.capitalize()


ORDER = ("screen", "dialog", "status", "field", "integration", "role", "scope", "theme")


def group(statements):
    """{subject key: [statements]}, only subjects with statements from at least two places."""
    subjects = {}
    for st in statements:
        for key in st.subjects:
            subjects.setdefault(key, []).append(st)
    return {k: v for k, v in sorted(subjects.items(), key=lambda kv: (ORDER.index(kv[0].split(":")[0]) if kv[0].split(":")[0] in ORDER else 99, kv[0]))
            if len({s.loc for s in v}) >= 2}


def build(spec):
    """The whole result for a spec (a dict): {clashes, look_here, subjects: [{key, title, statements}]}."""
    sp = Spec(spec)
    statements = link_subjects(sp, spec_statements(sp))
    subjects = group(statements)
    labels = {_text(st.field[1].get("label")).lower(): _text(st.field[1].get("label")) for st in statements if st.field}
    found, looks = clashes(sp, statements)
    pairs = {(c["a"]["loc"], c["b"]["loc"]) for c in found + looks}
    looks += look_here(subjects, pairs)
    return {"source": "spec", "version": _text((sp.spec.get("project") or {}).get("version")), "clashes": found,
            "look_here": looks,
            "subjects": [{"key": k, "title": subject_title(sp, k, labels), "statements": [s.as_dict() for s in v]} for k, v in subjects.items()]}


REQ_ID = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+(?:\.\d+)*\b")


def text_statements(text):
    """Each line of an extracted document (text.md) as a statement, located by its requirement id, else its
    section heading and page."""
    out, heading, page = [], "", None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^=== PAGE (\d+) ===$", line)
        if m:
            page = int(m.group(1))
            continue
        m = re.match(r"^#+\s+(.*)$", line)
        if m:
            heading = m.group(1).strip()
            continue
        if not line or re.match(r"^\[IMAGE \d+", line) or re.fullmatch(r"\|?[\s|:-]*\|?", line):
            continue
        if line.startswith("|"):
            line = " | ".join(c.strip() for c in line.strip("|").split("|") if c.strip())
        line = re.sub(r"^[-*]\s+", "", line)
        rid = REQ_ID.search(line)
        where = rid.group(0) if rid else (f"§{heading}" if heading else "Start of document")
        if page:
            where += f" (p{page})"
        st = Statement(where, line, kind="text")
        st.subjects.update(f"theme:{name}" for name, rx in THEME_RE.items() if rx.search(line))
        out.append(st)
    return out


def build_text(text):
    """The result for an extracted document: themes and look-here pairs only (a document has no structure to
    check mechanically)."""
    statements = text_statements(text)
    subjects = group(statements)
    return {"source": "document", "version": "", "clashes": [], "look_here": look_here(subjects),
            "subjects": [{"key": k, "title": f"Theme: {k.split(':', 1)[1]}", "statements": [s.as_dict() for s in v]}
                         for k, v in subjects.items()]}


def render(result, name):
    q = lambda d: f"**{d['loc']}**: “{d['text'] if len(d['text']) <= 300 else d['text'][:299] + '…'}”"  # noqa: E731
    lines = [f"# Contradictions pack: {name}", "",
             "Internal working file for the review. Every real contradiction becomes one register item, with both "
             "locations in `source` and both texts quoted.", ""]
    lines += ["## 1. Clashes (found mechanically)", ""]
    if result["source"] == "document":
        lines += ["A document has no structure to check mechanically: read the look-here pairs and the themes.", ""]
    elif not result["clashes"]:
        lines += ["None found. That does not mean there are none: read parts 2 and 3.", ""]
    for i, c in enumerate(result["clashes"], 1):
        lines += [f"{i}. [{c['rule']}] {c['why']}", f"   - {q(c['a'])}", f"   - {q(c['b'])}", ""]
    lines += ["## 2. Look here (word cues: judge each one)", ""]
    if not result["look_here"]:
        lines += ["No pairs with conflicting cue words.", ""]
    for i, c in enumerate(result["look_here"], 1):
        lines += [f"{i}. {c['why']}", f"   - {q(c['a'])}", f"   - {q(c['b'])}", ""]
    lines += ["## 3. Everything said about each subject", "",
              "Read each subject's statements together: do they agree on who, when, what happens on failure, limits "
              "and numbers? A statement appears under every subject it names.", ""]
    for s in result["subjects"]:
        lines += [f"### {s['title']}", ""] + [f"- {q(d)}" for d in s["statements"]] + [""]
    return "\n".join(lines)


def write(result, out_dir, name):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pack.md").write_text(render(result, name), encoding="utf-8")
    (out_dir / "pack.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_dir / "pack.md"


def summary(result, where):
    lines = [f"Clashes (mechanical): {len(result['clashes'])}"]
    for c in result["clashes"]:
        lines.append(f"  - [{c['rule']}] {c['why']}\n      {c['a']['loc']}  vs  {c['b']['loc']}")
    lines.append(f"Look here (word cues, judge each): {len(result['look_here'])}")
    for c in result["look_here"][:15]:
        lines.append(f"  - {c['why']}\n      {c['a']['loc']}  vs  {c['b']['loc']}")
    if len(result["look_here"]) > 15:
        lines.append(f"  … and {len(result['look_here']) - 15} more in the pack")
    lines.append(f"Subjects with two or more statements: {len(result['subjects'])}")
    if where:
        lines.append(f"Pack: {where}")
    return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", help="projects/<slug>")
    ap.add_argument("--text", help="an extracted document's text.md instead of a project's spec")
    ap.add_argument("--out", help="the folder for pack.md and pack.json")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--strict", action="store_true", help="exit with 1 when there is a clash")
    a = ap.parse_args()
    if a.text:
        path = Path(a.text)
        if not path.is_file():
            sys.exit(f"No file at {path}")
        result = build_text(path.read_text(encoding="utf-8"))
        out_dir, name = Path(a.out) if a.out else path.parent.parent, path.parent.parent.name
    elif a.project:
        spec_file = layout.spec_file(a.project)
        if not spec_file.exists():
            sys.exit(f"No spec at {spec_file}")
        spec = yaml.safe_load(spec_file.read_text(encoding="utf-8")) or {}
        result = build(spec)
        version = result["version"] or "draft"
        out_dir = Path(a.out) if a.out else layout.reviews_dir(a.project) / f"spec-v{version}-contradictions"
        name = f"spec v{version}"
    else:
        ap.error("give projects/<slug>, or --text <text.md>")
    where = write(result, out_dir, name)
    print(json.dumps(result, indent=2, ensure_ascii=False) if a.json else summary(result, where))
    return 1 if a.strict and result["clashes"] else 0


if __name__ == "__main__":
    sys.exit(main())
