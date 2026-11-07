"""A project's overview page: what is in the folder, whose each file is, and the next step.

Usage:
    python -I tools/overview.py build projects/<slug>
    python -I tools/overview.py build --all

build   writes "Project overview.html" at the top of the project folder: one self-contained page (open it
        with a double-click, from the shared folder too) that lists the project's documents in the order of
        the process, each a link to the real file with a plain line about what it is and who it is for
        (from the client, for the client, internal ...). On top: the next step and the words to say to
        Claude, and four figures (client questions, internal fixes, the mock-up, the requirements
        document). It never shows mandays, rates or cost. Also writes, when the project has a mock-up, the
        "Open the mock-up" shortcuts (.cmd for Windows, .command for a Mac) that start the mock-up through
        Blueprint so comments are saved, and the Word version of each review that has none or an older one
        (and, in the new folder layout, of the mock-up's change notes, in "2 Reviews").
        It works on projects in either folder layout (see tools/layout.py) and links each file where it is.
        --all does it for every active project.

The page is rebuilt by the tools that write into a project (register, workshop, estimate, requirements
document, filing and issuing, a new project, the review's Word file); a failure there never stops them.
"""
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layout  # noqa: E402  (where everything is in a project folder)
import project as project_tool  # noqa: E402
import status  # noqa: E402  (the project's stage and next step: one place decides them)

PAGE = layout.OVERVIEW
SHORTCUT_WINDOWS, SHORTCUT_MAC = layout.SHORTCUTS
EXAMPLES = ROOT / "examples"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
STAMP = re.compile(r'<div class="stamp">.*?</div>', re.S)
DATED = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\s+")
OUTPUT_VERSION = re.compile(r" v(\d+(?:\.\d+)*)\.(docx|pdf)$")


# ---------------------------------------------------------------- small helpers
def esc(text):
    return html.escape(str(text), quote=True)


def short_date(day):
    return f"{day.day} {MONTHS[day.month - 1][:3]} {day.year}"


def long_moment(moment):
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year}, {moment:%H:%M}"


def iso_day(text):
    try:
        return dt.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def file_day(path):
    """The date a file's name starts with ("2026-11-12 client comments.docx"), else when it was last saved."""
    m = DATED.match(path.name)
    if m:
        day = iso_day("-".join(m.groups()))
        if day:
            return day
    return dt.date.fromtimestamp(path.stat().st_mtime)


def readable_dates(text):
    return re.sub(r"\b(\d{4}-\d{2}-\d{2})\b", lambda m: short_date(iso_day(m.group(1))) if iso_day(m.group(1)) else m.group(1), text)


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


def tidy(text):
    """A status line as the page shows it: dates readable, "question(s)" as the number says."""
    text = readable_dates(text or "")
    return re.sub(r"\b(\d+)\b([^\d:;]*?)\(s\)", lambda m: m.group(1) + m.group(2) + ("" if m.group(1) == "1" else "s"), text)


def capital(text):
    if not text or re.match(r"v\d", text):
        return text
    return text[0].upper() + text[1:]


def link(project, path):
    rel = Path(path).relative_to(project).as_posix() + ("/" if Path(path).is_dir() else "")
    return quote(rel, safe="/")


def stem(path):
    """A file's name without the date in front and without its extension."""
    return DATED.sub("", Path(path).stem)


def newest(paths):
    return max(paths, key=lambda f: f.stat().st_mtime) if paths else None


def says(text):
    """Text with the words to say to Claude ('like this') as segments: str, or ("say", words)."""
    out = []
    for i, piece in enumerate(re.split(r"(?<![\w])'([^']+?)'(?![\w])", text)):
        if piece:
            out.append(("say", piece) if i % 2 else piece)
    return out


def quoted(text):
    return re.findall(r"(?<![\w])'([^']+?)'(?![\w])", text or "")


# ---------------------------------------------------------------- what is in the project
def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_spec(project):
    import yaml

    try:
        spec = yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError):
        return {}
    return spec if isinstance(spec, dict) else {}


def review_word(project, review_dir):
    """The review's Word file when it exists, else its review.md."""
    import review_doc

    docx = review_doc.docx_path(project, review_dir)
    return docx if docx.exists() else review_dir / "review.md"


def note_word(project, note):
    """A note's Word file (new layout) when it exists, else the note itself."""
    docx = layout.note_docx(project, note)
    return docx if docx is not None and docx.exists() else note


def reviews_of_generated(name, doc_versions):
    """The document version a review folder is about when it reviews a generated requirements document, else None."""
    m = re.search(r"v(\d+(?:\.\d+)*)", name)
    version = m.group(1) if m else None
    if "generated" in name.lower() or (version in doc_versions and name.lower().startswith(("requirements", "generated"))):
        return version or ""
    return None


def render_reviews(project):
    """The Word file of every review that has none, or an older one than its review.md, and in the new layout of
    every note kept with the reviews (best effort)."""
    import review_doc

    reviews = layout.reviews_dir(project)
    for md in sorted(reviews.glob("*/review.md")) if reviews.exists() else []:
        docx = review_doc.docx_path(project, md.parent)
        try:
            if not docx.exists() or docx.stat().st_mtime < md.stat().st_mtime:
                review_doc.render(project, md.parent)
        except Exception:  # open in Word, or a format mistake: the page links review.md instead
            continue
    for note in layout.review_notes(project):
        docx = layout.note_docx(project, note)
        try:
            if docx is not None and (not docx.exists() or docx.stat().st_mtime < note.stat().st_mtime):
                review_doc.render_note(project, note)
        except Exception:  # the page links the note itself instead
            continue
    # The mock-up's comments as one workbook in 2 Reviews, when the comments changed since it was written. (In
    # the old layout it is written only as comments are marked: a page built there adds nothing to the folder.)
    comments, book = layout.feedback_file(project), layout.comments_xlsx(project)
    if layout.is_new(project) and comments.exists() and (not book.exists() or book.stat().st_mtime < comments.stat().st_mtime):
        import mockup
        mockup.refresh_comments_workbook(project)


