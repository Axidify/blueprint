"""Build, serve and screenshot a project's clickable mock-up.

Usage:
    python -I tools/mockup.py build        <project_dir>
    python -I tools/mockup.py serve        <project_dir> [--port 8765] [--lan]
    python -I tools/mockup.py screenshots  <project_dir>
    python -I tools/mockup.py feedback     <project_dir>

<project_dir> is projects/<slug> (or examples/<name>). It must contain spec/app.yaml; the format is in
docs/spec-format.md.

build        validates the spec and writes <project_dir>/mockup/ (self-contained: open index.html).
serve        serves the mock-up on http://localhost:<port>; feedback comments are saved to
             <project_dir>/feedback/feedback.json. --lan lets others on the network open it and comment.
             --version 0.2 serves a saved earlier version (every build keeps one in mockup/versions/).
             It stops with a message when the port is already taken (another mock-up is still open):
             close that one, or pick another port with --port.
screenshots  builds, then captures every screen (and extra shots from the spec) with Microsoft Edge into
             <project_dir>/mockup/screenshots/, listed in shots.json. It notes which screens they show, so the
             document generator can warn when the spec's screens have changed since.
feedback     prints the saved comments, grouped by screen.
"""
import argparse
import datetime as dt
import difflib
import hashlib
import http.server
import json
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))  # the sibling tools: `python -I` does not put this folder on the path
ENGINE = ROOT / "tools" / "mockup"
SCREEN_TYPES = {"login", "dashboard", "list", "form", "detail", "custom"}
STATUS_COLORS = ("green", "amber", "red", "grey")  # "gray" is accepted too
FIELD_TYPES = {"text", "textarea", "select", "radio", "checkbox", "date", "datetime", "number", "file", "signature", "user"}
# The keys the spec format knows, by where they are written. A key that is not one of these but nearly spells
# one ("colums") is reported; any other unknown key is left alone, so a team may keep notes of its own.
KNOWN_KEYS = {
    "screen": {"id", "type", "title", "subtitle", "menu", "roles", "description", "caption", "screenshot_role", "screenshot_pages",
               "stats", "list", "buttons", "sections", "data", "record", "fields_from", "timeline", "html"},
    "list": {"data", "where", "columns", "filters", "actions", "toolbar", "search", "sort", "empty"},
    "column": {"field", "label", "chip"},
    "section": {"title", "page", "page_title", "note", "fields"},
    "field": {"id", "label", "type", "required", "readonly", "default", "length", "options", "options_from", "placeholder", "help",
              "source", "validation"},
    "button": {"label", "style", "to", "toast", "dialog", "roles", "when", "example", "access"},
    "dialog": {"id", "title", "message", "fields", "list", "doc_table", "srs_table", "confirm"},
}


# ------------------------------------------------------------------ spec
def load_spec(project):
    path = Path(project) / "spec" / "app.yaml"
    if not path.exists():
        sys.exit(f"No spec at {path}")
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = validate(spec)
    if errors:
        print("Spec errors:\n  " + "\n  ".join(errors))
        sys.exit(1)
    return json.loads(json.dumps(spec, default=str))  # dates -> strings


