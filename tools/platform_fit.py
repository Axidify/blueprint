"""Check a project against what its technology can actually do, from platform sheets in the knowledge base.

Usage:
    python -I tools/platform_fit.py check  projects/<slug> [--knowledge <folder>]
    python -I tools/platform_fit.py apply  projects/<slug> [--knowledge <folder>]
    python -I tools/platform_fit.py show   "<product>" [--knowledge <folder>]
    python -I tools/platform_fit.py sheet  "<product>" --docs <address> [--project projects/<slug>] [--knowledge <folder>]
    python -I tools/platform_fit.py record "<product>" <PF-id | new> [--feature "..."] [--spec "key, key"]
                                       [--support standard|configuration|custom|"not supported"] [--takes "..."]
                                       [--block BB-07] [--source <address>] [--confirmed "<name> <date>"]

A project's technology is `project.platform` in its spec, and `project.stack` for the other products it uses
(a database, a directory, a cloud service): products with documentation of their own. The client's own
systems (its directory, its document system, an in-house service) are integrations in the spec, not stack
entries, and never get a sheet: a sheet is shared knowledge and is never named after a client. Each product has a sheet, knowledge/platforms/<product>.md, saying
for each feature whether the product does it as standard, by configuration, by custom work or not at all, with
the page of the product's own documentation it was checked against. The `platform-fit` skill looks those pages
up online and keeps the sheets; this tool reads and writes them, and never goes online itself.

check   which features the spec uses and what the sheets say about each: custom work and what is not supported
        first, then features no sheet covers and rows never checked against the documentation, each with what
        to look up. Standard and configuration are counted.
apply   writes the result into the spec as `platform_fit`, replacing what was there: for each feature that is
        not standard, where it is used (`used_in`) and the parts of the mock-up that show it (`elements`). It is
        internal: never in the requirements document. The mock-up only tags those parts "Custom development"
        (or "Not standard on <product>") while presenting, with what it takes; never in screenshots. The rest of
        the spec file is left exactly as it is.
show    a product's sheet, in short.
sheet   starts an empty sheet for a product, with the address of its documentation. With --project, a name
        that contains the client's name (from that project's spec) is refused.
record  adds a row to a product's sheet (`new`) or changes one. --source records the documentation page and
        today's date as the date it was checked; --confirmed records the lead developer who confirmed it.

The sheets are shared by everyone using the workspace: change them only after the user agrees.
"""
import argparse
import datetime as dt
import fnmatch
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402

LEVELS = ("standard", "configuration", "custom", "not supported")
COLUMNS = ("ID", "Feature", "Spec", "Support", "What it takes", "Block", "Source", "Checked", "Confirmed")
KEYS = ("id", "feature", "spec", "support", "takes", "block", "source", "checked", "confirmed")
NONE = "–"
FIT_MARK = "# platform_fit: written by tools/platform_fit.py apply"


# ---------------------------------------------------------------- the knowledge base
def knowledge_dir(override=None):
    if override:
        return Path(override)
    own = ROOT / "knowledge"
    return own if own.exists() else workspace.TEMPLATES / "knowledge"


def words(text):
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def blank(value):
    return str(value or "").strip() in ("", NONE, "-")