def knowledge_dir():
    """The team's knowledge base beside projects/ (as the estimate tool reads it), or the starter one."""
    own = project_tool.knowledge_dir()
    return own if own.exists() else ROOT / "templates" / "knowledge"


def estimate_line(project, path):
    """Whether an estimate prices the build, in words: no figure of it ever reaches the page."""
    try:
        import estimate as estimate_tool

        res, errors = estimate_tool.compute(json.loads(path.read_text(encoding="utf-8")), project, knowledge_dir())
    except Exception:
        return "Internal estimate for the lead developer"
    if errors:
        return "The estimate file has mistakes to fix before it can be read"
    if res["lines"] and len(res["unpriced"]) == len(res["lines"]):
        words = "Nothing is priced yet: a count of the work only"
    elif res["partial"]:
        words = "The build is not priced yet: it needs the lead developer's rates"
    elif res["unpriced"]:
        words = "Priced as a range, apart from a few lines without a rate"
    else:
        words = "Priced as a range, with its assumptions"
    return words + (f", {res['confidence']} confidence" if res.get("confidence") else "")


def doc_state(s):
    """(status class, word) for the newest generated requirements document, or None when there is none."""
    if not s.get("latest_doc"):
        return None
    spec, issued = s.get("spec_version"), s.get("last_issued") or {}
    if issued and str(issued.get("version")) == str(s.get("doc_version")):
        return "done", "Sent to the client"
    if spec and (s.get("doc_version") != spec or s["doc_mtime"] < s.get("spec_mtime", 0)):
        return "late", "Older than the spec"
    if s.get("client_high_open") or not status.doc_reviewed(s):
        return "late", "Not ready to send"
    return "progress", "Ready to send"


def gather(project):
    """Everything the page shows, as plain data."""
    p = Path(project)
    s = status.project_status(p)
    spec = read_spec(p)
    P = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    register = read_json(layout.register_json(p), {})
    register = register if isinstance(register, dict) else {}
    items = [i for i in register.get("items") or [] if isinstance(i, dict)]
    info = {
        "name": str(P.get("name") or register.get("project") or p.name.replace("-", " ").title()),
        "client": str(P.get("client") or register.get("client") or ""),
        "platform": str(P.get("platform") or register.get("platform") or ""),
    }
    feedback = read_json(layout.feedback_file(p), [])
    standing = [c for c in feedback if isinstance(c, dict) and not c.get("withdrawn")] if isinstance(feedback, list) else []
    m = {"project": p, "s": s, "info": info, "items": items, "spec": spec, "P": P,
         "handled": sum(1 for c in standing if c.get("status") and c.get("status") != "working"),
         "waiting": s.get("feedback_unprocessed") or 0,
         "scope": sum(1 for c in standing if c.get("status") == "scope")}
    docs = layout.docs_dir(p)
    m["docs"] = sorted((f for f in docs.glob("*") if f.is_file() and not f.name.startswith(("~$", ".")) and f.suffix.lower() != ".json"),
                       key=lambda f: (file_day(f), f.name)) if docs.exists() else []
    outputs = {}
    out_dir = layout.output_dir(p)
    for f in out_dir.glob("*") if out_dir.exists() else []:
        hit = OUTPUT_VERSION.search(f.name)
        if f.is_file() and hit:
            outputs.setdefault(hit.group(1), {})[hit.group(2)] = f
    m["outputs"] = outputs
    reviews, generated_reviews = [], {}
    reviews_dir = layout.reviews_dir(p)
    for md in sorted(reviews_dir.glob("*/review.md"), key=lambda f: f.stat().st_mtime) if reviews_dir.exists() else []:
        version = reviews_of_generated(md.parent.name, set(outputs))
        if version is None:
            reviews.append(md.parent)
        else:
            generated_reviews.setdefault(version, []).append(md.parent)
    m["reviews"], m["generated_reviews"] = reviews, generated_reviews
    m["notes"] = layout.review_notes(p)
    try:
        m["comments"] = [c for c in json.loads(layout.feedback_file(p).read_text(encoding="utf-8")) if isinstance(c, dict)] if layout.feedback_file(p).exists() else []
    except Exception:
        m["comments"] = []
    m["workshops"] = []
    sources = layout.workshops_source(p)
    for f in sorted(sources.glob("*.json")) if sources.exists() else []:
        agenda = read_json(f, {})
        agenda = agenda if isinstance(agenda, dict) else {}
        m["workshops"].append((f, agenda))
    m["issued"] = [i for i in (read_json(layout.issued_file(p), []) or []) if isinstance(i, dict)]
    shots = layout.screenshots_dir(p)
    m["shots"] = sorted(shots.glob("*.png")) if shots.is_dir() else []
    saved = layout.versions_dir(p)
    natural = lambda v: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", v.name)]
    m["versions"] = sorted((v for v in saved.iterdir() if (v / "index.html").exists()), key=natural) if saved.is_dir() else []
    est_dir = layout.estimates_source(p)
    if est_dir.is_dir():
        import estimate as estimate_tool

        m["estimates"] = sorted(est_dir.glob("*.json"), key=estimate_tool.newest_first_key, reverse=True)
    else:
        m["estimates"] = []
    backlog_dir = layout.backlog_source(p)
    m["backlogs"] = sorted(backlog_dir.glob("*.json"), key=lambda f: (file_day(f), f.name), reverse=True) if backlog_dir.is_dir() else []
    return m


# ---------------------------------------------------------------- the page's parts
def row(icon, name, sub, tag, day, href=None):
    return {"icon": icon, "name": name, "sub": sub, "tag": tag, "day": day, "href": href}


def presented_label(name):
    """A saved version's folder name as people read it: "v0.1-presented-20261106-2052" is "v0.1 as presented on 6 Nov, 20:52"."""
    hit = re.fullmatch(r"(v.+?)-presented-(\d{8})-(\d{4})", name)
    if not hit:
        return name
    try:
        moment = dt.datetime.strptime(hit.group(2) + hit.group(3), "%Y%m%d%H%M")
    except ValueError:
        return name
    return f"{hit.group(1)} as presented on {moment.day} {MONTHS[moment.month - 1][:3]}, {moment:%H:%M}"