def validate(spec):
    errors = []
    for key in ("project", "roles", "screens"):
        if not spec.get(key):
            errors.append(f"missing '{key}'")
    if errors:
        return errors
    roles = {r["id"] for r in spec["roles"]}
    screens = {s["id"]: s for s in spec["screens"]}
    dialogs = {d["id"] for d in spec.get("dialogs", [])}
    data = spec.get("data", {}) or {}
    if len(screens) != len(spec["screens"]):
        errors.append("duplicate screen ids")

    def misspelt(where, kind, item):
        """A key that nearly spells a known one is a typo: the mock-up would silently ignore it."""
        for key in item if isinstance(item, dict) else []:
            if key not in KNOWN_KEYS[kind]:
                close = difflib.get_close_matches(str(key), sorted(KNOWN_KEYS[kind]), 1, 0.75)
                if close:
                    errors.append(f"{where}: '{key}' is not a {kind} setting (did you mean '{close[0]}'?)")

    def as_written(value):
        """A field name as the mock-up sees it. YAML reads an unquoted `no` or `yes` as false or true, and in
        the mock-up's data both the record's key and the column's field become the word "false" or "true"."""
        return json.dumps(value) if isinstance(value, bool) else str(value)

    def fields_of(name):
        """Every field name used by the records of a data list (None when the list is empty or missing)."""
        rows_ = data.get(name) or []
        return {as_written(k) for row in rows_ if isinstance(row, dict) for k in row} or None

    def in_data(where, name, what, field):
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
            if source:
                name, _, field = str(source).partition(".")
                if name not in data or not field:
                    errors.append(f"{where}, field {f.get('id', '?')}: options_from '{source}' must be <data list>.<field>, with a list from data")
                else:
                    in_data(f"{where}, field {f.get('id', '?')}", name, "options_from", field)

    def check_list(where, lst):
        misspelt(where, "list", lst)
        name = lst.get("data")
        if name not in data:
            errors.append(f"{where}: list data '{name}' not in data")
            return
        for c in lst.get("columns") or []:
            misspelt(f"{where}, a column", "column", c)
            if c.get("field") is not None:
                in_data(where, name, "column", c["field"])
        for key in ("filters", "search"):
            for field in lst.get(key) or []:
                in_data(where, name, f"{key[:-1] if key == 'filters' else key} field", field)
        for field in lst.get("where") or {}:
            in_data(where, name, "'where'", field)
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

    def check_target(where, item):
        if item.get("to") and item["to"] not in screens:
            errors.append(f"{where}: unknown screen '{item['to']}'")
        if item.get("dialog") and item["dialog"] not in dialogs:
            errors.append(f"{where}: unknown dialog '{item['dialog']}'")
        for r in item.get("roles", []) or []:
            if r not in roles:
                errors.append(f"{where}: unknown role '{r}'")

    for s in spec["screens"]:
        w = f"screen {s['id']}"
        if s.get("type") not in SCREEN_TYPES:
            errors.append(f"{w}: type must be one of {sorted(SCREEN_TYPES)}")
        for r in s.get("roles", []) or []:
            if r not in roles:
                errors.append(f"{w}: unknown role '{r}'")
        misspelt(w, "screen", s)
        if s.get("screenshot_role") and s["screenshot_role"] not in roles:
            errors.append(f"{w}: screenshot_role '{s['screenshot_role']}' is not a role")
        lst = s.get("list")
        if lst:
            check_list(w, lst)
            for stat in s.get("stats") or []:
                if isinstance(stat.get("count"), dict) and lst.get("data") in data:
                    for field in stat["count"]:
                        in_data(f"{w}, figure {stat.get('label', '?')}", lst["data"], "'count'", field)
        for b in s.get("buttons", []) or []:
            misspelt(f"{w}, button {b.get('label', '?')}", "button", b)
            check_target(w, b)
            if s.get("data") in data:
                for field in b.get("when") or {}:
                    in_data(f"{w}, button {b.get('label', '?')}", s["data"], "'when'", field)
        if s.get("type") == "detail" and s.get("data") not in data:
            errors.append(f"{w}: detail data '{s.get('data')}' not in data")
        elif s.get("data") and s["data"] not in data:
            errors.append(f"{w}: data '{s['data']}' not in data")
        elif s.get("data") and s.get("record") is not None:
            has_record(w, s["data"], s["record"])
        for sec in s.get("sections") or []:
            misspelt(f"{w}, section {sec.get('title', '?')}", "section", sec)
            check_fields(w, sec.get("fields"))
        if s.get("fields_from") and s["fields_from"] not in screens:
            errors.append(f"{w}: fields_from '{s['fields_from']}' is not a screen")
        ids = [f["id"] for sec in s.get("sections", []) for f in sec.get("fields", [])]
        if len(ids) != len(set(ids)):
            errors.append(f"{w}: duplicate field ids")
    for st in spec.get("statuses", []) or []:
        if st.get("color") and str(st["color"]).lower() not in STATUS_COLORS + ("gray",):
            errors.append(f"status {st.get('id') or st.get('name')}: color '{st['color']}' must be one of {', '.join(STATUS_COLORS)}")
    for d in spec.get("dialogs", []):
        misspelt(f"dialog {d['id']}", "dialog", d)
        check_fields(f"dialog {d['id']}", d.get("fields"))
        if d.get("list"):
            check_list(f"dialog {d['id']}", d["list"])
        if d.get("confirm"):
            check_target(f"dialog {d['id']}", d["confirm"])
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
    return errors


# ------------------------------------------------------------------ build
INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="assets/base.css"><link rel="stylesheet" href="assets/theme.css">
</head><body><div id="app"></div>
<script src="spec.js"></script><script src="assets/app.js"></script>
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


