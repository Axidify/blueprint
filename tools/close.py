"""Close a delivered project: draft the knowledge-base changes from the project's own records, for the user
to confirm. Nothing is written to the shared knowledge base until `apply`, and then only what is named.

Usage:
    python -I tools/close.py check projects/<slug> [--actuals <actuals.json>]
    python -I tools/close.py draft projects/<slug> [--actuals <actuals.json>]
    python -I tools/close.py apply projects/<slug> [--only actuals|log] [--force]

check   holds every change request against the version the client signed: the CR log (crs.json) and the
        list the lead developer gives with the actuals. A CR with verdict In scope, or one whose text reads
        closely like a requirement, screen, rule or decision of the signed version, is flagged: it is not a
        change request, and the knowledge base must not learn it as one. The match counts shared words: it is
        a lead, read the cited text before deciding.
draft   writes, into the project's _blueprint/close/ (close/ in the old folder layout):
          "actuals draft.md"         the record for knowledge/actuals/<slug>.md
          "knowledge proposal.md"    the projects-log row, gap-pattern evidence, building-block notes and the
                                     CR check, to show the user
          close.json                 what apply writes, and the check's flags
        from the project's spec, the issued version, the CR log, the register, the latest estimate and the
        actuals file. Figures that are not given stay "not given": nothing is guessed.
apply   after the user agreed: copies the actuals draft (as edited since) to knowledge/actuals/<slug>.md and
        adds or replaces the project's row in knowledge/projects-log.md. --only picks one. An actuals record
        that exists is kept unless --force. Gap patterns and building blocks are not written by the tool:
        they are edited by hand, in general terms, after the user agreed.

The actuals file (default _blueprint/close/actuals.json), written from the lead developer's figures:
{
  "phase": "Phase 1",
  "team": "1 developer, 50% tester",
  "delivered": "2027-03",
  "test": false,                       true for test data: every draft says TEST DATA, and the projects-log row
                                       is marked TEST so estimates never count it as a delivered project
  "source": "2027-03-31 actuals from the lead developer.txt",
  "sold_md": 45,                       development sold in the scope of work; leave out when not given
  "crs_billed_md": 7,                  optional: else the sold_md of the CR log's billed CRs
  "actual": [ {"area": "Forms and workflow", "md": 40},
              {"area": "UAT support", "md": 6, "kind": "testing"} ],     development unless kind is testing
  "crs": [ {"title": "Export all records", "md": 5, "cr": "CR-001", "gap_pattern": "GP-04"} ],
                                       what the lead developer lists as change requests: md is the effort
                                       spent; cr links it to the CR log; verdict (in-scope | ambiguous | new)
                                       once decided
  "deferred": ["Dealer sign-in, to phase 2"],
  "lessons": ["Offline sync was the largest single area and has no building block"]
}

Rates, cost and prices stay internal: the drafts are for the knowledge base, never for the client.
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import change_request as crtool  # noqa: E402  (the signed version and the scope check)
import estimate  # noqa: E402  (the knowledge base, the estimate's totals, test rows)
import layout  # noqa: E402
import register  # noqa: E402  (the similarity measure)
import workspace  # noqa: E402  (the day rate)

DRAFT = "actuals draft.md"
PROPOSAL = "knowledge proposal.md"
RECORD = "close.json"
LOG_HEAD = ["Project", "Platform", "Phase", "Team", "Dev estimate (MD)", "CRs billed (MD)", "Dev actual (MD)",
            "Variance vs billed", "CRs", "Notes"]
BILLED = ("quoted", "approved", "built")
NOT_GIVEN = "not given"


def close_dir(project):
    return layout.machine(project) / "close"


def num(x):
    return estimate.num(float(x))


def read_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError:
        return None
    except ValueError as e:
        sys.exit(f"{what} ({Path(path).name}) is not valid JSON: {e}")


def figure(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------- what the project holds
def gather(project, actuals_file=None, kdir=None):
    p = Path(project)
    spec = crtool.read_yaml(layout.spec_file(p)) if layout.spec_file(p).exists() else {}
    P = spec.get("project") or {}
    path = Path(actuals_file) if actuals_file else close_dir(p) / "actuals.json"
    actuals = read_json(path, "The actuals file") if path.exists() else None
    if actuals_file and actuals is None:
        sys.exit(f"No actuals file at {path}.")
    log = crtool.load_log(p) if layout.cr_log(p).exists() else {"crs": []}
    issues = crtool.project_tool.load_issues(p)
    est = None
    found = sorted(layout.estimates_source(p).glob("*.json"), key=estimate.newest_first_key) if layout.estimates_source(p).exists() else []
    if found:
        data = read_json(found[-1], "The estimate")
        if isinstance(data, dict):
            res, errors = estimate.compute(data, p, kdir or estimate.knowledge_dir())
            est = {"file": found[-1].name, "data": data, "res": None if errors else res}
    return {"slug": p.name, "project": p, "name": P.get("name") or log.get("project") or p.name,
            "client": P.get("client") or "", "platform": log.get("platform") or P.get("platform") or "",
            "spec_version": str(P.get("version") or ""), "issues": issues, "log": log,
            "actuals": actuals if isinstance(actuals, dict) else {}, "actuals_file": path if actuals else None, "estimate": est}


# ---------------------------------------------------------------- the CR check
def link(item, crs):
    """The CR log entry a CR of the lead developer's list is: by its cr id, or a title alike enough."""
    if item.get("cr"):
        return next((c for c in crs if c.get("id") == item["cr"]), None)
    words = register.words(item.get("title", ""))
    best = max(((register.dice(words, register.words(f"{c.get('title', '')}")), c) for c in crs), key=lambda x: x[0], default=(0, None))
    return best[1] if best[0] >= 0.5 else None