def read_sheet(path):
    """A platform sheet: {path, product, documentation, version, confirmed_by, rows: [{id, feature, spec: [...], ...}]}."""
    path = Path(path)
    sheet = {"path": path, "product": path.stem, "documentation": "", "version": "", "confirmed_by": "", "rows": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#\s+Platform:\s*(.+)$", line)
        if m:
            sheet["product"] = m.group(1).strip()
            continue
        for label, key in (("Documentation", "documentation"), ("Version", "version"), ("Confirmed by", "confirmed_by")):
            if line.startswith(f"{label}:"):
                sheet[key] = line.split(":", 1)[1].strip()
        if re.match(r"^\|\s*PF-\d+", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            row = dict(zip(KEYS, cells + [NONE] * (len(KEYS) - len(cells))))
            row["spec"] = [k.strip() for k in row["spec"].split(",") if k.strip()]
            row["support"] = row["support"].lower()
            sheet["rows"].append(row)
    return sheet


def sheets(kdir):
    folder = Path(kdir) / "platforms"
    return [read_sheet(p) for p in sorted(folder.glob("*.md"))] if folder.is_dir() else []


def find_sheet(product, kdir):
    """The sheet for a product: the one whose name's words all appear in the product's ("Joget DX" for
    "JOGET DX 9 Enterprise"), the longest such name first. None when there is none."""
    want = words(product)
    fitting = [s for s in sheets(kdir) if words(s["product"]) and words(s["product"]) <= want]
    return max(fitting, key=lambda s: len(words(s["product"])), default=None)


# ---------------------------------------------------------------- what a spec uses
def stack_of(spec):
    """The products a project is built with: its platform first, then the rest of its stack."""
    project = spec.get("project") or {}
    found = []
    for product in [project.get("platform"), *(project.get("stack") or [])]:
        if product and str(product).strip() and str(product).strip() not in found:
            found.append(str(product).strip())
    if not found:
        found = [str(p) for p in (workspace.company().get("platforms") or [])[:1]]
    return found


def client_system(product, spec):
    """Why a stack entry looks like the client's own system rather than a product, or "" when it does not: it
    names the client (project.client_short or project.client). An entry that only matches an integration is
    not enough: "Active Directory" is both a product and the client's directory."""
    project = spec.get("project") or {}
    text = f" {' '.join(re.findall(r'[a-z0-9]+', str(product).lower()))} "
    for key in ("client_short", "client"):
        name = " ".join(re.findall(r"[a-z0-9]+", str(project.get(key) or "").lower()))
        if name and f" {name} " in text:
            return "it names the client"
    return ""


# A screen for managing users, roles or permissions, told by its list data or, for a screen only an admin
# role can open, by its title, menu label or id.
USER_DATA = re.compile(r"^(users?|roles?|permissions?|(user[ _-]?)?groups?|user[ _-]?(roles?|accounts?|groups?))$", re.I)
USER_WORDS = re.compile(r"\b(users?|roles?|permissions?|user groups?|user accounts?|access rights?)\b", re.I)


def user_management(screen, spec):
    lst = screen.get("list") if isinstance(screen.get("list"), dict) else {}
    if USER_DATA.match(str(lst.get("data") or "").strip()):
        return True
    admins = {str(r.get("id")) for r in spec.get("roles") or []
              if isinstance(r, dict) and "admin" in f"{r.get('id')} {r.get('name')}".lower()}
    roles = [str(r) for r in screen.get("roles") or []]
    named = " ".join(str(screen.get(k) or "") for k in ("title", "menu")) + " " + re.sub(r"[-_]", " ", str(screen.get("id") or ""))
    return bool(roles) and set(roles) <= admins and bool(USER_WORDS.search(named))


def label_of(field):
    """A list filter's label as the mock-up shows it when no column names the field: "leave_type" is "Leave Type"."""
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), str(field).replace("_", " "))


