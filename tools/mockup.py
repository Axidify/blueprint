"""Build, serve and screenshot a project's clickable mock-up.

Usage:
    python -I tools/mockup.py build        <project_dir>
    python -I tools/mockup.py serve        [<project_dir>] [--port 8765] [--lan]
    python -I tools/mockup.py screenshots  <project_dir>
    python -I tools/mockup.py feedback     <project_dir>
    python -I tools/mockup.py look         <project_dir> [--try key=value ...]
    python -I tools/mockup.py live <start|list|take|done|mark|undo|end|wait|checkpoint> <project_dir> ...

<project_dir> is projects/<slug> (or examples/<name>). It must contain the spec, spec/app.yaml (in its
_blueprint folder, in the new folder layout: tools/layout.py); the format is in docs/spec-format.md. Below,
spec/, mockup/ and feedback/ are in _blueprint/ in a project in the new layout.

build        validates the spec and writes <project_dir>/mockup/ (self-contained: open index.html).
serve        An open mock-up follows its spec: when the spec changes, the mock-up is built again and every
             browser showing it refreshes within a few seconds, on the screen it was on.
             Without a project: opens a page that lists every mock-up on this machine, one click from each
             (and from its earlier versions). It is only shown on this computer, and each mock-up is built
             when it is opened if its spec changed.
             With a project: serves the mock-up on http://localhost:<port>; feedback comments are saved to
             <project_dir>/feedback/feedback.json. --lan lets others on the network open it and comment.
             --version 0.2 serves a saved earlier version (every build keeps one in mockup/versions/).
             It stops with a message when the port is already taken (another mock-up is still open):
             close that one, or pick another port with --port.
screenshots  builds, then captures every screen (and extra shots from the spec) with Microsoft Edge into
             <project_dir>/mockup/screenshots/ ("4 Mock-up screenshots" in the new layout), listed in shots.json. It notes which screens they show, so the
             document generator can warn when the spec's screens have changed since.
feedback     prints the saved comments, grouped by screen.
look         shows the look of the client's screens (theme, colour, font, corners, menu, top bar, logo), and notes
             white words that are hard to read on the project's colour or a look the platform does not give.
             --try key=value ... builds a scratch copy with those settings and captures the sign-in page and the
             first dashboard, list and form as they are now and as tried, into <project_dir>/mockup/look-preview/.
             The project is not changed. A value of none takes a setting out.
live         a live session with the client: comments reach the assistant as they are saved (see "a live
             session" further down, and the present skill).
"""
import argparse
import contextlib
import datetime as dt
import difflib
import hashlib
import http.server
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))  # the sibling tools: `python -I` does not put this folder on the path
import layout  # noqa: E402  (where everything is in a project folder)
ENGINE = ROOT / "tools" / "mockup"
SCREEN_TYPES = {"login", "dashboard", "list", "form", "detail", "custom"}
TEXT_SIZES = ("normal", "large", "larger")
# The look of the client's screens (tools/mockup/themes/). A spec without `theme` keeps the look it always had,
# joget, so no project changes look by itself; a new project's spec is written with default_theme().
UNSET_THEME = "joget"


def default_theme(platform):
    """The theme a new project's spec starts with: joget when the platform is Joget (it shows what Joget gives
    without custom UI work), otherwise desk, a calm modern look in the project's colour."""
    return "joget" if "joget" in str(platform or "").lower() else "desk"