def check_crs(g):
    """[{source, id, title, md, verdict, flag, lead}] for every CR of the log and of the lead developer's list.
    flag: "in-scope" (the verdict says so), "probably" or "check" (the signed version reads like it), or ""."""
    crs = [c for c in g["log"].get("crs") or [] if isinstance(c, dict)]
    try:
        basis = crtool.signed_basis(g["project"]) if (crs or g["actuals"].get("crs")) else None
    except SystemExit:
        basis = None
    rows, linked = [], set()

    def lead(text):
        if basis is None:
            return "", None
        level, leads = crtool.signed_leads(g["project"], text, basis)
        return ("" if level == "none" else level), (leads[0] if leads else None)

    for item in g["actuals"].get("crs") or []:
        if not isinstance(item, dict):
            continue
        entry = link(item, crs)
        verdict = item.get("verdict") or (entry or {}).get("verdict") or ""
        row = {"source": "lead developer", "id": (entry or {}).get("id", ""), "title": item.get("title", ""),
               "md": item.get("md"), "billed": (entry or {}).get("sold_md") if (entry or {}).get("status") in BILLED else None,
               "verdict": verdict, "gap_pattern": item.get("gap_pattern") or (entry or {}).get("gap_pattern", ""),
               "flag": "", "lead": None}
        if entry:
            linked.add(entry.get("id"))
        if verdict == "in-scope":
            row["flag"] = "in-scope"
        elif not item.get("verdict"):  # a verdict in the actuals file is the BA's decision at close-out
            level, best = lead(f"{item.get('title', '')}. {item.get('request', '')}")
            if not entry or level == "probably":  # a logged CR keeps its verdict unless the match is close
                row["flag"], row["lead"] = level, best
        rows.append(row)
    for c in crs:
        if c.get("id") in linked:
            continue
        row = {"source": "CR log", "id": c.get("id", ""), "title": c.get("title", ""), "md": None,
               "billed": c.get("sold_md") if c.get("status") in BILLED else None, "verdict": c.get("verdict", ""),
               "gap_pattern": c.get("gap_pattern", ""), "gap_note": c.get("gap_note", ""), "flag": "", "lead": None}
        if c.get("verdict") == "in-scope":
            row["flag"] = "in-scope"
        elif c.get("verdict") == "new":
            level, best = lead(f"{c.get('title', '')}. {c.get('request', '')}")
            if level == "probably":
                row["flag"], row["lead"] = level, best
        rows.append(row)
    return basis, rows