def features(spec, project=None, places=None):
    """Every feature the spec uses, named as the sheets' Spec column names it: {key: [where it is used]}.
    With `places` (a dict), also where each is drawn in the mock-up, filled in as {key: [{screen or dialog,
    element}]}, the element named as the mock-up names it (its data-el), so the mock-up can tag it."""
    found = {}
    places = {} if places is None else places

    def add(key, where, at=None, element=None):
        found.setdefault(key, [])
        if where not in found[key]:
            found[key].append(where)
        if at and element:
            spot = {**at, "element": element}
            places.setdefault(key, [])
            if spot not in places[key]:
                places[key].append(spot)

    def fields(items, where, at):
        for f in items or []:
            if isinstance(f, dict):
                add(f"field:{f.get('type') or 'text'}", where, at, f"field:{f.get('id')}")
                if f.get("options_from"):
                    add("field:lookup", where, at, f"field:{f.get('id')}")

    def listing(lst, where, at):
        if not isinstance(lst, dict):
            return
        add("list", where, at, "region:list")
        columns = {str(c.get("field")): c.get("label") for c in lst.get("columns") or [] if isinstance(c, dict)}
        for f in lst.get("filters") or []:
            add("list:filters", where, at, f"filter:{columns.get(str(f)) or label_of(f)}")
        for f in lst.get("search") or []:
            add("list:search", where, at, f"search:{columns.get(str(f)) or f}")
        if lst.get("sort"):
            add("list:sort", where, at, "region:list")
        actions = [a for a in lst.get("actions") or [] if isinstance(a, dict)]
        for a in actions:
            add("list:row actions", where, at, f"action:{a.get('label')}")
            if a.get("when"):
                add("list:conditional actions", where, at, f"action:{a.get('label')}")
            if a.get("roles"):
                add("list:actions by role", where, at, f"action:{a.get('label')}")
        if lst.get("where_by_role"):
            add("list:filter by role", where, at, "region:list")
        if "waiting_for_me" in (lst.get("where") or {}) or any("waiting_for_me" in (a.get("when") or {}) for a in actions):
            add("list:task inbox", where, at, "region:list")
        for kind, items in (("action", actions), ("button", [b for b in lst.get("toolbar") or [] if isinstance(b, dict)])):
            for a in items:
                if a.get("label") and not a.get("example"):
                    add(f"action:{a['label']}".lower(), where, at, f"{kind}:{a['label']}")

    for s in spec.get("screens") or []:
        if not isinstance(s, dict):
            continue
        where = f"screen {s.get('id')}"
        at = {"screen": str(s.get("id"))}
        heading = None if s.get("type") == "login" else "region:page heading"
        add(f"screen:{s.get('type')}", where, at, heading)
        if user_management(s, spec):
            add("screen:user management", where, at, heading)
        sections = [x for x in s.get("sections") or [] if isinstance(x, dict)]
        if len({x.get("page", 1) for x in sections}) > 1:
            add("form:multi-page", where, at, "region:form steps")
        for section in sections:
            fields(section.get("fields"), where, at)
        listing(s.get("list"), where, at)
        for stat in s.get("stats") or []:
            if isinstance(stat, dict):
                add("stat:count" if stat.get("count") is not None else "stat:formula", where, at, f"stat:{stat.get('label')}")
        for b in s.get("buttons") or []:
            if isinstance(b, dict) and b.get("label") and not b.get("example"):
                add(f"action:{b['label']}".lower(), where, at, f"button:{b['label']}")
        if s.get("timeline"):
            add("approval progress", where, at, "section:Approval Progress")
    for name, rows in (spec.get("data") or {}).items():
        if any(isinstance(r, dict) and r.get("timeline") for r in rows or []):
            add("approval progress", f"data {name}")
            for s in spec.get("screens") or []:  # drawn on the detail screens of that list
                if isinstance(s, dict) and s.get("type") == "detail" and s.get("data") == name:
                    add("approval progress", f"data {name}", {"screen": str(s.get("id"))}, "section:Approval Progress")
    for d in spec.get("dialogs") or []:
        if isinstance(d, dict):
            where = f"dialog {d.get('id')}"
            at = {"dialog": str(d.get("id"))}
            add("dialog", where, at, f"dialog:{d.get('title')}")
            fields(d.get("fields"), where, at)
            listing(d.get("list"), where, at)
            if isinstance(d.get("confirm"), dict) and d["confirm"].get("label"):
                add(f"action:{d['confirm']['label']}".lower(), where, at, f"button:{d['confirm']['label']}")
    if spec.get("statuses"):
        add("workflow", "statuses")
    for r in spec.get("roles") or []:
        if isinstance(r, dict):
            add("role", f"role {r.get('id')}")
            if r.get("scope"):
                add("role:data scope", f"role {r.get('id')}")
    for n in spec.get("notifications") or []:
        if isinstance(n, dict):
            where = f"notification {n.get('event')}"
            add("notification:email", where)
            if "remind" in f"{n.get('event')} {n.get('template')}".lower():
                add("notification:reminder", where)
    for i in spec.get("integrations") or []:
        if isinstance(i, dict) and i.get("system"):
            add(f"integration:{i['system']}".lower(), f"integration {i['system']}")
    project_info = spec.get("project") or {}
    if project_info.get("theme"):
        add("look:theme", "project")
    if str(project_info.get("text_size") or "normal").lower() != "normal":
        add("look:text size", "project")
    if project is not None:
        own = [name for name in ("mockup.js", "mockup.css") if (Path(project) / "spec" / name).is_file()]
        if own:
            add("code:project", " and ".join(f"spec/{name}" for name in own))
    return found