def presented_day(versions):
    days = []
    for v in versions:
        hit = re.fullmatch(r"v.+?-presented-(\d{8})-\d{4}", v.name)
        if hit:
            try:
                days.append(dt.datetime.strptime(hit.group(1), "%Y%m%d").date())
            except ValueError:
                pass
    return max(days) if days else None


def stage_documents(m):
    p, rows = m["project"], []
    reviewed = [(review_dir, (review_dir / "review.md").read_text(encoding="utf-8", errors="replace"))
                for review_dir in m["reviews"] + [d for ds in m["generated_reviews"].values() for d in ds]]
    for f in m["docs"]:
        kind = {".pdf": "PDF", ".docx": "Word document", ".doc": "Word document", ".xlsx": "Excel workbook",
                ".xls": "Excel workbook", ".pptx": "Slides", ".txt": "Text", ".md": "Notes", ".eml": "E-mail",
                ".msg": "E-mail"}.get(f.suffix.lower(), f.suffix.lstrip(".").upper() or "File")
        when = next((dt.date.fromtimestamp((d / "review.md").stat().st_mtime) for d, text in reviewed if f.name in text), None)
        sub = [f"{kind}, kept as received" + (f". Reviewed on {short_date(when)}" if when else "")]
        internal = "internal" in f.name.lower()
        rows.append(row("inbox", stem(f), sub, "internal" if internal else "from-client", file_day(f), link(p, f)))
    if rows:
        state = ("done", "Received" if len(rows) == 1 else f"{len(rows)} received")
        return {"step": "1", "title": "Client documents", "state": state, "rows": rows}
    return {"step": "1", "title": "Client documents", "state": None, "rows": [],
            "hint": says("No documents yet: drop the brief or scope of work into the inbox and say 'process my inbox'")}


def stage_review(m):
    p, rows = m["project"], []
    xlsx = layout.register_xlsx(p)
    if xlsx.exists():
        rows.append(row("sheet", "Questions and fixes register",
                        ["For the team: never send it. Type the client's answers into its \"For client\" sheet"],
                        "internal", file_day(xlsx), link(p, xlsx)))
        to_send = layout.client_register_xlsx(p)
        if to_send.exists():
            rows.append(row("sheet", "Questions for the client", ["The client's questions alone: the file to send"],
                            "for-client", file_day(to_send), link(p, to_send)))
    elif m["items"]:
        rows.append(row("sheet", "Questions and fixes register", says("Not made into Excel yet: say 'render the register'"),
                        "internal", file_day(layout.register_json(p))))
    for review_dir in reversed(m["reviews"]):
        import review_doc

        target = review_word(p, review_dir)
        rows.append(row("file", f"Review of {review_doc.readable_name(review_dir.name)}",
                        ["Verdict, top risks and commercial notes" + ("" if target.suffix == ".docx" else ". The Word version is made the next time this page is built")],
                        "internal", file_day(review_dir / "review.md"), link(p, target)))
    for note in m["notes"]:
        if re.match(r"mockup-v.+-changes\.md$", note.name):
            continue  # change notes of the mock-up: under Mock-up
        rows.append(row("file", capital(note.stem.replace("-", " ")), ["Notes from a review"], "internal", file_day(note), link(p, note_word(p, note))))
    found = sum(1 for i in m["items"] if str(i.get("stage", "")).startswith("requirements"))
    if m["reviews"]:
        state = ("done", "Done" + (f" · {plural(found, 'finding')}" if found else ""))
    elif rows:
        state = ("neutral", "No document reviewed yet")
    else:
        return {"step": "2", "title": "Review", "state": None, "rows": [],
                "hint": says("Nothing reviewed yet: for a requirements document, say 'review the requirements document'")}
    return {"step": "2", "title": "Review", "state": state, "rows": rows}


def stage_workshops(m):
    p, rows, today = m["project"], [], dt.date.today()
    upcoming, held = [], []
    for f, agenda in m["workshops"]:
        day = iso_day(agenda.get("date") or f.name) or file_day(f)
        (upcoming if day >= today else held).append(day)
        title = str(agenda.get("workshop") or stem(f))
        short = title.split(":")[0].strip() or title
        questions = sum(len(sec.get("items") or []) for sec in agenda.get("sections") or [] if isinstance(sec, dict))
        minutes = agenda.get("duration_minutes")
        length = ""
        if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0:
            length = f" in {plural(int(minutes // 60), 'hour')}" if minutes % 60 == 0 else f" in {minutes:g} minutes"
        client, notes = layout.workshop_documents(p, f)
        about = plural(questions, "question") + length + (". Send it a few days ahead" if day >= today else "")
        if client.exists():
            rows.append(row("file", f"{short} agenda", [about], "for-client", day, link(p, client)))
        else:
            rows.append(row("file", f"{short} agenda", says("Not written yet: say 'prepare the workshop'"), "for-client", day))
        if notes.exists():
            rows.append(row("file", f"{short} facilitator notes",
                            ["Why each question matters, our recommendation, what was left for later"], "internal", day, link(p, notes)))
    if upcoming:
        state = ("progress", f"Next on {short_date(min(upcoming))[:-5]}")
    elif held:
        state = ("done", f"Last on {short_date(max(held))}")
    else:
        return {"step": "3", "title": "Workshops", "state": None, "rows": [],
                "hint": says("No workshop prepared yet: say 'prepare the workshop' for an agenda of the open questions")}
    return {"step": "3", "title": "Workshops", "state": state, "rows": rows}