def flag_text(row, version):
    if row["flag"] == "in-scope":
        return f"in scope of v{version}" + (" (its CR log verdict)" if row["id"] else " (verdict given)")
    if not row["lead"]:
        return ""
    s, e = row["lead"]
    quote = e["text"] if len(e["text"]) <= 140 else e["text"][:137] + "..."
    word = "probably in" if row["flag"] == "probably" else "check against"
    return f"{word} v{version}: {e['ref']} [{e['where']}] (match {s:.2f}) “{quote}”"


# ---------------------------------------------------------------- the drafts
def totals(g, rows):
    a = g["actuals"]
    areas = [x for x in a.get("actual") or [] if isinstance(x, dict) and figure(x.get("md"))]
    dev = [x for x in areas if x.get("kind", "development") != "testing"]
    test = [x for x in areas if x.get("kind") == "testing"]
    billed_crs = [r for r in rows if r["flag"] != "in-scope" and figure(r["billed"])]
    billed = a.get("crs_billed_md") if figure(a.get("crs_billed_md")) else (sum(r["billed"] for r in billed_crs) if billed_crs else None)
    sold = a.get("sold_md") if figure(a.get("sold_md")) else None
    out = {"sold": sold, "crs_billed": billed, "dev": sum(x["md"] for x in dev) if dev else None,
           "test": sum(x["md"] for x in test) if test else None, "dev_areas": dev, "test_areas": test}
    out["billed_total"] = (sold or 0) + (billed or 0) if sold is not None else None
    if out["billed_total"] and out["dev"] is not None:
        diff = out["dev"] - out["billed_total"]
        out["variance"] = (diff, diff / out["billed_total"] * 100)
    else:
        out["variance"] = None
    return out


def variance_text(t):
    if not t["variance"]:
        return "cannot be worked out: " + ("nothing sold to compare with" if t["sold"] is None else "no actual development given")
    diff, pct = t["variance"]
    return f"{'+' if diff >= 0 else '−'}{num(abs(diff))} MD ({'+' if diff >= 0 else '−'}{abs(pct):.0f}%)"


def md(value):
    return f"{num(value)}" if figure(value) else NOT_GIVEN