def row_for(key, rows):
    """The first row whose Spec column matches the feature."""
    return next((r for r in rows if any(fnmatch.fnmatchcase(key.lower(), p.lower()) for p in r["spec"])), None)


def checked(row):
    return not blank(row.get("source")) or not blank(row.get("confirmed"))


# ---------------------------------------------------------------- check
def fit(spec, project=None, kdir=None):
    """{stack, sheets: [sheet], missing: [product], own: [(product, why)], items: [{key, used_in, product, row}]}.
    `row` is None for a feature no sheet covers; `own` are stack entries that look like the client's own systems."""
    kdir = knowledge_dir(kdir)
    stack = stack_of(spec)
    found, missing, own = [], [], []
    for product in stack:
        why = client_system(product, spec)
        if why:
            own.append((product, why))
            continue
        sheet = find_sheet(product, kdir)
        if sheet and sheet not in found:
            found.append(sheet)
        elif not sheet:
            missing.append(product)
    items, places = [], {}
    for key, used_in in features(spec, project, places).items():
        match = next(((s, r) for s in found for r in [row_for(key, s["rows"])] if r), (None, None))
        items.append({"key": key, "used_in": used_in, "elements": places.get(key, []),
                      "product": match[0]["product"] if match[0] else None, "row": match[1]})
    return {"stack": stack, "sheets": found, "missing": missing, "own": own, "items": items}


def groups(result):
    """The features grouped by the sheet row that covers them: [{product, row, keys, used_in}], and the
    features no row covers: [{key, used_in}]."""
    found, loose = {}, []
    for i in result["items"]:
        if not i["row"]:
            loose.append({"key": i["key"], "used_in": i["used_in"]})
            continue
        g = found.setdefault((i["product"], i["row"]["id"]), {"product": i["product"], "row": i["row"], "keys": [], "used_in": [], "elements": []})
        g["keys"].append(i["key"])
        g["used_in"] += [w for w in i["used_in"] if w not in g["used_in"]]
        g["elements"] += [e for e in i.get("elements") or [] if e not in g["elements"]]
    order = {level: n for n, level in enumerate(("not supported", "custom", "configuration", "standard"))}
    return sorted(found.values(), key=lambda g: (order.get(g["row"]["support"], 9), g["row"]["id"])), loose