def build(project):
    spec = load_spec(project)
    out = Path(project) / "mockup"
    (out / "assets").mkdir(parents=True, exist_ok=True)
    theme = spec["project"].get("theme", "joget")
    theme_file = ENGINE / "themes" / f"{theme}.css"
    if not theme_file.exists():
        sys.exit(f"Unknown theme '{theme}'. Available: {[p.stem for p in (ENGINE / 'themes').glob('*.css')]}")
    shutil.copy(ENGINE / "app.js", out / "assets" / "app.js")
    shutil.copy(ENGINE / "base.css", out / "assets" / "base.css")
    (out / "assets" / "theme.css").write_text(theme_css(theme_file), encoding="utf-8")
    (out / "spec.js").write_text("window.SPEC = " + json.dumps(spec, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    p = spec["project"]
    (out / "index.html").write_text(INDEX.format(title=f"{p['name']} – Mock-up v{p.get('version', '')}"), encoding="utf-8")
    snapshot(project, spec)
    print(f"Built {out / 'index.html'} ({len(spec['screens'])} screens, theme {theme})")
    return spec


# ------------------------------------------------------------------ serve
def snapshot(project, spec):
    """Keep a copy of this mock-up version in mockup/versions/v<version>/, so it can be shown again later.
    The copy of a version that was issued to the client is never replaced: it stays what the client saw."""
    import project as project_tool

    out = Path(project) / "mockup"
    version = str(spec["project"].get("version", "draft"))
    dest = out / "versions" / f"v{version}"
    issued = project_tool.is_issued(Path(project), version)
    if issued and dest.exists():
        print(f"v{version} was issued to {issued['to']} on {issued['date']}: the saved mock-up of that version is kept as it was. "
              "What you just built is the working mock-up only; bump project.version in the spec to keep it as a version.")
        return
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(out, dest, ignore=lambda d, names: ["versions"] if Path(d) == out else [])


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


def make_server(mock, fb_file, host, port):
    """The server for the built mock-up in `mock`, saving comments to `fb_file`. Raises OSError when the
    port is taken. Port 0 picks a free one (see server.server_address)."""
    mock, fb_file = Path(mock).resolve(), Path(fb_file).resolve()
    fb_file.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def read():
        return json.loads(fb_file.read_text(encoding="utf-8")) if fb_file.exists() else []

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
                return self._json(read())
            return super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/api/feedback"):
                return self._json({"error": "not found"}, 404)
            try:
                item = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                item = None
            if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                # Answer, so the mock-up can tell the comment was not saved and keep it in the browser.
                return self._json({"error": "a comment is a JSON object with a 'text'"}, 400)
            with lock:
                items = read()
                item["id"] = f"FB-{len(items) + 1:03d}"
                item["received"] = dt.datetime.now().isoformat(timespec="seconds")
                items.append(item)
                fb_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
            try:
                print(f"  feedback {item['id']} on {item.get('screen')} / {item.get('element') or 'screen'}: {item.get('text')}")
            except Exception:  # a console that cannot show the characters must not turn a saved comment into an error
                print(f"  feedback {item['id']} saved")
            return self._json(item)

    return MockupServer((host, port), Handler)


def serve(project, port, lan, version=None):
    if not version:
        build(project)
    mock = (Path(project) / "mockup").resolve()
    if version:
        mock = mock / "versions" / f"v{version.lstrip('v')}"
        if not mock.exists():
            have = sorted(p.name for p in (Path(project) / "mockup" / "versions").glob("v*"))
            sys.exit(f"No mock-up v{version.lstrip('v')}. Available: {', '.join(have) or 'none'}")
        print(f"Showing the saved mock-up {mock.name} (comments are still saved to the project).")
    fb_file = (Path(project) / "feedback" / "feedback.json").resolve()
    try:
        server = make_server(mock, fb_file, "0.0.0.0" if lan else "127.0.0.1", port)
    except OSError as e:
        sys.exit(f"Cannot start the mock-up on port {port}: it is already in use, most likely by another mock-up "
                 f"that is still open.\nClose that window and start again, or use another port by adding "
                 f"--port {port + 1}.\n(The system said: {e})")
    url = f"http://localhost:{port}/"
    print(f"Serving {mock} at {url}{' (also on your network)' if lan else ''}")
    print(f"Feedback is saved to {fb_file}. Press Ctrl+C to stop.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


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
            q = {"role": role, "clean": 1}
            if len(pages) > 1:
                q["page"] = page
            shots.append({"name": name, "screen": s["id"], "page": page, "role": role, "hash": f"#/{s['id']}?" + "&".join(f"{k}={v}" for k, v in q.items())})
    if spec.get("process_flow"):
        shots.append({"name": "process-flow", "screen": "__flow", "role": spec["roles"][0]["id"], "hash": "#/__flow?clean=1"})
    for extra in spec.get("screenshots", []) or []:
        q = {"role": extra.get("role") or (next(x for x in spec["screens"] if x["id"] == extra["screen"]).get("roles") or [spec["roles"][0]["id"]])[0], "clean": 1}
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
                 "doc_table", "srs_table"}
CONDITIONS = {"where", "when", "count"}  # their keys are data field names, never spec keys: kept whole


def drawn(spec):
    """The part of a spec the mock-up draws: screens, dialogs, roles, statuses, sample data and the look.
    Requirements, sign-off, the timeline and descriptions are left out, so rewording a requirement does not
    make the screenshots look out of date."""
    def strip(node):
        if isinstance(node, dict):
            return {k: (v if k in CONDITIONS else strip(v)) for k, v in node.items() if k not in DOCUMENT_ONLY}
        if isinstance(node, list):
            return [strip(x) for x in node]
        return node

    p = spec.get("project") or {}
    part = {"project": {k: p.get(k) for k in DRAWN_PROJECT}, "data": spec.get("data")}
    for key in ("roles", "statuses", "screens", "dialogs", "process_flow"):  # this order is part of the fingerprint
        part[key] = strip(spec.get(key))
    # A status's rules (who may edit, cancel or delete, and where it moves next) are for the document only.
    # Everything else about it stays as it was, so the fingerprint of a spec does not change with an update
    # of Blueprint: a changed fingerprint makes every project's screenshots look out of date.
    for status in part["statuses"] or []:
        if isinstance(status, dict):
            for key in ("edit", "cancel", "delete", "next"):
                status.pop(key, None)
    return part


def fingerprint(spec):
    """One value that changes whenever something the mock-up draws changes (key order counts: the first key
    of a data record is its identifier)."""
    return hashlib.sha256(json.dumps(drawn(spec), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def record_screenshots(project, spec):
    """Note which screens the screenshots just taken show."""
    record = {"screens": fingerprint(spec), "taken": dt.datetime.now().isoformat(timespec="seconds")}
    (Path(project) / "mockup" / "screenshots" / RECORD).write_text(json.dumps(record, indent=2), encoding="utf-8")


def screenshot_problems(project, spec):
    """What is wrong with the saved screenshots for this spec, as sentences for whoever generates the
    document: taken before the screens last changed, or missing. Empty when they are in order.

    Screenshots taken by an older Blueprint have no record of the screens they show; for those only the list
    of shots is compared, which catches added and removed screens, steps, roles and dialogs."""
    project = Path(project)
    shot_dir = project / "mockup" / "screenshots"
    retake = f"Take them again: python -I tools/mockup.py screenshots {project}"
    expected = shot_list(spec)
    try:
        plan = json.loads((project / "mockup" / "shots.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        plan = None
    try:
        shown = json.loads((shot_dir / RECORD).read_text(encoding="utf-8")).get("screens")
    except (OSError, ValueError, AttributeError):
        shown = None
    problems = []
    if plan != expected or (shown is not None and shown != fingerprint(spec)):
        problems.append("the screens in the spec changed after the screenshots were taken, so the pictures may not "
                        f"show what the tables describe. {retake}")
    own_flow = (project / "spec" / "process-flow.png").exists()  # the project's own diagram replaces the shot
    missing = [s["name"] for s in expected
               if not (shot_dir / f"{s['name']}.png").exists() and not (s["name"] == "process-flow" and own_flow)]
    if missing:
        more = f" and {len(missing) - 8} more" if len(missing) > 8 else ""
        problems.append(f"no picture for {', '.join(missing[:8])}{more}: the document has no figure there. {retake}")
    return problems


def screenshots(project):
    spec = build(project)
    mock = (Path(project) / "mockup").resolve()
    out = mock / "screenshots"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    shots = shot_list(spec)
    plan = mock / "shots.json"
    plan.write_text(json.dumps(shots, indent=2), encoding="utf-8")
    script = ROOT / "tools" / "screenshot.mjs"
    result = subprocess.run(["node", str(script), str(mock / "index.html"), str(plan), str(out)], cwd=ROOT)
    if result.returncode:
        sys.exit(result.returncode)  # the script has said why (77: Microsoft Edge could not be started)
    record_screenshots(project, spec)
    snapshot(project, spec)
    print(f"Wrote {len(shots)} screenshots to {out}")


def show_feedback(project):
    fb = Path(project) / "feedback" / "feedback.json"
    items = json.loads(fb.read_text(encoding="utf-8")) if fb.exists() else []
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
            print(f"- {it.get('id', '')} [{it.get('element') or 'screen'}] ({it.get('author') or 'anon'}, {it.get('role')}, v{it.get('version')}): {it.get('text')}"
                  + (f"  -> {it['status']}" if it.get("status") else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["build", "serve", "screenshots", "feedback"])
    ap.add_argument("project")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--version", help="serve a saved mock-up version, e.g. 0.2")
    a = ap.parse_args()
    if a.command == "build":
        build(a.project)
    elif a.command == "serve":
        serve(a.project, a.port, a.lan, a.version)
    elif a.command == "screenshots":
        screenshots(a.project)
    else:
        show_feedback(a.project)


if __name__ == "__main__":
    main()
