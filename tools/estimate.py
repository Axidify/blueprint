"""Manday estimates: read the rates, list what a project contains, and render an estimate as Excel.

Usage:
    python -I tools/estimate.py blocks    "<platform>"
    python -I tools/estimate.py inventory projects/<slug>
    python -I tools/estimate.py render    projects/<slug> ["<estimate.json>"] [--force]
    python -I tools/estimate.py weeks     projects/<slug> --team 2 ["<estimate.json>"]
    python -I tools/estimate.py rates-from "<estimate.xlsx>" [--json]

blocks     the building blocks and rates for a platform in knowledge/building-blocks.md, the shares for
           other work set there, and how many delivered projects in knowledge/projects-log.md they rest on
inventory  what the project has to count from: roles, screens, forms, lists, dialogs, integrations,
           notifications, open register items, the client's documents
render     checks an estimate file, works out the ranges, the confidence level and the comparison with the
           scope of work, and writes the Excel file: into "Internal – estimates and change requests" (next
           to the .json in a project not yet in the new folder layout). Without a file name it takes the
           newest file in the project's estimates folder (_blueprint/estimates/, or estimates/). When rates
           were typed into the Rates needed sheet of the Excel file it would replace, it stops (take them in
           with rates-from first); --force writes it anyway and keeps that file beside it
weeks      turns the estimate's mandays into working weeks for a team size, per scope-of-work line or
           group, for drafting the project timeline (weeks only: the estimate's mandays never go to the client;
           the timeline shows the scope of work's mandays instead)
rates-from the rates a lead developer filled in on the Rates needed sheet of an estimate's Excel file, as
           rows for knowledge/building-blocks.md (or --json); it changes nothing

Figures are never invented: a rate or share comes from the knowledge base or from the lead developer for
this estimate. A line without one is listed with its count and left out of the totals ("not priced").

An estimate is internal: its source lives in the project's _blueprint/estimates/ (estimates/ in the old folder
layout), its Excel file in "Internal – estimates and change requests", and neither goes to the client.

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
import datetime as dt
import os
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
    import layout

    path = layout.register_json(project)
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

# The look of the workbook, shared with the register, the UAT workbook and the CR log (tools/sheets.py,
# docs/design-language.md): true greys, hairlines between rows, status as a coloured word, the one accent
# colour for the headline and for the cells to fill in.
import sheets  # noqa: E402

XL_FONT = sheets.FONT
INK, GREY = sheets.INK, sheets.GREY
HEAD_FILL, HEAD_LINE, ROW_LINE = sheets.HEAD_FILL, sheets.HEAD_LINE, sheets.ROW_LINE
GREEN, ORANGE, RED, ACCENT = sheets.GREEN, sheets.ORANGE, sheets.RED, sheets.ACCENT
INPUT_FILL, INPUT_LINE = sheets.INPUT_FILL, sheets.INPUT_LINE  # a cell to fill in, as on every workbook
INTERNAL = "Internal: not for the client"
DASH = "—"
RATES_SHEET = "Rates needed"
RATE_HEADS = ("Low MD per unit", "High MD per unit")


def readable_date(text):
    """'2026-11-06' -> '6 November 2026'; anything else as it is."""
    try:
        d = dt.date.fromisoformat(str(text))
    except ValueError:
        return str(text)
    return f"{d.day} {d:%B %Y}"


def span(low, high, unit=""):
    """A range for a cell: (1, 2) -> '1–2', (3, 3) -> '3'."""
    return f"{num(low)}{unit}" if round(low, 1) == round(high, 1) else f"{num(low)}–{num(high)}{unit}"


def plural(n, word, many=None):
    return f"{num(n)} {word if n == 1 else many or word + 's'}"


def row_height(text, width, size=11):
    """Points for a wrapped cell of this many character widths: Excel does not size merged cells itself."""
    per_line = max(10, width * 1.25 * 11 / size)
    lines = sum(max(1, math.ceil(len(part) / per_line)) for part in str(text).split("\n"))
    return round(lines * size * 1.32 + 5, 1)


def render_xlsx(est, res, out):
    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.worksheet.page import PageMargins

    def put(ws, r, c, value, color=INK, bold=False, size=11, wrap=True, align=None, fill=None, fmt=None, indent=0):
        if isinstance(value, float):
            value = round(value, 1)
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
        cell = ws.cell(row=r, column=c, value=value)
        if not isinstance(value, CellRichText):
            cell.font = Font(name=XL_FONT, size=size, bold=bold, color=color)
        cell.alignment = Alignment(wrap_text=wrap, vertical="center", indent=indent,
                                   horizontal=align or ("right" if numeric or value == DASH else "left"))
        if numeric:
            cell.number_format = fmt or ("#,##0" if float(value).is_integer() else "#,##0.0")
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        return cell

    def rich(*parts):
        """Text in pieces: (text, colour, size, bold)."""
        return CellRichText(*[TextBlock(InlineFont(rFont=XL_FONT, sz=size, color=color, b=bold or None), text)
                              for text, color, size, bold in parts if text])

    def edge(ws, r, columns, bottom=ROW_LINE, top=None):
        for c in range(1, columns + 1):
            ws.cell(row=r, column=c).border = Border(bottom=Side(style="thin", color=bottom) if bottom else Side(),
                                                     top=Side(style="thin", color=top) if top else Side())

    def heads(ws, r, names, right=(), indent=()):
        for c, name in enumerate(names, 1):
            put(ws, r, c, name, color=GREY, bold=True, size=10, fill=HEAD_FILL, align="right" if c in right else "left",
                indent=1 if c in indent else 0)
        edge(ws, r, len(names), bottom=HEAD_LINE)

    def total_row(ws, r, columns):
        for c in range(1, columns + 1):
            cell = ws.cell(row=r, column=c)
            cell.fill = PatternFill("solid", fgColor=HEAD_FILL)
            if not isinstance(cell.value, CellRichText):
                cell.font = Font(name=XL_FONT, size=11, bold=True, color=INK)
        edge(ws, r, columns, bottom=HEAD_LINE, top=HEAD_LINE)

    def sheet(title, widths, titles="1:1", freeze="A2", one_page=False):
        ws = wb.worksheets[0] if wb.worksheets[0].title == "Sheet" else wb.create_sheet()
        ws.title = title
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
        ws.sheet_view.showGridLines = False
        ws.freeze_panes = freeze
        ws.print_title_rows = titles
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 1 if one_page else 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.75, bottom=0.75, header=0.3, footer=0.3)
        for part, text in ((ws.oddHeader.center, INTERNAL), (ws.oddFooter.center, "Page &P of &N")):
            part.text, part.size, part.color = text, 9, GREY
        return ws

    def merged(ws, r, columns, text, width, color=INK, bold=False, size=11):
        put(ws, r, 1, text, color=color, bold=bold, size=size)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=columns)
        ws.row_dimensions[r].height = row_height(text, width, size)

    wb = Workbook()
    lines, risks = res["lines"], res["risks"]
    low, high = res["total"]
    build = [l for l in lines if l["kind"] == "block"]
    other = [l for l in lines if l["kind"] != "block"]
    unpriced = res["unpriced"]
    nothing = len(unpriced) == len(lines)
    build_unpriced = res["build_unpriced"]
    other_unpriced = [l for l in other if not l["priced"]]
    n, m = len(build_unpriced), res["build_lines"]
    understated = bool(build_unpriced) and any(l["pct"] and l["priced"] for l in lines)
    need = {}  # building blocks the estimate uses with no rate: block -> its unpriced lines
    for l in build_unpriced:
        need.setdefault(l["block"], []).append(l)
    sized = [r for r in risks if r["sized"]]
    unsized = [r for r in risks if not r["sized"]]
    waiting = lambda c: c["verdict"].startswith("Cannot compare") or "(not priced)" in c["verdict"]
    conf = res["confidence"]

    # ------------------------------------------------ Overview: the answer first, then the figures
    width = (40, 11, 11, 70)
    o = sheet("Overview", width, titles="1:2", freeze="A3", one_page=True)
    full = sum(width)
    put(o, 1, 1, f"Estimate · {est['project']}", bold=True, size=20, wrap=False)
    o.row_dimensions[1].height = 30
    put(o, 2, 1, f"{est['platform']} · counted from {est['basis']} · {readable_date(est['date'])} · {INTERNAL}",
        color=GREY, wrap=False)
    if nothing:
        headline, tone = (f"Nothing is priced yet: none of the {len(lines)} lines has a rate or share, so this is a "
                          "count only."), ORANGE
        under = "Ask for the rates and shares below, and the next estimate turns this count into mandays."
    elif build_unpriced:
        headline, tone = (f"The build is not priced yet: {n} of {m} building-block lines need a rate, so there is "
                          "no project total."), ORANGE
        under = "The figures below are what is priced so far, not a figure for the project."
    elif other_unpriced:
        headline, tone = (f"Priced lines: {rng(low, high, ' mandays')} (confidence: {conf}). "
                          f"{plural(len(other_unpriced), 'item')} of other work {'has' if len(other_unpriced) == 1 else 'have'} "
                          "no share yet, so this is not the whole project."), ORANGE
        under = res["reading"]
    else:
        headline, tone = f"Likely effort: {rng(low, high, ' mandays')} (confidence: {conf})", ACCENT
        under = res["reading"]
    r = 4
    merged(o, r, 4, headline, full, color=tone, bold=True, size=15)
    if under:
        r += 1
        merged(o, r, 4, under, full, color=GREY)
    r += 2
    heads(o, r, ("Mandays", "Low", "High", "What it means"), right=(2, 3), indent=(4,))
    figures = []  # (label, low, high, meaning, total?)
    priced_build = [l for l in build if l["priced"]]
    priced_other = [l for l in other if l["priced"]]
    if build:
        if nothing:
            means = f"{plural(m, 'line')} counted, none priced yet"
        elif build_unpriced:
            means = (f"{m - n} of {m} lines {'has' if m - n == 1 else 'have'} a rate; {n} {'needs' if n == 1 else 'need'} "
                     "one (Rates needed sheet)")
        else:
            means = f"{plural(m, 'line')}, counted in building blocks (Lines sheet)"
        figures.append(("Building blocks" + (", priced lines" if build_unpriced and priced_build else ""),
                        res["build"][0] if priced_build else DASH, res["build"][1] if priced_build else DASH, means, False))
    if other:
        bits = [f"{plural(len(other), 'item')} around the build: project management, testing and the like"]
        if understated:
            bits.append("shares of the build are understated until the build is priced")
        if other_unpriced:
            bits.append(f"{len(other_unpriced)} not priced yet")
        figures.append(("Other work", res["other"][0] if priced_other else DASH,
                        res["other"][1] if priced_other else DASH, "; ".join(bits), False))
    if build_unpriced and not nothing:
        figures.append(("Priced so far", low, high, "Not a figure for the project: it leaves out the lines that need a rate", True))
    elif other_unpriced and not nothing:
        figures.append(("Total of the priced lines", low, high,
                        f"Leaves out {plural(len(other_unpriced), 'item')} of other work with no share set", True))
    elif not nothing:
        figures.append(("Total", low, high, "Every line at its low end, to every line at its high end", True))
    if sized:
        figures.append(("Open questions, the costly way", res["risk"][0], res["risk"][1],
                        f"Up to {num(res['risk'][1])} MD more if {plural(len(sized), 'sized question')} "
                        f"{'goes' if len(sized) == 1 else 'go'} the costly way; "
                        "widens the high end only" + (f"; {len(unsized)} more not sized yet" if unsized else ""), False))
        if not build_unpriced and not nothing:
            figures.append(("Total with open questions", low, high + res["risk"][1],
                            "The high end if every sized question goes the costly way", True))
    elif unsized:
        figures.append(("Open questions", DASH, DASH,
                        f"{plural(len(unsized), 'open question')} not sized yet (Risks and questions sheet)", False))
    co = workspace.company()
    cost_fmt = "#,##0"
    if co.get("day_rate"):
        label = f"Cost at {(co.get('currency') or '').strip()} {co['day_rate']:,} a day".replace("  ", " ")
        if build_unpriced or nothing:
            figures.append((label, DASH, DASH, "Not worked out: the build is not priced", False))
        else:
            top = high + res["risk"][1]
            means = "; ".join(x for x in ("Priced lines only" if unpriced else "",
                                          "Low end to the high end including open questions" if res["risk"][1] else "") if x)
            figures.append((label, round(low * co["day_rate"]), round(top * co["day_rate"]),
                            means or "Low end to the high end", "cost"))
    if res["sow_total"] is not None:
        count = len(est["sow"].get("lines", []))
        figures.append(("Scope of work sold", res["sow_total"], "",
                        f"All {plural(count, 'line')} of the scope of work; the Against SOW sheet compares them line by line", False))
        blocked = [c for c in res["comparison"] if waiting(c) and c["ref"] != "–"]
        if blocked:
            figures.append(("… of which can be compared now", res["sow_covered"], "",
                            f"{plural(len(blocked), 'line')} can't be compared until their lines are priced", False))
        elif res["sow_covered"] != res["sow_total"]:
            figures.append(("… of which this estimate prices", res["sow_covered"], "", "Compare this with the total above", False))
    for label, lo, hi, means, style in figures:
        r += 1
        put(o, r, 1, label)
        for c, v in ((2, lo), (3, hi)):
            put(o, r, c, v, color=GREY if v == DASH else INK, fmt=cost_fmt if style == "cost" else None)
        put(o, r, 4, means, color=GREY, indent=1)
        o.row_dimensions[r].height = row_height(means, width[3])
        if style is True:
            total_row(o, r, 4)
            o.cell(row=r, column=4).font = Font(name=XL_FONT, size=11, color=GREY)
        else:
            edge(o, r, 4)
    r += 2
    o.cell(row=r, column=1).value = rich(("Confidence: ", INK, 13, True),
                                         (conf.capitalize(), {"low": ORANGE, "high": GREEN}.get(conf, INK), 13, True))
    o.row_dimensions[r].height = 20
    for why in res["reasons"]:
        r += 1
        merged(o, r, 4, f"•  {why}", full)
    r += 2
    put(o, r, 1, "What to do next", bold=True, size=13, wrap=False)
    o.row_dimensions[r].height = 20
    steps = []
    ask = []
    if need:
        ask.append(f"the rates on the Rates needed sheet ({plural(len(need), 'building block')})")
    if other_unpriced:
        ask.append(f"the shares for {plural(len(other_unpriced), 'item')} of other work (Lines sheet)")
    if ask:
        steps.append("Ask the lead developer for " + " and ".join(ask) + ".")
    questions = [q for q in res["questions"] if not (ask and q["question"].lower().startswith("lead developer:"))]
    if questions:
        steps.append("Settle the questions that narrow the range most (Risks and questions sheet), starting with: "
                     + " and ".join(f"“{q['question']}”" for q in questions[:2]))
    if res["sow_total"] is not None:
        differ = [c for c in res["comparison"] if c["diff"]]
        steps.append("Compare with the scope of work on the Against SOW sheet"
                     + (f": {plural(len(differ), 'line')} {'differs' if len(differ) == 1 else 'differ'} from the estimate."
                        if differ else "."))
    steps.append("Once the questions are answered or the spec moves on, say “estimate this project” again.")
    for i, step in enumerate(steps[:3], 1):
        r += 1
        merged(o, r, 4, f"{i}.  {step}", full)
    if est.get("sources"):
        r += 2
        merged(o, r, 4, "Sources: " + "; ".join(est["sources"]), full, color=GREY, size=9)

    # ------------------------------------------------ Lines: every line, by group, readable name first
    cols = ("ID", "Item", "What was counted", "Rate per unit", "Mandays low", "Mandays high", "Status", "SOW line", "Notes")
    e = sheet("Lines", (6, 36, 38, 13, 13, 13, 24, 9, 46), freeze="C2")
    heads(e, 1, cols, right=(4, 5, 6), indent=(7,))

    def counted(l):
        code = l.get("block") or l.get("other") or ""
        if l["kind"] == "block":
            text = f"{num(l['count'])} × {l['block_name'] or l['block']}"
            code = code if l["block_name"] else ""
        elif l["pct"]:
            text = f"Share of the build: {span(*l['pct'], unit='%')}"
        elif l["kind"] == "md":
            text = "Lead developer's figure"
        elif l["priced"]:
            text = f"Fixed: {span(l['low'], l['high'], ' MD')}"
        else:
            text = "Share or mandays not set"
        return rich((text, INK, 11, False), (f"   {code}" if code else "", GREY, 9, False))

    def status(l):
        unread = "cannot be read" in l["rate_from"]
        if l["kind"] == "block":
            if l["priced"]:
                return ("Priced, provisional rate", GREEN) if l["rate_from"].startswith("provisional") else ("Priced", GREEN)
            return ("Rate can't be read", RED) if unread else ("Needs a rate", ORANGE)
        if l["pct"]:
            if not l["priced"]:
                return "Not priced: the build isn't", ORANGE
            return ("Understated", ORANGE) if build_unpriced else ("Share of the build", GREEN)
        if not l["priced"]:
            return ("Share can't be read", RED) if unread else ("Needs a share", ORANGE)
        return "Priced", GREEN

    def line_row(r, l):
        put(e, r, 1, l["id"], color=GREY, size=9)
        put(e, r, 2, l["item"])
        put(e, r, 3, counted(l))
        if l["kind"] == "block":
            if l["priced"]:
                put(e, r, 4, span(l["rate_low"], l["rate_high"], " MD"), align="right")
            else:
                put(e, r, 4, "needs a rate", color=ORANGE, align="right")
        for c, v in ((5, l["low"]), (6, l["high"])):
            put(e, r, c, v if l["priced"] else DASH, color=INK if l["priced"] else GREY)
        word, tone = status(l)
        put(e, r, 7, word, color=tone, bold=True, indent=1)
        put(e, r, 8, str(l["sow_ref"]) if l.get("sow_ref") is not None else "", color=GREY)
        notes = [l.get("note"), l.get("rate_note")]
        if "cannot be read" in l["rate_from"]:
            notes.append(l["rate_from"][0].upper() + l["rate_from"][1:])
        if l["pct"] and l["priced"] and build_unpriced:
            notes.append("A share of the priced building blocks only, until the build is priced.")
        put(e, r, 9, " ".join(x for x in notes if x), color=GREY)
        edge(e, r, len(cols))

    r = 1
    for part, title in ((build, "Building blocks"), (other, "Other work")):
        if not part:
            continue
        groups = {}
        for l in part:
            groups.setdefault(l.get("group") or title, []).append(l)
        for name, members in groups.items():
            r += 1
            put(e, r, 2, name, bold=True, wrap=False)
            put(e, r, 3, plural(len(members), "line"), color=GREY, size=9)
            edge(e, r, len(cols), bottom=HEAD_LINE)
            for l in members:
                r += 1
                line_row(r, l)
        r += 1
        priced = [l for l in part if l["priced"]]
        put(e, r, 2, f"Subtotal: {title.lower()}" + (", priced lines only" if len(priced) < len(part) else ""))
        for c, key in ((5, "low"), (6, "high")):
            put(e, r, c, sum(l[key] for l in priced) if priced else DASH)
        total_row(e, r, len(cols))
    r += 1
    put(e, r, 2, "Nothing priced yet" if nothing else "Priced so far (the build is not priced)" if build_unpriced
        else "Total of the priced lines" if unpriced else "Total")
    for c, v in ((5, low), (6, high)):
        put(e, r, c, DASH if nothing else v)
    total_row(e, r, len(cols))
    e.cell(row=r, column=2).font = Font(name=XL_FONT, size=12, bold=True, color=INK)

    # ------------------------------------------------ Rates needed: a form for the lead developer
    if need:
        rn = sheet(RATES_SHEET, (42, 34, 52, 15, 15), titles="1:3", freeze="A4")
        put(rn, 1, 1, f"Rates needed for {est['platform']}", bold=True, size=15, wrap=False)
        rn.row_dimensions[1].height = 24
        merged(rn, 2, 5, "Fill in a low and high figure per unit, then tell Claude 'save these rates' and the estimate "
                         "is priced next time.", 158, color=GREY)
        heads(rn, 3, ("Building block", "What drives the effort", "Used in this project") + RATE_HEADS, right=(4, 5))
        check = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True,
                               error="Write mandays per unit as a number, such as 1.5", errorTitle="Mandays per unit")
        rn.add_data_validation(check)
        thin = Side(style="thin", color=INPUT_LINE)
        for r, (code, members) in enumerate(sorted(need.items()), 4):
            known = res["blocks"].get(code) or {}
            put(rn, r, 1, rich((known.get("name") or code, INK, 11, False), (f"   {code}" if known.get("name") else "", GREY, 9, False)))
            put(rn, r, 2, known.get("drivers", ""), color=GREY)
            total = sum(l["count"] for l in members)
            used = (f"{num(total)} for {members[0]['item']}" if len(members) == 1 else
                    f"{num(total)} in all: " + "; ".join(f"{l['item']} ({num(l['count'])})" for l in members))
            put(rn, r, 3, used)
            edge(rn, r, 3)
            for c in (4, 5):
                cell = put(rn, r, c, None, fill=INPUT_FILL, align="right")
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
                check.add(cell.coordinate)

    # ------------------------------------------------ Against SOW
    if res["comparison"]:
        w = sheet("Against SOW", (9, 48, 11, 13, 13, 46, 18))
        heads(w, 1, ("SOW line", "Scope of work item", "Sold (MD)", "Estimate low", "Estimate high", "Difference",
                     "Estimate lines"), right=(3, 4, 5), indent=(6,))
        compared = [c for c in res["comparison"] if not waiting(c)]
        later = [c for c in res["comparison"] if waiting(c)]

        def tone(verdict):
            if "below" in verdict or verdict.startswith("Not in the scope"):
                return ORANGE
            return GREEN if "above" in verdict or verdict.startswith("Within") else GREY

        def ids(c):
            """The estimate lines of a SOW line; a long run of them in short."""
            got = [x for x in c["lines"].split(", ") if x]
            return c["lines"] if len(got) <= 6 else f"{got[0]} … {got[-1]} ({len(got)} lines)"

        def sold(c):
            return c["sow"] if isinstance(c["sow"], (int, float)) else DASH if c["ref"] == "–" else ""

        r = 1
        for c in compared:
            r += 1
            put(w, r, 1, str(c["ref"]), color=GREY)
            put(w, r, 2, c["item"])
            put(w, r, 3, sold(c), color=GREY if sold(c) == DASH else INK)
            for col, key in ((4, "low"), (5, "high")):
                put(w, r, col, c[key] if c["lines"] else DASH, color=INK if c["lines"] else GREY)
            verdict = c["verdict"].replace("Scope of work is", "Sold")
            put(w, r, 6, verdict, color=tone(c["verdict"]), bold=tone(c["verdict"]) != GREY, indent=1)
            put(w, r, 7, ids(c), color=GREY, size=9)
            edge(w, r, 7)
        if compared:
            r += 1
            put(w, r, 2, "Total of the lines compared")
            put(w, r, 3, sum(c["sow"] for c in compared if isinstance(c["sow"], (int, float))))
            put(w, r, 4, sum(c["low"] for c in compared))
            put(w, r, 5, sum(c["high"] for c in compared))
            total_row(w, r, 7)
        if later:
            r += 2
            put(w, r, 2, "Can't be compared yet", color=GREY, bold=True, fill=HEAD_FILL, wrap=False)
            for col in range(1, 8):
                w.cell(row=r, column=col).fill = PatternFill("solid", fgColor=HEAD_FILL)
            edge(w, r, 7, bottom=HEAD_LINE)
            for c in later:
                r += 1
                missing = re.match(r"Cannot compare: (.+) not priced", c["verdict"])
                if c["ref"] == "–":
                    why = "Not in the scope of work, and not priced yet"
                elif missing:
                    k = len(missing.group(1).split(", "))
                    why = f"Waiting for rates: {plural(k, 'of its lines', 'of its lines')} {'needs' if k == 1 else 'need'} one"
                else:
                    why = "A share of the build, which is not all priced yet"
                put(w, r, 1, str(c["ref"]), color=GREY)
                put(w, r, 2, c["item"])
                put(w, r, 3, sold(c), color=GREY if sold(c) == DASH else INK)
                put(w, r, 4, DASH, color=GREY)
                put(w, r, 5, DASH, color=GREY)
                put(w, r, 6, why, color=GREY, indent=1)
                put(w, r, 7, ids(c), color=GREY, size=9)
                edge(w, r, 7)
        if res["sow_total"] is not None:
            r += 1
            put(w, r, 2, "Scope of work, all lines")
            put(w, r, 3, res["sow_total"])
            total_row(w, r, 7)

    # ------------------------------------------------ Risks and questions
    q = sheet("Risks and questions", (9, 72, 15, 17, 16))
    put(q, 1, 1, "Risks and questions", bold=True, size=15, wrap=False)
    q.row_dimensions[1].height = 24
    r = 1

    def section(title, names, right=()):
        nonlocal r
        r += 2
        put(q, r, 1, title, bold=True, size=13, wrap=False)
        q.row_dimensions[r].height = 20
        r += 1
        heads(q, r, names, right=right)

    def none_listed(text):
        nonlocal r
        r += 1
        put(q, r, 2, text, color=GREY)

    section("Questions that would narrow the range", ("#", "Question", "From", "Mandays of range it covers", ""), right=(4,))
    for i, x in enumerate(res["questions"], 1):
        r += 1
        put(q, r, 1, i, color=GREY, align="left")
        put(q, r, 2, x["question"])
        put(q, r, 3, x.get("source", ""), color=GREY)
        put(q, r, 4, x["addresses"] if x["addresses"] else DASH, color=INK if x["addresses"] else GREY)
        edge(q, r, 5)
    if not res["questions"]:
        none_listed("None listed.")
    section("Open questions that could add work", ("ID", "What is open", "Severity", "Effort impact", "Adds up to (MD)"),
            right=(5,))
    flagged = {it.get("id"): it for it in res["register_flagged"]}
    items = [(x["id"], x["item"] + (f" ({x['note']})" if x.get("note") else ""), flagged.get(x["id"], {}),
              x["high"] if x["sized"] else "not sized") for x in risks]
    items += [(it.get("id", ""), it.get("finding", ""), it, "not sized") for it in res["register_flagged"]
              if it.get("id") not in {x["id"] for x in risks}]
    for rid, text, it, adds in items:
        r += 1
        put(q, r, 1, rid, color=GREY)
        put(q, r, 2, text)
        sev = it.get("severity") or DASH
        put(q, r, 3, sev, color=ORANGE if sev == "high" else GREY, bold=sev == "high")
        put(q, r, 4, it.get("effort_impact") or DASH, color=GREY)
        put(q, r, 5, adds, color=GREY if adds == "not sized" else INK, align="right")
        edge(q, r, 5)
    if not items:
        none_listed("None open.")
    section("Gap patterns that apply", ("ID", "Why it applies", "", "", ""))
    for g in est.get("gap_patterns", []):
        r += 1
        put(q, r, 1, g.get("id", ""), color=GREY)
        put(q, r, 2, g.get("why", ""))
        edge(q, r, 5)
    if not est.get("gap_patterns"):
        none_listed("None listed.")

    # ------------------------------------------------ Assumptions
    a = sheet("Assumptions", (6, 120))
    heads(a, 1, ("#", "Assumption"))
    for i, text in enumerate(est.get("assumptions", []), 1):
        put(a, i + 1, 1, i, color=GREY, align="left")
        put(a, i + 1, 2, text)
        edge(a, i + 1, 2)

    wb.active = 0
    wb.save(out)


def rates_typed(path):
    """How many building blocks have a rate typed into the Rates needed sheet of an existing Excel file (0 when
    there is no file, no such sheet, or it cannot be read)."""
    from openpyxl import load_workbook

    if not Path(path).exists():
        return 0
    try:
        ws = load_workbook(path, data_only=True)[RATES_SHEET]
    except Exception:
        return 0
    rows = list(ws.iter_rows(values_only=True))
    head = next((i for i, row in enumerate(rows) if RATE_HEADS[0] in row), None)
    if head is None:
        return 0
    cols = [rows[head].index(h) for h in RATE_HEADS[:2] if h in rows[head]]
    return sum(1 for row in rows[head + 1:] if re.search(r"BB-\d+\s*$", str(row[0] or ""))
               and any(c < len(row) and str(row[c] if row[c] is not None else "").strip() for c in cols))


def read_rates_sheet(path):
    """The rates a lead developer filled in on a returned workbook's Rates needed sheet."""
    from openpyxl import load_workbook

    try:
        wb = load_workbook(path, data_only=True)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f"Cannot read {path}: {e}")
    if RATES_SHEET not in wb.sheetnames:
        sys.exit(f"{Path(path).name} has no '{RATES_SHEET}' sheet: every building block of that estimate had a rate.")
    ws = wb[RATES_SHEET]
    m = re.match(r"Rates needed for (.+)", str(ws["A1"].value or ""))
    out = {"platform": m.group(1).strip() if m else "", "rates": [], "empty": [], "problems": []}
    rows = list(ws.iter_rows(values_only=True))
    head = next((i for i, row in enumerate(rows) if RATE_HEADS[0] in row), None)
    if head is None:
        sys.exit(f"The '{RATES_SHEET}' sheet of {Path(path).name} has no '{RATE_HEADS[0]}' column.")
    col_low, col_high = rows[head].index(RATE_HEADS[0]), rows[head].index(RATE_HEADS[1])

    def figure(value, code):
        if value is None or str(value).strip() == "":
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value), float(value)
        got = parse_rate(str(value))
        if got is None:
            out["problems"].append(f"{code}: '{value}' is not a number (write decimals with a point)")
        return got

    for row in rows[head + 1:]:
        found = re.search(r"(BB-\d+)\s*$", str(row[0] or ""))
        if not found:
            continue
        code = found.group(1)
        name = str(row[0])[:found.start()].strip()
        drivers = str(row[1] or "").strip()
        before = len(out["problems"])
        lo, hi = figure(row[col_low], code), figure(row[col_high], code)
        if len(out["problems"]) > before:
            continue
        if lo is None and hi is None:
            out["empty"].append({"block": code, "name": name})
            continue
        lo, hi = lo or hi, hi or lo
        if lo[0] > hi[1]:
            out["problems"].append(f"{code}: the low figure {num(lo[0])} is above the high figure {num(hi[1])}")
            continue
        out["rates"].append({"block": code, "name": name, "drivers": drivers, "low": lo[0], "high": hi[1],
                             "rate": span(lo[0], hi[1])})
    return out


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

    import layout

    p = Path(a.project)
    print(f"Inventory of {p.as_posix()}")
    docs_dir = layout.docs_dir(p)
    docs = sorted(x.name for x in docs_dir.glob("*") if x.is_file()) if docs_dir.exists() else []
    print(f"\nDocuments in {layout.shown(p, docs_dir)}/: {len(docs)}")
    for d in docs:
        print(f"  {d}")
    spec_file = layout.spec_file(p)
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
        print(f"\nNo spec yet: count from the brief or scope of work in {layout.shown(p, docs_dir)}/.")
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
    earlier = sorted(layout.estimates_source(p).glob("*.json")) if layout.estimates_source(p).exists() else []
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
    import layout

    p = Path(a.project)
    folder = layout.estimates_source(p)
    if a.file:
        path = Path(a.file)
        if not path.exists():
            path = folder / a.file
    else:
        found = sorted(folder.glob("*.json"), key=newest_first_key) if folder.exists() else []
        if not found:
            sys.exit(f"No estimate in {folder}")
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
    import layout

    path, est, res = load_estimate(a)
    # Beside its .json source in a project in the old layout; in the new one, the Excel file goes into
    # "Internal – estimates and change requests" and the source stays in _blueprint/estimates/.
    out = layout.estimate_xlsx(a.project, path) if path.parent.resolve() == layout.estimates_source(a.project).resolve() else path.with_suffix(".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    typed = rates_typed(out)
    if typed and not a.force:
        sys.exit(f"Rates were typed into the Rates needed sheet of {out.name} ({plural(typed, 'building block')}): writing it "
                 f"again would lose them. Nothing was written. Take them in first with: python -I tools/estimate.py "
                 f"rates-from \"{out}\", or add --force to write it anyway (the filled-in file is then kept beside it).")
    if typed:
        kept = out.with_name(f"{out.stem} - rates kept {dt.datetime.now().strftime('%Y-%m-%d %H%M')}.xlsx")
        try:
            os.replace(out, kept)
        except PermissionError:
            sys.exit(f"Cannot move {out.name} aside: close it in Excel and run this again. Nothing was written.")
        print(f"  The workbook with the typed rates is kept as {kept.name}")
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
    print("Effort divided by the team: it assumes the work can be shared out and nobody waits. These mandays stay")
    print("internal: only weeks go into the timeline, with the scope of work's mandays (never these) per item.")
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


def cmd_rates_from(a):
    found = read_rates_sheet(a.workbook)
    if a.json:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return
    name = Path(a.workbook).name
    if found["rates"]:
        print(f"Rates filled in on {name}" + (f", for {found['platform']}" if found["platform"] else "") + ":")
        print("| ID | Building block | What drives the effort | Rate (MD) | Confidence |")
        for x in found["rates"]:
            print(f"| {x['block']} | {x['name']} | {x['drivers']} | {x['rate']} | low |")
    else:
        print(f"No rates are filled in on {name} yet.")
    if found["empty"]:
        print("Not filled in: " + ", ".join(f"{x['block']} {x['name']}".strip() for x in found["empty"]))
    for problem in found["problems"]:
        print(f"Not read: {problem}")
    if found["rates"]:
        print("To save them, put each rate in the Rate (MD) cell of its row in knowledge/building-blocks.md, "
              "low confidence, once the user agrees; then render the estimate again.")


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
    r.add_argument("--force", action="store_true",
                   help="write the Excel file even when rates were typed into its Rates needed sheet (that file is kept beside it)")
    r.set_defaults(fn=cmd_render)
    w = sub.add_parser("weeks")
    w.add_argument("project")
    w.add_argument("file", nargs="?")
    w.add_argument("--team", type=float, required=True, help="people working on it at the same time")
    w.add_argument("--days", type=float, default=5, help="working days a week per person (default 5)")
    w.set_defaults(fn=cmd_weeks)
    f = sub.add_parser("rates-from")
    f.add_argument("workbook", help="an estimate's Excel file with its Rates needed sheet filled in")
    f.add_argument("--json", action="store_true", help="print the rates as JSON")
    f.set_defaults(fn=cmd_rates_from)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