def shown_path(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()


def cmd_check(project, kdir=None):
    import mockup

    project = Path(project)
    spec = mockup.load_spec(project)
    result = fit(spec, project, kdir)
    name = (spec.get("project") or {}).get("name", project.name)
    print(f"Platform check of {name}, built with {', '.join(result['stack']) or 'no platform named'}")
    for sheet in result["sheets"]:
        state = f"confirmed by {sheet['confirmed_by']}" if not blank(sheet["confirmed_by"]) else "not yet confirmed by a lead developer"
        print(f"  Sheet: {shown_path(sheet['path'])} ({sheet['product']}, {state})")
    for product, why in result["own"]:
        print(f"  {product}: looks like the client's own system ({why}), not a product. No sheet for it: describe it "
              "under integrations in the spec and take it out of project.stack. A sheet is never named after a client.")
    for product in result["missing"]:
        print(f"  No sheet for {product}: if it is a product with documentation of its own, find that online and start "
              f"one: python -I tools/platform_fit.py sheet \"{product}\" --docs <address>. If it is the client's own "
              "system, it belongs under integrations in the spec, not in project.stack.")
    grouped, loose = groups(result)
    for level, title in (("not supported", "Not supported"), ("custom", "Custom work")):
        rows = [g for g in grouped if g["row"]["support"] == level]
        if rows:
            print(f"\n{title}: {len(rows)}")
            for g in rows:
                r = g["row"]
                print(f"  {r['id']} {r['feature']}" + (f"   [{r['block']}]" if not blank(r["block"]) else ""))
                print(f"        what it takes: {r['takes']}")
                print(f"        used in: {', '.join(g['used_in'])}")
                print(f"        {'source: ' + r['source'] if not blank(r['source']) else 'not yet checked against the documentation'}")
    if loose:
        print(f"\nNot covered by any sheet: {len(loose)} (look each up in the documentation, then add a row: record \"<product>\" new ...)")
        for i in loose:
            print(f"  {i['key']}   used in: {', '.join(i['used_in'])}")
    unchecked = [g for g in grouped if not checked(g["row"])]
    if unchecked:
        print(f"\nNot yet checked against the documentation: {len(unchecked)} of the {len(grouped)} kinds of feature used here")
        for g in unchecked:
            print(f"  {g['row']['id']} {g['row']['feature']} ({g['row']['support']})")
    docs = [f"{s['product']}: {s['documentation']}" for s in result["sheets"] if not blank(s["documentation"])]
    if (unchecked or loose) and docs:
        print(f"  Look them up in the product's own documentation ({'; '.join(docs)}), with product and feature words only.")
    count = {level: sum(1 for g in grouped if g["row"]["support"] == level) for level in LEVELS}
    print(f"\nKinds of feature used: standard {count['standard']} · configuration {count['configuration']} · custom {count['custom']}"
          f" · not supported {count['not supported']} · not covered {len(loose)}")
    if count["custom"] or count["not supported"]:
        print("Custom work and what is not supported belong in the estimate as their own lines, and in front of the client "
              "where the design could use the standard way instead.")
    return result


# ---------------------------------------------------------------- apply
def fit_record(result):
    """What `apply` writes into the spec: every kind of feature that is not standard, and how many are."""
    grouped, loose = groups(result)
    listed = []
    for g in grouped:
        r = g["row"]
        if r["support"] == "standard":
            continue
        entry = {"what": r["feature"], "support": r["support"], "row": f"{g['product']} {r['id']}", "takes": r["takes"]}
        if not blank(r["block"]):
            entry["block"] = r["block"]
        entry["source"] = r["source"] if not blank(r["source"]) else "not yet checked against the documentation"
        entry.update(features=g["keys"], used_in=g["used_in"])
        if g.get("elements"):  # where the mock-up draws it, so it can tag it as custom work while presenting
            entry["elements"] = g["elements"]
        listed.append(entry)
    for i in loose:
        listed.append({"what": i["key"], "support": "not covered", "used_in": i["used_in"]})
    return {"checked": dt.date.today().isoformat(), "stack": result["stack"],
            "standard": sum(1 for g in grouped if g["row"]["support"] == "standard"), "features": listed}


def replace_fit(text, record):
    """The spec file's text with its platform_fit replaced (or added at the end); every other line as it was."""
    import yaml

    block = (FIT_MARK + ". Internal: never in the requirements document or the mock-up.\n"
             + yaml.safe_dump({"platform_fit": record}, sort_keys=False, allow_unicode=True, width=1000).rstrip("\n"))
    lines = text.split("\n")
    start = next((n for n, line in enumerate(lines) if line.startswith(FIT_MARK) or line.startswith("platform_fit:")), None)
    if start is None:
        return text.rstrip("\n") + "\n\n" + block + "\n"
    n = start
    while n < len(lines) and not lines[n].startswith("platform_fit:"):
        n += 1
    n += 1
    while n < len(lines) and (lines[n].strip() == "" or lines[n].startswith((" ", "\t", "-"))):
        n += 1
    rest = "\n".join(lines[n:])
    head = "\n".join(lines[:start]).rstrip("\n")
    return (head + "\n\n" if head else "") + block + "\n" + ("\n" + rest if rest.strip() else "")


def cmd_apply(project, kdir=None):
    import mockup

    project = Path(project)
    result = cmd_check(project, kdir)
    path = project / "spec" / "app.yaml"
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = replace_fit(raw.replace("\r\n", "\n"), fit_record(result))
    path.write_text(text, encoding="utf-8", newline=newline)
    mockup.load_spec(project)  # stops if the spec no longer reads, which would be a fault of this tool
    listed = len(fit_record(result)["features"])
    print(f"\nWrote platform_fit into {path.as_posix()}: {listed} kind{'s' if listed != 1 else ''} of feature that {'are' if listed != 1 else 'is'} not standard.")


# ---------------------------------------------------------------- the sheets
def writable(kdir, given):
    """The knowledge base to write to. The starter knowledge in the app is never written to by accident."""
    kdir = knowledge_dir(kdir)
    if not given and kdir == workspace.TEMPLATES / "knowledge":
        sys.exit("There is no knowledge base in the workspace yet: run setup first. (The starter knowledge in the app is not changed here.)")
    return kdir


def cell(value):
    return str(value).replace("|", "/").replace("\n", " ").strip() or NONE


def cmd_sheet(product, docs, kdir=None, given=False, project=None):
    if project is not None:
        import mockup

        why = client_system(product, mockup.load_spec(Path(project)))
        if why:
            sys.exit(f"Not started: {product} looks like the client's own system ({why}). The sheets are shared "
                     "knowledge and are never named after a client: describe it under integrations in the spec instead.")
    kdir = writable(kdir, given)
    existing = find_sheet(product, kdir)
    if existing:
        sys.exit(f"{product} already has a sheet: {existing['path']}")
    slug = re.sub(r"[^a-z0-9]+", "-", product.lower()).strip("-")
    path = kdir / "platforms" / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""# Platform: {product}

Documentation: {docs}
Version: (the version and edition your projects are built on)
Confirmed by: {NONE}

What {product} gives as standard, what needs configuration, what needs custom work, and what it does not
support, feature by feature, each checked against the page of its documentation in the Source column. The
columns are explained in the Joget DX sheet's introduction and in docs/knowledge.md.

| {' | '.join(COLUMNS)} |
|{'---|' * len(COLUMNS)}
""", encoding="utf-8")
    print(f"Started {path}. Add its rows with: python -I tools/platform_fit.py record \"{product}\" new --feature ... --spec ... --support ... --source <address>")


def cmd_show(product, kdir=None):
    sheet = find_sheet(product, knowledge_dir(kdir))
    if not sheet:
        sys.exit(f"No sheet for {product}. There are: {', '.join(s['product'] for s in sheets(knowledge_dir(kdir))) or 'none'}")
    print(f"{sheet['product']}: {len(sheet['rows'])} features. Documentation: {sheet['documentation'] or 'not given'}")
    print(f"  {sum(1 for r in sheet['rows'] if not blank(r['source']))} checked against the documentation, "
          f"{sum(1 for r in sheet['rows'] if not blank(r['confirmed']))} confirmed by a lead developer")
    for level in LEVELS:
        rows = [r for r in sheet["rows"] if r["support"] == level]
        if rows:
            print(f"\n{level.capitalize()}:")
            for r in rows:
                print(f"  {r['id']} {r['feature']}  ({', '.join(r['spec'])})" + ("" if checked(r) else "  [not checked]"))


def cmd_record(product, row_id, values, kdir=None, given=False):
    kdir = writable(kdir, given)
    sheet = find_sheet(product, kdir)
    if not sheet:
        sys.exit(f"No sheet for {product}: start one with  python -I tools/platform_fit.py sheet \"{product}\" --docs <address>")
    if values.get("support") and values["support"].lower() not in LEVELS:
        sys.exit(f"Support must be one of {', '.join(LEVELS)}")
    if values.get("source"):
        values["checked"] = dt.date.today().isoformat()
    path = Path(sheet["path"])
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    rows_at = [n for n, line in enumerate(lines) if re.match(r"^\|\s*PF-\d+", line)]
    if str(row_id).lower() == "new":
        missing = [k for k in ("feature", "spec", "support") if not values.get(k)]
        if missing:
            sys.exit(f"A new row needs --{', --'.join(missing)}")
        number = max((int(re.search(r"PF-(\d+)", lines[n]).group(1)) for n in rows_at), default=0) + 1
        row = {k: NONE for k in KEYS} | {"id": f"PF-{number:02d}"} | {k: v for k, v in values.items() if v}
        table_end = rows_at[-1] if rows_at else next(n for n, line in enumerate(lines) if line.startswith("|---"))
        lines.insert(table_end + 1, "| " + " | ".join(cell(row[k]) for k in KEYS) + " |")
        said = f"Added {row['id']} {cell(row['feature'])} to the {sheet['product']} sheet."
    else:
        at = next((n for n in rows_at if re.match(rf"^\|\s*{re.escape(row_id)}\s*\|", lines[n], re.I)), None)
        if at is None:
            sys.exit(f"No row {row_id} in the {sheet['product']} sheet")
        cells = [c.strip() for c in lines[at].strip().strip("|").split("|")]
        row = dict(zip(KEYS, cells + [NONE] * (len(KEYS) - len(cells))))
        row.update({k: v for k, v in values.items() if v})
        lines[at] = "| " + " | ".join(cell(row[k]) for k in KEYS) + " |"
        said = f"Updated {row['id']} {cell(row['feature'])} in the {sheet['product']} sheet."
    path.write_text("\n".join(lines), encoding="utf-8", newline=newline)
    print(said)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["check", "apply", "show", "sheet", "record"])
    ap.add_argument("target", help="projects/<slug> for check and apply; the product's name for the others")
    ap.add_argument("row", nargs="?", help="record: the row's id, or new")
    ap.add_argument("--knowledge", help="the knowledge base folder (default: the workspace's)")
    ap.add_argument("--docs", help="sheet: the address of the product's documentation")
    ap.add_argument("--project", help="sheet: the project the product is for (refuses a name with the client's in it)")
    for name in ("feature", "spec", "support", "takes", "block", "source", "confirmed"):
        ap.add_argument(f"--{name}")
    a = ap.parse_args()
    if a.command in ("check", "apply"):
        if not (Path(a.target) / "spec" / "app.yaml").exists():
            sys.exit(f"No spec at {Path(a.target) / 'spec' / 'app.yaml'}")
        if a.command == "check":
            cmd_check(a.target, a.knowledge)
        else:
            cmd_apply(a.target, a.knowledge)
        return None
    if a.command == "show":
        return cmd_show(a.target, a.knowledge)
    if a.command == "sheet":
        if not a.docs:
            ap.error("sheet needs --docs, the address of the product's documentation")
        return cmd_sheet(a.target, a.docs, a.knowledge, bool(a.knowledge), a.project)
    if not a.row:
        ap.error("record needs a row id, or new")
    values = {k: getattr(a, k) for k in ("feature", "spec", "support", "takes", "block", "source", "confirmed")}
    if values["support"]:
        values["support"] = values["support"].lower()
    return cmd_record(a.target, a.row, values, a.knowledge, bool(a.knowledge))


if __name__ == "__main__":
    main()
