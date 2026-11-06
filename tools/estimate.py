"""Manday estimates: read the rates, list what a project contains, and render an estimate as Excel.

Usage:
    python -I tools/estimate.py blocks    "<platform>"
    python -I tools/estimate.py inventory projects/<slug>
    python -I tools/estimate.py render    projects/<slug> ["<estimate.json>"]
    python -I tools/estimate.py weeks     projects/<slug> --team 2 ["<estimate.json>"]

blocks     the building blocks and rates for a platform in knowledge/building-blocks.md, the shares for
           other work set there, and how many delivered projects in knowledge/projects-log.md they rest on
inventory  what the project has to count from: roles, screens, forms, lists, dialogs, integrations,
           notifications, open register items, documents in docs/
render     checks an estimate file, works out the ranges, the confidence level and the comparison with the
           scope of work, and writes the Excel file next to it. Without a file name it takes the newest
           file in projects/<slug>/estimates/
weeks      turns the estimate's mandays into working weeks for a team size, per scope-of-work line or
           group, for drafting the project timeline (weeks only: mandays never go to the client)

Figures are never invented: a rate or share comes from the knowledge base or from the lead developer for
this estimate. A line without one is listed with its count and left out of the totals ("not priced").

An estimate is internal: it lives in projects/<slug>/estimates/ and never goes to the client.

estimates/<date> estimate from <basis>.json:
{
  "project": "Courier Booking System",
  "platform": "Joget DX",
  "date": "2026-11-06",
  "basis": "spec v0.3",              what it was counted from, in words
  "basis_kind": "spec",              brief | sow | notes | spec | requirements-document
  "sources": ["spec/app.yaml v0.3", "register.json"],
  "lines": [ ...line... ],
  "risks": [ {"ref": "R-012", "item": "...", "md": [0, 4]} ],     optional: open questions; "md" when sized
  "assumptions": ["..."],
  "gap_patterns": [ {"id": "GP-03", "why": "..."} ],              optional: patterns that apply
  "questions": [ {"question": "...", "source": "GP-03", "narrows": ["L05", "R-012"]} ],
  "sow": {"source": "docs/2026-11-02 SOW.xlsx", "lines": [ {"ref": "3.1", "item": "...", "mandays": 10} ]},
  "confidence": "low",               optional: a lower level than the rules give, with "confidence_reason"
}

A line has "id", "item", optional "group", "sow_ref" and "note", and exactly one of:
  "block": "BB-02", "count": 2       counted in building blocks; the rate comes from the knowledge base.
                                     Add "rate": [low, high] (mandays per unit) when the lead developer
                                     gives one for this estimate (a provisional rate); say who in "rate_note".
                                     With no rate from either, the line is not priced
  "other": "OW-01"                   work around the build (project management, testing ...); the share or
                                     mandays come from the "Other work" table in building-blocks.md. Not
                                     priced when nothing is set there
  "md": [low, high]                  mandays given directly by the lead developer
  "percent": [10, 15]                a share of the building-block subtotal, given by the lead developer

Totals are the sum of the low ends and the sum of the high ends. Risks widen the high end only.
See docs/estimates.md.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402  (company profile: day rate and currency)

BASIS_KINDS = ("brief", "sow", "notes", "spec", "requirements-document")
EARLY = ("brief", "sow", "notes")  # counted before the requirements are known
LEVELS = ("low", "medium", "high")
# A single calibrated rate becomes a range by its confidence in the knowledge base: (low factor, high factor).
SPREAD = {"high": (0.9, 1.1), "medium": (0.75, 1.25), "low": (0.75, 1.5)}
MIN_PROJECTS = 3  # delivered projects on the platform before an estimate may be more than low-confidence
READING_NOTE_FROM = 5  # lines with a range, from which the estimate explains what the ends of its total mean
CLOSED = ("resolved", "wont-fix")


def knowledge_dir(override=None):
    if override:
        return Path(override)
    own = ROOT / "knowledge"
    return own if own.exists() else workspace.TEMPLATES / "knowledge"


def num(x):
    """1.0 -> '1', 2.50 -> '2.5'."""
    return f"{round(x, 1):g}"


def rng(low, high, unit=" MD"):
    return f"{num(low)}{unit}" if round(low, 1) == round(high, 1) else f"{num(low)} – {num(high)}{unit}"


# ---------------------------------------------------------------- knowledge base

def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


# A rate cell: an optional "about", a number or a range, then anything at all (a unit, "per form", a note).
RATE = re.compile(r"^\s*(?:(?:about|around|approx\.?|approximately|circa|c\.)\s+|[~≈]\s*)?"
                  r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?))?(?![\d.,]*\d)", re.I)


def parse_rate(cell):
    """'TBD' -> None; '2–4' -> (2, 4); '1 per migration' -> (1, 1); '3 (was 5)' -> (3, 3).

    Only the figure the cell starts with counts. Every number in the cell used to be collected, so a note
    made a range: '3 (was 5)' read as 3 to 5, '0.5 MD each (2023 rate)' as 0.5 to 2023. A cell that has a
    figure but does not start with a plain number or range ('1,5', 'from 2') gives None: see rate_problem."""
    m = RATE.match(cell or "")
    if not m:
        return None
    low = float(m.group(1))
    return (low, float(m.group(2))) if m.group(2) else (low, low)


def rate_problem(cell):
    """Why a rate cell with a figure in it could not be read, or None (also None for an empty or TBD cell)."""
    if parse_rate(cell) is None and re.search(r"\d", cell or ""):
        return f"'{cell.strip()}' is not a number or a range such as 2–4 (write decimals with a point)"
    return None


def read_blocks(platform, kdir):
    """Building blocks for a platform: ({id: {name, drivers, rate, confidence}}, platforms in the file)."""
    path = kdir / "building-blocks.md"
    blocks, platforms, current, cols = {}, [], None, {}
    if not path.exists():
        return blocks, platforms
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+Platform:\s*(.+?)\s*$", line)
        if m:
            current = m.group(1)
            platforms.append(current)
            continue
        if line.startswith("## "):
            current = None
        if current is None or current.lower() != (platform or "").lower() or not line.startswith("|"):
            continue
        row = cells(line)
        if row and row[0].upper() == "ID":
            cols = {name.lower(): i for i, name in enumerate(row)}
            continue
        if not re.match(r"^BB-\d+$", row[0]):
            continue
        get = lambda key, default: row[next((i for name, i in cols.items() if name.startswith(key)), default)] \
            if len(row) > next((i for name, i in cols.items() if name.startswith(key)), default) else ""
        conf = get("confidence", 4).lower()
        blocks[row[0]] = {"name": get("building block", 1), "drivers": get("what drives", 2),
                          "rate": parse_rate(get("rate", 3)), "rate_problem": rate_problem(get("rate", 3)),
                          "confidence": conf if conf in LEVELS else None}
    return blocks, platforms


def read_other_work(kdir):
    """Work around the build, from the 'Other work' table: {id: {name, share, unit}}. unit: percent | md."""
    path = kdir / "building-blocks.md"
    out, inside = {}, False
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("other work")
            continue
        if not inside or not line.startswith("|"):
            continue
        row = cells(line)
        if not re.match(r"^OW-\d+$", row[0]) or len(row) < 3:
            continue
        out[row[0]] = {"name": row[1], "share": parse_rate(row[2]), "rate_problem": rate_problem(row[2]),
                       "unit": "md" if re.search(r"\bMD\b|manday", row[2], re.I) else "percent"}
    return out


def logged_projects(platform, kdir):
    """Delivered projects in the projects log: (on this platform, all)."""
    path = kdir / "projects-log.md"
    on_platform, everyone = set(), set()
    if not path.exists():
        return on_platform, everyone
    header = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        row = cells(line)
        if header is None:
            header = [c.lower() for c in row]
            continue
        if set("".join(row)) <= set("-: ") or not row[0]:
            continue
        everyone.add(row[0])
        i = header.index("platform") if "platform" in header else 1
        if len(row) > i and row[i].lower() == (platform or "").lower():
            on_platform.add(row[0])
    return on_platform, everyone


def read_register(project):
    path = Path(project) / "register.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("items", [])


def open_risk_items(items):
    """Open register items that can move the estimate: high severity, or a medium or high effort impact."""
    out = [it for it in items if it.get("status") not in CLOSED
           and (it.get("severity") == "high" or it.get("effort_impact") in ("medium", "high"))]
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda it: (order.get(it.get("severity"), 9), order.get(it.get("effort_impact"), 9), it.get("id", "")))


# ---------------------------------------------------------------- estimate

def pair(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), float(value)
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
        return float(value[0]), float(value[1])
    return None


def compute(est, project, kdir):
    """Check the estimate and work out every figure. Returns (result, errors)."""
    errors = []
    for key in ("project", "platform", "date", "basis", "basis_kind", "lines", "assumptions"):
        if not est.get(key):
            errors.append(f"missing {key}")
    if est.get("basis_kind") and est["basis_kind"] not in BASIS_KINDS:
        errors.append(f"basis_kind '{est['basis_kind']}' not in {list(BASIS_KINDS)}")
    if est.get("confidence") and est["confidence"] not in LEVELS:
        errors.append(f"confidence '{est['confidence']}' not in {list(LEVELS)}")
    platform = est.get("platform", "")
    blocks, platforms = read_blocks(platform, kdir)
    on_platform, _ = logged_projects(platform, kdir)
    other_work = read_other_work(kdir)
    sow_refs = {str(l.get("ref")) for l in (est.get("sow") or {}).get("lines", [])}

    lines, seen = [], set()
    for i, line in enumerate(est.get("lines") or []):
        where = line.get("id") or f"line #{i + 1}"
        if not line.get("id") or not line.get("item"):
            errors.append(f"{where}: needs id and item")
            continue
        if line.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(line.get("id"))
        kinds = [k for k in ("block", "other", "md", "percent") if k in line]
        if len(kinds) != 1:
            errors.append(f"{where}: needs exactly one of block (with count), other, md or percent")
            continue
        out = {**line, "kind": kinds[0], "low": 0.0, "high": 0.0, "rate_from": "", "rate_low": None, "rate_high": None,
               "block_name": "", "priced": True, "calibrated": False, "pct": None}
        if est.get("sow") and line.get("sow_ref") is not None and str(line["sow_ref"]) not in sow_refs:
            errors.append(f"{where}: sow_ref '{line['sow_ref']}' is not a line of the scope of work")
        if out["kind"] == "block":
            count = line.get("count")
            if not isinstance(count, (int, float)) or isinstance(count, bool) or count <= 0:
                errors.append(f"{where}: count must be a number above 0")
                continue
            known = blocks.get(line["block"])
            if blocks and not known:
                errors.append(f"{where}: {line['block']} is not a building block for {platform} in building-blocks.md")
                continue
            out["block_name"] = known["name"] if known else ""
            given = pair(line.get("rate")) if "rate" in line else None
            if "rate" in line and not given:
                errors.append(f"{where}: rate must be [low, high] mandays per unit")
                continue
            if given:
                rate = given
                out["rate_from"] = "provisional" if not (known and known["rate"]) else "provisional (overrides the knowledge base)"
                out["calibrated"] = False
            elif known and known["rate"]:
                lo, hi = known["rate"]
                if lo == hi:
                    f = SPREAD[known["confidence"] or "low"]
                    lo, hi = lo * f[0], hi * f[1]
                rate = (lo, hi)
                out["rate_from"] = f"knowledge base ({known['confidence'] or 'low'} confidence)"
                out["calibrated"] = known["confidence"] in ("medium", "high")  # low: a figure not yet backed by actuals
            else:
                rate = None
                unread = known and known.get("rate_problem")
                out.update(priced=False, rate_from=f"the rate in building-blocks.md cannot be read ({unread}): not priced" if unread
                           else "no rate set: not priced")
            if rate and (rate[0] > rate[1] or rate[0] < 0):
                errors.append(f"{where}: rate low must not be above rate high")
                continue
            if rate:
                out.update(rate_low=rate[0], rate_high=rate[1], low=rate[0] * count, high=rate[1] * count)
        elif out["kind"] == "other":
            known = other_work.get(line["other"])
            if other_work and not known:
                errors.append(f"{where}: {line['other']} is not in the Other work table of building-blocks.md")
                continue
            if not known or not known["share"]:
                unread = known and known.get("rate_problem")
                out.update(priced=False, rate_from=f"the share in building-blocks.md cannot be read ({unread}): not priced" if unread
                           else "no share set: not priced")
            elif known["unit"] == "md":
                out.update(low=known["share"][0], high=known["share"][1], rate_from="knowledge base")
            else:
                out.update(pct=known["share"])
        elif out["kind"] == "md":
            md = pair(line["md"])
            if not md or md[0] > md[1] or md[0] < 0:
                errors.append(f"{where}: md must be [low, high] mandays")
                continue
            out.update(low=md[0], high=md[1], rate_from="lead developer's figure")
        else:
            pct = pair(line["percent"])
            if not pct or pct[0] > pct[1] or pct[0] < 0:
                errors.append(f"{where}: percent must be [low, high] percent of the building-block subtotal")
                continue
            out.update(pct=pct)
        lines.append(out)

    build_low = sum(l["low"] for l in lines if l["kind"] == "block")
    build_high = sum(l["high"] for l in lines if l["kind"] == "block")
    build_lines = [l for l in lines if l["kind"] == "block"]
    build_priced = any(l["priced"] for l in build_lines)
    # The build is not priced while any building-block line has no rate: the figures are then what is priced
    # so far, never a total for the project, and a share of the building blocks is a share of too little.
    build_unpriced = [l for l in build_lines if not l["priced"]]
    for l in lines:
        if l["pct"]:
            pct = l["pct"]
            if not build_priced:
                l.update(priced=False, rate_from=f"{rng(pct[0], pct[1], '%')} of building blocks, none priced yet: not priced")
                continue
            l.update(low=build_low * pct[0] / 100, high=build_high * pct[1] / 100,
                     rate_from=f"{rng(pct[0], pct[1], '%')} of building blocks"
                               + (", knowledge base" if l["kind"] == "other" else "")
                               + (f", of the priced ones only: understated while {len(build_unpriced)} are not priced"
                                  if build_unpriced else ""))

    risks = []
    for i, r in enumerate(est.get("risks") or []):
        md = pair(r["md"]) if "md" in r else (0.0, 0.0)
        if not r.get("item") or not md or md[0] > md[1] or md[0] < 0:
            errors.append(f"risk #{i + 1}: needs item, and md must be [low, high] when given")
            continue
        rid = r.get("ref") or f"K{i + 1:02d}"
        if rid in seen:
            errors.append(f"risk {rid}: id already used")
        seen.add(rid)
        risks.append({**r, "id": rid, "low": md[0], "high": md[1], "sized": "md" in r})

    other_low = sum(l["low"] for l in lines if l["kind"] != "block")
    other_high = sum(l["high"] for l in lines if l["kind"] != "block")
    low, high = build_low + other_low, build_high + other_high
    risk_low, risk_high = sum(r["low"] for r in risks), sum(r["high"] for r in risks)
    unpriced = [l for l in lines if not l["priced"]]
    if len(unpriced) < len(lines) and not errors and round(low, 1) == round(high, 1):
        errors.append("the total is a single number: an estimate is a range, so give the lines a low and a high end")

    spread = {l["id"]: l["high"] - l["low"] for l in lines}
    spread.update({r["id"]: r["high"] for r in risks})
    label = {l["id"]: l["item"] for l in lines}
    label.update({r["id"]: r["item"] for r in risks})
    drivers = sorted(((k, label[k], v) for k, v in spread.items() if v > 0), key=lambda d: -d[2])

    questions = []
    for i, q in enumerate(est.get("questions") or []):
        if not q.get("question"):
            errors.append(f"question #{i + 1}: needs question")
            continue
        unknown = [n for n in q.get("narrows", []) if n not in spread]
        if unknown:
            errors.append(f"question #{i + 1}: narrows {unknown}, which are not line or risk ids")
        questions.append({**q, "addresses": sum(spread.get(n, 0) for n in q.get("narrows", []))})
    questions.sort(key=lambda q: -q["addresses"])

    # Scope of work, line by line
    comparison, sow_total, sow_covered = [], None, None
    if est.get("sow"):
        priced = [l for l in est["sow"].get("lines", []) if isinstance(l.get("mandays"), (int, float))]
        sow_total = sum(l["mandays"] for l in priced)
        # A share of building blocks that are not all priced is understated: it cannot be compared either.
        comparable = lambda x: x["priced"] and not (x["pct"] and build_unpriced)
        sow_covered = 0  # SOW lines whose estimate lines can all be compared: the like-for-like figure
        for l in priced:
            mine = [x for x in lines if str(x.get("sow_ref")) == str(l.get("ref"))]
            if mine and all(comparable(x) for x in mine):
                sow_covered += l["mandays"]
        for s in est["sow"].get("lines", []):
            mine = [l for l in lines if str(l.get("sow_ref")) == str(s.get("ref"))]
            lo, hi, md = sum(l["low"] for l in mine), sum(l["high"] for l in mine), s.get("mandays")
            missing = [l["id"] for l in mine if not l["priced"]]
            shares = [l["id"] for l in mine if l["priced"] and not comparable(l)]
            if not mine:
                verdict, diff = "Not estimated: no line of the estimate covers it", 0
            elif missing:
                verdict, diff = f"Cannot compare: {', '.join(missing)} not priced", 0
            elif shares:
                verdict, diff = (f"Cannot compare yet: {', '.join(shares)} is a share of building blocks that are not "
                                 "all priced"), 0
            elif not isinstance(md, (int, float)):
                verdict, diff = "No mandays in the scope of work", 0
            elif md < lo:
                verdict, diff = f"Scope of work is {num(lo - md)} MD below the low end", md - lo
            elif md > hi:
                verdict, diff = f"Scope of work is {num(md - hi)} MD above the high end", md - hi
            else:
                verdict, diff = "Within the range", 0
            comparison.append({"ref": s.get("ref"), "item": s.get("item", ""), "sow": md, "low": lo, "high": hi,
                               "lines": ", ".join(l["id"] for l in mine), "verdict": verdict, "diff": diff})
        for l in lines:
            if l.get("sow_ref") is None:
                comparison.append({"ref": "–", "item": l["item"], "sow": None, "low": l["low"], "high": l["high"],
                                   "lines": l["id"], "verdict": "Not in the scope of work"
                                   + ("" if l["priced"] else " (not priced)"), "diff": -l["low"] if comparable(l) else 0})
        comparison.sort(key=lambda c: -abs(c["diff"]))

    # Confidence: start high, and let each rule lower it
    reg = read_register(project)
    flagged = open_risk_items(reg)
    open_high = [it for it in flagged if it.get("severity") == "high"]
    level, reasons = "high", []

    def cap(to, why):
        nonlocal level
        reasons.append(why)
        if LEVELS.index(to) < LEVELS.index(level):
            level = to

    n = len(on_platform)
    if n < MIN_PROJECTS:
        cap("low", f"The rates rest on {n} delivered project{'s' if n != 1 else ''} on {platform}. Until "
                   f"{MIN_PROJECTS} are logged, every estimate is low-confidence.")
    if est.get("basis_kind") in EARLY:
        what = {"brief": "a brief", "sow": "a scope of work", "notes": "workshop notes"}[est["basis_kind"]]
        cap("low", f"It is counted from {what}, before the requirements are known: screens, fields and rules can "
                   "still change.")
    if unpriced:
        cap("low", f"{len(unpriced)} of {len(lines)} lines have no rate or share set and are not priced: the total "
                   "leaves them out, so it is not the whole project.")
    counted = [l for l in lines if l["priced"] and not l["pct"]]  # percent lines only follow the build
    counted_high = sum(l["high"] for l in counted)
    share = sum(l["high"] for l in counted if not l.get("calibrated")) / counted_high if counted_high else 0
    why = (f"{round(share * 100)}% of the priced mandays use low-confidence rates or the lead developer's figures for "
           "this estimate, not rates calibrated from delivered projects.")
    if share > 0.5:
        cap("low", why)
    elif share > 0.2:
        cap("medium", why)
    if open_high:
        cap("medium", f"{len(open_high)} high-severity register item{'s are' if len(open_high) != 1 else ' is'} still open.")
    if est.get("confidence") in LEVELS:
        cap(est["confidence"], est.get("confidence_reason") or f"The estimator set the confidence to {est['confidence']}.")
    if not reasons:
        reasons.append("The rates are calibrated, the count comes from the spec and no high-severity question is open.")

    # How to read the total. It adds every low end and every high end, so its two ends are the cases where
    # every line lands low or every line lands high. No narrower figure is given (an estimate here is never a
    # midpoint or a "most likely" number); with many lines the reader is told what the ends mean.
    independent = [l for l in lines if l["priced"] and not l["pct"] and l["high"] > l["low"]]
    reading = "" if build_unpriced else (f"The total adds the low end of every line and the high end of every line. With {len(independent)} lines that "
               "each have a range, all of them landing low, or all of them landing high, is unlikely: expect the outcome "
               "inside the range, not at either end. The range is not narrowed for that; watch the widest lines instead."
               if len(independent) >= READING_NOTE_FROM else "")

    used = sorted({l["block"] for l in lines if l["kind"] == "block"})
    no_rate = [b for b in used if not (blocks.get(b) and blocks[b]["rate"])]
    return {
        "lines": lines, "risks": risks, "questions": questions, "drivers": drivers, "comparison": comparison,
        "sow_total": sow_total, "sow_covered": sow_covered, "build": (build_low, build_high), "other": (other_low, other_high),
        "total": (low, high), "risk": (risk_low, risk_high), "confidence": level, "reasons": reasons,
        "projects_logged": sorted(on_platform), "platform_known": bool(blocks), "platforms": platforms,
        "blocks": blocks, "blocks_used": used, "blocks_without_rate": no_rate, "register_flagged": flagged,
        "uncalibrated_share": share, "unpriced": unpriced, "other_work": other_work, "reading": reading,
        "build_unpriced": build_unpriced, "build_lines": len(build_lines),
        "partial": bool(build_unpriced) and len(unpriced) < len(lines),
    }, errors


# ---------------------------------------------------------------- Excel

def render_xlsx(est, res, out):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill("solid", fgColor="1F3864")
    total_fill = PatternFill("solid", fgColor="D9E1F2")
    warn_fill = PatternFill("solid", fgColor="FFE699")
    wrap = Alignment(wrap_text=True, vertical="top")
    bold = Font(bold=True)
    internal = "Internal: not for the client"
    md = lambda x: round(x, 1)

    def table(ws, columns, rows, start=1, fills=None):
        for c, (name, width) in enumerate(columns, 1):
            cell = ws.cell(row=start, column=c, value=name)
            cell.font, cell.fill, cell.alignment = Font(bold=True, color="FFFFFF"), header_fill, wrap
            ws.column_dimensions[get_column_letter(c)].width = width
        for r, row in enumerate(rows, start + 1):
            for c, value in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=round(value, 2) if isinstance(value, float) else value)
                cell.alignment = wrap
                if fills and fills.get(r - start - 1):
                    cell.fill = fills[r - start - 1]
                    cell.font = bold if fills[r - start - 1] is total_fill else Font()
        ws.freeze_panes = ws.cell(row=start + 1, column=1)
        ws.oddHeader.center.text = internal
        return start + len(rows) + 1

    wb = Workbook()
    low, high = res["total"]
    co = workspace.company()

    # Summary
    s = wb.active
    s.title = "Summary"
    s.column_dimensions["A"].width = 34
    s.column_dimensions["B"].width = 16
    s.column_dimensions["C"].width = 16
    s.column_dimensions["D"].width = 70
    rows = [
        (f"Estimate: {est['project']}", "", "", "", "title"),
        (internal, "", "", "", "warn"),
        ("",),
        ("Platform", est["platform"]),
        ("Date", est["date"]),
        ("Counted from", est["basis"]),
        ("Sources", "; ".join(est.get("sources", []))),
        ("",),
        ("Mandays", "Low", "High", "", "head"),
        ("Building blocks", res["build"][0], res["build"][1]),
        ("Other work", res["other"][0], res["other"][1]),
        ("Total, as understood today", low, high, "", "total"),
    ]
    partial = res["partial"]
    if partial:
        n, m = len(res["build_unpriced"]), res["build_lines"]
        shares = any(l["pct"] and l["priced"] for l in res["lines"])
        rows[-3:] = [
            ("The build is not priced", "", "", f"{n} of {m} building-block lines have no rate yet, so there is no "
             "total for the project: the figures below are what is priced so far", "warn"),
            ("Building blocks, priced lines only", res["build"][0], res["build"][1], f"{m - n} of {m} lines"),
            ("Other work", res["other"][0], res["other"][1],
             "Shares of the building blocks are understated: they cover the priced lines only" if shares else ""),
            ("Priced so far (not a project figure)", low, high, "Leaves out the lines not priced", "total")]
        rows.append(("Lines not priced (no rate or share set)", len(res["unpriced"]), "",
                     ", ".join(l["id"] for l in res["unpriced"]) + ": left out of the figures above"))
    elif res["unpriced"]:
        rows[-1] = ("Total of the priced lines", low, high, "Not the whole project: see the lines not priced", "total")
        rows.append(("Lines not priced (no rate or share set)", len(res["unpriced"]), "",
                     ", ".join(l["id"] for l in res["unpriced"]) + ": left out of the totals"))
    if any(r["sized"] for r in res["risks"]):
        rows += [("Open questions, if answered the costly way", res["risk"][0], res["risk"][1])]
        if not partial:
            rows += [("Total with open questions", low, high + res["risk"][1], "", "total")]
    if co.get("day_rate") and partial:
        cur = (co.get("currency") or "").strip()
        rows += [(f"Cost at {cur} {co['day_rate']:,} a day".replace("  ", " "), "", "",
                  "Not worked out: the build is not priced")]
    elif co.get("day_rate"):
        cur = (co.get("currency") or "").strip()
        top = high + res["risk"][1]
        rows += [(f"Cost at {cur} {co['day_rate']:,} a day".replace("  ", " "), round(low * co["day_rate"]), round(top * co["day_rate"]),
                  "; ".join(x for x in ("Priced lines only" if res["unpriced"] else "",
                                        "Low end to the high end including open questions" if res["risk"][1] else "") if x))]
    if res["sow_total"] is not None and partial:
        blocked = [c for c in res["comparison"] if c["verdict"].startswith("Cannot compare") and c["ref"] != "–"]
        rows += [("Scope of work, lines that can be compared", res["sow_covered"], "",
                  "Compare line by line on the Against SOW sheet"
                  + (f"; {len(blocked)} line(s) cannot be compared until the build is priced: "
                     + ", ".join(str(c["ref"]) for c in blocked) if blocked else "")),
                 ("Scope of work, all lines", res["sow_total"], "", est["sow"].get("source", ""))]
    elif res["sow_total"] is not None:
        rows += [("Scope of work, lines this estimate prices", res["sow_covered"], "", "Compare this with the total above"),
                 ("Scope of work, all lines", res["sow_total"], "", est["sow"].get("source", ""))]
    rows += [("",), ("Confidence", res["confidence"].capitalize(), "", "", "total")]
    rows += [("", "", "", r) for r in res["reasons"]]
    rows += [("",), ("Calibration", "", "", "", "head"),
             ("Delivered projects logged on this platform", len(res["projects_logged"])),
             ("Building blocks used", len(res["blocks_used"])),
             ("… of which have no rate in the knowledge base", len(res["blocks_without_rate"]), "",
              ", ".join(res["blocks_without_rate"])),
             ("",), ("What makes the range wide", "Mandays of range", "", "", "head")]
    rows += [(f"{k}  {name}", v) for k, name, v in res["drivers"][:6]]
    for r, row in enumerate(rows, 1):
        style = row[4] if len(row) > 4 else ""
        for c, value in enumerate(row[:4], 1):
            cell = s.cell(row=r, column=c, value=round(value, 1) if isinstance(value, float) else value)
            cell.alignment = wrap
            if style == "title":
                cell.font = Font(bold=True, size=14)
            elif style == "warn" and c == 1:
                cell.font, cell.fill = bold, warn_fill
            elif style == "head":
                cell.font, cell.fill = Font(bold=True, color="FFFFFF"), header_fill
            elif style == "total":
                cell.font, cell.fill = bold, total_fill
    s.oddHeader.center.text = internal

    # Estimate lines
    e = wb.create_sheet("Estimate")
    cols = [("ID", 7), ("Group", 22), ("Item", 40), ("Block", 8), ("Building block", 28), ("Count", 8),
            ("Rate low", 9), ("Rate high", 9), ("Rate from", 26), ("MD low", 9), ("MD high", 9), ("SOW ref", 9),
            ("Notes", 50)]
    rows, fills = [], {}
    for kind, title in (("block", "Building blocks"), ("other", "Other work")):
        part = [l for l in res["lines"] if (l["kind"] == "block") == (kind == "block")]
        if not part:
            continue
        for l in part:
            notes = " ".join(x for x in (l.get("note"), l.get("rate_note")) if x)
            rows.append([l["id"], l.get("group", ""), l["item"], l.get("block", ""), l["block_name"], l.get("count", ""),
                         l["rate_low"] if l["rate_low"] is not None else "", l["rate_high"] if l["rate_high"] is not None else "",
                         l["rate_from"], md(l["low"]) if l["priced"] else "", md(l["high"]) if l["priced"] else "",
                         l.get("sow_ref", ""), notes])
        fills[len(rows)] = total_fill
        rows.append(["", "", f"Subtotal: {title.lower()}", "", "", "", "", "", "", md(sum(l["low"] for l in part)),
                     md(sum(l["high"] for l in part)), "", ""])
    fills[len(rows)] = total_fill
    rows.append(["", "", "Priced so far (the build is not priced)" if res["partial"] else
                 "Total of the priced lines" if res["unpriced"] else "Total, as understood today", "", "", "", "",
                 "", "", md(low), md(high), "", ""])
    table(e, cols, rows, fills=fills)

    # Against the scope of work
    if res["comparison"]:
        w = wb.create_sheet("Against SOW")
        blank = lambda c: "not priced" in c["verdict"]
        rows = [[c["ref"], c["item"], c["sow"] if c["sow"] is not None else "", "" if blank(c) else md(c["low"]),
                 "" if blank(c) else md(c["high"]), c["verdict"], c["lines"]]
                for c in res["comparison"]]
        fills = {i: warn_fill for i, c in enumerate(res["comparison"]) if c["diff"]}
        fills[len(rows)] = total_fill
        rows.append(["", "Priced so far (the build is not priced)" if res["partial"] else "Total of the lines this estimate prices",
                     res["sow_covered"], md(low), md(high), "", ""])
        table(w, [("SOW ref", 9), ("Scope of work item", 44), ("SOW MD", 9), ("Estimate low", 12), ("Estimate high", 12),
                  ("Difference", 46), ("Estimate lines", 18)], rows, fills=fills)

    # Uncertainty
    u = wb.create_sheet("Uncertainty")
    rows = [["Confidence", "", res["confidence"].capitalize(), "", "", ""]]
    rows += [["Why", "", r, "", "", ""] for r in res["reasons"]]
    if res["reading"]:
        rows.append(["How to read the total", "", res["reading"], "", "", ""])
    rows += [["Open question, sized" if r["sized"] else "Open question, not sized", r["id"], r["item"],
              r["low"] if r["sized"] else "", r["high"] if r["sized"] else "", r.get("note", "")] for r in res["risks"]]
    rows += [["Line not priced", l["id"], l["item"], "", "", l["rate_from"]] for l in res["unpriced"]]
    sized = {r["id"] for r in res["risks"]}
    rows += [["Open register item", it.get("id", ""), it.get("finding", ""), "", "",
              f"{it.get('severity', '')} severity" + (f", {it['effort_impact']} effort impact" if it.get("effort_impact") else "")]
             for it in res["register_flagged"] if it.get("id") not in sized]
    rows += [["Gap pattern that applies", g.get("id", ""), g.get("why", ""), "", "", ""] for g in est.get("gap_patterns", [])]
    rows += [["Building block with no rate yet", b, (res["blocks"].get(b) or {}).get("name", ""), "", "",
              "Set it in building-blocks.md to price these lines every time"] for b in res["blocks_without_rate"]]
    table(u, [("What", 30), ("Ref", 9), ("Detail", 70), ("MD low", 9), ("MD high", 9), ("Notes", 40)], rows)

    a = wb.create_sheet("Assumptions")
    table(a, [("#", 5), ("Assumption", 110)], [[i, t] for i, t in enumerate(est.get("assumptions", []), 1)])

    q = wb.create_sheet("Questions")
    table(q, [("#", 5), ("Question that would narrow the range", 80), ("From", 12), ("Narrows", 18),
              ("Mandays of range it covers", 14)],
          [[i, x["question"], x.get("source", ""), ", ".join(x.get("narrows", [])), x["addresses"]]
           for i, x in enumerate(res["questions"], 1)])

    wb.save(out)


# ---------------------------------------------------------------- commands

def cmd_blocks(a):
    kdir = knowledge_dir(a.knowledge)
    blocks, platforms = read_blocks(a.platform, kdir)
    on_platform, everyone = logged_projects(a.platform, kdir)
    if not blocks:
        print(f"No building blocks for '{a.platform}' in {kdir / 'building-blocks.md'}."
              + (f" Platforms there: {', '.join(platforms)}." if platforms else ""))
        print("Lines for this platform are not priced unless the lead developer gives a rate for the estimate.")
    for bid, b in blocks.items():
        if b["rate"]:
            rate = f"{rng(*b['rate'])} per unit, {b['confidence'] or 'low'} confidence"
        elif b.get("rate_problem"):
            rate = f"RATE NOT READ: {b['rate_problem']}"
        else:
            rate = "no rate yet"
        print(f"{bid}  {b['name']}  [{rate}]  driven by: {b['drivers']}")
    with_rate = sum(1 for b in blocks.values() if b["rate"])
    print(f"\n{with_rate} of {len(blocks)} building blocks have a rate. A line with no rate is not priced unless the "
          "lead developer gives one for the estimate.")
    other = read_other_work(kdir)
    print("\nOther work (share of the building-block subtotal, or mandays):" if other
          else "\nOther work: no 'Other work' table in building-blocks.md, so nothing is added around the build.")
    for oid, o in other.items():
        share = (rng(*o["share"], unit=" MD" if o["unit"] == "md" else "%") if o["share"]
                 else f"SHARE NOT READ: {o['rate_problem']}" if o.get("rate_problem") else "not set: left out")
        print(f"{oid}  {o['name']}  [{share}]")
    print(f"Delivered projects logged on {a.platform}: {len(on_platform)}"
          + (f" ({', '.join(sorted(on_platform))})" if on_platform else "")
          + f"; on any platform: {len(everyone)}. Below {MIN_PROJECTS}, every estimate is low-confidence.")


def cmd_inventory(a):
    import yaml

    p = Path(a.project)
    print(f"Inventory of {p.as_posix()}")
    docs = sorted(x.name for x in (p / "docs").glob("*") if x.is_file()) if (p / "docs").exists() else []
    print(f"\nDocuments in docs/: {len(docs)}")
    for d in docs:
        print(f"  {d}")
    spec_file = p / "spec" / "app.yaml"
    if spec_file.exists():
        spec = yaml.safe_load(spec_file.read_text(encoding="utf-8")) or {}
        proj = spec.get("project") or {}
        print(f"\nSpec v{proj.get('version', '?')}, platform {proj.get('platform', '?')}")
        roles = spec.get("roles") or []
        print(f"Roles: {len(roles)} ({', '.join(r.get('name', r.get('id', '')) for r in roles)})")
        print(f"Statuses: {len(spec.get('statuses') or [])}")
        screens = spec.get("screens") or []
        print(f"Screens: {len(screens)} ({', '.join(f'{n} {t}' for t, n in sorted(Counter(s.get('type') for s in screens).items()))})")

        def describe_fields(sections):
            fields = [f for sec in sections or [] for f in sec.get("fields") or []]
            pages = len({sec.get("page") for sec in sections or [] if sec.get("page")}) or 1
            types = Counter(f.get("type", "text") for f in fields)
            special = [f"{n} {t}" for t, n in sorted(types.items()) if t in ("file", "signature", "user")]
            calc = sum(1 for f in fields if str(f.get("source", "")).lower().startswith("calculated"))
            rules = sum(1 for f in fields if f.get("validation"))
            bits = [f"{pages} page{'s' if pages != 1 else ''}", f"{len(fields)} fields"]
            bits += special + ([f"{calc} calculated"] if calc else []) + ([f"{rules} with a validation rule"] if rules else [])
            return ", ".join(bits)

        def describe_list(lst):
            buttons = (lst.get("toolbar") or []) + (lst.get("actions") or [])
            exports = sum(1 for b in buttons if "export" in str(b.get("label", "")).lower())
            bits = [f"{len(lst.get('columns') or [])} columns", f"{len(lst.get('filters') or [])} filters",
                    f"{len(lst.get('actions') or [])} row actions"]
            return ", ".join(bits + ([f"{exports} export"] if exports else []))

        for sc in screens:
            bits = []
            if sc.get("sections"):
                bits.append(describe_fields(sc["sections"]))
            if sc.get("fields_from"):
                bits.append(f"shows the fields of {sc['fields_from']}, read-only")
            if sc.get("stats"):
                bits.append(f"{len(sc['stats'])} stat cards")
            if sc.get("list"):
                bits.append("list: " + describe_list(sc["list"]))
            dialogs = [b["dialog"] for b in sc.get("buttons") or [] if b.get("dialog")]
            if dialogs:
                bits.append("opens " + ", ".join(dialogs))
            exports = sum(1 for b in sc.get("buttons") or [] if "export" in str(b.get("label", "")).lower())
            if exports:
                bits.append(f"{exports} export button")
            who = ", ".join(sc.get("roles") or ["everyone"])
            print(f"  {sc.get('id')} [{sc.get('type')}] for {who}: {'; '.join(bits) or '–'}")
        dialogs = spec.get("dialogs") or []
        print(f"Dialogs: {len(dialogs)}")
        for d in dialogs:
            extra = (f"{len(d.get('fields') or [])} fields" if d.get("fields") else "confirmation only") + (", with a list" if d.get("list") else "")
            print(f"  {d.get('id')}: {extra}")
        flow = (spec.get("process_flow") or {}).get("steps") or []
        if flow:
            print(f"Process flow: {len(flow)} steps ({', '.join(str(s.get('name')) for s in flow)})")
        integ = spec.get("integrations") or []
        print(f"Integrations: {len(integ)}")
        for i in integ:
            print(f"  {i.get('system')} ({i.get('direction', '?')}): {i.get('purpose', '')}")
        notes = spec.get("notifications") or []
        print(f"Notifications: {len(notes)}" + (" (none listed; check the requirements for e-mails)" if not notes else ""))
        reqs = spec.get("requirements") or []
        items = [it for g in reqs for it in g.get("items") or []]
        tbc = sum(1 for it in items if isinstance(it, dict) and it.get("tbc"))
        print(f"Requirements: {len(reqs)} groups, {len(items)} items, {tbc} waiting on a decision")
        print(f"NFRs: {len(spec.get('nfr') or [])}; timeline in the spec: {'yes' if spec.get('timeline') else 'no'}")
    else:
        print("\nNo spec yet: count from the brief or scope of work in docs/.")
    reg = read_register(p)
    if reg:
        still = [it for it in reg if it.get("status") not in CLOSED]
        sev = Counter(it.get("severity") for it in still)
        print(f"\nRegister: {len(still)} open ({sev['high']} high, {sev['medium']} medium, {sev['low']} low)")
        for it in open_risk_items(reg):
            impact = f", {it['effort_impact']} effort impact" if it.get("effort_impact") else ""
            print(f"  {it.get('id')} [{it.get('severity')}{impact}, {it.get('category', '')}] {str(it.get('finding', ''))[:140]}")
    else:
        print("\nRegister: no items")
    earlier = sorted((p / "estimates").glob("*.json")) if (p / "estimates").exists() else []
    if earlier:
        print(f"\nEarlier estimates: {', '.join(x.name for x in earlier)}")


def newest_first_key(path):
    """Orders estimate files oldest to newest: by the date the name starts with (or the date inside), then by
    the name with its numbers read as numbers, so "spec v0.10" comes after "spec v0.9"."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    date = m.group(1) if m else ""
    if not date:
        try:
            date = str(json.loads(path.read_text(encoding="utf-8")).get("date") or "")
        except (OSError, ValueError, AttributeError):
            date = ""
    return date, [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def load_estimate(a):
    """The estimate file named on the command line, or the newest in the project's estimates folder."""
    p = Path(a.project)
    if a.file:
        path = Path(a.file)
        if not path.exists():
            path = p / "estimates" / a.file
    else:
        found = sorted((p / "estimates").glob("*.json"), key=newest_first_key) if (p / "estimates").exists() else []
        if not found:
            sys.exit(f"No estimate in {p / 'estimates'}")
        path = found[-1]
    if not path.exists():
        sys.exit(f"No estimate file {path}")
    est = json.loads(path.read_text(encoding="utf-8"))
    res, errors = compute(est, p, knowledge_dir(a.knowledge))
    if errors:
        print(f"{path.name} needs fixing:")
        print("\n".join(f"  - {e}" for e in errors))
        sys.exit(1)
    return path, est, res


def cmd_render(a):
    path, est, res = load_estimate(a)
    out = path.with_suffix(".xlsx")
    try:
        render_xlsx(est, res, out)
    except PermissionError:
        sys.exit(f"Cannot write {out}: close it in Excel and run this again.")

    low, high = res["total"]
    unpriced, lines = res["unpriced"], res["lines"]
    print(f"Estimate for {est['project']} ({est['platform']}), counted from {est['basis']}")
    if len(unpriced) == len(lines):
        print(f"  Nothing is priced: none of the {len(lines)} lines has a rate or share. This is a count only.")
    elif res["partial"]:
        n, m = len(res["build_unpriced"]), res["build_lines"]
        print(f"  The build is not priced: {n} of {m} building-block lines have no rate yet, so there is no total "
              "for the project yet.")
        print("  Priced so far (not a project figure):")
        print(f"    Building blocks: {rng(*res['build'])} ({m - n} of {m} lines)")
        shares = any(l["pct"] and l["priced"] for l in lines)
        print(f"    Other work:      {rng(*res['other'])}"
              + (" (shares of the building blocks are understated: they cover the priced lines only)" if shares else ""))
        if any(r["sized"] for r in res["risks"]):
            print(f"    Open questions answered the costly way would add up to {num(res['risk'][1])} MD more")
    else:
        print(f"  Building blocks: {rng(*res['build'])}")
        print(f"  Other work:      {rng(*res['other'])}")
        print(f"  Total{' of the priced lines' if unpriced else ''}: {rng(low, high)}")
        if res["reading"]:
            print(f"    {res['reading']}")
        if any(r["sized"] for r in res["risks"]):
            print(f"  With open questions answered the costly way: up to {num(high + res['risk'][1])} MD")
    if unpriced:
        print(f"  Not priced ({len(unpriced)} of {len(lines)} lines, left out of the "
              f"{'figures above' if res['partial'] else 'total'}):")
        for l in unpriced:
            what = f"{l.get('count')} x {l['block']} {l['block_name']}".strip() if l["kind"] == "block" else l.get("other", "")
            print(f"    - {l['id']} {l['item']}: {what}")
        print("    Set the rates and shares in knowledge/building-blocks.md, or ask the lead developer for a range.")
    unsized = [r for r in res["risks"] if not r["sized"]]
    if unsized:
        print(f"  Open questions not sized: {len(unsized)} ({', '.join(r['id'] for r in unsized)})")
    print(f"  Confidence: {res['confidence']}")
    for r in res["reasons"]:
        print(f"    - {r}")
    if not res["platform_known"]:
        print(f"  The knowledge base has no building blocks for {est['platform']}.")
    if res["drivers"]:
        print("  Widest lines:")
        for k, name, v in res["drivers"][:5]:
            print(f"    - {k} {name}: {num(v)} MD of range")
    if res["sow_total"] is not None and res["partial"]:
        blocked = [c for c in res["comparison"] if c["verdict"].startswith("Cannot compare") and c["ref"] != "–"]
        if blocked:
            print(f"  Scope of work ({num(res['sow_total'])} MD in all): {len(blocked)} of "
                  f"{len(est['sow'].get('lines', []))} lines cannot be compared yet, because the build is not priced:")
            for c in blocked:
                sow = f"{num(c['sow'])} MD" if isinstance(c["sow"], (int, float)) else "no mandays"
                print(f"    - {c['ref']} {c['item']} ({sow})")
        shown = [c for c in res["comparison"] if c["diff"]][:5]
        if shown:
            print("  Lines that can be compared now:")
        for c in shown:
            sow = f"{num(c['sow'])} MD" if c["sow"] is not None else "not in the SOW"
            print(f"    - {c['ref']} {c['item']}: {sow} against {rng(c['low'], c['high'])}. {c['verdict']}")
    elif res["sow_total"] is not None:
        print(f"  Scope of work: {num(res['sow_covered'])} MD for the lines this estimate prices "
              f"({num(res['sow_total'])} MD in all), against {rng(low, high)}")
        for c in [c for c in res["comparison"] if c["diff"]][:5]:
            sow = f"{num(c['sow'])} MD" if c["sow"] is not None else "not in the SOW"
            print(f"    - {c['ref']} {c['item']}: {sow} against {rng(c['low'], c['high'])}. {c['verdict']}")
    if res["questions"]:
        print("  Questions that narrow the range most:")
        for x in res["questions"][:5]:
            print(f"    - ({num(x['addresses'])} MD) {x['question']}" if x["addresses"] else f"    - {x['question']}")
    print(f"Wrote {out}")
    print("Internal: not for the client.")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(a.project)
    except Exception:
        pass


def cmd_weeks(a):
    """Mandays to working weeks for a team size, grouped the way the timeline is drawn."""
    path, est, res = load_estimate(a)
    if a.team <= 0 or a.days <= 0:
        sys.exit("--team and --days must be above 0")
    per_week = a.team * a.days
    weeks = lambda md: math.ceil(md / per_week * 2) / 2  # rounded up to half a week

    def span(lo, hi):
        lo, hi = weeks(lo), weeks(hi)
        return f"{num(hi)} week{'s' if hi != 1 else ''}" if lo == hi else f"{num(lo)} – {num(hi)} weeks"

    sow = {str(l.get("ref")): l.get("item", "") for l in (est.get("sow") or {}).get("lines", [])}
    groups = {}
    for l in res["lines"]:
        if sow and l.get("sow_ref") is not None:
            key = f"{l['sow_ref']} {sow.get(str(l['sow_ref']), '')}".strip()
        else:
            key = l.get("group") or l["item"]
            key = f"{key} (not in the scope of work)" if sow else key
        groups.setdefault(key, []).append(l)

    people = f"{num(a.team)} developer{'s' if a.team != 1 else ''}"
    print(f"Working weeks for {people}, {num(a.days)} days a week, from {path.name}")
    print("Effort divided by the team: it assumes the work can be shared out and nobody waits. Mandays stay internal;")
    print("only weeks go into the timeline.")
    for key, part in groups.items():
        priced = [l for l in part if l["priced"]]
        missing = [l["id"] for l in part if not l["priced"]]
        lo, hi = sum(l["low"] for l in priced), sum(l["high"] for l in priced)
        text = f"{rng(lo, hi)} -> {span(lo, hi)}" if priced else "not priced: no weeks"
        notes = []
        if priced and all(l["pct"] for l in priced):
            notes.append("a share of the build: it usually runs alongside it")
        if missing and priced:
            notes.append(f"understated: {', '.join(missing)} not priced")
        print(f"  {key}: {text}" + (f"  ({'; '.join(notes)})" if notes else ""))
    b_lo, b_hi = res["build"]
    if b_hi:
        print(f"Build in all: {rng(b_lo, b_hi)} -> {span(b_lo, b_hi)}")
    if any(r["sized"] for r in res["risks"]):
        print(f"Open questions answered the costly way could add up to {span(res['risk'][1], res['risk'][1])}.")
    if res["unpriced"]:
        print(f"{len(res['unpriced'])} of {len(res['lines'])} lines are not priced, so these weeks are not the whole project.")
    print(f"Confidence of the estimate: {res['confidence']}.")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--knowledge", help="knowledge base folder (default: knowledge/, or the starter one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("blocks")
    b.add_argument("platform")
    b.set_defaults(fn=cmd_blocks)
    i = sub.add_parser("inventory")
    i.add_argument("project")
    i.set_defaults(fn=cmd_inventory)
    r = sub.add_parser("render")
    r.add_argument("project")
    r.add_argument("file", nargs="?")
    r.set_defaults(fn=cmd_render)
    w = sub.add_parser("weeks")
    w.add_argument("project")
    w.add_argument("file", nargs="?")
    w.add_argument("--team", type=float, required=True, help="people working on it at the same time")
    w.add_argument("--days", type=float, default=5, help="working days a week per person (default 5)")
    w.set_defaults(fn=cmd_weeks)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