def stage_mockup(m):
    p, s, rows = m["project"], m["s"], []
    version = s.get("spec_version")
    if not version and not layout.spec_file(p).exists():
        return {"step": "4", "title": "Mock-up", "state": None, "rows": [],
                "hint": says("No mock-up yet: say 'build a mock-up'")}
    index = layout.mockup_dir(p) / "index.html"
    label = f"Mock-up v{version}" if version else "Mock-up"
    if index.exists():
        rows.append(row("screen", label, ["Opens in the browser to look through. To save comments, double-click "
                                          "“Open the mock-up” in this folder"], "show", file_day(index), link(p, index)))
    else:
        rows.append(row("screen", label, says("Not built yet: say 'build the mock-up'"), "show", None))
    for note in reversed(m["notes"]):
        hit = re.match(r"mockup-(v.+)-changes\.md$", note.name)
        if not hit:
            continue
        sub = ["Changes per screen from the session, and the questions still open"]
        if note == next((n for n in reversed(m["notes"]) if n.name.startswith("mockup-v")), None) and m["scope"]:
            sub += [", ", ("status", "late", plural(m["scope"], "possible change request"))]
        rows.append(row("file", f"What changed in {hit.group(1)}", sub, "internal", file_day(note), link(p, note_word(p, note))))
    book = layout.comments_xlsx(p)
    if book.exists():
        comments = [c for c in m.get("comments") or [] if not c.get("withdrawn")]
        waiting = sum(1 for c in comments if not c.get("status") or c.get("status") == "working")
        sub = [f"Every comment on the mock-up and what became of it, {plural(len(comments), 'comment')}"]
        if waiting:
            sub += [", ", ("status", "late", f"{waiting} not worked in yet")]
        rows.append(row("file", "Mock-up comments", sub, "internal", file_day(book), link(p, book)))
    if m["shots"]:
        folder = layout.screenshots_dir(p)
        rows.append(row("image", "Screenshots", [f"{plural(len(m['shots']), 'screen')}, as used in the requirements document"],
                        "shareable", dt.date.fromtimestamp(newest(m["shots"]).stat().st_mtime), link(p, folder)))
    earlier = [v for v in reversed(m["versions"]) if v.name != f"v{version}"]
    if earlier:
        sub = []
        for n, v in enumerate(earlier):
            sub += ([" · "] if n else []) + [("link", presented_label(v.name), link(p, v / "index.html"))]
        first = re.match(r"v[\d.]+", earlier[-1].name)
        if first:
            sub += [". To present one, say "] + [("say", f"show mock-up {first.group(0)}")]
        rows.append(row("history", "Earlier versions", sub, None, None))
    if m["waiting"]:
        state = ("late", plural(m["waiting"], "comment") + " waiting")
    elif not index.exists():
        state = ("neutral", "Not built yet")
    elif m["handled"]:
        state = ("done", (f"v{version} · " if version else "") + plural(m["handled"], "comment") + " handled")
    else:
        state = ("progress", (f"v{version} · " if version else "") + "ready to show")
    return {"step": "4", "title": "Mock-up", "state": state, "rows": rows}


def stage_document(m):
    p, s, rows = m["project"], m["s"], []
    if not m["outputs"]:
        when = "say 'generate the requirements document'" if s.get("spec_version") else "once the mock-up is agreed, say 'generate the requirements document'"
        return {"step": "5", "title": "Requirements document", "state": None, "rows": [],
                "hint": says(f"No requirements document yet: {when}")}
    issued = {str(i.get("version")): i for i in m["issued"]}
    version = s.get("doc_version") or sorted(m["outputs"], key=lambda v: [int(x) for x in v.split(".")])[-1]
    files = m["outputs"].get(version, {})
    state = doc_state(s) or ("neutral", "Generated")
    title = re.sub(r" v[\d.]+$", "", Path((files.get("pdf") or files.get("docx")).name).stem)
    title = title.split(" – ", 1)[1] if " – " in title else title
    if files.get("pdf"):
        if version in issued:
            sub = [("status", "done", f"Sent to the client on {short_date(iso_day(issued[version].get('date')) or file_day(files['pdf']))}")]
        else:
            if state[1] == "Older than the spec":
                sub = [("status", "late", "Older than the spec: generate it again")]
            elif state[1] == "Not ready to send" and s.get("client_high_open"):
                sub = [("status", "blocked", plural(s["client_high_open"], "decision") + " block sign-off")]
            elif state[1] == "Not ready to send":
                sub = [("status", "late", "Not reviewed yet")]
            else:
                sub = [("status", state[0], state[1])]
            if s.get("internal_open"):
                sub += [f" · {plural(s['internal_open'], 'fix', 'fixes')} for our team still open"]
        rows.append(row("file", f"{title} v{version} (PDF)", sub, "for-client", file_day(files["pdf"]), link(p, files["pdf"])))
    if files.get("docx"):
        name = "The same document in Word" if files.get("pdf") else f"{title} v{version}"
        rows.append(row("file", name, ["Change it through Claude, not in Word: hand edits are lost when it is generated again"],
                        "for-client", file_day(files["docx"]), link(p, files["docx"])))
    for review_dir in reversed(m["generated_reviews"].get(version, []) + m["generated_reviews"].get("", [])):
        target = review_word(p, review_dir)
        rows.append(row("file", f"Review of v{version}", ["What to fix before it goes to the client"], "internal",
                        file_day(review_dir / "review.md"), link(p, target)))
    older = sorted((v for v in m["outputs"] if v != version), key=lambda v: [int(x) for x in v.split(".")], reverse=True)
    if older:
        sub = []
        for n, v in enumerate(older):
            target = m["outputs"][v].get("pdf") or m["outputs"][v].get("docx")
            sub += ([" · "] if n else []) + [("link", f"v{v}", link(p, target))]
            if v in issued:
                sub += [f" sent {short_date(iso_day(issued[v].get('date')) or file_day(target))}"]
        rows.append(row("history", "Earlier versions", sub, None, None))
    word = {"Sent to the client": "sent to the client"}.get(state[1], state[1][0].lower() + state[1][1:])
    return {"step": "5", "title": "Requirements document", "state": (state[0], f"v{version} · {word}"), "rows": rows}


