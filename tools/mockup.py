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
screenshots  builds, then captures every screen (and extra shots from the spec) with Microsoft Edge into
             <project_dir>/mockup/screenshots/, listed in shots.json.
feedback     prints the saved comments, grouped by screen.
"""
import argparse
import datetime as dt
import http.server
import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "tools" / "mockup"
SCREEN_TYPES = {"login", "dashboard", "list", "form", "detail", "custom"}


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
        lst = s.get("list")
        if lst:
            if lst.get("data") not in data:
                errors.append(f"{w}: list data '{lst.get('data')}' not in data")
            for a in lst.get("actions", []) + lst.get("toolbar", []):
                check_target(w, a)
        for b in s.get("buttons", []) or []:
            check_target(w, b)
        if s.get("type") == "detail" and s.get("data") not in data:
            errors.append(f"{w}: detail data '{s.get('data')}' not in data")
        if s.get("fields_from") and s["fields_from"] not in screens:
            errors.append(f"{w}: fields_from '{s['fields_from']}' is not a screen")
        ids = [f["id"] for sec in s.get("sections", []) for f in sec.get("fields", [])]
        if len(ids) != len(set(ids)):
            errors.append(f"{w}: duplicate field ids")
    for d in spec.get("dialogs", []):
        if d.get("confirm"):
            check_target(f"dialog {d['id']}", d["confirm"])
    for shot in spec.get("screenshots", []) or []:
        if shot.get("screen") not in screens:
            errors.append(f"screenshot {shot}: unknown screen")
        check_target(f"screenshot {shot.get('name')}", shot)
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
    shutil.copy(theme_file, out / "assets" / "theme.css")
    (out / "spec.js").write_text("window.SPEC = " + json.dumps(spec, indent=1, ensure_ascii=False) + ";\n", encoding="utf-8")
    p = spec["project"]
    (out / "index.html").write_text(INDEX.format(title=f"{p['name']} – Mock-up v{p.get('version', '')}"), encoding="utf-8")
    print(f"Built {out / 'index.html'} ({len(spec['screens'])} screens, theme {theme})")
    return spec


# ------------------------------------------------------------------ serve
def serve(project, port, lan):
    build(project)
    mock = (Path(project) / "mockup").resolve()
    fb_file = (Path(project) / "feedback" / "feedback.json").resolve()
    fb_file.parent.mkdir(exist_ok=True)
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
            item = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            with lock:
                items = read()
                item["id"] = f"FB-{len(items) + 1:03d}"
                item["received"] = dt.datetime.now().isoformat(timespec="seconds")
                items.append(item)
                fb_file.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  feedback {item['id']} on {item.get('screen')} / {item.get('element') or 'screen'}: {item.get('text')}")
            return self._json(item)

    host = "0.0.0.0" if lan else "127.0.0.1"
    server = http.server.ThreadingHTTPServer((host, port), Handler)
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
        sys.exit(result.returncode)
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
    a = ap.parse_args()
    if a.command == "build":
        build(a.project)
    elif a.command == "serve":
        serve(a.project, a.port, a.lan)
    elif a.command == "screenshots":
        screenshots(a.project)
    else:
        show_feedback(a.project)


if __name__ == "__main__":
    main()