def draft_actuals(g, t, basis, rows):
    a, test = g["actuals"], bool(g["actuals"].get("test"))
    mark = " (TEST DATA)" if test else ""
    issued = g["issues"][-1] if g["issues"] else None
    out = [f"# {g['name']} – actuals{mark}", ""]
    if test:
        out += ["> TEST DATA: every figure here is made up for a test. It must never calibrate an estimate.", ""]
    out += [f"**Client:** {g['client'] or NOT_GIVEN} · **Platform:** {g['platform'] or NOT_GIVEN} · "
            f"**Team:** {a.get('team') or NOT_GIVEN} · **Phase:** {a.get('phase') or NOT_GIVEN}"
            + (f" · **Delivered:** {a['delivered']}" if a.get("delivered") else ""),
            f"**Requirements document:** " + (f"v{issued['version']}, issued {issued.get('date', '?')}" if issued else "never recorded as issued"),
            "", "## Effort", "", "| Item | Mandays |", "|---|---|",
            f"| Development sold | {md(t['sold'])} |", f"| CRs billed | {md(t['crs_billed'])} |",
            f"| Total billed for development | {md(t['billed_total'])} |"]
    areas = ", ".join(f"{x['area']} {num(x['md'])}" for x in t["dev_areas"])
    out.append(f"| Actual development | {md(t['dev'])}{f' ({areas})' if areas else ''} |")
    if t["test"] is not None:
        tested = ", ".join(f"{x['area']} {num(x['md'])}" for x in t["test_areas"])
        out.append(f"| Actual testing and UAT support | {num(t['test'])} ({tested}) |")
    out.append(f"| Variance | {variance_text(t)} |")
    rate = workspace.company().get("day_rate")
    if t["variance"] and rate and t["variance"][0] > 0:
        out.append(f"| Absorbed (at the day rate) | about {(workspace.company().get('currency') or '').strip()} "
                   f"{round(t['variance'][0] * rate):,} |".replace("  ", " "))
    est = g["estimate"]
    if est and est["res"]:
        low, high = est["res"]["total"]
        out += ["", f"The estimate ({est['file']}) said {estimate.rng(low, high)}"
                + (" for the priced lines only" if est["res"].get("unpriced") else "") + "."]
    version = basis["version"] if basis else "?"
    real = [r for r in rows if r["flag"] not in ("in-scope", "probably")]
    out += ["", "## Change requests", "", "| # | CR | Verdict | Billed (MD) | Actual (MD) | Gap pattern |", "|---|---|---|---|---|---|"]
    for n, r in enumerate(real, 1):
        out.append(f"| {n} | {(r['id'] + ' ') if r['id'] else ''}{r['title']} | {r['verdict'] or 'to decide'} | "
                   f"{md(r['billed']) if r['billed'] is not None else '–'} | {md(r['md']) if r['md'] is not None else '–'} | "
                   f"{r['gap_pattern'] or '–'} |")
    if not real:
        out.append("| – | none | | | | |")
    flagged = [r for r in rows if r["flag"] in ("in-scope", "probably")]
    if flagged:
        out += ["", f"## Listed as change requests, but in the signed v{version}", "",
                "Not change requests: they were in what the client signed. They are not billed, and they are not gap "
                "evidence; if one took longer than planned, it is an estimating lesson.", ""]
        out += [f"- {(r['id'] + ' ') if r['id'] else ''}{r['title']}" + (f" ({num(r['md'])} MD)" if figure(r["md"]) else "")
                + f": {flag_text(r, version)}" for r in flagged]
    if a.get("deferred"):
        out += ["", "## Deferred", ""] + [f"- {x}" for x in a["deferred"]]
    out += ["", "## Lessons", ""] + ([f"- {x}" for x in a.get("lessons") or []] or ["- (from the lead developer: where the time went, and why)"])
    if a.get("source"):
        out += ["", f"Source: {a['source']}."]
    return "\n".join(out) + "\n"


def log_row(g, t, rows):
    a, test = g["actuals"], bool(g["actuals"].get("test"))
    real = [r for r in rows if r["flag"] not in ("in-scope", "probably") and r["verdict"] != "in-scope"]
    billed = [r for r in real if figure(r["billed"])]
    notes = " ".join(x for x in (("TEST DATA." if test else ""), "; ".join(a.get("lessons") or [])[:200]) if x)
    return [g["slug"] + (" (TEST)" if test else ""), g["platform"] or NOT_GIVEN, a.get("phase") or NOT_GIVEN,
            a.get("team") or NOT_GIVEN, md(t["sold"]) if t["sold"] is not None else "n/a",
            md(t["crs_billed"]) if t["crs_billed"] is not None else "n/a", md(t["dev"]) if t["dev"] is not None else "n/a",
            variance_text(t) if t["variance"] else "n/a", f"{len(real)}" + (f" ({len(billed)} billed)" if real else ""), notes]


def row_text(cells):
    return "| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |"