def stage_estimate(m):
    p, s, rows = m["project"], m["s"], []
    for n, f in enumerate(m["estimates"]):
        xlsx = layout.estimate_xlsx(p, f)
        if n == 0:
            sub = [estimate_line(p, f) + ". Never send it to the client"]
        else:
            sub = ["An earlier estimate, kept to see how the range moved"]
        name = capital(stem(f))
        if xlsx.exists():
            rows.append(row("sheet", name, sub, "internal", file_day(xlsx), link(p, xlsx)))
        else:
            rows.append(row("sheet", name, says("Not made into Excel yet: say 'estimate this project'"), "internal", file_day(f)))
    if not rows:
        return {"step": "LD", "title": "Estimate", "state": None, "rows": [],
                "hint": says("No estimate yet: the lead developer says 'estimate this project'")}
    if s.get("spec_mtime") and s.get("estimate_mtime") and s["spec_mtime"] > s["estimate_mtime"]:
        state = ("late", "Older than the spec")
    elif s.get("spec_mtime"):
        state = ("done", "Up to date with the spec")
    else:
        state = ("neutral", "From the brief")
    return {"step": "LD", "title": "Estimate", "state": state, "rows": rows}


def stage_backlog(m):
    """The newest development backlog and the files made from it; nothing at all before there is one."""
    if not m["backlogs"]:
        return None
    p, f = m["project"], m["backlogs"][0]
    data = read_json(f, {})
    stories = [s for s in (data.get("stories") or [] if isinstance(data, dict) else []) if isinstance(s, dict)]
    outs = layout.backlog_outputs(p, f)
    files = [(outs["internal"], "sheet", f"Backlog for the team: {len(stories)} stories, with how their story points were "
              "worked out. Never send it to the client", "internal"),
             (outs["traceability"], "sheet", "Each requirement with its screens, user stories, UAT scenarios "
              "and change requests", "for-client"),
             (outs["project_desk"], "sheet", "Import it in Project Desk: Schedule, Import / export, "
              "Import from file", "internal"),
             (outs["jira"], "sheet", "For Jira's CSV import", "internal"),
             (outs["ado"], "sheet", "For Azure DevOps: Boards, Queries, Import work items", "internal")]
    rows = [row(icon, capital(stem(path)), [sub], tag, file_day(path), link(p, path)) for path, icon, sub, tag in files if path.exists()]
    if not rows:
        rows.append(row("sheet", capital(stem(f)), says("Not made into its files yet: say 'render the backlog'"), "internal", file_day(f)))
    state = ("late", "Older than the spec") if m["s"].get("spec_mtime") and m["s"]["spec_mtime"] > f.stat().st_mtime else ("done", "Up to date with the spec")
    return {"step": "6", "title": "Development backlog", "state": state, "rows": rows}


def focus(m, stages):
    """The one next step: the stage logic of tools/status.py, in the page's words, with one button."""
    s, p = m["s"], m["project"]
    main, hint = (tidy(x) for x in status.next_steps(s))
    head, sep, rest = main.partition(": ")
    if sep:
        heading, body, line = capital(head), says(capital(rest) + "."), []
    else:
        tail = re.search(r"\s*\(([^()]*)\)\s*$", main)
        core = main[:tail.start()] if tail else main
        heading = capital(re.sub(r"\bsay\s+'([^']+)'", r"\1", core).replace("'", ""))
        body = says(capital(tail.group(1)) + ".") if tail else []
        line = [("say", q) for q in quoted(core)]
    also = says(capital(hint)) if hint else []
    button = primary(m, (quoted(main) or [""])[0])
    return {"heading": heading, "body": body, "say": line, "also": also, "button": button, "problems": s.get("problems") or []}


def primary(m, phrase):
    """(label, link) of the document the next step needs most, or None."""
    p, s = m["project"], m["s"]
    agenda = None
    today = dt.date.today()
    for f, data in m["workshops"]:
        day = iso_day(data.get("date") or f.name)
        docx = layout.workshop_documents(p, f)[0]
        if day and day >= today and docx.exists() and (agenda is None or day < agenda[0]):
            agenda = (day, docx)
    mock = layout.mockup_dir(p) / "index.html"
    version = s.get("doc_version")
    files = m["outputs"].get(version, {}) if version else {}
    document = files.get("pdf") or files.get("docx")
    review = review_word(p, m["reviews"][-1]) if m["reviews"] else None
    client_doc = m["docs"][-1] if m["docs"] else None
    xlsx = layout.register_xlsx(p)
    choices = {
        "present the mock-up": [("Open the agenda", agenda[1] if agenda else None), ("Open the mock-up", mock)],
        "apply the feedback": [("Open the mock-up", mock)],
        "prepare the workshop": [("Open the register", xlsx)],
        "build a mock-up": [("Open the review", review), ("Open the brief", client_doc)],
        "review the requirements document": [("Open the document", client_doc)],
        "generate the requirements document": [("Open the requirements document", document), ("Open the mock-up", mock)],
        "review the generated requirements document": [("Open the requirements document", document)],
        "close the project": [("Open the requirements document", document)],
        # after the version went to the client (tools/status.py follows the latest stage)
        "write the UAT scripts": [("Open the requirements document", document)],
        "is this a change request": [("Open the CR log", layout.cr_log_xlsx(p)), ("Open the requirements document", document)],
        "process my inbox": [("Open the requirements document", document)],
    }
    options = choices.get(phrase) or ([("Open the requirements document", document)] if phrase.startswith("record that") else [])
    for label, target in options:
        if target is not None and Path(target).exists():
            return label, link(p, target)
    return None


def figures(m):
    s = m["s"]
    out = []
    if "client_open" in s:
        high = s["client_high_open"]
        out.append((str(s["client_open"]), "Questions for the client",
                    ("blocked", f"{high} block sign-off") if high else (("done", "None block sign-off") if s["client_open"] else ("done", "All answered"))))
        internal = s["internal_open"]
        out.append((str(internal), "Fixes for our team", ("neutral", "Before the document goes out") if internal else ("done", "None open")))
    else:
        out.append(("–", "Questions for the client", ("neutral", "No register yet")))
        out.append(("–", "Fixes for our team", ("neutral", "No register yet")))
    version = s.get("spec_version")
    index = layout.mockup_dir(m["project"]) / "index.html"
    if not version and not index.exists():
        out.append(("–", "Mock-up", ("neutral", "Not built yet")))
    else:
        shown = presented_day(m["versions"])
        if m["waiting"]:
            state = ("late", plural(m["waiting"], "comment") + " waiting")
        elif shown or m["handled"]:
            parts = ([f"Last shown {short_date(shown)[:-5]}"] if shown else []) + ([plural(m["handled"], "comment") + " handled"] if m["handled"] else [])
            state = ("done", " · ".join(parts))
        elif index.exists():
            state = ("progress", "Ready to show")
        else:
            state = ("neutral", "Not built yet")
        out.append((f"v{version}" if version else "–", "Mock-up", state))
    state = doc_state(s)
    out.append((f"v{s['doc_version']}" if state and s.get("doc_version") else "–", "Requirements document", state or ("neutral", "Not generated yet")))
    return out