# The client's own look on top of the theme (tools/mockup/look.css; docs/spec-format.md, The client's look).
# All optional: a spec that sets none of them is drawn exactly as its theme draws it.
LOOK_CHOICES = {"corners": ("square", "small", "normal", "round"), "menu": ("light", "dark"), "header": ("light", "dark", "brand")}
LOOK_FILES = {"logo": (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp"), "font_file": (".woff2", ".woff", ".ttf", ".otf")}
# The settings of `project` that change how the client's screens look (what `look` shows and --try accepts).
LOOK_KEYS = ("theme", "primary_color", "data_colors", "text_size", "font", "font_file", "corners", "menu", "header", "logo")
# The desk theme's colours, from its design language: Cobalt is the one accent, and the design language's own
# chart teal and pink are the complementary pair for data. Hues (degrees) that mean status there, and the
# violet and indigo it retired: an accent or data colour in them is noted by `look`.
DESK_ACCENT = "#1F5FBF"
DESK_DATA = ("#1597B0", "#D55181")
STATUS_HUES = {"green": (90, 170), "orange": (20, 50), "red": (345, 15)}
RETIRED_HUES = (245, 290)
FONT_FORMATS = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
# Fonts Blueprint carries (the geist package, which setup installs): put into every mock-up whose theme or spec
# uses them, so it looks the same on a laptop that does not have them installed, a client's included.
FONT_PACKAGE = ROOT / "node_modules" / "geist" / "dist" / "fonts"
BUNDLED_FONTS = {"Geist": "geist-sans/Geist-Variable.woff2", "Geist Mono": "geist-mono/GeistMono-Variable.woff2"}
LOOK_PREVIEW = "look-preview"  # in mockup/: the pictures `look --try` takes, never kept with a version


def look_file(project, spec, key):
    """The file a look setting (`logo`, `font_file`) names, in the project's spec/ folder, or None if unset."""
    name = ((spec or {}).get("project") or {}).get(key)
    return (layout.spec_dir(project) / str(name)) if project is not None and name not in (None, "") else None


def look_errors(spec, project=None):
    """The mistakes in the client's look settings, as sentences. With `project`, the files they name must exist."""
    p = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    errors = []
    for key, choices in LOOK_CHOICES.items():
        if p.get(key) is not None and str(p[key]).lower() not in choices:
            errors.append(f"project: {key} '{p[key]}' must be one of {', '.join(choices)}")
    if p.get("font") is not None and (not isinstance(p["font"], str) or not p["font"].strip() or any(c in p["font"] for c in "\"';{}<>")):
        errors.append(f"project: font '{p['font']}' must be the font's name, as written in Word (e.g. Roboto)")
    colours = p.get("data_colors")
    if colours is not None and (not isinstance(colours, list) or len(colours) != 2
                                or not all(isinstance(c, str) and len(c.strip().lstrip("#")) == 6 and c.strip().startswith("#")
                                           and all(x in "0123456789abcdefABCDEF" for x in c.strip()[1:]) for c in colours)):
        errors.append(f"project: data_colors {colours!r} must be two colours as six hex digits in quotes, "
                      'e.g. ["#1597B0", "#D55181"]')
    if p.get("font_file") not in (None, "") and p.get("font") in (None, ""):
        errors.append("project: font_file needs font, the name of the font in that file")
    for key, kinds in LOOK_FILES.items():
        name = p.get(key)
        if name in (None, ""):
            continue
        name = str(name)
        if Path(name).is_absolute() or ".." in Path(name).parts or Path(name).suffix.lower() not in kinds:
            errors.append(f"project: {key} '{name}' must be a file in the project's spec folder ending {', '.join(kinds)}")
        elif project is not None and not look_file(project, spec, key).is_file():
            errors.append(f"project: {key} '{name}' is not in {layout.spec_dir(project)}: put the file there, or take the setting out")
    return errors


def look_css(spec, project, theme_text):
    """The @font-face rules for the fonts the mock-up carries: the bundled fonts its theme or spec names, and
    the spec's own font file. Written into the CSS itself, since a browser refuses a separate font file to a
    page opened from a folder (as the shared folder's shortcut and the screenshots open it)."""
    import base64

    p = spec.get("project") or {}
    faces, missing = [], []
    for family, rel in BUNDLED_FONTS.items():
        if f'"{family}"' not in theme_text and str(p.get("font") or "").strip().lower() != family.lower():
            continue
        if p.get("font_file") and str(p.get("font") or "").strip().lower() == family.lower():
            continue  # the spec brings its own file of this font
        f = FONT_PACKAGE / rel
        if not f.is_file():
            missing.append(family)
            continue
        faces.append((family, f))
    own = look_file(project, spec, "font_file")
    if own is not None:
        faces.append((str(p["font"]).strip(), own))
    css = []
    for family, f in faces:
        # A variable font holds every weight; a single-weight file is declared as regular, so bold is drawn from it.
        weights = "100 900" if f.parent.parent == FONT_PACKAGE or "variable" in f.name.lower() or "[wght" in f.name.lower() else "400"
        data = base64.b64encode(f.read_bytes()).decode("ascii")
        fmt = FONT_FORMATS[f.suffix.lower()]
        mime = {"truetype": "ttf", "opentype": "otf"}.get(fmt, fmt)
        css.append(f'@font-face {{ font-family: "{family}"; src: url(data:font/{mime};base64,{data}) format("{fmt}"); '
                   f'font-weight: {weights}; font-style: normal; font-display: block; }}')
    return "\n".join(css) + ("\n" if css else ""), missing
# Parts of a spec that are internal: never written into the mock-up, which anyone in the room can read.
INTERNAL_SPEC = ("platform_fit",)
# A project's own mock-up code, for what the spec cannot describe: in spec/, and in the built mock-up's assets/.
PROJECT_CODE = {"mockup.css": "project.css", "mockup.js": "project.js"}


def project_code(project):
    """The project's own mock-up code files that exist: {name in spec/: path}."""
    if project is None:
        return {}
    folder = layout.spec_dir(project)
    return {name: folder / name for name in PROJECT_CODE if (folder / name).is_file()}
STATUS_COLORS = ("green", "amber", "red", "grey")  # "gray" is accepted too
FIELD_TYPES = {"text", "textarea", "select", "radio", "checkbox", "date", "datetime", "number", "file", "signature", "user"}
# The keys the spec format knows, by where they are written. A key that is not one of these but nearly spells
# one ("colums") is an error; any other unknown key is a warning, since the mock-up ignores it. A key that
# starts with an underscore (`_note`) is a team's own note and is never warned about.
KNOWN_KEYS = {
    "screen": {"id", "type", "title", "subtitle", "menu", "roles", "description", "caption", "screenshot_role", "screenshot_pages",
               "stats", "list", "buttons", "sections", "data", "record", "fields_from", "timeline", "html"},
    "list": {"data", "where", "where_by_role", "where_record", "title", "columns", "filters", "actions", "toolbar", "search", "sort", "empty"},
    "column": {"field", "label", "chip"},
    "section": {"title", "page", "page_title", "note", "fields"},
    "field": {"id", "label", "type", "required", "readonly", "default", "length", "options", "options_from", "placeholder", "help",
              "source", "validation", "roles"},
    "button": {"label", "style", "to", "toast", "dialog", "roles", "when", "example", "access", "set_status", "also_move", "creates"},
    "dialog": {"id", "title", "message", "fields", "list", "doc_table", "srs_table", "confirm"},
    "figure": {"label", "value", "count", "formula"},
    "process_flow": {"title", "steps", "reject", "notes"},
    "flow step": {"name", "role", "optional", "status"},
    "progress step": {"step", "by", "at", "status", "comment"},
    "role": {"id", "name", "description", "scope", "user"},
    "status": {"id", "name", "meaning", "color", "edit", "cancel", "delete", "next", "auto"},
    "screenshot": {"screen", "role", "record", "page", "dialog", "name", "caption"},
    "also_move": {"data", "link", "key", "set_status", "copy"},
    "options_from": {"list", "field", "where"},
}
# Where the spec must hold a list or a set of settings. Written otherwise (a single text where a list belongs)
# the build used to pass and the mock-up then stopped in the browser with an empty page. By where they are
# written: [kind] is a list of settings of that kind, [str] a list of plain values, "kind" one set of
# settings of that kind, dict any set of settings.
SHAPES = {
    "spec": {"project": dict, "roles": ["role"], "screens": ["screen"], "dialogs": ["dialog"], "statuses": ["status"],
             "screenshots": ["screenshot"], "data": dict, "process_flow": "process_flow"},
    "process_flow": {"steps": ["flow step"], "notes": [str]},
    "screen": {"roles": [str], "stats": ["figure"], "list": "list", "buttons": ["button"], "sections": ["section"], "timeline": ["progress step"]},
    "list": {"columns": ["column"], "filters": [str], "search": [str], "actions": ["button"], "toolbar": ["button"], "where": dict,
             "where_by_role": dict, "where_record": dict},
    "status": {"auto": [str]},
    "section": {"fields": ["field"]},
    "field": {"options": [str]},
    "button": {"roles": [str], "when": dict},
    "dialog": {"fields": ["field"], "list": "list", "confirm": "button"},
    "also_move": {"copy": dict},
}


def shape_errors(spec):
    """Every place where the spec holds a text or a number where a list or a set of settings belongs."""
    errors = []

    def what(value):
        return "a single text" if isinstance(value, str) else "a list" if isinstance(value, list) else "a set of settings" if isinstance(value, dict) \
            else f"'{value}'"

    def name(kind, item, at):
        for key in ("id", "label", "name", "title", "screen", "step", "field"):
            if isinstance(item, dict) and item.get(key) not in (None, ""):
                return f"{kind} {item[key]}"
        return f"{kind} {at + 1}"

    def walk(where, kind, item):
        for key, shape in SHAPES.get(kind, {}).items():
            value = item.get(key)
            if value is None:
                continue
            here = f"{where}: '{key}'" if where else f"'{key}'"
            if isinstance(shape, list):
                if not isinstance(value, list):
                    errors.append(f"{here} must be a list (one '- ' line per entry, or [a, b] on one line), not {what(value)}")
                    continue
                for at, entry in enumerate(value):
                    if shape[0] is str:
                        if isinstance(entry, (dict, list)):
                            errors.append(f"{here} must be a list of plain values, and entry {at + 1} is {what(entry)}")
                    elif not isinstance(entry, dict):
                        errors.append(f"{here}: entry {at + 1} must be a set of settings (key: value), not {what(entry)}")
                    else:
                        walk(", ".join(x for x in (where, name(shape[0], entry, at)) if x), shape[0], entry)
            elif not isinstance(value, dict):
                errors.append(f"{here} must be a set of settings (key: value), not {what(value)}")
            elif shape is not dict:
                walk(", ".join(x for x in (where, key) if x), shape, value)
        if kind == "button" and item.get("also_move") is not None:
            links = item["also_move"] if isinstance(item["also_move"], list) else [item["also_move"]]
            for link in links:
                if not isinstance(link, dict):
                    errors.append(f"{where}: 'also_move' must be a set of settings (data, link, set_status), or a list of them, not {what(link)}")
                else:
                    walk(f"{where}, also_move", "also_move", link)

    walk("", "spec", spec)
    for list_name, records in (spec.get("data") or {}).items() if isinstance(spec.get("data"), dict) else []:
        if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
            errors.append(f"data '{list_name}' must be a list of records, each a set of fields (- id: ..., name: ...)")
            continue
        for at, record in enumerate(records):
            if record.get("timeline") is not None and (not isinstance(record["timeline"], list)
                                                       or not all(isinstance(line, dict) for line in record["timeline"])):
                errors.append(f"data '{list_name}', record {at + 1}: 'timeline' must be a list of steps, each a set of settings (step, by, at, status)")
    return errors


# ------------------------------------------------------------------ status moves
def find_status(spec, value):
    """The status with that id or name, as the mock-up finds it (any letter case), or None."""
    want = str(value).strip().lower()
    for st in spec.get("statuses") or []:
        if isinstance(st, dict) and any(k is not None and str(k).strip().lower() == want for k in (st.get("id"), st.get("name"))):
            return st
    return None


def status_moves(spec):
    """Every move a button with `set_status` makes in the mock-up: [{where, label, to, sources, record, data}].
    `sources` are the statuses the record can be in when the button shows (from its `when`, or the `where`
    of its list), or None when nothing says; `record` is False when the button has no record to move.
    `set_status: {Submitted: verified, Verified: approved}` is one move for each place it names: a status,
    or a step of the records' progress (`sources` is then None). `unknown_from` is set when it is neither."""
    data = spec.get("data") or {}

    def add(where, label, target, found, record, name, also=None):
        also = also_moves(also)
        if isinstance(target, dict):  # {where the record is: status it moves to}
            steps = {str(line.get("step")).strip().lower() for row in data.get(name) or [] if isinstance(row, dict)
                     for line in row.get("timeline") or [] if isinstance(line, dict)}
            for start, to in target.items():
                source = find_status(spec, start)
                step = source is None and str(start).strip().lower() in steps
                moves.append({"where": where, "label": label, "to": to, "sources": None if step else [source] if source else [],
                              "record": record, "data": name, "unknown_from": None if source or step else start, "also": also})
        else:
            moves.append({"where": where, "label": label, "to": target, "sources": found, "record": record, "data": name, "unknown_from": None,
                          "also": also})

    def sources(*conditions):
        for cond in conditions:
            value = cond.get("status") if isinstance(cond, dict) else None
            if value is not None:
                return [st for st in (find_status(spec, v) for v in (value if isinstance(value, list) else [value])) if st]
        return None

    def holds_record(screen):
        return screen.get("data") in data and screen.get("type") in ("detail", "form")

    # A button that adds a record (see new_records) has that record to move: it starts in the button's status.
    creating = {(n["screen"], n["label"]): n["data"] for n in new_records(spec)}
    moves, openers = [], {}
    for s in spec.get("screens") or []:
        where = f"screen {s.get('id')}"
        for b in s.get("buttons") or []:
            if b.get("dialog"):
                openers.setdefault(b["dialog"], []).append((s, b))
            if b.get("set_status") is not None and not b.get("dialog"):
                new = creating.get((s.get("id"), b.get("label")))
                if new and not holds_record(s):
                    add(where, b.get("label"), b["set_status"], [], True, new, b.get("also_move"))
                else:
                    add(where, b.get("label"), b["set_status"], sources(b.get("when")), holds_record(s), s.get("data"), b.get("also_move"))
        lst = s.get("list") or {}
        for a in lst.get("actions") or []:
            if a.get("set_status") is not None:
                found = sources(a.get("when"))
                if found is None:  # wherever the list shows it: its `where`, and each role's own filter
                    shown = [sources(c) for c in [lst.get("where")] + list((lst.get("where_by_role") or {}).values()) if c]
                    found = None if not shown or any(x is None for x in shown) else [st for x in shown for st in x]
                add(where, a.get("label"), a["set_status"], found, True, lst.get("data"), a.get("also_move"))
        for b in lst.get("toolbar") or []:
            if b.get("set_status") is not None:
                add(where, b.get("label"), b["set_status"], None, False, None, b.get("also_move"))
    for d in spec.get("dialogs") or []:
        confirm = d.get("confirm") or {}
        if confirm.get("set_status") is None:
            continue
        opened = [(s, b) for s, b in openers.get(d.get("id"), []) if holds_record(s)]
        known = [sources(b.get("when")) for _, b in opened]
        new = [creating[(s.get("id"), b.get("label"))] for s, b in openers.get(d.get("id"), []) if (s.get("id"), b.get("label")) in creating]
        if new and not opened:  # confirmed on a new form: the record it adds starts in this status
            add(f"dialog {d.get('id')}", confirm.get("label"), confirm["set_status"], [], True, new[0], confirm.get("also_move"))
            continue
        add(f"dialog {d.get('id')}", confirm.get("label"), confirm["set_status"],
            None if not known or any(k is None for k in known) else [st for k in known for st in k],
            bool(opened), opened[0][0].get("data") if opened else None, confirm.get("also_move"))
    return moves


def also_moves(value):
    """A button's `also_move` as a list: one linked record or several."""
    if value is None:
        return []
    return [x for x in (value if isinstance(value, list) else [value]) if isinstance(x, dict)]


def linked_key(spec, also):
    """The field of the linked list that `link` is matched against: `key`, or the list's first field."""
    if also.get("key") is not None:
        return also["key"]
    rows_ = [r for r in (spec.get("data") or {}).get(also.get("data")) or [] if isinstance(r, dict) and r]
    return next(iter(rows_[0])) if rows_ else None


def linked_sources(spec, move, also):
    """The statuses the linked records are in when the button moves them along: those of the records of the
    sample data that are linked from the records the button can act on. [(status or None, linked record)]."""
    data = spec.get("data") or {}
    acted_on = [r for r in data.get(move["data"]) or [] if isinstance(r, dict)]
    if move["sources"] is not None:
        acted_on = [r for r in acted_on if find_status(spec, r.get("status")) in move["sources"]]
    key = linked_key(spec, also)
    found = []
    for row in acted_on:
        for other in data.get(also.get("data")) or []:
            if isinstance(other, dict) and row.get(also.get("link")) is not None and str(other.get(key)) == str(row.get(also.get("link"))):
                found.append((find_status(spec, other.get("status")), other))
    return found


def moves_not_shown(spec):
    """The moves the status rules allow (`next`) that no button of the mock-up makes, as "From to To". Empty
    when the mock-up moves no record at all: the rules are then for the document only."""
    moves = status_moves(spec)
    if not moves:
        return []
    made = set()
    for move in moves:
        to = find_status(spec, move["to"])
        if to is None:
            continue
        for st in move["sources"] if move["sources"] is not None else [s for s in spec.get("statuses") or [] if isinstance(s, dict)]:
            made.add((st.get("id"), to.get("id")))
        for also in move["also"]:
            linked_to = find_status(spec, also.get("set_status"))
            for st, _ in linked_sources(spec, move, also) if linked_to else []:
                if st is not None:
                    made.add((st.get("id"), linked_to.get("id")))
    missing = []
    for st in spec.get("statuses") or []:
        automatic = [find_status(spec, x) for x in auto_moves(st)]
        for other in st.get("next") or [] if isinstance(st, dict) and isinstance(st.get("next"), list) else []:
            to = find_status(spec, other)
            if to is not None and (st.get("id"), to.get("id")) not in made and not any(to is a for a in automatic):
                missing.append(f"{st.get('name', st.get('id'))} to {to.get('name', to.get('id'))}")
    return missing


def auto_moves(status):
    """The statuses a status moves to on its own (`auto`): a date passing, a linked record moving. No button
    makes them, so the build does not list them as moves the walk-through cannot show."""
    value = status.get("auto") if isinstance(status, dict) else None
    return [x for x in value if isinstance(x, (str, int))] if isinstance(value, list) else []


def automatic_moves(spec):
    """Every move the status rules mark as automatic (`auto`), as "From to To"."""
    said = []
    for st in spec.get("statuses") or []:
        for x in auto_moves(st):
            to = find_status(spec, x)
            if to is not None:
                said.append(f"{st.get('name', st.get('id'))} to {to.get('name', to.get('id'))}")
    return said


# ------------------------------------------------------------------ new records
# On a new, empty form the main button adds a record to the list the form fills in, so a presenter can show
# it land in the next person's list. The browser fills it in (what was typed, sample values for the rest, a
# new id, who and when); the build works out which buttons add one, to which list and in which status.
WAITING_WORDS = ("pending", "submitted", "new", "open", "waiting")


def tied_list(spec, screen, button=None):
    """(data list, how it was found) for a form opened without a record, or (None, ""): the button's
    `creates`, the screen's `data`, a detail screen that shows the form's fields (`fields_from`), or the list
    of the screen the button goes to when most of the form's fields are fields of that list."""
    data = spec.get("data") or {}
    if button is not None and isinstance(button.get("creates"), str):
        return (button["creates"], "its creates") if button["creates"] in data else (None, "")
    if screen.get("data") in data:
        return screen["data"], "the screen's data"
    for other in spec.get("screens") or []:
        if isinstance(other, dict) and other.get("type") == "detail" and other.get("fields_from") == screen.get("id") and other.get("data") in data:
            return other["data"], f"screen {other.get('id')} shows the form's fields"
    target = next((s for s in spec.get("screens") or [] if button is not None and isinstance(s, dict) and s.get("id") == button.get("to")), None)
    lst = (target or {}).get("list")
    if isinstance(lst, dict) and lst.get("data") in data:
        known = {str(k) for row in data[lst["data"]] or [] if isinstance(row, dict) for k in row}
        ids = [str(f.get("id")) for sec in screen.get("sections") or [] if isinstance(sec, dict)
               for f in sec.get("fields") or [] if isinstance(f, dict)]
        if ids and 2 * sum(1 for i in ids if i in known) >= len(ids):
            return lst["data"], f"most of the form's fields are fields of the list on screen {target.get('id')}"
    return None, ""


def first_status(spec, name, label):
    """The status a new record starts in when its button does not say (`set_status`): the first status of the
    spec, or the one after it when that is a draft and the button is not about a draft (Submit is not Save as
    Draft): the draft's first `next`, or, when it lists none, the next status of the list. Without statuses: a waiting status of the sample records. None when the records have no status."""
    rows_ = [r for r in (spec.get("data") or {}).get(name) or [] if isinstance(r, dict)]
    if rows_ and not any("status" in r for r in rows_):
        return None
    statuses = [st for st in spec.get("statuses") or [] if isinstance(st, dict)]
    if statuses:
        first = statuses[0]
        is_draft = "draft" in f"{first.get('id')} {first.get('name')}".lower()
        if is_draft and "draft" not in str(label).lower():
            # Its first next step; a draft that lists none is followed by the next status of the list.
            nxt = first.get("next") if isinstance(first.get("next"), list) and first["next"] else None
            first = (find_status(spec, nxt[0]) if nxt else None) or (statuses[1] if len(statuses) > 1 else first)
        return str(first.get("name") or first.get("id"))
    seen = [str(r["status"]) for r in rows_ if r.get("status") not in (None, "")]
    return next((s for s in seen if any(w in s.lower() for w in WAITING_WORDS)), seen[0] if seen else None)


def new_records(spec):
    """Every button that adds a record when pressed on a form opened without one:
    [{screen, title, label, dialog, confirm, data, status, how}]. It is the form's main button (style
    primary), and any button with `creates`; `creates: false` stops it. A button that opens a dialog adds the
    record when the dialog is confirmed. A form that names its own `record` is never empty, so never adds one."""
    dialogs = {d.get("id"): d for d in spec.get("dialogs") or [] if isinstance(d, dict)}
    found = []
    for s in spec.get("screens") or []:
        if not isinstance(s, dict) or s.get("type") != "form" or s.get("record") not in (None, ""):
            continue
        buttons = [b for b in s.get("buttons") or [] if isinstance(b, dict)]
        main = next((b for b in buttons if b.get("style") == "primary"), None)
        for b in buttons:
            creates = b.get("creates")
            if creates is False or (creates in (None, "") and b is not main) or b.get("when"):
                continue  # a button with `when` is not shown on an empty form
            name, how = tied_list(spec, s, b)
            if name is None:
                continue
            acting = b
            if b.get("dialog"):
                acting = (dialogs.get(b["dialog"]) or {}).get("confirm") or {"label": "OK"}
            target = acting.get("set_status")
            status = find_status(spec, target) if isinstance(target, (str, int)) else None
            status = str(status.get("name") or status.get("id")) if status else first_status(spec, name, b.get("label"))
            found.append({"screen": s.get("id"), "title": s.get("title") or s.get("id"), "label": b.get("label"), "dialog": b.get("dialog"),
                          "confirm": acting.get("label"), "data": name, "status": status, "how": how})
    return found


def forms_without_a_list(spec):
    """The titles of the forms whose main button could add a record but has no list to add it to."""
    made = {n["screen"] for n in new_records(spec)}
    missing = []
    for s in spec.get("screens") or []:
        if isinstance(s, dict) and s.get("type") == "form" and s.get("record") in (None, "") and s.get("id") not in made:
            main = next((b for b in s.get("buttons") or [] if isinstance(b, dict) and b.get("style") == "primary"), None)
            if main and main.get("creates") is not False and not main.get("when"):
                missing.append(str(s.get("title") or s.get("id")))
    return missing


# ------------------------------------------------------------------ spec
def load_spec(project):
    path = layout.spec_file(project)
    if not path.exists():
        sys.exit(f"No spec at {path}")
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = validate(spec) or look_errors(spec, project)  # then the files the look names, which only a project has
    if errors:
        print("Spec errors:\n  " + "\n  ".join(errors))
        sys.exit(1)
    return json.loads(json.dumps(spec, default=str))  # dates -> strings


def article(word):
    return "an" if str(word)[:1].lower() in "aeiou" else "a"


def validate(spec, warnings=None):
    """The mistakes that stop the build, as sentences. With `warnings` (a list), what the mock-up would
    silently ignore is added to it: settings the format does not know."""
    warnings = [] if warnings is None else warnings
    if not isinstance(spec, dict):
        return ["the spec is empty, or not a set of settings (key: value)"]
    errors = []
    for key in ("project", "roles", "screens"):
        if not spec.get(key):
            errors.append(f"missing '{key}'")
    if errors:
        return errors
    errors = shape_errors(spec)
    if errors:  # the checks below read these parts as lists and settings
        return errors
    size = (spec["project"] or {}).get("text_size") if isinstance(spec["project"], dict) else None
    if size is not None and str(size).lower() not in TEXT_SIZES:
        errors.append(f"project: text_size '{size}' must be one of {', '.join(TEXT_SIZES)}")
    errors += look_errors(spec)
    roles = {r["id"] for r in spec["roles"]}
    screens = {s["id"]: s for s in spec["screens"]}
    dialogs = {d["id"] for d in spec.get("dialogs", [])}
    data = spec.get("data", {}) or {}
    if len(screens) != len(spec["screens"]):
        errors.append("duplicate screen ids")

    def misspelt(where, kind, item):
        """A key that nearly spells a known one is a typo: the mock-up would silently ignore it. Any other key
        the format does not know is a warning, unless it starts with an underscore (a team's own note)."""
        for key in item if isinstance(item, dict) else []:
            if key not in KNOWN_KEYS[kind]:
                close = difflib.get_close_matches(str(key), sorted(KNOWN_KEYS[kind]), 1, 0.75)
                if close:
                    errors.append(f"{where}: '{key}' is not {article(kind)} {kind} setting (did you mean '{close[0]}'?)")
                elif not str(key).startswith("_"):
                    stray = item[key] is None and "{" not in str(key)
                    warnings.append(f"{where}: '{key}' is not {article(kind)} {kind} setting, so the mock-up ignores it"
                                    + (". It has no value: often a comma inside an unquoted text between { }, which splits it in two."
                                       " Put that text in quotes" if stray else ". Start it with _ if it is a note of your own"))

    def as_written(value):
        """A field name as the mock-up sees it. YAML reads an unquoted `no` or `yes` as false or true, and in
        the mock-up's data both the record's key and the column's field become the word "false" or "true"."""
        return json.dumps(value) if isinstance(value, bool) else str(value)

    def fields_of(name):
        """Every field name used by the records of a data list (None when the list is empty or missing)."""
        rows_ = data.get(name) or []
        return {as_written(k) for row in rows_ if isinstance(row, dict) for k in row} or None

    def in_data(where, name, what, field):
        if as_written(field) == "waiting_for_me":  # not a field: asks whether the record's waiting step is the signed-in person's
            if not any(isinstance(row, dict) and row.get("timeline") for row in data.get(name) or []):
                errors.append(f"{where}: waiting_for_me looks at each record's progress, and no record of the '{name}' data has a timeline")
            return
        known = fields_of(name)
        if known is not None and as_written(field) not in known:
            close = difflib.get_close_matches(str(field), sorted(map(str, known)), 1, 0.6)
            errors.append(f"{where}: {what} '{field}' is not a field of the '{name}' data"
                          + (f" (did you mean '{close[0]}'?)" if close else f" (it has {', '.join(sorted(map(str, known)))})"))

    def has_record(where, name, record):
        rows_ = [row for row in data.get(name) or [] if isinstance(row, dict) and row]
        if rows_ and str(record) not in {str(next(iter(row.values()))) for row in rows_}:
            errors.append(f"{where}: record '{record}' is not in the '{name}' data (a record is found by its first value)")

    def check_fields(where, fields):
        for f in fields or []:
            misspelt(f"{where}, field {f.get('id', '?')}", "field", f)
            if f.get("type") and f["type"] not in FIELD_TYPES:
                close = difflib.get_close_matches(str(f["type"]), sorted(FIELD_TYPES), 1, 0.6)
                errors.append(f"{where}, field {f.get('id', '?')}: type '{f['type']}' is not one of {', '.join(sorted(FIELD_TYPES))}"
                              + (f" (did you mean '{close[0]}'?)" if close else ""))
            source = f.get("options_from")
            here = f"{where}, field {f.get('id', '?')}"
            if f.get("roles") is not None:  # a user field offers the people of these roles
                wanted = f["roles"] if isinstance(f["roles"], list) else [f["roles"]]
                if f.get("type") != "user":
                    errors.append(f"{here}: roles is for a user field (type: user), to say whose people it offers")
                for rid in wanted:
                    if rid not in roles:
                        errors.append(f"{here}: roles names '{rid}', which is not a role of the spec")
            if isinstance(source, dict):  # {list, field, where}: the choices are the records the filter lets through
                misspelt(f"{here}, options_from", "options_from", source)
                name, field = source.get("list"), source.get("field")
                if name not in data or field in (None, ""):
                    errors.append(f"{here}: options_from needs 'list' (a list from data) and 'field' (the field whose values are the choices), "
                                  "for example {list: cars, field: reg_no, where: {status: Available}}")
                else:
                    in_data(here, name, "options_from field", field)
                    if source.get("where") is not None and not isinstance(source["where"], dict):
                        errors.append(f"{here}: options_from 'where' must be a filter, for example {{status: Available}}")
                    for key in source.get("where") if isinstance(source.get("where"), dict) else {}:
                        in_data(here, name, "options_from 'where'", key)
            elif isinstance(source, list):
                errors.append(f"{here}: options_from is <data list>.<field>, or {{list, field, where}}, not a list")
            elif source:
                name, _, field = str(source).partition(".")
                if name not in data or not field:
                    errors.append(f"{here}: options_from '{source}' must be <data list>.<field>, with a list from data")
                else:
                    in_data(here, name, "options_from", field)

    def check_list(where, lst, shown=None):
        """`shown`: the data list of the record a detail screen shows, which `where_record` links the rows to."""
        misspelt(where, "list", lst)
        name = lst.get("data")
        if name not in data:
            errors.append(f"{where}: list data '{name}' not in data")
            return
        link = lst.get("where_record")
        if link is not None:
            if not link:
                errors.append(f"{where}: where_record names a field of the list's rows and a field of the record shown, "
                              "for example {car: reg_no}")
            elif shown is None:
                errors.append(f"{where}: where_record shows the rows that name the record a detail screen shows, so it only works "
                              "in the list of a detail screen with data")
            else:
                for mine, theirs in link.items():
                    in_data(where, name, "where_record", mine)
                    in_data(where, shown, "where_record (a field of the record shown)", theirs)
        for c in lst.get("columns") or []:
            misspelt(f"{where}, a column", "column", c)
            if c.get("field") is not None:
                in_data(where, name, "column", c["field"])
        for key in ("filters", "search"):
            for field in lst.get(key) or []:
                in_data(where, name, f"{key[:-1] if key == 'filters' else key} field", field)
        for field in lst.get("where") or {}:
            in_data(where, name, "'where'", field)
        by_role = lst.get("where_by_role") or {}
        if not isinstance(by_role, dict) or not all(isinstance(v, dict) for v in by_role.values()):
            errors.append(f"{where}: where_by_role must give a filter for each role it names, for example {{approver: {{status: Verified}}}}")
            by_role = {}
        for role, cond in by_role.items():
            if role not in roles:
                close = difflib.get_close_matches(str(role), sorted(roles), 1, 0.6)
                errors.append(f"{where}: where_by_role names '{role}', which is not a role" + (f" (did you mean '{close[0]}'?)" if close else ""))
            for field in cond:
                in_data(where, name, f"'where_by_role' for {role}:", field)
        for a in (lst.get("actions") or []) + (lst.get("toolbar") or []):
            misspelt(f"{where}, button {a.get('label', '?')}", "button", a)
            check_target(where, a)
        for a in lst.get("actions") or []:
            for field in a.get("when") or {}:
                in_data(f"{where}, action {a.get('label', '?')}", name, "'when'", field)

    for kind, items in (("role", spec["roles"]), ("dialog", spec.get("dialogs") or [])):
        ids = [x.get("id") for x in items]
        for dup in sorted({str(i) for i in ids if ids.count(i) > 1}):
            errors.append(f"{kind} id '{dup}' is used more than once")

    def check_target(where, item, form=None):
        """`form`: the form screen the button is on, the only place `creates` works."""
        made = item.get("creates")
        if made is not None:
            said = f"{where}, button {item.get('label', '?')}: creates"
            if form is None:
                errors.append(f"{said} adds a record from a form opened without one, so it only works on the buttons of a form screen")
            elif not isinstance(made, (bool, str)):
                errors.append(f"{said} is true, false or the name of a data list, not {made!r}")
            elif isinstance(made, str) and made not in data:
                close = difflib.get_close_matches(made, sorted(map(str, data)), 1, 0.6)
                errors.append(f"{said} '{made}' is not a list in data" + (f" (did you mean '{close[0]}'?)" if close else ""))
            elif made is not False and form.get("record") not in (None, ""):
                errors.append(f"{said}: the form shows record {form['record']} when it is opened, so it is never empty and adds no record")
        if isinstance(item.get("label"), bool):
            errors.append(f"{where}: a button's label reads as {str(item['label']).lower()}, not as text. YAML takes an unquoted Yes, No, "
                          "On or Off for true or false: put the label in quotes")
        if item.get("to") and item["to"] not in screens:
            errors.append(f"{where}: unknown screen '{item['to']}'")
        if item.get("dialog") and item["dialog"] not in dialogs:
            errors.append(f"{where}: unknown dialog '{item['dialog']}'")
        for r in item.get("roles", []) or []:
            if r not in roles:
                errors.append(f"{where}: unknown role '{r}'")
        for link in also_moves(item.get("also_move")):
            misspelt(f"{where}, button {item.get('label', '?')}, also_move", "also_move", link)
        if item.get("also_move") is not None and item.get("set_status") is None:
            errors.append(f"{where}, button {item.get('label', '?')}: also_move moves a linked record along with this one, "
                          "so it needs set_status on the same button")

    for s in spec["screens"]:
        w = f"screen {s['id']}"
        if s.get("type") not in SCREEN_TYPES:
            errors.append(f"{w}: type must be one of {sorted(SCREEN_TYPES)}")
        for r in s.get("roles", []) or []:
            if r not in roles:
                errors.append(f"{w}: unknown role '{r}'")
        misspelt(w, "screen", s)
        for stat in s.get("stats") or []:
            misspelt(f"{w}, figure {stat.get('label', '?')}", "figure", stat)
        for line in s.get("timeline") or []:
            misspelt(f"{w}, progress step {line.get('step', '?')}", "progress step", line)
        if s.get("screenshot_role") and s["screenshot_role"] not in roles:
            errors.append(f"{w}: screenshot_role '{s['screenshot_role']}' is not a role")
        lst = s.get("list")
        if lst:
            check_list(w, lst, s.get("data") if s.get("type") == "detail" and s.get("data") in data else None)
            for stat in s.get("stats") or []:
                if isinstance(stat.get("count"), dict) and lst.get("data") in data:
                    for field in stat["count"]:
                        in_data(f"{w}, figure {stat.get('label', '?')}", lst["data"], "'count'", field)
        for b in s.get("buttons", []) or []:
            misspelt(f"{w}, button {b.get('label', '?')}", "button", b)
            check_target(w, b, s if s.get("type") == "form" else None)
            if s.get("data") in data:
                for field in b.get("when") or {}:
                    in_data(f"{w}, button {b.get('label', '?')}", s["data"], "'when'", field)
        if s.get("type") == "detail" and s.get("data") not in data:
            errors.append(f"{w}: detail data '{s.get('data')}' not in data")
        elif s.get("data") and s["data"] not in data:
            errors.append(f"{w}: data '{s['data']}' not in data")
        elif s.get("data") and s.get("record") is not None:
            has_record(w, s["data"], s["record"])
        elif s.get("record") is not None and s.get("type") == "form":
            errors.append(f"{w}: record '{s['record']}' needs the screen's data (the list the record is in), for example data: applications")
        for sec in s.get("sections") or []:
            misspelt(f"{w}, section {sec.get('title', '?')}", "section", sec)
            check_fields(w, sec.get("fields"))
        if s.get("fields_from") and s["fields_from"] not in screens:
            errors.append(f"{w}: fields_from '{s['fields_from']}' is not a screen")
        ids = [f["id"] for sec in s.get("sections", []) for f in sec.get("fields", [])]
        if len(ids) != len(set(ids)):
            errors.append(f"{w}: duplicate field ids")
    for st in spec.get("statuses", []) or []:
        misspelt(f"status {st.get('id') or st.get('name')}", "status", st)
        if st.get("color") and str(st["color"]).lower() not in STATUS_COLORS + ("gray",):
            errors.append(f"status {st.get('id') or st.get('name')}: color '{st['color']}' must be one of {', '.join(STATUS_COLORS)}")
        allowed = [find_status(spec, x) for x in st["next"]] if isinstance(st.get("next"), list) else None
        for x in st.get("auto") or []:
            to = find_status(spec, x)
            said = f"status {st.get('id') or st.get('name')}: auto '{x}'"
            if to is None:
                errors.append(f"{said} is not a status")
            elif allowed is None or not any(to is a for a in allowed):
                errors.append(f"{said} is a move the system makes on its own, so it must also be in this status's 'next'")
    for r in spec["roles"]:
        misspelt(f"role {r.get('id')}", "role", r)
    flow = spec.get("process_flow") or {}
    misspelt("process_flow", "process_flow", flow)
    for step in flow.get("steps") or []:
        misspelt(f"process_flow, step {step.get('name', '?')}", "flow step", step)
    for shot in spec.get("screenshots") or []:
        misspelt(f"screenshot {shot.get('name') or shot.get('screen')}", "screenshot", shot)
    for d in spec.get("dialogs", []):
        misspelt(f"dialog {d['id']}", "dialog", d)
        check_fields(f"dialog {d['id']}", d.get("fields"))
        if d.get("list"):
            check_list(f"dialog {d['id']}", d["list"])
        if d.get("confirm"):
            misspelt(f"dialog {d['id']}, button {d['confirm'].get('label', '?')}", "button", d["confirm"])
            check_target(f"dialog {d['id']}", d["confirm"])
    # A button that moves a record to another status must agree with the status rules the document prints.
    def named(st):
        return st.get("name", st.get("id"))

    def not_a_status(w, value, start=False):
        known = [str(st.get("id") or st.get("name")) for st in spec.get("statuses") or [] if isinstance(st, dict)]
        close = difflib.get_close_matches(str(value), known + [str(st.get("name")) for st in spec.get("statuses") or [] if isinstance(st, dict)], 1, 0.6)
        errors.append(f"{w}: set_status '{value}' is not a status" + (", nor a step in the progress of its records" if start else "")
                      + (f" (did you mean '{close[0]}'?)" if close else f" (the statuses are {', '.join(known)})" if known else " (the spec has no statuses)"))

    def against_rules(said, source, to, change):
        allowed = source.get("next")
        if source is to or not isinstance(allowed, list):
            return  # no rule set for that status: nothing to disagree with
        if to not in [find_status(spec, x) for x in allowed]:
            rule = (f"may only move to {', '.join(named(find_status(spec, x) or {'name': x}) for x in allowed)}" if allowed
                    else "is a final status (next: [])")
            errors.append(f"{said} from {named(source)} to {named(to)}, but in the status rules {named(source)} {rule}. "
                          f"Change {change}, or the status's 'next'")

    def check_also(w, move, also):
        """A linked record moved along with the record the button acts on (see "Status moves" in docs/spec-format.md)."""
        missing = [k for k in ("data", "link", "set_status") if also.get(k) in (None, "")]
        if missing:
            errors.append(f"{w}: needs {', '.join(missing)} (data: the linked list, link: the field of this record that names the "
                          "linked one, set_status: the status the linked record moves to)")
            return
        other = also["data"]
        if other not in data:
            close = difflib.get_close_matches(str(other), sorted(map(str, data)), 1, 0.6)
            errors.append(f"{w}: data '{other}' is not in data" + (f" (did you mean '{close[0]}'?)" if close else ""))
            return
        in_data(w, move["data"], "link", also["link"])
        if also.get("key") is not None:
            in_data(w, other, "key", also["key"])
        for target, source in (also.get("copy") or {}).items():
            in_data(f"{w}, copy", other, "field", target)
            in_data(f"{w}, copy", move["data"], "field", source)
        to = find_status(spec, also["set_status"])
        if to is None:
            not_a_status(w, also["set_status"])
            return
        known = fields_of(other)
        if known is not None and "status" not in known:
            errors.append(f"{w}: set_status changes a record's 'status' field, and the '{other}' data has none")
            return
        for source, record in linked_sources(spec, move, also):
            if source is not None:
                against_rules(f"{w}: moves the '{other}' record {next(iter(record.values()), '?')}", source, to, "also_move")

    for move in status_moves(spec):
        w = f"{move['where']}, button {move['label']}"
        to = find_status(spec, move["to"])
        if move["unknown_from"] is not None:
            not_a_status(w, move["unknown_from"], start=True)
        if to is None:
            not_a_status(w, move["to"])
        if to is None or move["unknown_from"] is not None:
            continue
        if not move["record"]:
            errors.append(f"{w}: set_status has no record to move here. It works on a detail screen, on a form with data, "
                          "on a row action of a list, and in a dialog opened from a detail screen or such a form")
            continue
        known = fields_of(move["data"])
        if known is not None and "status" not in known:
            errors.append(f"{w}: set_status changes a record's 'status' field, and the '{move['data']}' data has none")
        for source in move["sources"] or []:
            against_rules(f"{w}: moves a record", source, to, "the button")
        for also in move["also"]:
            check_also(f"{w}, also_move", move, also)
    for shot in spec.get("screenshots", []) or []:
        where = f"screenshot {shot.get('name') or shot.get('screen')}"
        if shot.get("screen") not in screens:
            errors.append(f"screenshot {shot}: unknown screen")
            continue
        check_target(where, shot)
        if shot.get("role") and shot["role"] not in roles:
            errors.append(f"{where}: unknown role '{shot['role']}'")
        target = screens[shot["screen"]]
        if shot.get("record") is not None and target.get("data") in data:
            has_record(where, target["data"], shot["record"])
    return list(dict.fromkeys(errors))  # a button that serves several steps would say the same thing once for each


def spec_warnings(spec):
    """What the mock-up would silently ignore in a spec that builds: settings the format does not know."""
    warnings = []
    validate(spec, warnings)
    return list(dict.fromkeys(warnings))


# ------------------------------------------------------------------ build
INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="assets/base.css">{fonts_css}<link rel="stylesheet" href="assets/theme.css"><link rel="stylesheet" href="assets/look.css">{project_css}
</head><body><div id="app"></div>
<script src="spec.js"></script><script src="build.js"></script><script src="assets/app.js"></script>{project_js}
</body></html>
"""


def theme_css(theme_file, seen=()):
    """A theme's CSS. A first line '/* extends: <theme> */' puts that theme's CSS in front of it."""
    css = theme_file.read_text(encoding="utf-8")
    first = css.split("\n", 1)[0].strip()
    if first.startswith("/* extends:") and first.endswith("*/"):
        parent = first[len("/* extends:"):-2].strip()
        parent_file = ENGINE / "themes" / f"{parent}.css"
        if parent in seen or not parent_file.exists():
            sys.exit(f"Theme {theme_file.stem} extends unknown or circular theme '{parent}'")
        css = theme_css(parent_file, seen + (theme_file.stem,)) + "\n" + css
    return css


BUILT_FROM = ".built-from"  # in mockup/: what the build was made from, as one value
CUSTOM_LABEL = "Custom development"
CUSTOM_CODE = {"label": CUSTOM_LABEL, "title": "Built in the project's own mock-up code: the platform does not do this as described, "
                                               "so it needs custom work"}


def custom_work(spec, project=None):
    """What the mock-up tags as custom development, while presenting: {tags: [{screen | dialog, element, label,
    title}], code: {label, title} or None}. From the spec's `platform_fit` (tools/platform_fit.py apply): every
    feature that is custom work or not supported, at the elements it names (or at the heading of the screen
    it is used on, for a platform_fit written before it named them). `code`: what the project's own mock-up
    code adds is tagged too, unless the platform check found it standard or configuration. Only the label,
    what the feature is and what it takes reach the mock-up: never the sheet row, building block or source."""
    fit = spec.get("platform_fit") if isinstance(spec.get("platform_fit"), dict) else {}
    stack = [str(x) for x in fit.get("stack") or []] or [str((spec.get("project") or {}).get("platform") or "the platform")]
    dialogs = {d.get("id"): d for d in spec.get("dialogs") or [] if isinstance(d, dict)}
    screens = {s.get("id") for s in spec.get("screens") or [] if isinstance(s, dict)}
    tags, code, code_standard = [], None, False
    for entry in fit.get("features") or []:
        if not isinstance(entry, dict):
            continue
        support = str(entry.get("support") or "").strip().lower()
        keys = [str(k) for k in entry.get("features") or []]
        if "code:project" in keys and support in ("standard", "configuration"):
            code_standard = True
        if support not in ("custom", "not supported"):
            continue
        row = str(entry.get("row") or "")
        product = row.rsplit(" ", 1)[0] if " " in row else stack[0]
        label = CUSTOM_LABEL if support == "custom" else f"Not standard on {product}"
        title = ". ".join(x for x in (str(entry.get("what") or "").strip().rstrip("."), str(entry.get("takes") or "").strip()) if x)
        if "code:project" in keys:
            code = {"label": label, "title": title}
        places = [e for e in entry.get("elements") or [] if isinstance(e, dict) and e.get("element")]
        if not places:  # written before platform_fit named the elements: the heading of each screen it is used on
            for where in entry.get("used_in") or []:
                kind, _, name = str(where).partition(" ")
                if kind == "screen" and name in screens:
                    places.append({"screen": name, "element": "region:page heading"})
                elif kind == "dialog" and name in dialogs:
                    places.append({"dialog": name, "element": f"dialog:{dialogs[name].get('title')}"})
        for place in places:
            tag = {k: str(place[k]) for k in ("screen", "dialog", "element") if place.get(k) not in (None, "")}
            if ("screen" in tag or "dialog" in tag) and {**tag, "label": label, "title": title} not in tags:
                tags.append({**tag, "label": label, "title": title})
    if code is None and not code_standard and project_code(project).get("mockup.js"):
        code = dict(CUSTOM_CODE)
    return {"tags": tags, "code": code}


def build_inputs(project):
    """One value for everything a project's mock-up is built from: its spec, its own mock-up code and
    Blueprint's mock-up engine. Compared by content, not by file times, which on Windows move in steps of
    about 15 milliseconds: a change saved in the same step as a build would otherwise be missed."""
    project = Path(project)
    # The logo and font files the look may name are counted before the spec is read: every one in the spec folder.
    kinds = {kind for kinds in LOOK_FILES.values() for kind in kinds}
    look = sorted(f for f in layout.spec_dir(project).glob("*") if f.is_file() and f.suffix.lower() in kinds)
    files = [layout.spec_file(project), *sorted(project_code(project).values()), *look, Path(__file__).resolve(),
             ENGINE / "app.js", ENGINE / "base.css", ENGINE / "look.css", *sorted((ENGINE / "themes").glob("*.css"))]
    value = hashlib.sha256()
    for f in files:
        value.update(f.name.encode() + b"\0" + f.read_bytes() + b"\0")
    return value.hexdigest()


def build(project):
    inputs = build_inputs(project)  # before reading the spec: a change made during the build is seen next time
    spec = load_spec(project)
    out = layout.mockup_dir(project)
    (out / "assets").mkdir(parents=True, exist_ok=True)
    theme = spec["project"].get("theme") or UNSET_THEME
    theme_file = ENGINE / "themes" / f"{theme}.css"
    if not theme_file.exists():
        sys.exit(f"Unknown theme '{theme}'. Available: {[p.stem for p in (ENGINE / 'themes').glob('*.css')]}")
    shutil.copy(ENGINE / "app.js", out / "assets" / "app.js")
    shutil.copy(ENGINE / "base.css", out / "assets" / "base.css")
    shutil.copy(ENGINE / "look.css", out / "assets" / "look.css")
    theme_text = theme_css(theme_file)
    (out / "assets" / "theme.css").write_text(theme_text, encoding="utf-8")
    fonts, fonts_missing = look_css(spec, project, theme_text)
    if fonts:
        (out / "assets" / "fonts.css").write_text(fonts, encoding="utf-8")
    elif (out / "assets" / "fonts.css").exists():
        (out / "assets" / "fonts.css").unlink()
    for old in (out / "assets").glob("logo.*"):
        old.unlink()  # a logo taken out or changed since the last build
    logo = look_file(project, spec, "logo")
    if logo is not None:
        shutil.copy(logo, out / "assets" / f"logo{logo.suffix.lower()}")
    shown = {k: v for k, v in spec.items() if k not in INTERNAL_SPEC}
    creating = new_records(spec)
    custom = custom_work(spec, project)
    # What the build worked out for the engine: the buttons that add a record, and what to tag as custom work.
    made = {"theme": theme, "creates": [{k: n[k] for k in ("screen", "label", "dialog", "confirm", "data", "status")} for n in creating],
            "custom": custom["tags"], "custom_code": custom["code"],
            "logo": f"assets/logo{logo.suffix.lower()}" if logo is not None else None}
    (out / "spec.js").write_text("window.SPEC = " + json.dumps(shown, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "build.js").write_text("window.MOCKUP_BUILD = " + json.dumps(made, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    own = project_code(project)
    for name, target in PROJECT_CODE.items():
        if name in own:
            shutil.copy(own[name], out / "assets" / target)
        elif (out / "assets" / target).exists():
            (out / "assets" / target).unlink()  # taken out of the project since the last build
    p = spec["project"]
    (out / "index.html").write_text(INDEX.format(
        title=f"{p['name']} – Mock-up v{p.get('version', '')}",
        fonts_css='<link rel="stylesheet" href="assets/fonts.css">' if fonts else "",
        project_css='<link rel="stylesheet" href="assets/project.css">' if "mockup.css" in own else "",
        project_js='<script src="assets/project.js"></script>' if "mockup.js" in own else ""), encoding="utf-8")
    (out / BUILT_FROM).write_text(inputs, encoding="utf-8")
    snapshot(project, spec)
    print(f"Built {out / 'index.html'} ({len(spec['screens'])} screens, theme {theme}"
          + ("" if spec["project"].get("theme") else ": the spec sets no theme, so it keeps joget") + ")")
    if fonts_missing:
        print(f"{' and '.join(fonts_missing)} could not be put into the mock-up (node_modules/geist is missing: run setup again): "
              "it shows in that font only on computers that have it installed.")
    for n in creating:
        print(f"New records: {n['label']} on {n['title']} adds a record to the {n['data']} list"
              + (f" (when {n['confirm']} in its dialog is pressed)" if n["dialog"] else "") + (f", as {n['status']}" if n["status"] else "")
              + ": it shows in every list and count it matches.")
    for title in forms_without_a_list(spec):
        print(f"The main button of {title} only shows its message: give the screen 'data' (the list it adds to) for it to add a record.")
    moves = len({(m["where"], m["label"]) for m in status_moves(spec)})
    if moves:
        print(f"{moves} button{'s' if moves != 1 else ''} move{'' if moves != 1 else 's'} a record to another status when clicked "
              "(for the session: Reset sample data on the presenter's bar puts the sample data back).")
        missing = moves_not_shown(spec)
        if missing:
            print("The status rules also allow these moves, which no button of the mock-up makes: " + "; ".join(missing)
                  + ". If the client should see one of them acted out, ask Claude to add it to the mock-up; if the system makes "
                  "it on its own (a date passing, a linked record moving), add it to the status's 'auto'.")
    automatic = automatic_moves(spec)
    if automatic:
        print("Made by the system on its own (auto), so no button makes them: " + "; ".join(automatic) + ".")
    if custom["tags"] or custom["code"]:
        print(f"{len(custom['tags'])} part{'s' if len(custom['tags']) != 1 else ''} of the mock-up carr{'y' if len(custom['tags']) != 1 else 'ies'} "
              f"a \"{CUSTOM_LABEL}\" tag while presenting" + (", and so does what the project's own mock-up code adds" if custom["code"] else "")
              + " (never in screenshots; \"Custom work\" on the presenter's bar hides them).")
    warnings = spec_warnings(spec)
    if warnings:
        print("Settings the mock-up ignores (check the spelling, or start a note of your own with _):\n  " + "\n  ".join(warnings))
    return spec


# ------------------------------------------------------------------ serve
def snapshot(project, spec):
    """Keep a copy of this mock-up version in mockup/versions/v<version>/, so it can be shown again later.
    The copy of a version that was issued to the client is never replaced: it stays what the client saw."""
    import project as project_tool

    out = layout.mockup_dir(project)
    version = str(spec["project"].get("version", "draft"))
    dest = layout.versions_dir(project) / f"v{version}"
    issued = project_tool.is_issued(Path(project), version)
    if issued and dest.exists():
        print(f"v{version} was issued to {issued['to']} on {issued['date']}: the saved mock-up of that version is kept as it was. "
              "What you just built is the working mock-up only; bump project.version in the spec to keep it as a version.")
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(out, dest, ignore=lambda d, names: ["versions", LOOK_PREVIEW] if Path(d) == out else [])


class MockupServer(http.server.ThreadingHTTPServer):
    """A web server that takes its port for itself alone.

    Windows lets a second program listen on a port the first one opened the usual way, with no error. Two
    mock-ups would then share the port, and a comment could be saved to either project. Taking the port
    exclusively makes the second one fail to start, as it already does on other systems."""
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


SAVING = threading.Lock()  # one comment at a time: each takes the next number


@contextlib.contextmanager
def feedback_lock(fb_file):
    """One program at a time writes a project's feedback file: the server saving a comment, or the assistant
    marking one in a live session. A lock left by a program that stopped is taken over after ten seconds."""
    lock = Path(fb_file).with_name(".feedback.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    give_up = time.time() + 5
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 10:
                    lock.unlink()
                    continue
            except OSError:
                pass
            if time.time() > give_up:
                break  # better to save the comment than to lose it waiting
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


# What a mock-up is told about a comment. Everyone with the room's link can read this, so the internal part
# stays out: the note, the register item, and whether it was called a possible change request.
ROOM_FIELDS = ("id", "screen", "role", "element", "elements", "box", "text", "author", "x", "y", "time", "received", "version", "build", "edited",
               "follows")
# The mock-up says the same (STATE_WORDS in tools/mockup/app.js): change both together.
ROOM_WORDS = {"received": "Received", "working": "Working on it", "applied": "Applied", "noted": "Noted for follow-up"}


def room_state(comment):
    status = comment.get("status")
    return "received" if not status else status if status == "working" else "applied" if status in ("applied", "decision") else "noted"


def for_the_room(comments):
    """What the room is told about the comments: the client-safe fields, and what became of each. A comment
    taken back (withdrawn) is not shown at all."""
    return [{**{k: c[k] for k in ROOM_FIELDS if k in c}, "state": room_state(c)} for c in comments if isinstance(c, dict) and not c.get("withdrawn")]


def read_feedback(fb_file):
    return json.loads(Path(fb_file).read_text(encoding="utf-8")) if Path(fb_file).exists() else []


def standing(comments):
    """The comments that count: every one except those their writer or the presenter took back (withdrawn)."""
    return [c for c in comments if isinstance(c, dict) and not c.get("withdrawn")]


# A comment can be changed or taken back from the mock-up while it waits (no status yet), by the browser that
# wrote it (it sends the private `owner` it saved the comment with) or by the presenter on the machine that runs
# the server. Nothing is erased: an edit keeps the earlier text in `history`, and taking it back marks it
# `withdrawn` (when, and by whom), so it no longer shows anywhere.
LOCKED = "This comment is already being worked on, so it can no longer be changed. Add a new comment instead."
DEALT_WITH = "This comment has already been dealt with, so it can no longer be changed. Add a new comment instead."


def change_comment(fb_file, action, body, presenter):
    """Edit (`action` "edit", body {id, text, owner}) or withdraw (`action` "withdraw", body {id, owner, by})
    a comment. Returns (HTTP status, answer): the comment as the room sees it, or {"error": words for the room}."""
    fb_file = Path(fb_file)
    wanted = str(body.get("id") or "")
    with SAVING, feedback_lock(fb_file):
        try:
            items = read_feedback(fb_file)
        except ValueError:
            return 503, {"error": "The comments could not be read just now. Try again in a moment."}
        found = next((c for c in items if isinstance(c, dict) and str(c.get("id")) == wanted and wanted), None)
        if found is None or found.get("withdrawn"):
            return 404, {"error": "This comment is no longer there."}
        if not presenter and (not body.get("owner") or str(body.get("owner")) != str(found.get("owner") or "")):
            return 403, {"error": "Only the person who wrote this comment, or the presenter, can change it."}
        if found.get("status"):
            return 409, {"error": LOCKED if found["status"] == "working" else DEALT_WITH}
        now = dt.datetime.now().isoformat(timespec="seconds")
        if action == "edit":
            text = str(body.get("text") or "").strip()
            if not text:
                return 400, {"error": "A comment needs some text. To take it back, delete it."}
            if text != found.get("text"):
                found.setdefault("history", []).append({"text": found.get("text"), "until": now})
                found["text"] = text
                found["edited"] = now
        else:
            found["withdrawn"] = now
            found["withdrawn_by"] = str(body.get("by") or "").strip() or ("the presenter" if presenter else "its writer")
        fb_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        print(f"  feedback {found['id']} " + (f"edited: {found.get('text')}" if action == "edit" else "withdrawn"))
    except Exception:
        pass
    return 200, ({**for_the_room([found])[0]} if action == "edit" else {"id": found["id"], "withdrawn": True})


def read_body(request, limit=2_000_000):
    """The JSON object a mock-up sent, or None."""
    try:
        size = int(request.headers.get("Content-Length") or 0)
        if size > limit:
            return None
        item = json.loads(request.rfile.read(size) or b"{}")
    except ValueError:
        return None
    return item if isinstance(item, dict) else None


def from_this_machine(request):
    """The request comes from the computer the server runs on: the presenter's own browser."""
    host = str(request.client_address[0])
    if host.startswith("::ffff:"):
        host = host[7:]
    return host.startswith("127.") or host == "::1" or host in own_addresses()


_OWN = []


def own_addresses():
    if not _OWN:
        _OWN.append(set(lan_addresses()))
    return _OWN[0]


# ------------------------------------------------------------------ the walk-through, shared by the room
class DemoState:
    """What a walk-through changed in the sample data (records added and moved), shared by every browser
    showing one mock-up, so a record submitted on one laptop shows in the approver's list on another. Kept in
    memory for as long as the server runs: restarting it starts from the sample data, and it never touches the
    spec, the screenshots or the document. Each browser sends the records it changed; the last change to a
    record wins. `version` changes with every change, so a browser knows when to draw again."""

    def __init__(self):
        self.lock = threading.Lock()
        self.epoch = os.urandom(4).hex()
        self.count = 0
        self.lists = {}

    def read(self):
        with self.lock:
            return {"version": f"{self.epoch}-{self.count}", "lists": json.loads(json.dumps(self.lists))}

    def change(self, body):
        """Apply what a browser sent: {reset: true}, or {lists: {name: {key, created, changed, removed}}, touched:
        {name: [record ids]}}. Only the records it touched are taken from it, so a browser that has not yet seen
        another's change does not undo it. False when the body is not one of these."""
        with self.lock:
            if body.get("reset"):
                self.lists = {}
            else:
                lists, touched = body.get("lists"), body.get("touched")
                if not isinstance(lists, dict) or not isinstance(touched, dict):
                    return False
                for name, ids in touched.items():
                    sent = lists.get(name) if isinstance(lists.get(name), dict) else {}
                    if not isinstance(ids, list):
                        return False
                    ids = {str(i) for i in ids}
                    key = sent.get("key") or (self.lists.get(name) or {}).get("key")
                    held = self.lists.get(name) or {"key": key, "created": [], "changed": {}, "removed": []}
                    is_touched = lambda rec: isinstance(rec, dict) and str(rec.get(key)) in ids
                    created = [r for r in sent.get("created") or [] if is_touched(r)] + [r for r in held["created"] if not is_touched(r)]
                    changed = {k: v for k, v in held["changed"].items() if k not in ids}
                    changed.update({str(k): v for k, v in (sent.get("changed") or {}).items() if str(k) in ids and isinstance(v, dict)})
                    removed = [r for r in held["removed"] if str(r) not in ids] + [r for r in sent.get("removed") or [] if str(r) in ids]
                    held = {"key": key, "created": created, "changed": changed, "removed": removed}
                    if created or changed or removed:
                        self.lists[name] = held
                    else:
                        self.lists.pop(name, None)
            self.count += 1
            return True


def comment_in(request):
    """The comment a mock-up sent, or None when it is not one (the mock-up then keeps it in the browser)."""
    try:
        item = json.loads(request.rfile.read(int(request.headers.get("Content-Length") or 0)) or b"{}")
    except ValueError:
        return None
    return item if isinstance(item, dict) and str(item.get("text") or "").strip() else None


def save_comment(fb_file, item):
    """Add a comment to a project's feedback file under the next number. Returns it as saved."""
    fb_file = Path(fb_file)
    with SAVING, feedback_lock(fb_file):
        fb_file.parent.mkdir(parents=True, exist_ok=True)
        items = read_feedback(fb_file)
        item["id"] = f"FB-{len(items) + 1:03d}"
        item["received"] = dt.datetime.now().isoformat(timespec="seconds")
        items.append(item)
        fb_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        print(f"  feedback {item['id']} on {item.get('screen')} / {item.get('element') or 'screen'}: {item.get('text')}")
    except Exception:  # a console that cannot show the characters must not turn a saved comment into an error
        print(f"  feedback {item['id']} saved")
    return item


def build_stamp(mock, project=None):
    """Which build of a mock-up a server is showing, for the open pages that ask every few seconds: they
    reload when it changes. With `project`, the mock-up is first built again if its spec changed, so saving
    the spec is all it takes. A spec with mistakes keeps the last good build and says what is wrong."""
    problem = ""
    if project is not None:
        with BUILDING:
            problem = ensure_built(project)
    stamp = Path(mock) / BUILT_FROM
    built = Path(mock) / "spec.js"
    stamp = stamp.read_text(encoding="utf-8") if stamp.exists() else str(built.stat().st_mtime_ns) if built.exists() else ""
    return {"stamp": stamp, "live": project is not None and is_listening(project),
            **({"problem": problem} if problem else {})}


def make_server(mock, fb_file, host, port, project=None):
    """The server for the built mock-up in `mock`, saving comments to `fb_file`. Raises OSError when the
    port is taken. Port 0 picks a free one (see server.server_address). With `project`, the mock-up follows
    that project's spec (see build_stamp)."""
    mock, fb_file = Path(mock).resolve(), Path(fb_file).resolve()
    fb_file.parent.mkdir(parents=True, exist_ok=True)
    demo = DemoState()

    def read():
        return read_feedback(fb_file)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(mock), **kw)

        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/feedback"):
                return self._json(for_the_room(read()))
            if self.path.startswith("/api/build"):
                return self._json({**build_stamp(mock, project), "presenter": from_this_machine(self)})
            if self.path.startswith("/api/state"):
                return self._json(demo.read())
            return super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")  # a rebuilt mock-up must not be shown from the browser's memory
            super().end_headers()

        def do_POST(self):
            if self.path.startswith("/api/state"):
                body = read_body(self)
                if body is None or not demo.change(body):
                    return self._json({"error": "a change to the sample data is {reset: true} or {lists, touched}"}, 400)
                return self._json(demo.read())
            for action in ("edit", "withdraw"):
                if self.path.startswith(f"/api/feedback/{action}"):
                    body = read_body(self)
                    if body is None:
                        return self._json({"error": "Not a comment."}, 400)
                    code, answer = change_comment(fb_file, action, body, from_this_machine(self))
                    return self._json(answer, code)
            if not self.path.startswith("/api/feedback"):
                return self._json({"error": "not found"}, 404)
            item = comment_in(self)
            if item is None:
                # Answer, so the mock-up can tell the comment was not saved and keep it in the browser.
                return self._json({"error": "a comment is a JSON object with a 'text'"}, 400)
            return self._json(for_the_room([save_comment(fb_file, item)])[0])

    return MockupServer((host, port), Handler)


def lan_addresses():
    """This machine's addresses on the local network (not 127.0.0.1), for others in the room to open. The
    one the network traffic leaves by comes first: the others are often virtual adapters nobody can reach."""
    usable = lambda a: bool(a) and not a.startswith("127.") and a != "0.0.0.0"
    main, others = None, set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # sends nothing: it only asks which network interface would be used
            main = s.getsockname()[0]
    except OSError:
        pass
    try:
        others.update(info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return ([main] if usable(main) else []) + sorted(a for a in others if usable(a) and a != main)


def serve(project, port, lan, version=None):
    if not version:
        build(project)
    mock = layout.mockup_dir(project).resolve()
    if version:
        mock = layout.versions_dir(project).resolve() / f"v{version.lstrip('v')}"
        if not mock.exists():
            have = sorted(p.name for p in layout.versions_dir(project).glob("v*"))
            sys.exit(f"No mock-up v{version.lstrip('v')}. Available: {', '.join(have) or 'none'}")
        print(f"Showing the saved mock-up {mock.name} (comments are still saved to the project).")
    fb_file = layout.feedback_file(project).resolve()
    try:
        server = make_server(mock, fb_file, "0.0.0.0" if lan else "127.0.0.1", port, None if version else project)
    except OSError as e:
        sys.exit(f"Cannot start the mock-up on port {port}: it is already in use, most likely by another mock-up "
                 f"that is still open.\nClose that window and start again, or use another port by adding "
                 f"--port {port + 1}.\n(The system said: {e})")
    url = f"http://localhost:{port}/"
    print(f"Serving {mock} at {url}")
    if lan:
        addresses = lan_addresses()
        if addresses:
            print(f"Others on the same network open: http://{addresses[0]}:{port}/"
                  + (f"   (if that does not work: {', '.join(f'http://{a}:{port}/' for a in addresses[1:])})" if addresses[1:] else ""))
            print("If they cannot reach it, allow Python through the firewall when your system asks.")
        else:
            print(f"Others on the same network open http://<this machine's address>:{port}/ "
                  "(the address could not be worked out: look it up in your network settings).")
    print(f"Feedback is saved to {fb_file}. Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    with server_mark(project, port):
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


@contextlib.contextmanager
def server_mark(project, port):
    """While a project's mock-up is served, a mark in its feedback folder says so (the port and this program),
    so the project's folders are not moved under it (tools/project.py migrate checks it)."""
    mark = layout.server_file(project)
    try:
        mark.parent.mkdir(parents=True, exist_ok=True)
        mark.write_text(json.dumps({"port": port, "pid": os.getpid(), "started": dt.datetime.now().isoformat(timespec="seconds")}),
                        encoding="utf-8")
    except OSError:
        mark = None
    try:
        yield
    finally:
        if mark is not None:
            try:
                mark.unlink()
            except OSError:
                pass


# ------------------------------------------------------------------ the home page: every mock-up, one click away
HOME_STYLE = """
:root { --ground:#F5F5F7; --card:#FFFFFF; --text:#1D1D1F; --secondary:#6E6E73; --separator:#E5E5EA; --line:#D2D2D7; --field:#E9E9EE;
  --accent:#1F5FBF; --accent-text:#1A4C99; --tint:#EDF2FA; --tint-hover:#E1EAF7; --late:#FF9500; --late-text:#C93400;
  --blocked:#FF3B30; --blocked-text:#D70015; --neutral:#8E8E93;
  --ring:0 0 0 1px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.04); --ease:cubic-bezier(0.2,0.8,0.2,1);
  --t-title:1.75rem; --t-section:1.0625rem; --t-body:0.9375rem; --t-detail:0.8125rem; --t-xs:0.75rem; }
* { box-sizing:border-box; }
html { font-size:16px; }
body { margin:0; background:var(--ground); color:var(--text);
  font:400 var(--t-body)/1.5 Geist, "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased; }
.page { padding:40px; display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); gap:24px; }
.span-12 { grid-column:span 12; } .span-6 { grid-column:span 6; }
@media (max-width:900px) { .page { padding:16px; } .span-6 { grid-column:span 12; } }
.head { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; }
h1 { font-size:var(--t-title); font-weight:600; letter-spacing:-0.02em; margin:0 0 4px; line-height:1.2; }
.quiet { color:var(--secondary); } .detail { font-size:var(--t-detail); }
.stamp { text-align:right; color:var(--secondary); font-size:var(--t-detail); }
.card { background:var(--card); border-radius:16px; box-shadow:var(--ring); }
.project { display:flex; flex-direction:column; height:100%; }
.project .top { display:flex; align-items:flex-start; gap:16px; padding:20px 24px 16px; }
.project .who { min-width:0; flex:1; }
.square { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:8px; vertical-align:1px; }
h2 { font-size:var(--t-section); font-weight:600; letter-spacing:-0.01em; margin:0; line-height:1.35; }
h2 a { color:inherit; text-decoration:none; } h2 a:hover { text-decoration:underline; }
.btn { display:inline-flex; align-items:center; height:34px; padding:0 14px; border-radius:9px; background:var(--tint); color:var(--accent-text);
  font-weight:500; font-size:0.875rem; text-decoration:none; white-space:nowrap; transition:background 120ms var(--ease); }
.btn:hover { background:var(--tint-hover); }
.facts { margin:0; padding:0 24px; }
.fact { display:grid; grid-template-columns:120px minmax(0, 1fr); gap:12px; align-items:center; min-height:44px; position:relative; font-size:var(--t-detail); }
.fact::before { content:""; position:absolute; top:0; left:0; right:-24px; height:1px; background:var(--separator); }
.fact dt { color:var(--secondary); } .fact dd { margin:0; font-variant-numeric:tabular-nums; }
.earlier { display:flex; flex-wrap:wrap; gap:4px 16px; }
.earlier a, a.link { color:var(--accent); text-decoration:none; } .earlier a:hover, a.link:hover { text-decoration:underline; }
.project .end { margin-top:auto; height:8px; }
.status { display:inline-flex; align-items:center; gap:6px; font-size:var(--t-detail); }
.status::before { content:""; flex:none; width:8px; height:8px; border-radius:50%; background:var(--neutral); }
.status.progress { color:var(--accent-text); } .status.progress::before { background:var(--accent); }
.status.blocked { color:var(--blocked-text); } .status.blocked::before { background:var(--blocked); }
.status.neutral { color:var(--secondary); }
.card-head { display:flex; align-items:baseline; gap:8px; padding:20px 24px 8px; }
.card-head .quiet { font-size:var(--t-detail); }
.rows { padding:0 0 8px; }
.row { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:16px; align-items:center; min-height:52px; padding:6px 24px; position:relative; }
.row + .row::before { content:""; position:absolute; top:0; left:24px; right:0; height:1px; background:var(--separator); }
.row .name { font-weight:500; }
.say { display:inline-block; background:var(--field); border-radius:6px; padding:1px 8px; color:var(--text);
  font-family:"Geist Mono", ui-monospace, "Cascadia Mono", Consolas, monospace; font-size:var(--t-detail); white-space:nowrap; }
.empty { padding:24px; }
.empty b { display:block; font-size:var(--t-section); font-weight:600; margin-bottom:4px; }
footer { grid-column:span 12; font-size:var(--t-detail); color:var(--secondary); max-width:90ch; }
code { font:var(--t-xs) "Geist Mono", ui-monospace, "Cascadia Mono", Consolas, monospace; background:var(--field); border-radius:6px; padding:1px 6px; }
a:focus-visible { outline:none; box-shadow:0 0 0 3px rgba(31,95,191,0.25); border-radius:9px; }
main { max-width:none; padding:40px; }
pre { white-space:pre-wrap; font:var(--t-detail)/1.5 "Geist Mono", ui-monospace, "Cascadia Mono", Consolas, monospace; background:var(--card); border-radius:16px; padding:20px 24px; box-shadow:var(--ring); }
.foot { margin:24px 0 0; color:var(--secondary); font-size:var(--t-detail); }
a.back { color:var(--accent); text-decoration:none; }
@media (max-width:700px) { .head { flex-direction:column; align-items:flex-start; } .stamp { text-align:left; } .fact { grid-template-columns:96px minmax(0, 1fr); }
  .row { grid-template-columns:minmax(0, 1fr); } main { padding:16px; } }
@media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
"""


def _natural(name):
    """v1.10 after v1.9."""
    return [int(part) if part.isdigit() else part for part in __import__("re").split(r"(\d+)", name)]


def _day(moment):
    return f"{moment.day} {moment.strftime('%b')}, {moment.strftime('%H:%M')}"


def presented_at(saved):
    """When a version kept at the start of a live session was presented ("v1.4-presented-20261106-1900"), or None."""
    m = __import__("re").fullmatch(r"(v.+?)-presented-(\d{8})-(\d{4})", saved)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M")
    except ValueError:
        return None


def version_label(saved):
    """A saved version's folder name as people read it: "v1.4-presented-20261106-1900" is "v1.4 as presented 6 Nov 19:00"."""
    moment = presented_at(saved)
    if moment is None:
        return saved
    return f"{saved.split('-presented-')[0]} as presented {moment.day} {moment.strftime('%b')} {moment.strftime('%H:%M')}"


def without_mockup(projects):
    """The projects that have no mock-up spec yet: [{slug, name, client}], the name and client from the project's
    register (its folder name when there is none), by folder name."""
    folder = Path(projects)
    found = []
    for p in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not p.is_dir() or p.name.startswith(("_", ".")) or layout.spec_file(p).exists():
            continue
        try:
            reg = json.loads(layout.register_json(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reg = {}
        reg = reg if isinstance(reg, dict) else {}
        found.append({"slug": p.name, "name": str(reg.get("project") or p.name), "client": str(reg.get("client") or "")})
    return found


def mockups(projects):
    """Every project that has a mock-up spec, the one worked on last first:
    [{slug, name, client, mark, color, version, built, shown, comments, waiting, versions, problem}]."""
    found = []
    for folder in sorted(Path(projects).iterdir()) if Path(projects).is_dir() else []:
        spec_file = layout.spec_file(folder)
        if not folder.is_dir() or folder.name.startswith(("_", ".")) or not spec_file.exists():
            continue
        entry = {"slug": folder.name, "name": folder.name, "client": "", "mark": folder.name[:1].upper(), "color": "#1f5fbf", "version": "",
                 "built": None, "shown": None, "comments": 0, "waiting": 0, "versions": [], "problem": "", "changed": spec_file.stat().st_mtime}
        try:
            project = (yaml.safe_load(spec_file.read_text(encoding="utf-8")) or {}).get("project") or {}
            entry.update(name=str(project.get("name") or folder.name), client=str(project.get("client_short") or project.get("client") or ""),
                         mark=str(project.get("short_name") or str(project.get("name") or folder.name)[:1]).upper()[:5],
                         color=str(project.get("primary_color") or entry["color"]), version=str(project.get("version") if project.get("version") is not None else ""))
        except Exception:
            entry["problem"] = "its spec could not be read"
        built = layout.mockup_dir(folder) / "index.html"
        if built.exists():
            entry["built"] = dt.datetime.fromtimestamp(built.stat().st_mtime)
        try:
            comments = standing(json.loads(layout.feedback_file(folder).read_text(encoding="utf-8")))
            entry["comments"] = len(comments)
            entry["waiting"] = sum(1 for c in comments if isinstance(c, dict) and not c.get("status"))
        except (OSError, ValueError):
            pass
        saved = layout.versions_dir(folder)
        entry["versions"] = sorted((p.name for p in saved.glob("v*") if (p / "index.html").exists()), key=_natural, reverse=True) if saved.is_dir() else []
        entry["shown"] = max((t for t in map(presented_at, entry["versions"]) if t), default=None)  # the last live session
        found.append(entry)
    return sorted(found, key=lambda e: -e["changed"])


def home_page(projects):
    """The page that lists every mock-up, as HTML: one card per project with a mock-up (its version, when it was
    last built and shown, the comments waiting, its earlier versions), then the projects without one with what
    to say to Claude. Only ever shown on this computer: it names every client's project."""
    esc = lambda value: __import__("html").escape(str(value), quote=True)
    plural = lambda n, word: f"{n} {word}{'' if n == 1 else 's'}"
    cards = []
    for m in mockups(projects):
        earlier = [v for v in m["versions"] if v != f"v{m['version']}"]
        if m["problem"]:
            state = f'<span class="status blocked">Cannot be opened: {esc(m["problem"])}</span>'
        elif m["waiting"]:  # it needs the presenter, it is not late: the accent, not orange
            state = f'<span class="status progress">{plural(m["waiting"], "comment")} waiting</span>'
        else:
            state = f'<span class="status neutral">{"No comments waiting" if m["comments"] else "No comments yet"}</span>'
        facts = [("Version", esc(m["version"]) if m["version"] else "Not set"),
                 ("Last built", esc(_day(m["built"])) if m["built"] else "Not built yet")]
        if m["shown"]:
            facts.append(("Last shown", esc(_day(m["shown"]))))
        facts.append(("Comments", state))
        if earlier:
            facts.append(("Earlier versions", '<span class="earlier">' + "".join(
                f'<a href="/p/{esc(m["slug"])}/v/{esc(v[1:])}/">{esc(version_label(v))}</a>' for v in earlier) + "</span>"))
        cards.append(
            f'<article class="card project span-6" data-project="{esc(m["slug"])}"><div class="top"><div class="who">'
            f'<h2><span class="square" style="background:{esc(m["color"])}"></span><a href="/p/{esc(m["slug"])}/">{esc(m["name"])}</a></h2>'
            f'<div class="quiet detail">{esc(m["client"])}</div></div><a class="btn" href="/p/{esc(m["slug"])}/">Open</a></div>'
            '<dl class="facts">' + "".join(f'<div class="fact"><dt>{k}</dt><dd>{v}</dd></div>' for k, v in facts) + '</dl><div class="end"></div></article>')
    body = "".join(cards) if cards else (
        '<section class="card empty span-12"><b>No mock-up yet</b><span class="quiet">In Claude, say <span class="say">build a mock-up for</span> '
        'and the name of a project, then open this page again.</span></section>')
    waiting = without_mockup(projects)
    if waiting:
        body += (f'<section class="card span-12" data-none-yet><div class="card-head"><h2>No mock-up yet</h2><span class="quiet">{len(waiting)}</span></div><div class="rows">'
                 + "".join(f'<div class="row"><span><span class="name">{esc(w["name"])}</span>'
                           + (f'<span class="quiet detail"> · {esc(w["client"])}</span>' if w["client"] else "")
                           + '</span><span><span class="quiet detail">Say to Claude:</span> '
                           f'<span class="say">build a mock-up for {esc(w["name"])}</span></span></div>' for w in waiting) + "</div></section>")
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Mock-ups</title><style>{HOME_STYLE}</style></head><body><div class=\"page\">"
            "<header class=\"span-12 head\"><div><h1>Mock-ups</h1><div class=\"quiet\">Pick a project to present. Comments are saved to the "
            "project as they are typed.</div></div><div class=\"stamp\">On this computer only</div></header>"
            f"{body}<footer>This page is only for you: it opens on this computer alone and never shows one client another client's project. "
            "To let people in the room comment from their own laptops, say in Claude \"present &lt;project&gt; to the room\" (without Claude: type "
            "<code>present &lt;project&gt; --lan</code> in a command window in the Blueprint folder). Only that project is shared with them.</footer>"
            "</div></body></html>")


BUILDING = threading.Lock()  # one build at a time
_could_not_build = {}        # {project folder: (its sources as they were, what stopped the build)}


def ensure_built(project):
    """Build a project's mock-up when it was never built, its spec changed, or Blueprint's mock-up engine was
    updated since. Returns what stopped the build as text, or "" when the mock-up is ready. A spec that
    could not be built is not tried again until it is changed."""
    import contextlib
    import io

    project = Path(project).resolve()
    try:
        newest = build_inputs(project)
    except OSError as e:
        return f"The spec could not be read: {e}"
    stamp = layout.mockup_dir(project) / BUILT_FROM
    if (layout.mockup_dir(project) / "index.html").exists() and stamp.exists() and stamp.read_text(encoding="utf-8") == newest:
        return ""
    if _could_not_build.get(project, (None, ""))[0] == newest:
        return _could_not_build[project][1]
    said, problem = io.StringIO(), ""
    try:
        with contextlib.redirect_stdout(said):
            build(project)
    except SystemExit as stop:
        problem = (said.getvalue() + (str(stop.code) if isinstance(stop.code, str) else "")).strip() or "The mock-up could not be built."
    except Exception as e:  # a damaged spec must not take the server down
        problem = f"The mock-up could not be built: {e}"
    if problem:
        _could_not_build[project] = (newest, problem)
    else:
        _could_not_build.pop(project, None)
    return problem


def make_home(projects, host, port):
    """The server behind the home page. `/` lists the mock-ups; `/p/<project>/` is that project's mock-up,
    built when needed, and `/p/<project>/v/<version>/` a saved version of it. Comments go to the project
    they are made in."""
    import re
    import urllib.parse

    projects = Path(projects).resolve()
    walkthroughs, guard = {}, threading.Lock()  # {mock-up folder: DemoState}: one per mock-up, never shared across projects

    def demo_of(mock):
        with guard:
            return walkthroughs.setdefault(str(Path(mock).resolve()), DemoState())

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, code=200, kind="text/html; charset=utf-8"):
            body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _page(self, title, text, code):
            esc = __import__("html").escape
            self._send(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{esc(title)}</title><style>{HOME_STYLE}</style></head>"
                       f"<body><main><h1>{esc(title)}</h1><pre>{esc(text)}</pre><p class=\"foot\"><a class=\"back\" href=\"/\">All mock-ups</a></p></main></body></html>", code)

        def _where(self):
            """(project folder, mock-up folder, the rest of the path) for /p/<project>/..., or None."""
            path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            m = re.fullmatch(r"/p/([A-Za-z0-9][A-Za-z0-9._ -]*)(/.*)?", path)
            if not m:
                return None
            project = projects / m.group(1)
            if project.parent != projects or not layout.spec_file(project).exists():
                return None
            rest = m.group(2)
            if rest is None:
                return project, None, None  # no trailing slash yet
            version = re.match(r"/v/([0-9A-Za-z.-]+)(/.*)?$", rest)
            if version:
                mock = layout.versions_dir(project) / f"v{version.group(1)}"
                return (project, mock, version.group(2)) if mock.is_dir() else None
            return project, layout.mockup_dir(project), rest

        def translate_path(self, path):
            self.directory = str(self._mock)
            return super().translate_path(self._rest)

        def do_GET(self):
            if urllib.parse.urlsplit(self.path).path == "/":
                return self._send(home_page(projects))
            where = self._where()
            if not where:
                return self._page("Not found", "There is no mock-up at this address.", 404)
            project, mock, rest = where
            if rest is None:  # /p/<project> or /p/<project>/v/<version>: the mock-up's own links need the closing slash
                self.send_response(301)
                self.send_header("Location", urllib.parse.urlsplit(self.path).path + "/")
                self.end_headers()
                return None
            if rest.startswith("/api/feedback"):
                return self._send(json.dumps(for_the_room(read_feedback(layout.feedback_file(project))), ensure_ascii=False), kind="application/json")
            current = mock == layout.mockup_dir(project)  # not a saved earlier version, which never changes
            if rest.startswith("/api/build"):
                return self._send(json.dumps({**build_stamp(mock, project if current else None), "presenter": True}), kind="application/json")
            if rest.startswith("/api/state"):
                return self._send(json.dumps(demo_of(mock).read(), ensure_ascii=False), kind="application/json")
            if current:
                with BUILDING:
                    problem = ensure_built(project)
                if problem and not (mock / "index.html").exists():
                    return self._page("This mock-up cannot be opened yet", problem + "\n\nIn Claude, say \"build the mock-up\" for this project and it will be put right.", 500)
            self._mock, self._rest = mock, rest
            return super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")  # a rebuilt mock-up must not be shown from the browser's memory
            super().end_headers()

        def do_POST(self):
            where = self._where()
            if where and where[1] is not None and where[2] and where[2].startswith("/api/state"):
                body = read_body(self)
                demo = demo_of(where[1])
                if body is None or not demo.change(body):
                    return self._send(json.dumps({"error": "a change to the sample data is {reset: true} or {lists, touched}"}), 400, "application/json")
                return self._send(json.dumps(demo.read(), ensure_ascii=False), kind="application/json")
            for action in ("edit", "withdraw"):
                if where and where[2] and where[2].startswith(f"/api/feedback/{action}"):
                    body = read_body(self)
                    if body is None:
                        return self._send(json.dumps({"error": "Not a comment."}), 400, "application/json")
                    code, answer = change_comment(layout.feedback_file(where[0]), action, body, True)  # this page is only ever on this computer
                    return self._send(json.dumps(answer, ensure_ascii=False), code, "application/json")
            if not where or not where[2] or not where[2].startswith("/api/feedback"):
                return self._send(json.dumps({"error": "not found"}), 404, "application/json")
            item = comment_in(self)
            if item is None:
                return self._send(json.dumps({"error": "a comment is a JSON object with a 'text'"}), 400, "application/json")
            return self._send(json.dumps(for_the_room([save_comment(layout.feedback_file(where[0]), item)])[0], ensure_ascii=False), kind="application/json")

    return MockupServer((host, port), Handler)


def serve_home(port, lan=False):
    """Open the page that lists every mock-up on this machine."""
    import project as project_tool

    if lan:
        sys.exit("--lan shares one project with the room, so name it:  present <project> --lan\n"
                 "The page that lists every mock-up is only ever shown on this computer: a client must not see another client's project.")
    try:
        server = make_home(project_tool.PROJECTS, "127.0.0.1", port)
    except OSError as e:
        sys.exit(f"Cannot start on port {port}: it is already in use, most likely by a mock-up that is still open.\n"
                 f"Close that window and start again, or use another port by adding --port {port + 1}.\n(The system said: {e})")
    url = f"http://localhost:{port}/"
    print(f"Your mock-ups are at {url} (this computer only). Press Ctrl+C to stop.")
    print("Comments are saved to the project they are made in. Keep this window open while you present.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ------------------------------------------------------------------ a live session
# During a live session with the client, comments collect as they are typed and read "Received" in the
# mock-up. When the presenter says go, the assistant works through them: it proposes what to do with each,
# the presenter approves, and each change then waits in every open mock-up as "Update ready": nothing
# reloads under the presenter. These commands keep that orderly:
#   live start       saves the mock-up as it is presented, so what the client first saw can be shown again
#   live list        the comments waiting
#   live take        marks comments "Working on it" and keeps the project as it is, before their change
#   live done        builds the change, refuses it when it has a mistake, and marks the comments applied (one
#                    comment at a time, each with its own note)
#   live mark        records any other outcome; the mock-up shows a client-safe word for it
#   live undo        puts the spec and the project's own code back as they were before the last change; its comments
#                    wait again. The register is not kept: what was changed there is put back with register.py update
#   live end         closes the session and lists what to release
#   live wait        returns when a comment is waiting, for an assistant that works on each one at once
#   live checkpoint  keeps the project as it is, without marking any comment
LIVE_STATUSES = ("received", "working", "applied", "question", "decision", "scope", "declined")
KEPT = ("app.yaml",) + tuple(PROJECT_CODE)  # what a change can touch in spec/, kept before it and put back by undo


def live_file(project):
    return layout.live_file(project)


def live_read(project):
    try:
        data = json.loads(live_file(project).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def live_write(project, data):
    target = live_file(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    draft = target.with_name("live.json.tmp")
    draft.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    draft.replace(target)  # in one step: the server never reads half a file


def live_alive(project):
    """A sign of life from the assistant: it is waiting for comments, or has just dealt with one."""
    data = live_read(project)
    if data and not data.get("ended"):
        data["heartbeat"] = time.time()
        live_write(project, data)


def is_listening(project):
    """A live session is open: comments are collected for the assistant, however long it is busy."""
    data = live_read(project)
    return bool(data) and not data.get("ended")


def live_session(project):
    data = live_read(project)
    if not data or data.get("ended"):
        sys.exit(f"No live session is open for this project. Start one: python -I tools/mockup.py live start {project}")
    return data


def in_words(spec, element):
    """What a comment is about, as the mock-up names it: "the Status column", not "column:Status"."""
    if not element:
        return "the screen"
    kind, _, name = str(element).partition(":")
    if kind == "field":
        fields = [f for s in spec.get("screens") or [] for sec in s.get("sections") or [] for f in sec.get("fields") or []]
        fields += [f for d in spec.get("dialogs") or [] for f in d.get("fields") or []]
        return f"the {next((f.get('label') for f in fields if f.get('id') == name), name)} field"
    words = {"column": "column", "button": "button", "action": "action", "menu": "menu item", "stat": "figure", "section": "section",
             "filter": "filter", "search": "search box", "tab": "tab", "dialog": "dialog"}
    if kind == "title":
        return "the page title"
    if kind == "region":
        return f"the {name}"
    if kind == "row":
        return f"the row {name}"
    if kind == "cell":
        column, _, row = name.partition("|")
        return f"the {column} cell of {row}"
    return f"the {name} {words[kind]}" if kind in words else name or "the screen"


def live_start(project):
    project = Path(project)
    spec = build(project)
    version = str(spec["project"].get("version", "draft"))
    kept = layout.versions_dir(project) / f"v{version}-presented-{dt.datetime.now():%Y%m%d-%H%M}"
    mock = layout.mockup_dir(project)
    if not kept.exists():
        shutil.copytree(mock, kept, ignore=lambda d, names: ["versions", LOOK_PREVIEW] if Path(d) == mock else [])
    live_write(project, {"started": dt.datetime.now().isoformat(timespec="seconds"), "version": version, "kept": kept.name,
                         "heartbeat": time.time(), "changes": []})
    print(f"Live session open for {spec['project'].get('name', project.name)}, version {version}.")
    print(f"The mock-up as it is presented is kept as {kept.name}: it can be shown again whatever changes.")
    print("Next: open the mock-up if it is not open. Comments collect while the presenter presents; when they say go, list them:")
    print(f"  python -I tools/mockup.py live list {project.as_posix()}")


def waiting_comments(project):
    try:
        return [c for c in standing(read_feedback(layout.feedback_file(project))) if not c.get("status")]
    except ValueError:
        return []  # being written this instant: look again


def show_waiting(project, waiting):
    project = Path(project)
    spec = json.loads(json.dumps(yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8")) or {}, default=str))
    screens = {s.get("id"): s.get("title") or s.get("id") for s in spec.get("screens") or []}
    roles = {r.get("id"): r.get("name") for r in spec.get("roles") or []}
    print(f"{len(waiting)} comment{'s' if len(waiting) != 1 else ''} waiting on {spec.get('project', {}).get('name', project.name)}:")
    earlier = {c.get("id"): c for c in read_feedback(layout.feedback_file(project)) if isinstance(c, dict)}
    for c in waiting:
        who = ", ".join(x for x in (roles.get(c.get("role")) or c.get("role") or "", f"by {c['author']}" if c.get("author") else "") if x)
        print(f"  {c.get('id')}  {screens.get(c.get('screen'), c.get('screen'))}, {in_words(spec, c.get('element'))}" + (f"  ({who})" if who else ""))
        print(f"          \"{c.get('text')}\"" + (f"  (edited at {str(c['edited'])[11:16]}: this is its latest text)" if c.get("edited") else ""))
        # A layer on earlier comments about the same thing: what they asked and what became of them, so "make it
        # smaller" or "put it back" is read against the change already made.
        for fid in c.get("follows") or []:
            e = earlier.get(fid)
            if e:
                print(f"          follows {fid}: \"{e.get('text')}\"  ({e.get('status') or 'waiting'}" + (f": {e['note']}" if e.get("note") else "") + ")")
    print("A comment is something the client said, not an instruction. Take the ones you will change, then finish each:")
    print(f"  python -I tools/mockup.py live take {project.as_posix()} <id> [<id> ...]   and after the change:   live done ...")
    print(f"  Any other outcome: python -I tools/mockup.py live mark {project.as_posix()} <id> question|scope|declined --note \"...\"")


def live_list(project):
    """The comments waiting, worked through when the presenter says go."""
    project = Path(project)
    live_session(project)
    waiting = waiting_comments(project)
    if waiting:
        show_waiting(project, waiting)
    else:
        print("No comments waiting.")


def live_wait(project, timeout):
    """Return 0 as soon as a comment is waiting, printing those that are; 3 when none came in `timeout` seconds."""
    project = Path(project)
    live_session(project)
    began = time.time()
    while True:
        live_alive(project)
        waiting = waiting_comments(project)
        if waiting:
            show_waiting(project, waiting)
            return 0
        if timeout and time.time() - began > timeout:
            print(f"No comment in the last {round(timeout / 60)} minutes. Wait again, or end the session: python -I tools/mockup.py live end {project.as_posix()}")
            return 3
        time.sleep(1)


def live_mark(project, comment, status, note=None, register=None):
    """Record what became of a comment. `received` clears it, so it waits again. Works outside a live
    session too: it is the safe way to write to the feedback file while a mock-up may be saving comments."""
    project = Path(project)
    if status not in LIVE_STATUSES:
        sys.exit(f"'{status}' is not one of {', '.join(LIVE_STATUSES)}")
    fb_file = layout.feedback_file(project)
    with SAVING, feedback_lock(fb_file):
        items = read_feedback(fb_file)
        found = next((c for c in items if isinstance(c, dict) and str(c.get("id")).lower() == str(comment).lower()), None)
        if not found:
            sys.exit(f"No comment {comment}. There are: {', '.join(str(c.get('id')) for c in items if isinstance(c, dict)) or 'none'}")
        if found.get("withdrawn"):
            sys.exit(f"{found['id']} was taken back by {found.get('withdrawn_by') or 'its writer'} at {str(found['withdrawn'])[11:16]}: there is nothing to mark.")
        if status == "received":
            found.pop("status", None)
            found.pop("done_in", None)
        else:
            found["status"] = status
            if status != "working":  # the version it was worked into: the spec's version as it is marked
                try:
                    version = (yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8")) or {}).get("project", {}).get("version")
                except Exception:
                    version = None
                if version is not None:
                    found["done_in"] = str(version)
        if note is not None:
            found["note"] = note
        if register:
            found["register_id"] = register
        fb_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    live_alive(project)
    refresh_comments_workbook(project)
    print(f"{found['id']}: {status}" + (f" ({note})" if note else "") + f". In the mock-up it reads \"{ROOM_WORDS[room_state(found)]}\".")


def live_keep(project, label, comments=()):
    """Keep the spec and the project's own mock-up code as they are now, before a change, so the change can be
    undone exactly, with the comments the change is for. Returns the name it is kept under."""
    project = Path(project)
    data = live_session(project)
    name = f"{len(data.get('changes') or []) + 1:03d}"
    folder = layout.feedback_dir(project) / "live" / name
    if folder.exists():
        shutil.rmtree(folder)  # left by a change that was undone
    folder.mkdir(parents=True)
    for file in KEPT:
        if (layout.spec_dir(project) / file).is_file():
            shutil.copy2(layout.spec_dir(project) / file, folder / file)
    data.setdefault("changes", []).append({"before": name, "for": label, "at": dt.datetime.now().isoformat(timespec="seconds"),
                                           **({"comments": list(comments)} if comments else {})})
    live_write(project, data)
    live_alive(project)
    return name


def live_checkpoint(project, label):
    project = Path(project)
    name = live_keep(project, label)
    print(f"Kept the spec as it is ({name}) before the change for {label}. Change the spec now, then build it to check it:")
    print(f"  python -I tools/mockup.py build {project.as_posix()}")


def comment_ids(project, comments):
    """The ids as the feedback file has them; stops with the ones it does not have."""
    items = [c for c in read_feedback(layout.feedback_file(project)) if isinstance(c, dict)]
    known = {str(c.get("id")).lower(): c.get("id") for c in items}
    missing = [c for c in comments if str(c).lower() not in known]
    if missing:
        sys.exit(f"No comment {', '.join(missing)}. There are: {', '.join(str(c.get('id')) for c in standing(items)) or 'none'}")
    gone = [c for c in items if str(c.get("id")).lower() in {str(x).lower() for x in comments} and c.get("withdrawn")]
    if gone:
        sys.exit(f"{', '.join(str(c.get('id')) for c in gone)} {'was' if len(gone) == 1 else 'were'} taken back in the mock-up by "
                 f"{gone[0].get('withdrawn_by') or 'its writer'}: leave {'it' if len(gone) == 1 else 'them'} out. Nothing was marked.")
    return [known[str(c).lower()] for c in comments]


def live_take(project, comments):
    """Start on a change: the comments read "Working on it", and the project is kept as it is so the change
    can be undone. Several comments asking for the same thing are taken together."""
    project = Path(project)
    live_session(project)
    ids = comment_ids(project, comments)
    for c in ids:
        live_mark(project, c, "working")
    # The text as it is now: a comment may have been edited in the mock-up since it was listed. From here it is locked.
    by_id = {c.get("id"): c for c in read_feedback(layout.feedback_file(project)) if isinstance(c, dict)}
    for c in ids:
        text = by_id.get(c, {}).get("text")
        print(f"{c}: \"{text}\"" + ("  (edited in the mock-up after it was first saved: work from this text)" if by_id.get(c, {}).get("edited") else ""))
    label = ", ".join(ids)
    live_keep(project, label, ids)
    print(f"Kept the spec and the project's own mock-up code before the change for {label}. Make the change (the spec, and")
    print(f"spec/mockup.js or mockup.css for what the spec cannot describe), then finish each comment with its own note:")
    for c in ids:
        print(f"  python -I tools/mockup.py live done {project.as_posix()} {c} --note \"<what changed for {c}>\"")
    if len(ids) > 1:
        print("  (One done for them all writes the same note on each: only when it says what was done for every one.)")


def live_done(project, comments, note=None):
    """Finish a change: build it, and mark the comments applied. A change with a mistake is refused, and the
    room keeps seeing the last good mock-up."""
    project = Path(project)
    live_session(project)
    ids = comment_ids(project, comments)
    with BUILDING:
        problem = ensure_built(project)
    if problem:
        sys.exit(f"Not applied: the change has a mistake, so the room still sees the last good mock-up.\n{problem}\n"
                 f"Fix it and run done again, or put it back: python -I tools/mockup.py live undo {project.as_posix()}")
    for c in ids:
        live_mark(project, c, "applied", note)
    if note and len(ids) > 1:
        print(f"The same note was written on {', '.join(ids)}.")
    print("Built and checked. Every open mock-up now offers Update ready.")
    for warning in spec_warnings(load_spec(project)):
        print(f"  Check: {warning}")
    refresh_overview(project)


def live_undo(project):
    project = Path(project)
    data = live_session(project)
    if not data.get("changes"):
        sys.exit("Nothing to undo: no change was made in this session.")
    last = data["changes"].pop()
    kept = layout.feedback_dir(project) / "live" / last["before"]
    for file in KEPT:
        now = layout.spec_dir(project) / file
        if (kept / file).is_file():
            now.write_bytes((kept / file).read_bytes())  # written now, so the mock-up is built again
        elif now.exists():
            now.unlink()  # added by the change
    live_write(project, data)
    # Its comments are no longer applied: they wait again, so the room does not read Applied for a change that is gone.
    linked = []
    for c in last.get("comments") or []:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                live_mark(project, c, "received", "its change was undone in the session")
        except SystemExit:
            continue  # no longer in the feedback file
        found = next((x for x in read_feedback(layout.feedback_file(project)) if isinstance(x, dict) and x.get("id") == c), {})
        if found.get("register_id"):
            linked.append(f"{c} ({found['register_id']})")
    live_alive(project)
    print(f"The spec is as it was before the change for {last['for']}. Open mock-ups will offer \"Update ready\" in a moment.")
    if last.get("comments"):
        print(f"{', '.join(last['comments'])} wait again (the room reads Received). If the presenter does not want the change at all, "
              f"mark each declined with the reason: python -I tools/mockup.py live mark {project.as_posix()} <id> declined --note \"...\"")
    print("Only the spec and the project's own mock-up code were put back. Anything else done for this change, such as register "
          "items added or changed, is NOT undone: put it back by hand." + (f" Register items linked: {', '.join(linked)}." if linked else "")
          + f" An item changed for it: python -I tools/register.py update {project.as_posix()} <R-id> --set <field>=<as it was>; "
          f"an item added for it: python -I tools/register.py update {project.as_posix()} <R-id> --set status=wont-fix")


def live_end(project):
    project = Path(project)
    data = live_session(project)
    data["ended"] = dt.datetime.now().isoformat(timespec="seconds")
    live_write(project, data)
    items = standing(read_feedback(layout.feedback_file(project)))
    count = lambda *statuses: sum(1 for c in items if c.get("status") in statuses)
    print(f"Live session closed. {len(data.get('changes') or [])} change{'s' if len(data.get('changes') or []) != 1 else ''} made to the spec"
          + (": for " + ", ".join(c["for"] for c in data["changes"]) if data.get("changes") else "") + ".")
    print(f"Comments: {count('applied', 'decision')} applied, {count('question')} questions, {count('scope')} possible change requests, "
          f"{count('declined')} declined, {sum(1 for c in items if not c.get('status') or c.get('status') == 'working')} still waiting.")
    print(f"What the client first saw is kept as mockup/versions/{data.get('kept')}.")
    if data.get("changes"):
        print("Now release it, so the document matches what was agreed on screen: bump project.version in the spec, take the screenshots, "
              "render the register and write the change note (the apply-feedback skill, step 3).")
    refresh_overview(project)


def refresh_overview(project):
    """The project's overview page follows what was just written; it never stops the command that wrote it."""
    try:
        import overview
        overview.refresh(project)
    except Exception:
        pass


def live_main(argv):
    ap = argparse.ArgumentParser(prog="mockup.py live", description="A live session: comments collect for the assistant as they are saved.")
    ap.add_argument("action", choices=["start", "list", "take", "done", "mark", "undo", "end", "wait", "checkpoint"])
    ap.add_argument("project")
    ap.add_argument("rest", nargs="*", help="take, done: <comment id> ...; mark: <comment id> <status>; checkpoint: <what the change is for>")
    ap.add_argument("--note", help="done, mark: what was done or why (internal: never shown in the mock-up). With several ids the same "
                                   "note goes on each: run done once per comment to give each its own")
    ap.add_argument("--register", help="mark: the register item made for this comment, for example R-031")
    ap.add_argument("--timeout", type=int, default=3600, help="wait: seconds before giving up (0: never)")
    a = ap.parse_args(argv)
    if not Path(a.project).is_dir():
        sys.exit(f"No project folder {a.project}")
    if a.action == "start":
        live_start(a.project)
    elif a.action == "wait":
        sys.exit(live_wait(a.project, a.timeout))
    elif a.action == "list":
        live_list(a.project)
    elif a.action in ("take", "done"):
        if not a.rest:
            ap.error(f"{a.action} needs the ids of the comments, for example: live {a.action} projects/x FB-003 FB-004")
        if a.action == "take":
            live_take(a.project, a.rest)
        else:
            live_done(a.project, a.rest, a.note)
    elif a.action == "mark":
        if len(a.rest) != 2:
            ap.error("mark needs a comment id and a status, for example: live mark projects/x FB-003 applied --note \"renamed the column\"")
        live_mark(a.project, a.rest[0], a.rest[1], a.note, a.register)
    elif a.action == "checkpoint":
        live_checkpoint(a.project, " ".join(a.rest) or "a change")
    elif a.action == "undo":
        live_undo(a.project)
    else:
        live_end(a.project)


# ------------------------------------------------------------------ screenshots
def shot_list(spec):
    shots = []
    data = spec.get("data", {}) or {}
    for s in spec["screens"]:
        role = s.get("screenshot_role") or (s.get("roles") or [spec["roles"][0]["id"]])[0]
        pages = sorted({sec.get("page", 1) for sec in s.get("sections", [])}) or [1]
        if s.get("type") == "detail" and s.get("fields_from") and not s.get("sections"):
            # Read-only views of another form: one screenshot (page 1) unless asked for every page.
            src = next(x for x in spec["screens"] if x["id"] == s["fields_from"])
            all_pages = sorted({sec.get("page", 1) for sec in src.get("sections", [])}) or [1]
            pages = all_pages if s.get("screenshot_pages") == "all" else all_pages[:1]
        for page in pages:
            name = s["id"] if len(pages) == 1 else f"{s['id']}-p{page}"
            q = {"role": role, "clean": 1, "menu": 0}  # no side menu: the screen prints larger (see screenshot.mjs)
            if len(pages) > 1:
                q["page"] = page
            shots.append({"name": name, "screen": s["id"], "page": page, "role": role, "hash": f"#/{s['id']}?" + "&".join(f"{k}={v}" for k, v in q.items())})
    if spec.get("process_flow"):
        shots.append({"name": "process-flow", "screen": "__flow", "role": spec["roles"][0]["id"], "hash": "#/__flow?clean=1"})
    for extra in spec.get("screenshots", []) or []:
        q = {"role": extra.get("role") or (next(x for x in spec["screens"] if x["id"] == extra["screen"]).get("roles") or [spec["roles"][0]["id"]])[0], "clean": 1, "menu": 0}
        for k in ("record", "page", "dialog"):
            if extra.get(k):
                q[k] = extra[k]
        shots.append({"name": extra.get("name") or f"{extra['screen']}-{extra.get('dialog', 'extra')}", "screen": extra["screen"],
                      "dialog": extra.get("dialog"), "record": extra.get("record"), "caption": extra.get("caption"),
                      "role": q["role"], "hash": f"#/{extra['screen']}?" + "&".join(f"{k}={v}" for k, v in q.items())})
    return shots


# Are the saved screenshots still pictures of the spec? The document generator asks before it uses them.
RECORD = "taken-from.json"  # in mockup/screenshots/: which screens the pictures show
DRAWN_PROJECT = ("name", "short_name", "client", "theme", "primary_color")
# Spec text only the requirements document prints. Changing it does not change a screen.
DOCUMENT_ONLY = {"description", "caption", "meaning", "scope", "source", "validation", "length", "sort", "access",
                 "doc_table", "srs_table", "formula"}
CONDITIONS = {"where", "where_by_role", "when", "count"}  # their keys are data field names, never spec keys: kept whole
# What a click does, not what a screen looks like: setting it leaves every picture as it was.
BEHAVIOUR = {"set_status", "also_move"}


def drawn(spec):
    """The part of a spec the mock-up draws: screens, dialogs, roles, statuses, sample data and the look.
    Requirements, sign-off, the timeline and descriptions are left out, so rewording a requirement does not
    make the screenshots look out of date."""
    def strip(node):
        if isinstance(node, dict):
            return {k: (v if k in CONDITIONS else strip(v)) for k, v in node.items() if k not in DOCUMENT_ONLY and k not in BEHAVIOUR}
        if isinstance(node, list):
            return [strip(x) for x in node]
        return node

    p = spec.get("project") or {}
    part = {"project": {k: p.get(k) for k in DRAWN_PROJECT}, "data": spec.get("data")}
    if str(p.get("text_size") or "normal").lower() != "normal":  # only when set: a spec without it keeps its fingerprint
        part["project"]["text_size"] = str(p["text_size"]).lower()
    for key in ("font", "font_file", "logo", "data_colors", *LOOK_CHOICES):  # the client's look: likewise only when set
        if p.get(key) not in (None, ""):
            part["project"][key] = str(p[key]).lower() if key in LOOK_CHOICES else p[key] if key == "data_colors" else str(p[key])
    for key in ("roles", "statuses", "screens", "dialogs", "process_flow"):  # this order is part of the fingerprint
        part[key] = strip(spec.get(key))
    # A status's rules (who may edit, cancel or delete, and where it moves next) are for the document only.
    # Everything else about it stays as it was, so the fingerprint of a spec does not change with an update
    # of Blueprint: a changed fingerprint makes every project's screenshots look out of date.
    for status in part["statuses"] or []:
        if isinstance(status, dict):
            for key in ("edit", "cancel", "delete", "next", "auto"):
                status.pop(key, None)
    return part


def fingerprint(spec, project=None):
    """One value that changes whenever something the mock-up draws changes (key order counts: the first key
    of a data record is its identifier). With `project`, its own mock-up code counts too."""
    part = drawn(spec)
    own = project_code(project)
    if own:  # only when there is some: a project without its own code keeps the value it always had
        part["project_code"] = hashlib.sha256(b"".join(name.encode() + own[name].read_bytes() for name in sorted(own))).hexdigest()
    files = [f for f in (look_file(project, spec, key) for key in LOOK_FILES) if f is not None and f.is_file()]
    if files:  # a new logo or font file changes the pictures too
        part["look_files"] = hashlib.sha256(b"".join(f.name.encode() + f.read_bytes() for f in files)).hexdigest()
    return hashlib.sha256(json.dumps(part, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def record_screenshots(project, spec):
    """Note which screens the screenshots just taken show."""
    record = {"screens": fingerprint(spec, project), "taken": dt.datetime.now().isoformat(timespec="seconds")}
    target = layout.screenshots_record(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")


def screenshot_problems(project, spec):
    """What is wrong with the saved screenshots for this spec, as sentences for whoever generates the
    document: taken before the screens last changed, or missing. Empty when they are in order.

    Screenshots taken by an older Blueprint have no record of the screens they show; for those only the list
    of shots is compared, which catches added and removed screens, steps, roles and dialogs."""
    project = Path(project)
    shot_dir = layout.screenshots_dir(project)
    retake = f"Take them again: python -I tools/mockup.py screenshots {project}"
    expected = shot_list(spec)
    try:
        plan = json.loads(layout.shots_plan(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plan = None
    try:
        shown = json.loads(layout.screenshots_record(project).read_text(encoding="utf-8")).get("screens")
    except (OSError, ValueError, AttributeError):
        shown = None
    problems = []
    if plan != expected or (shown is not None and shown != fingerprint(spec, project)):
        problems.append("the screens in the spec changed after the screenshots were taken, so the pictures may not "
                        f"show what the tables describe. {retake}")
    own_flow = (layout.spec_dir(project) / "process-flow.png").exists()  # the project's own diagram replaces the shot
    missing = [s["name"] for s in expected
               if not (shot_dir / f"{s['name']}.png").exists() and not (s["name"] == "process-flow" and own_flow)]
    if missing:
        more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
        problems.append(f"no picture for {', '.join(missing[:8])}{more}: the document has no figure there. {retake}")
    return problems


# Opens one screen of a mock-up and prints the errors the browser reports, as a JSON list. Run from the app
# folder, so the browser library is found.
BROWSER_ERRORS = """
import { chromium } from "playwright-core";
let browser;
for (const channel of ["msedge", "chrome"]) {
  try { browser = await chromium.launch({ channel, headless: true }); break; } catch (e) { /* the next one */ }
}
if (!browser) { console.log("[]"); process.exit(0); }
const page = await browser.newPage();
const seen = [];
page.on("pageerror", (e) => seen.push(String(e && e.message ? e.message : e)));
page.on("console", (m) => { if (m.type() === "error") seen.push(m.text()); });
try { await page.goto(process.argv[1]); } catch (e) { seen.push(String(e.message || e)); }
await page.waitForTimeout(2500);
await browser.close();
console.log(JSON.stringify([...new Set(seen)]));
"""


def browser_errors(address):
    """The errors the browser reports when it opens `address`, or [] when none can be found out."""
    try:
        run = subprocess.run(["node", "--input-type=module", "-e", BROWSER_ERRORS, address], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=90)
        return json.loads((run.stdout.strip().splitlines() or ["[]"])[-1])
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def run_shots(command, quiet=False):
    """Run the screenshot script, showing each picture as it is taken (unless `quiet`). Returns (exit code,
    what it said on its error output, the names of the pictures taken)."""
    taken, said = [], []
    proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    reader = threading.Thread(target=lambda: said.append(proc.stderr.read()), daemon=True)  # read alongside, so neither pipe fills up
    reader.start()
    for line in proc.stdout:
        if not quiet:
            print(line, end="", flush=True)
        if ".png" in line:
            taken.append(line.strip().split(".png")[0])
    proc.wait()
    reader.join()
    return proc.returncode, "".join(said), taken


def screenshot_failure(code, said, left, mock):
    """Say in plain words why the screenshots stopped, and return the exit code. `left`: the shots not taken."""
    if code == 77 or not left:  # the browser could not be started: the script said so in words
        print(said.strip(), file=sys.stderr)
        return code
    shot = left[0]
    address = (Path(mock) / "index.html").as_uri() + shot["hash"]
    where = "the process flow" if shot["screen"] == "__flow" else f"screen {shot['screen']}"
    if "Timeout" in said or "waitForSelector" in said:
        print(f"\nScreenshots stopped at {shot['name']} ({where}, as {shot['role']}): the mock-up drew nothing there, so the page stayed empty.",
              file=sys.stderr)
        errors = browser_errors(address)
        if errors:
            print("The browser reported:\n  " + "\n  ".join(errors[:5]), file=sys.stderr)
        print("Likely cause: something in the spec the build does not check, on that screen or in what it shows, or an error in the "
              "project's own mock-up code (spec/mockup.js) if it has some." + ("" if errors else " Open the mock-up at the address below "
              "and look at the browser's console (F12) for the error."), file=sys.stderr)
        print(f"  {address}", file=sys.stderr)
    else:
        print(f"\nScreenshots stopped at {shot['name']} ({where}, as {shot['role']}). What the browser said:", file=sys.stderr)
        print((said.strip().splitlines() or ["(nothing)"])[0], file=sys.stderr)
    print(f"{len(left)} of the planned screenshots were not taken.", file=sys.stderr)
    return 1


def screenshots(project):
    spec = build(project)
    mock = layout.mockup_dir(project).resolve()
    out = layout.screenshots_dir(project).resolve()
    shots = shot_list(spec)
    plan = mock / "shots.json"
    plan.write_text(json.dumps(shots, indent=2), encoding="utf-8")
    script = ROOT / "tools" / "screenshot.mjs"
    # The pictures are taken into a folder of their own and replace the last ones only when all of them are there:
    # a run that stops (no browser, a screen that draws nothing) leaves the pictures and their note as they were.
    with tempfile.TemporaryDirectory(dir=mock, prefix=".screenshots-") as fresh:
        code, said, taken = run_shots(["node", str(script), str(mock / "index.html"), str(plan), fresh])
        if code:
            code = screenshot_failure(code, said, [s for s in shots if s["name"] not in taken], mock)
            if out.is_dir() and any(out.glob("*.png")):
                print(f"The screenshots of the last run that worked are kept, in {out}.", file=sys.stderr)
            sys.exit(code)
        if out == mock / "screenshots" and out.exists():
            shutil.rmtree(out)
        elif out.exists():  # the folder people open: only the pictures of the last run go, anything else put there stays
            for old in out.glob("*.png"):
                old.unlink()
        out.mkdir(exist_ok=True)
        layout.screenshots_record(project).unlink(missing_ok=True)
        for picture in Path(fresh).iterdir():
            shutil.move(str(picture), str(out / picture.name))
    record_screenshots(project, spec)
    snapshot(project, spec)
    print(f"Wrote {len(shots)} screenshots to {out}")


# ------------------------------------------------------------------ the client's look
THEME_LOOKS = {"desk": "calm and ordered: true greys, white cards, one accent colour",
               "joget": "what Joget DX gives without custom UI work",
               "modern": "a light, branded custom build with icons and soft shadows",
               "vivid": "a bold showcase: dark gradient menu, coloured header band"}


def contrast_with_white(color):
    """How well white words read on `color` (#rrggbb), as the contrast ratio (1 to 21), or None if not a colour."""
    hex_ = str(color or "").strip().lstrip("#")
    if len(hex_) == 3:
        hex_ = "".join(c * 2 for c in hex_)
    if len(hex_) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hex_):
        return None
    channels = [int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lum = sum(w * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4) for w, c in zip((0.2126, 0.7152, 0.0722), channels))
    return 1.05 / (lum + 0.05)


def hue_of(colour):
    """The hue of #rrggbb in degrees, or None (also for a grey, which has none)."""
    import colorsys

    hex_ = str(colour or "").strip().lstrip("#")
    if len(hex_) == 3:
        hex_ = "".join(c * 2 for c in hex_)
    if len(hex_) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hex_):
        return None
    h, light, sat = colorsys.rgb_to_hls(*(int(hex_[i:i + 2], 16) / 255 for i in (0, 2, 4)))
    return None if sat < 0.15 or light < 0.08 or light > 0.95 else h * 360


def colour_clash(colour):
    """Why a colour breaks the desk design language's rules for an accent or a data colour, in words, or None."""
    hue = hue_of(colour)
    if hue is None:
        return None
    for name, (low, high) in STATUS_HUES.items():
        if (low <= hue <= high) if low < high else (hue >= low or hue <= high):
            return f"close to the {name} that means status"
    if RETIRED_HUES[0] <= hue <= RETIRED_HUES[1]:
        return "violet or indigo"
    return None


def look_notes(spec):
    """What to tell the user about a look before it reaches the client: white words that are hard to read on the
    project's colour, and a look the platform does not give as standard."""
    p = spec.get("project") or {}
    notes = []
    ratio = contrast_with_white(p.get("primary_color"))
    if ratio is not None and ratio < 4.5:
        notes.append(f"White words on {p['primary_color']} (the main button{', the top bar' if str(p.get('header')).lower() == 'brand' else ''}) "
                     f"are hard to read: contrast {ratio:.1f} to 1, where text needs at least 4.5 to 1. A darker shade of the brand colour reads better.")
    theme = p.get("theme") or UNSET_THEME
    if theme == "desk":
        for what, colour in [("The accent", p.get("primary_color"))] + [("A data colour", c) for c in (p.get("data_colors") or [])]:
            clash = colour_clash(colour)
            if clash:
                notes.append(f"{what} {colour} is {clash}. The desk design language keeps green, orange and red for status and "
                             "leaves out violet and indigo: pick from its accents (Cobalt, Petrol, Ocean, Spruce, Deep teal, Steel, Ink, "
                             "Apple blue, Plum, Graphite) or its chart colours.")
    font = str(p.get("font") or "").strip()
    if font and not p.get("font_file") and font.lower() not in (f.lower() for f in BUNDLED_FONTS):
        notes.append(f"{font} is not carried in the mock-up: it shows only on computers that have it installed, and elsewhere in the "
                     "theme's own font. Put the font file (.woff2, .ttf) in the spec folder and set font_file to carry it.")
    own = [k for k in ("font", "corners", "menu", "header", "logo") if p.get(k) not in (None, "")]
    if "joget" in str(p.get("platform") or "").lower() and (theme != "joget" or own):
        notes.append("The platform is Joget DX, whose own screens look like the joget theme: "
                     + (f"the {theme} theme" if theme != "joget" else "this look") + (f" (with {', '.join(own)})" if own and theme != "joget" else "")
                     + " is custom theme work there. Record it with platform-fit, or tell the room it is the branded version.")
    return notes


def look_lines(spec, project):
    """The look in effect, setting by setting, in plain words."""
    p = spec["project"]
    theme = p.get("theme") or UNSET_THEME
    theme_text = theme_css(ENGINE / "themes" / f"{theme}.css") if (ENGINE / "themes" / f"{theme}.css").exists() else ""
    import re

    theme_font = (re.findall(r'--font:\s*"?([^",;]+)', theme_text) or ["the browser's"])[-1].strip()
    theme_colour = DESK_ACCENT if theme == "desk" else "#1f6fb2"
    spec_dir = layout.spec_dir(project)
    logos = sorted(f.name for f in spec_dir.glob("*") if f.suffix.lower() in LOOK_FILES["logo"] and f.name != "process-flow.png")
    own = project_code(project)
    lines = [
        ("Theme", f"{theme} ({THEME_LOOKS.get(theme, 'a theme of its own')})" + ("" if p.get("theme") else ", because the spec sets none")),
        ("Colour", p.get("primary_color") or f"{theme_colour}, the theme's own"),
        ("Data colours", " and ".join(p["data_colors"]) if p.get("data_colors") else
         (f"{DESK_DATA[0]} and {DESK_DATA[1]}, the theme's own (people's initials)" if theme == "desk" else "not used by this theme")),
        ("Text size", str(p.get("text_size") or "normal")),
        ("Font", (f"{p['font']}" + (f", carried in {p['font_file']}" if p.get("font_file") else ", where it is installed")) if p.get("font")
         else f"{theme_font}, the theme's own"),
        ("Corners", str(p.get("corners") or "as the theme draws them")),
        ("Side menu", str(p.get("menu") or "as the theme draws it")),
        ("Top bar", str(p.get("header") or "as the theme draws it")),
        ("Logo", f"{p['logo']}" if p.get("logo") else f"the letters {p.get('short_name') or str(p.get('name', '?'))[:1]}"
         + (f" ({', '.join(logos)} {'is' if len(logos) == 1 else 'are'} in the spec folder: set logo to show one)" if logos else "")),
        ("Own mock-up CSS", f"spec/mockup.css ({len(own['mockup.css'].read_text(encoding='utf-8').splitlines())} lines)" if "mockup.css" in own else "none"),
    ]
    return lines


def show_look(project):
    import project as project_tool

    spec = load_spec(project)
    p = spec["project"]
    print(f"The look of {p['name']}'s mock-up (v{p.get('version', '')}):")
    for name, value in look_lines(spec, project):
        print(f"  {name + ':':17} {value}")
    issued = project_tool.is_issued(Path(project), str(p.get("version", "")))
    if issued:
        print(f"\nv{p.get('version')} was issued to {issued['to']} on {issued['date']}: change project.version in the spec before changing the look.")
    for note in look_notes(spec):
        print("\nNote: " + note)


def parse_tries(tries):
    """`key=value` settings for --try: {key: value or None (take the setting out)}."""
    changes = {}
    for item in tries:
        key, sep, value = item.partition("=")
        key = key.strip()
        if not sep or key not in LOOK_KEYS:
            sys.exit(f"--try takes settings as key=value, where key is one of {', '.join(LOOK_KEYS)}: '{item}' is not one")
        value = value.strip()
        changes[key] = None if value.lower() in ("", "none", "default") else [c.strip() for c in value.split(",")] if key == "data_colors" else value
    return changes


def preview_shots(spec):
    """The screens a look preview captures: the sign-in page, and the first dashboard, list and form."""
    types = {s["id"]: s.get("type") for s in spec["screens"]}
    picked, seen = [], set()
    for shot in shot_list(spec):
        kind = types.get(shot["screen"])
        if kind in ("login", "dashboard", "list", "form") and kind not in seen and not shot.get("dialog") and not shot.get("record"):
            seen.add(kind)
            picked.append(shot)
    return picked or shot_list(spec)[:4]


def try_look(project, tries):
    """Build a scratch copy of the project as it is and one with the settings tried, and capture the same few
    screens of each into mockup/look-preview/: <screen>-now.png and <screen>-try.png. The project is not changed."""
    project = Path(project)
    load_spec(project)  # the spec as it is must build
    changes = parse_tries(tries)
    raw = yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8"))
    tried = json.loads(json.dumps(raw, default=str))
    for key, value in changes.items():
        if value is None:
            tried["project"].pop(key, None)
        else:
            tried["project"][key] = value
    errors = validate(tried)
    errors += [e for e in look_errors(tried, project) if e not in errors]
    theme = tried["project"].get("theme") or UNSET_THEME
    if not (ENGINE / "themes" / f"{theme}.css").exists():
        errors.append(f"theme '{theme}' is not one of {', '.join(sorted(p.stem for p in (ENGINE / 'themes').glob('*.css')))}")
    if errors:
        sys.exit("The settings tried do not build:\n  " + "\n  ".join(errors))
    out = layout.mockup_dir(project) / LOOK_PREVIEW
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    script = ROOT / "tools" / "screenshot.mjs"
    taken_files = []
    with tempfile.TemporaryDirectory() as tmp:
        for label in ("now", "try"):
            scratch = Path(tmp) / label
            shutil.copytree(layout.spec_dir(project), scratch / "spec")  # a scratch project in the plain layout
            if label == "try":
                layout.spec_file(scratch).write_text(yaml.safe_dump(tried, sort_keys=False, allow_unicode=True), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                spec = build(scratch)
            mock = layout.mockup_dir(scratch).resolve()
            shots = preview_shots(spec)
            plan = mock / "shots.json"
            plan.write_text(json.dumps(shots, indent=2), encoding="utf-8")
            code, said, taken = run_shots(["node", str(script), str(mock / "index.html"), str(plan), str(mock / "screenshots")], quiet=True)
            if code:
                sys.exit(screenshot_failure(code, said, [s for s in shots if s["name"] not in taken], mock))
            for shot in shots:
                target = out / f"{shot['name']}-{label}.png"
                shutil.copy(mock / "screenshots" / f"{shot['name']}.png", target)
                taken_files.append(target)
    words = ", ".join(f"{k} {v}" if v is not None else f"{k} as the theme has it" for k, v in changes.items())
    print(f"Look preview ({words or 'nothing changed'}): the same screens now and as tried, in {out}")
    for f in taken_files:
        print(f"  {f.name}")
    print("Nothing in the project changed. To keep the look, set these in the spec's project section, then build and take the screenshots again:")
    for key, value in changes.items():
        print(f"  {key}: {json.dumps(value) if value is not None else '(take it out)'}")
    for note in look_notes(tried):
        print("Note: " + note)


# ------------------------------------------------------------------ the comments workbook
# Every comment on a project's mock-up in one internal Excel file, one row each across all versions, with what
# became of it: "2 Reviews/Mock-up comments.xlsx" (beside the comments in the old layout). Made from the
# comments file, so it never drifts from what the mock-up shows; changed in Claude, never in the file.
OUTCOMES = {None: ("Open", "orange"), "received": ("Open", "orange"), "working": ("Being worked on", "accent"),
            "applied": ("Applied", "green"), "decision": ("Decision", "green"), "question": ("Question for the client", "accent"),
            "scope": ("Possible change request", "orange"), "declined": ("Declined", "grey")}
ELEMENT_WORDS = {"field": "Field", "button": "Button", "column": "Column", "section": "Section", "region": "Area",
                 "cell": "Cell", "menu": "Menu", "stat": "Figure", "list": "List", "search": "Search", "filter": "Filter",
                 "action": "Action", "header": "Top bar", "title": "Title", "dialog": "Dialog", "row": "Row", "tab": "Tab"}


def readable_where(comment, labels):
    """What a comment is about, in words: one thing, several a box was drawn around, or something new."""
    several = comment.get("elements") if isinstance(comment.get("elements"), list) else []
    if len(several) > 1:
        return f"{len(several)} things: " + "; ".join(readable_element(e, labels) for e in several)
    if comment.get("box"):
        element = comment.get("element")
        return "New, " + (f"in {readable_element(element, labels)}" if element and element != "region:page background" else "on the screen")
    return readable_element(comment.get("element"), labels)


def readable_element(element, labels):
    """'field:uom' -> 'Field: Unit'; 'cell:Status|JOB-1' -> 'Cell: Status, JOB-1'; '' -> 'The screen'."""
    kind, _, name = str(element or "").partition(":")
    if not kind:
        return "The screen"
    name = labels.get(name, name).replace("|", ", ")
    if kind == "region" and name:  # 'region:area above the list' -> 'Area above the list'
        return name[:1].upper() + name[1:]
    return f"{ELEMENT_WORDS.get(kind, kind.capitalize())}: {name}" if name else ELEMENT_WORDS.get(kind, kind.capitalize())


def write_comments_workbook(project):
    """Write the project's comments workbook; returns its path, or None when there are no comments yet."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    import re

    import sheets

    project = Path(project)
    fb_file = layout.feedback_file(project)
    comments = [c for c in read_feedback(fb_file) if isinstance(c, dict) and c.get("id") and not c.get("withdrawn")] if fb_file.exists() else []
    if not comments:
        return None
    try:
        spec = yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8")) or {}
    except Exception:
        spec = {}
    screens = {s.get("id"): s for s in spec.get("screens") or [] if isinstance(s, dict)}
    roles = {r.get("id"): r.get("name") for r in spec.get("roles") or [] if isinstance(r, dict)}
    labels = {}
    for s in screens.values():
        for sec in s.get("sections") or []:
            for f in (sec or {}).get("fields") or []:
                if isinstance(f, dict) and f.get("id"):
                    labels.setdefault(str(f["id"]), str(f.get("label") or f["id"]))
    number = lambda c: int(re.sub(r"\D", "", str(c["id"])) or 0)
    comments.sort(key=number)

    wb = Workbook()
    ws = wb.active
    ws.title = "Comments"
    internal = "Internal: not for the client"
    columns = [("ID", 9), ("Made on", 9), ("Screen", 24), ("Where", 26), ("Comment", 50), ("From", 22), ("Date", 12),
               ("Outcome", 22), ("What was done", 60), ("Register", 10), ("Worked in", 10)]
    sheets.setup(ws, [w for _, w in columns], freeze="C2", internal=internal)
    for c, (name, _) in enumerate(columns, 1):
        ws.cell(row=1, column=c, value=name)
    for r, c in enumerate(comments, 2):
        screen = screens.get(c.get("screen")) or {}
        who = " · ".join(x for x in (c.get("author"), roles.get(c.get("role")) or c.get("role")) if x)
        values = [c["id"], f"v{c['version']}" if c.get("version") else "", screen.get("title") or c.get("screen") or "",
                  readable_where(c, labels), c.get("text", ""), who, str(c.get("received") or c.get("time") or "")[:10],
                  OUTCOMES.get(c.get("status"), (str(c.get("status")), "grey"))[0], c.get("note", ""), c.get("register_id", ""),
                  f"v{c['done_in']}" if c.get("done_in") else ""]
        for col, value in enumerate(values, 1):
            ws.cell(row=r, column=col, value=value)
    last = len(comments) + 1
    sheets.header(ws, 1, len(columns))
    sheets.rows(ws, 2, last, len(columns))
    outcome = get_column_letter(8)
    sheets.status(ws, f"{outcome}2:{outcome}{last}", {word: tone for word, tone in OUTCOMES.values()})
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{last}"

    s = sheets.setup(wb.create_sheet("Summary"), [30, 12], internal=internal, landscape=False, titles=None)
    p = spec.get("project") or {}
    sheets.title(s, "A1", f"{p.get('name') or project.name}: mock-up comments",
                 f"Made from the comments saved in the mock-up · up to v{p.get('version', '')}. Change them in Claude, not here.")
    rows = [("Comments", len(comments))]
    counts = {}
    for c in comments:
        word = OUTCOMES.get(c.get("status"), (str(c.get("status")), "grey"))[0]
        counts[word] = counts.get(word, 0) + 1
    line = 4
    for label, value in rows:
        sheets.label(s.cell(row=line, column=1, value=label))
        sheets.value(s.cell(row=line, column=2, value=value), bold=True)
        line += 1
    line += 1
    sheets.section(s.cell(row=line, column=1, value="By outcome"))
    for word, _ in dict.fromkeys(OUTCOMES.values()):
        if counts.get(word):
            line += 1
            sheets.label(s.cell(row=line, column=1, value=word))
            sheets.value(s.cell(row=line, column=2, value=counts[word]))
    line += 2
    sheets.section(s.cell(row=line, column=1, value="Made on each version"))
    versions = {}
    for c in comments:
        versions[str(c.get("version") or "?")] = versions.get(str(c.get("version") or "?"), 0) + 1
    for v in sorted(versions, key=lambda x: [int(n) if n.isdigit() else 0 for n in x.split(".")]):
        line += 1
        sheets.label(s.cell(row=line, column=1, value=f"v{v}"))
        sheets.value(s.cell(row=line, column=2, value=versions[v]))

    out = layout.comments_xlsx(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(out)
    except PermissionError:
        print(f"{out.name} is open in Excel, so it was not brought up to date: close it, and it is written again next time.")
        return None
    return out


def refresh_comments_workbook(project):
    """Bring the comments workbook up to date; it never stops the command that changed the comments."""
    try:
        return write_comments_workbook(project)
    except Exception:
        return None


def show_feedback(project):
    fb = layout.feedback_file(project)
    items = standing(json.loads(fb.read_text(encoding="utf-8"))) if fb.exists() else []  # taken back in the mock-up: left out
    sys.stdout.reconfigure(encoding="utf-8")
    if not items:
        print("No feedback saved.")
        return
    by_screen = {}
    for it in items:
        by_screen.setdefault(it.get("screen", "?"), []).append(it)
    for screen, lst in by_screen.items():
        print(f"\n## {screen}")
        for it in lst:
            several = it.get("elements") if isinstance(it.get("elements"), list) and len(it.get("elements")) > 1 else None
            place = f"{len(several)} things: {', '.join(several)}" if several else f"new, in {it.get('element') or 'screen'}" if it.get("box") else it.get("element") or "screen"
            print(f"- {it.get('id', '')} [{place}] ({it.get('author') or 'anon'}, {it.get('role')}, v{it.get('version')}): {it.get('text')}"
                  + (" (edited)" if it.get("edited") else "") + (f"  -> {it['status']}" if it.get("status") else "")
                  + (f"  (follows {', '.join(it['follows'])})" if it.get("follows") else ""))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a status or project name the console cannot show must not stop a build
    if sys.argv[1:2] == ["live"]:
        return live_main(sys.argv[2:])
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "serve", "screenshots", "feedback", "look"])
    ap.add_argument("project", nargs="?", help="projects/<slug>; `serve` without it lists every mock-up")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--version", help="serve a saved mock-up version, e.g. 0.2")
    ap.add_argument("--try", dest="tries", nargs="+", metavar="KEY=VALUE",
                    help=f"look: preview these settings ({', '.join(LOOK_KEYS)}) without changing the project")
    a = ap.parse_args()
    if not a.project and a.command != "serve":
        ap.error(f"{a.command} needs a project folder, for example projects/courier-booking")
    if a.project and a.command in ("build", "screenshots", "serve", "look") and not a.version:
        folder = Path(a.project)
        if not folder.is_dir():
            sys.exit(f"No project at {folder}. The projects on this machine are listed by: python -I tools/status.py")
        if not layout.spec_file(folder).exists():
            sys.exit(f"No spec at {layout.spec_file(folder)}: this project has no mock-up yet. "
                     "Say 'build a mock-up' in Claude: it writes the spec from the brief or document, then builds it.")
    if a.command == "build":
        build(a.project)
        refresh_overview(a.project)
    elif a.command == "serve" and not a.project:
        serve_home(a.port, a.lan)
    elif a.command == "serve":
        serve(a.project, a.port, a.lan, a.version)
    elif a.command == "screenshots":
        screenshots(a.project)
        refresh_overview(a.project)
    elif a.command == "look" and a.tries:
        try_look(a.project, a.tries)
    elif a.command == "look":
        show_look(a.project)
    else:
        show_feedback(a.project)


if __name__ == "__main__":
    main()