def draft_proposal(g, t, basis, rows, row):
    version = basis["version"] if basis else "?"
    test = bool(g["actuals"].get("test"))
    out = [f"# Proposed knowledge-base changes from closing {g['name']}" + (" (TEST DATA)" if test else ""), "",
           "Drafted by tools/close.py. Nothing here is in the knowledge base yet: it is shared by everyone using the "
           "workspace, so each part waits for the user's yes.", ""]
    if test:
        out += ["TEST DATA: the projects-log row is marked TEST, so estimates never count it as a delivered project.", ""]
    missing = [w for w, v in (("development sold (the scope of work's mandays, from the project lead)", t["sold"]),
                              ("actual development per area (from the lead developer)", t["dev"])) if v is None]
    if not g["actuals_file"]:
        missing.insert(0, f"the actuals file ({layout.shown(g['project'], close_dir(g['project']) / 'actuals.json')})")
    if missing:
        out += ["**Not given yet:** " + "; ".join(missing) + ". Ask for them; never guess them.", ""]
    out += [f"## 1. knowledge/actuals/{g['slug']}.md (new)", "", f"The draft is in \"{DRAFT}\" beside this file. Edit it there before applying.", "",
            "## 2. knowledge/projects-log.md: the row", "", row_text(LOG_HEAD), "|" + "---|" * len(LOG_HEAD), row_text(row), "",
            "## 3. knowledge/gap-patterns.md: evidence", ""]
    evidence = [r for r in rows if r["flag"] not in ("in-scope", "probably") and r["verdict"] in ("new", "ambiguous", "")]
    for r in evidence:
        cost = f"{num(r['md'])} MD spent" if figure(r["md"]) else ("billed " + num(r["billed"]) + " MD" if figure(r["billed"]) else "not billed")
        kind = "Cost" if r["verdict"] == "new" or figure(r["md"]) else "Review"
        pattern = r["gap_pattern"] if r["gap_pattern"] not in ("", "new") else (
            "a new pattern" + (f" ({r['gap_note']})" if r.get("gap_note") else "") + ", with the workshop question that would have caught it")
        out.append(f"- {pattern}: "
                   f"{kind} evidence – {g['slug']}{' ' + r['id'] if r['id'] else ''} ({r['verdict'] or 'verdict to decide'}, {cost}). "
                   "Describe the gap in general terms, without client content.")
    if not evidence:
        out.append("- None: no change request is left once those in the signed version are taken out.")
    out += ["", "## 4. knowledge/building-blocks.md", ""]
    est = g["estimate"]
    if est and est["data"].get("lines"):
        counts = {}
        for line in est["data"]["lines"]:
            if line.get("block"):
                counts[line["block"]] = counts.get(line["block"], 0) + (line.get("count") or 0)
        if counts:
            out.append(f"- Building blocks counted in {est['file']}: " + ", ".join(f"{b} × {num(c)}" for b, c in sorted(counts.items())) + ".")
        if t["dev"] is not None:
            out.append("- Only the total actual is known unless the lead developer gave effort per block: propose a calibration "
                       f"note (\"{g['platform']}: {num(t['dev'])} MD actual development for the blocks above"
                       + (", TEST" if test else "") + "\"), not new rates.")
    else:
        out.append("- No estimate in the project: nothing to calibrate against. A calibration note at most.")
    out += ["", f"## 5. Change requests held against the signed v{version}", ""]
    if basis is None:
        out.append("- No change requests, or nothing signed to compare with.")
    for r in rows:
        flag = flag_text(r, version)
        out.append(f"- {r['source']}: {(r['id'] + ' ') if r['id'] else ''}{r['title']} – {flag or 'no close match: a change request'}")
    if any(r["flag"] == "check" for r in rows):
        out += ["", "\"check against\" is a weaker match: read the cited text and record the verdict in the actuals file "
                "(\"verdict\": \"in-scope\" or \"new\"), then draft again."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- commands
def cmd_check(a):
    g = gather(a.project, a.actuals)
    basis, rows = check_crs(g)
    if not rows:
        print("No change requests in the CR log or the actuals file.")
        return
    version = basis["version"] if basis else "?"
    print(f"Change requests held against v{version}" + (f" ({basis['source']})" if basis else ""))
    for line in (basis or {}).get("warnings", []):
        print(f"Warning: {line}")
    for r in rows:
        print(f"- {r['source']}: {(r['id'] + ' ') if r['id'] else ''}{r['title']}: {flag_text(r, version) or 'no close match in the signed version'}")
    n = sum(1 for r in rows if r["flag"] in ("in-scope", "probably"))
    if n:
        print(f"{n} of {len(rows)} look like part of the signed version: not change requests, not gap evidence. Read the cited "
              "text before deciding.")


def cmd_draft(a):
    g = gather(a.project, a.actuals)
    basis, rows = check_crs(g)
    t = totals(g, rows)
    row = log_row(g, t, rows)
    folder = close_dir(g["project"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / DRAFT).write_text(draft_actuals(g, t, basis, rows), encoding="utf-8", newline="\n")
    (folder / PROPOSAL).write_text(draft_proposal(g, t, basis, rows, row), encoding="utf-8", newline="\n")
    record = {"drafted": dt.date.today().isoformat(), "slug": g["slug"], "test": bool(g["actuals"].get("test")),
              "phase": g["actuals"].get("phase") or "", "log_row": row,
              "flags": [{"source": r["source"], "id": r["id"], "title": r["title"], "flag": r["flag"]} for r in rows if r["flag"]]}
    (folder / RECORD).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"Drafted in {layout.shown(g['project'], folder)}/: \"{DRAFT}\", \"{PROPOSAL}\" (internal). Nothing was written to the knowledge base.")
    flagged = [r for r in rows if r["flag"] in ("in-scope", "probably")]
    if flagged:
        print(f"{len(flagged)} listed as change requests look like part of the signed version: "
              + ", ".join(r["id"] or r["title"] for r in flagged) + ". They are left out of the CRs and the gap evidence.")
    if t["sold"] is None:
        print("Development sold is not given: the variance cannot be worked out. Ask the project lead.")
    if record["test"]:
        print("TEST DATA: the row is marked TEST, so estimates will not count it.")


def find_row(lines, slug, phase):
    for i, line in enumerate(lines):
        if line.startswith("|"):
            c = estimate.cells(line)
            if c and re.sub(r"\s*\(TEST\)$", "", c[0]) == slug and (len(c) < 3 or c[2] == phase):
                return i
    return None


def cmd_apply(a):
    p = Path(a.project)
    folder = close_dir(p)
    record = read_json(folder / RECORD, "The close-out record")
    if not record:
        sys.exit(f"Nothing drafted: run `python -I tools/close.py draft {p.as_posix()}` and show the user the proposal first.")
    kdir = estimate.knowledge_dir(a.knowledge)
    done = []
    if a.only in (None, "actuals"):
        target = kdir / "actuals" / f"{record['slug']}.md"
        if target.exists() and not a.force:
            sys.exit(f"knowledge/actuals/{target.name} exists: nothing was written. Add --force to replace it, once the user agreed.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((folder / DRAFT).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        done.append(f"knowledge/actuals/{target.name}")
    if a.only in (None, "log"):
        path = kdir / "projects-log.md"
        text = path.read_text(encoding="utf-8") if path.exists() else (workspace.TEMPLATES / "knowledge" / "projects-log.md").read_text(encoding="utf-8")
        lines = text.rstrip("\n").splitlines()
        new = row_text(record["log_row"])
        i = find_row(lines, record["slug"], record["log_row"][2])
        if i is None:
            lines.append(new)
        else:
            lines[i] = new
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        done.append("knowledge/projects-log.md (" + ("row added" if i is None else "row replaced") + ")")
    print("Written: " + "; ".join(done) + ". The gap patterns and building blocks are edited by hand, as agreed.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "draft"):
        s = sub.add_parser(name)
        s.add_argument("project")
        s.add_argument("--actuals")
    s = sub.add_parser("apply")
    s.add_argument("project")
    s.add_argument("--only", choices=("actuals", "log"))
    s.add_argument("--force", action="store_true")
    s.add_argument("--knowledge", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if not Path(a.project).is_dir():
        sys.exit(f"No project folder at {a.project}.")
    {"check": cmd_check, "draft": cmd_draft, "apply": cmd_apply}[a.cmd](a)


if __name__ == "__main__":
    main()