# ---------------------------------------------------------------- HTML
ICONS = {
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    "sheet": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8M8 17h8M12 13v4"/>',
    "screen": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    "history": '<path d="M 3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M 3 3v5h5M12 7v5l4 2"/>',
    "chev": '<path d="m9 18 6-6-6-6"/>',
    "lock": '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "send": '<path d="M14.5 21.7a.5.5 0 0 0 .9-.1l6.5-19a.5.5 0 0 0-.6-.6l-19 6.5a.5.5 0 0 0-.1.9l7.9 3.2a2 2 0 0 1 1.1 1.1z"/><path d="m21.9 2.1-11 11"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
}
TAGS = {  # who a file is for: (words, icon, css class)
    "from-client": ("From the client", None, ""),
    "for-client": ("For the client", "send", ""),
    "show": ("Show the client", "send", ""),
    "shareable": ("Can be shared", "send", ""),
    "internal": ("Internal", "lock", " internal"),
}
CSS = """
:root { --ground:#F5F5F7; --card:#FFFFFF; --text:#1D1D1F; --secondary:#6E6E73; --separator:#E5E5EA; --line:#D2D2D7;
  --field:#E9E9EE; --accent:#1F5FBF; --accent-text:#1A4C99; --done:#34C759; --done-text:#248A3D; --late:#FF9500;
  --late-text:#C93400; --blocked:#FF3B30; --blocked-text:#D70015; --neutral:#8E8E93;
  --ring:0 0 0 1px rgba(0,0,0,0.05), 0 1px 3px rgba(0,0,0,0.04);
  --t-title:1.75rem; --t-focus:1.375rem; --t-section:1.0625rem; --t-body:0.9375rem; --t-detail:0.8125rem; --t-xs:0.75rem; }
* { box-sizing:border-box; }
html { font-size:16px; }
body { margin:0; background:var(--ground); color:var(--text);
  font:400 var(--t-body)/1.5 Geist, "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  -webkit-font-smoothing:antialiased; }
.page { padding:40px; display:grid; grid-template-columns:repeat(12, minmax(0, 1fr)); gap:24px; }
.span-12 { grid-column:span 12; } .span-3 { grid-column:span 3; }
@media (max-width:900px) { .page { padding:16px; } .span-3 { grid-column:span 6; } }
.head { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; }
h1 { font-size:var(--t-title); font-weight:600; letter-spacing:-0.02em; margin:0 0 4px; line-height:1.2; }
.quiet { color:var(--secondary); } .detail { font-size:var(--t-detail); }
.stamp { text-align:right; color:var(--secondary); font-size:var(--t-detail); }
.card { background:var(--card); border-radius:16px; box-shadow:var(--ring); }
.card-head { display:flex; align-items:center; gap:12px; padding:20px 24px 12px; }
.card-head h2 { font-size:var(--t-section); font-weight:600; letter-spacing:-0.01em; margin:0; }
.step { display:inline-grid; place-items:center; min-width:24px; height:24px; padding:0 4px; border-radius:6px; background:var(--field);
  font-size:var(--t-xs); font-weight:600; color:var(--secondary); }
.card-head .status { margin-left:auto; }
.focus { padding:24px; display:flex; gap:24px; align-items:center; justify-content:space-between;
  box-shadow:var(--ring), inset 4px 0 0 var(--accent); }
.focus .label { font-size:var(--t-detail); color:var(--accent); font-weight:500; }
.focus h2 { font-size:var(--t-focus); font-weight:600; letter-spacing:-0.015em; margin:4px 0 8px; line-height:1.3; }
.focus p { margin:0 0 12px; max-width:70ch; }
.focus .also { margin-top:12px; }
.focus .problem { margin-top:12px; }
.say { display:inline-block; background:var(--field); border-radius:6px; padding:1px 8px; color:var(--text);
  font-family:"Geist Mono", ui-monospace, Consolas, monospace; font-size:var(--t-detail); margin:0 2px; white-space:nowrap; }
.btn-primary { display:inline-flex; align-items:center; gap:8px; height:44px; padding:0 20px; border-radius:9px; background:var(--accent);
  color:#fff; text-decoration:none; font-weight:500; white-space:nowrap; transition:background 120ms cubic-bezier(0.2,0.8,0.2,1); }
.btn-primary:hover { background:#1A51A3; } .btn-primary:active { background:#16458A; }
a:focus-visible { outline:none; box-shadow:0 0 0 3px rgba(31,95,191,0.25); border-radius:9px; }
.figure { padding:20px 24px; height:100%; }
.span-3 > .card { height:100%; }
.figure .v { font-size:var(--t-title); font-weight:600; letter-spacing:-0.02em; line-height:1.1; font-variant-numeric:tabular-nums; }
.figure .l { margin-top:4px; }
.figure .status { margin-top:8px; white-space:normal; align-items:baseline; }
.figure .status::before { flex:none; transform:translateY(-1px); }
.status { display:inline-flex; align-items:center; gap:6px; font-size:var(--t-detail); white-space:nowrap; }
.status::before { content:""; width:8px; height:8px; border-radius:50%; background:var(--neutral); }
.status.done { color:var(--done-text); } .status.done::before { background:var(--done); }
.status.late { color:var(--late-text); } .status.late::before { background:var(--late); }
.status.blocked { color:var(--blocked-text); } .status.blocked::before { background:var(--blocked); }
.status.progress { color:var(--accent); } .status.progress::before { background:var(--accent); }
.status.neutral { color:var(--secondary); }
.rows { padding-bottom:8px; }
.row { display:grid; grid-template-columns:28px minmax(0, 1fr) 150px 110px 20px; gap:12px; align-items:center;
  min-height:56px; padding:8px 24px; text-decoration:none; color:inherit; position:relative; }
.row + .row::before { content:""; position:absolute; top:0; left:64px; right:0; height:1px; background:var(--separator); }
a.row:hover { background:#FAFAFC; } a.row:hover .chev { opacity:1; }
a.row:focus-visible { border-radius:0; box-shadow:inset 0 0 0 3px rgba(31,95,191,0.25); }
.row .icon { color:var(--secondary); display:grid; place-items:center; }
.row .name { display:block; font-weight:500; }
.row .sub { display:block; font-size:var(--t-detail); color:var(--secondary); }
.row .sub a { color:var(--accent); text-decoration:none; } .row .sub a:hover { text-decoration:underline; }
.row .when { font-size:var(--t-detail); color:var(--secondary); font-variant-numeric:tabular-nums; }
.chev { color:var(--secondary); opacity:0; transition:opacity 120ms cubic-bezier(0.2,0.8,0.2,1); }
.tag { justify-self:start; display:inline-flex; align-items:center; gap:6px; background:var(--field); border-radius:6px;
  padding:2px 8px; font-size:var(--t-xs); font-weight:500; white-space:nowrap; }
.tag svg { width:12px; height:12px; }
.tag.internal { color:var(--late-text); }
.hint { padding:0 24px 20px 24px; color:var(--secondary); font-size:var(--t-detail); }
svg { stroke:currentColor; fill:none; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
footer { grid-column:span 12; font-size:var(--t-detail); color:var(--secondary); display:flex; justify-content:space-between; gap:24px; flex-wrap:wrap; }
footer code { font-family:"Geist Mono", ui-monospace, Consolas, monospace; font-size:var(--t-xs); background:var(--field); border-radius:6px; padding:1px 6px; }
@media (max-width:700px) {
  .head, .focus { flex-direction:column; align-items:flex-start; } .stamp { text-align:left; }
  .row { grid-template-columns:28px minmax(0, 1fr); row-gap:4px; }
  .row > .tag, .row > .when { grid-column:2; } .row > .chev, .row > .spacer { display:none; }
}
@media (prefers-reduced-motion:reduce) { * { transition:none !important; } }
"""


def icon(name, size=20):
    return f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def segments(parts):
    out = []
    for part in parts:
        if isinstance(part, str):
            out.append(esc(part))
        elif part[0] == "say":
            out.append(f'<span class="say">{esc(part[1])}</span>')
        elif part[0] == "status":
            out.append(f'<span class="status {esc(part[1])}">{esc(part[2])}</span>')
        elif part[0] == "link":
            out.append(f'<a href="{esc(part[2])}">{esc(part[1])}</a>')
    return "".join(out)


def status_html(state, element="span"):
    return f'<{element} class="status {esc(state[0])}">{esc(state[1])}</{element}>' if state else ""


def row_html(r):
    tag = ""
    if r["tag"]:
        words, mark, cls = TAGS[r["tag"]]
        tag = f'<span class="tag{cls}">{icon(mark, 12) if mark else ""}{esc(words)}</span>'
    inner = (f'<span class="icon">{icon(r["icon"])}</span>'
             f'<span><span class="name">{esc(r["name"])}</span><span class="sub">{segments(r["sub"])}</span></span>'
             f'{tag or "<span></span>"}<span class="when">{esc(short_date(r["day"])) if r["day"] else ""}</span>')
    if r["href"]:
        return f'<a class="row" href="{esc(r["href"])}">{inner}<span class="chev">{icon("chev", 16)}</span></a>'
    return f'<div class="row">{inner}<span class="spacer"></span></div>'


def page(m, stages, moment=None):
    info, f = m["info"], focus(m, stages)
    moment = moment or dt.datetime.now()
    out = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">', '<meta name="generator" content="Blueprint">',
           f"<title>{esc(info['name'])} – Project overview</title>", f"<style>{CSS}</style>", "</head>", "<body>", '<div class="page">']
    line = " · ".join(x for x in (info["client"], info["platform"]) if x)
    out.append(f'<header class="span-12 head"><div><h1>{esc(info["name"])}</h1>'
               + (f'<div class="quiet">{esc(line)}</div>' if line else "")
               + f'</div><div class="stamp">Updated by Blueprint<br>{esc(long_moment(moment))}</div></header>')
    body = [f'<div class="label">Next step</div><h2>{esc(f["heading"])}</h2>']
    if f["body"]:
        body.append(f"<p>{segments(f['body'])}</p>")
    if f["say"]:
        body.append(f'<div><span class="quiet detail">Say to Claude:</span> {segments(f["say"])}</div>')
    if f["also"]:
        body.append(f'<div class="also quiet detail">{segments(f["also"])}</div>')
    for problem in f["problems"]:
        body.append(f'<div class="problem"><span class="status blocked">{esc(capital(problem))}</span></div>')
    button = f'<a class="btn-primary" href="{esc(f["button"][1])}">{esc(f["button"][0])}</a>' if f["button"] else ""
    out.append(f'<section class="card focus span-12"><div>{"".join(body)}</div>{button}</section>')
    for value, label, state in figures(m):
        out.append(f'<div class="span-3"><div class="card figure"><div class="v">{esc(value)}</div>'
                   f'<div class="l quiet detail">{esc(label)}</div>{status_html(state, "div")}</div></div>')
    for st in stages:
        title_attr = ' title="For the lead developer"' if st["step"] == "LD" else ""
        head = (f'<div class="card-head"><span class="step"{title_attr}>{esc(st["step"])}</span><h2>{esc(st["title"])}</h2>'
                f'{status_html(st["state"])}</div>')
        if st["rows"]:
            content = '<div class="rows">' + "".join(row_html(r) for r in st["rows"]) + "</div>"
        else:
            content = f'<div class="hint">{segments(st.get("hint") or [])}</div>'
        out.append(f'<section class="card span-12">{head}{content}</section>')
    if layout.is_new(m["project"]):
        working = (f"Blueprint's working files are in <code>{esc(layout.MACHINE)}</code>: leave them as they are. "
                   f"Files in <i>{esc(layout.INTERNAL)}</i> are never sent to the client.")
    else:
        working = ("Other files here are Blueprint's working files (<code>spec</code>, <code>feedback</code>, "
                   "<code>register.json</code>, the <code>.json</code> beside each document): leave them as they are, "
                   "or ask Claude to \u201cmigrate the folders\u201d to tidy them away.")
    out.append("<footer><span>Blueprint rebuilds this page whenever the project changes. Ask Claude anything about the project "
               f"in your own words.</span><span>{working}</span></footer>")
    out += ["</div>", "</body>", "</html>", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- the "Open the mock-up" shortcuts
WINDOWS_SHORTCUT = r"""@echo off
rem Opens this project's mock-up through Blueprint, so the comments typed in it are saved to this project.
rem Made by Blueprint. It finds Blueprint on this computer in %USERPROFILE%\.blueprint\app-path, which setup writes.
setlocal
chcp 65001 >nul
set "PROJECT=%~dp0"
set "PROJECT=%PROJECT:~0,-1%"
set "APP="
if exist "%USERPROFILE%\.blueprint\app-path" set /p APP=<"%USERPROFILE%\.blueprint\app-path"
if not defined APP goto missing
if not exist "%APP%\present.cmd" goto missing
call "%APP%\present.cmd" "%PROJECT%"
exit /b
:missing
echo.
echo Blueprint is not set up on this computer, so the mock-up cannot be started from here.
echo To set it up: get the Blueprint app folder (ask whoever looks after Blueprint in your team) and
echo double-click setup.cmd in it. Then double-click this file again.
echo.
echo To only look through the mock-up, without saving comments, open the mockup folder here (inside
echo _blueprint in a project in the new folder layout) and double-click index.html.
echo.
pause
exit /b 1
"""

MAC_SHORTCUT = """#!/usr/bin/env bash
# Double-click on a Mac to open this project's mock-up through Blueprint, so the comments typed in it are saved
# to this project. Made by Blueprint. It finds Blueprint on this computer in ~/.blueprint/app-path, which setup writes.
project="$(cd "$(dirname "$0")" && pwd)"
app=""
if [ -f "$HOME/.blueprint/app-path" ]; then app="$(head -n 1 "$HOME/.blueprint/app-path" | tr -d '\\r')"; fi
if [ -n "$app" ] && [ -f "$app/present.sh" ]; then
  bash "$app/present.sh" "$project"
  result=$?
else
  echo
  echo "Blueprint is not set up on this computer, so the mock-up cannot be started from here."
  echo "To set it up: get the Blueprint app folder (ask whoever looks after Blueprint in your team) and"
  echo "double-click setup.command in it. Then double-click this file again."
  echo
  echo "To only look through the mock-up, without saving comments, open the mockup folder here (inside"
  echo "_blueprint in a project in the new folder layout) and double-click index.html."
  result=1
fi
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
exit $result
"""


def write_if_changed(path, text, newline="\n", ignore=None):
    """Write only when the content changed (the page's time stamp aside), so a synced folder is not stirred up."""
    if path.exists():
        try:
            old = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError):
            old = None
        if old is not None:
            same = (ignore.sub("", old) == ignore.sub("", text)) if ignore else old == text
            if same:
                return False
    path.write_text(text, encoding="utf-8", newline=newline)
    return True


def write_shortcuts(project):
    """The two "Open the mock-up" files, for a project that has a mock-up. Same content in every project."""
    if not layout.spec_file(project).exists():
        return []
    win, mac = project / SHORTCUT_WINDOWS, project / SHORTCUT_MAC
    write_if_changed(win, WINDOWS_SHORTCUT, newline="\r\n")
    write_if_changed(mac, MAC_SHORTCUT, newline="\n")
    if sys.platform != "win32":
        try:
            mac.chmod(0o755)
        except OSError:
            pass
    return [win, mac]


# ---------------------------------------------------------------- commands
def build(project, moment=None):
    """Write the overview page (and the shortcuts and review Word files) into a project folder. Returns its path."""
    p = Path(project)
    if not p.is_dir():
        raise FileNotFoundError(f"No project folder {p}")
    render_reviews(p)
    m = gather(p)
    stages = [stage_documents(m), stage_review(m), stage_workshops(m), stage_mockup(m), stage_document(m), stage_estimate(m)]
    stages += [st for st in (stage_backlog(m),) if st]
    out = p / PAGE
    write_if_changed(out, page(m, stages, moment), ignore=STAMP)
    write_shortcuts(p)
    return out


def refresh(project):
    """Rebuild the page after a tool wrote into the project. Never raises: the tool's own work comes first. Quiet
    when it works, one line when it does not. The made-up sample in examples/ is left alone."""
    try:
        p = Path(project).resolve()
        if p == EXAMPLES or EXAMPLES in p.parents or not p.is_dir():
            return None
        return build(p)
    except Exception as e:  # noqa: BLE001  (whatever went wrong, the calling command has done its job)
        try:
            print(f"(The project overview page was not updated: {type(e).__name__}. "
                  f"To see why: python -I tools/overview.py build {Path(project).as_posix()})")
        except Exception:
            pass
        return None


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "build":
        sys.exit(__doc__)
    targets = [project_tool.PROJECTS / slug for slug in project_tool.active_slugs()] if args[1] == "--all" else [Path(args[1])]
    if args[1] == "--all" and not targets:
        print("No projects.")
    for p in targets:
        if not p.is_dir():
            sys.exit(f"No project folder {p}")
        out = build(p)
        extra = " and the Open the mock-up shortcuts" if (p / SHORTCUT_WINDOWS).exists() else ""
        print(f"Wrote {out}{extra}")


if __name__ == "__main__":
    main()
