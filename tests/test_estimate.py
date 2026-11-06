"""tools/estimate.py: rates from the knowledge base, the figures of an estimate, and the commands.

Every test has a knowledge base of its own in a temp folder, or reads the starter one in templates/. None
uses knowledge/ in the app folder, which is a link into the workspace. Projects are made in temp folders
from the made-up sample, and the Excel file is only ever written there.
"""
import copy
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

import support

import estimate

PLATFORM = "Sample Platform"
STARTER = support.ROOT / "templates" / "knowledge"
SAMPLE_ESTIMATE = sorted((support.EXAMPLE / "estimates").glob("*.json"))[-1]
INTERNAL = "Internal: not for the client"

BLOCKS = """# Building blocks for estimating

A rate is mandays per unit.

## Platform: Sample Platform

| ID | Building block | What drives the effort | Rate (MD) | Confidence |
|---|---|---|---|---|
| BB-01 | Simple form | Fields | 4 | high |
| BB-02 | Multi-page form | Pages | 4 | medium |
| BB-03 | Approval step | Routing rule | 4 | low |
| BB-04 | List with filters | Columns | 2–4 | medium |
| BB-05 | E-mail notification | Template | 0.5 to 1 | high |
| BB-06 | Environment migration | Environments | 1 per migration | high |
| BB-07 | Integration, per endpoint | Mapping | TBD | – |
| BB-08 | Dashboard | Status counts | 6 | – |

## Platform: Other Platform

| ID | Building block | What drives the effort | Rate (MD) | Confidence |
|---|---|---|---|---|
| BB-01 | Simple form | Fields | 10–20 | high |

## Other work

| ID | Item | Share or mandays | Notes |
|---|---|---|---|
| OW-01 | Project management | 10–15% | |
| OW-02 | Requirement workshops | 2–3 MD | |
| OW-03 | Internal testing | TBD | |

## Calibration notes

| BB-99 | A table row outside a platform section is not a building block | – | 9 | high |
"""

LOG = """# Projects log

| Project | Platform | Phase | Team | Dev estimate (MD) | Dev actual (MD) | Notes |
|---|---|---|---|---|---|---|
"""
# Three delivered projects on the platform (one in two phases, one written in lower case) and one elsewhere.
DELIVERED = [("Sample One", PLATFORM), ("Sample One", PLATFORM), ("Sample Two", PLATFORM.lower()),
             ("Sample Three", PLATFORM), ("Sample Four", "Other Platform")]


# ---------------------------------------------------------------------- helpers
def write_knowledge(folder, blocks=BLOCKS, delivered=DELIVERED):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "building-blocks.md").write_text(blocks, encoding="utf-8")
    rows = "".join(f"| {name} | {platform} | {i} | 2 | 40 | 44 | |\n" for i, (name, platform) in enumerate(delivered, 1))
    (folder / "projects-log.md").write_text(LOG + rows, encoding="utf-8")
    return folder


def starter_knowledge(folder, rates=None, shares=None):
    """A copy of the starter knowledge base, with rates and shares filled in the way a lead developer would."""
    folder.mkdir(parents=True)
    text = (STARTER / "building-blocks.md").read_text(encoding="utf-8")
    for block_id, (rate, confidence) in (rates or {}).items():
        text, found = re.subn(rf"^(\| {block_id} \|.*\|) TBD \| – \|$", rf"\1 {rate} | {confidence} |", text, flags=re.M)
        assert found == 1, f"{block_id} is not an unset row of the starter building blocks"
    for other_id, share in (shares or {}).items():
        text, found = re.subn(rf"^(\| {other_id} \|[^|]*\|) TBD \|", rf"\1 {share} |", text, flags=re.M)
        assert found == 1, f"{other_id} is not an unset row of the starter Other work table"
    (folder / "building-blocks.md").write_text(text, encoding="utf-8")
    shutil.copy(STARTER / "projects-log.md", folder / "projects-log.md")
    return folder


@pytest.fixture(autouse=True)
def no_workspace_knowledge(tmp_path, monkeypatch):
    """A test that forgets to name a knowledge folder gets the starter one, never the workspace's."""
    monkeypatch.setattr(estimate, "ROOT", tmp_path / "app")


@pytest.fixture
def kb(tmp_path):
    return write_knowledge(tmp_path / "knowledge")


def block(line_id, block_id, count=1, **more):
    return {"id": line_id, "item": f"Item {line_id}", "block": block_id, "count": count, **more}


def fixed(line_id, low, high, **more):
    return {"id": line_id, "item": f"Item {line_id}", "md": [low, high], **more}


def estimate_of(*lines, **keys):
    """An estimate with these lines; keys replace or add top-level keys, None removes one."""
    est = {"project": "Sample Booking System", "platform": PLATFORM, "date": "2026-11-06", "basis": "spec v0.1",
           "basis_kind": "spec", "lines": list(lines), "assumptions": ["One approval level."]}
    for key, value in keys.items():
        if value is None:
            est.pop(key, None)
        else:
            est[key] = value
    return est


def work_out(kb, est, project=None):
    """The figures of an estimate that must pass the checks."""
    res, errors = estimate.compute(est, project or kb / "no-project", kb)
    assert errors == []
    return res


def errors_of(kb, est):
    return estimate.compute(est, kb / "no-project", kb)[1]


def line(res, line_id):
    return next(l for l in res["lines"] if l["id"] == line_id)


def mandays(res, line_id):
    return line(res, line_id)["low"], line(res, line_id)["high"]


def rate(res, line_id):
    return line(res, line_id)["rate_low"], line(res, line_id)["rate_high"]


def register_project(folder, *items):
    """A project folder holding only a register with these items."""
    folder.mkdir(parents=True, exist_ok=True)
    reg = {"project": "Sample Booking System", "client": "Sample Client Sdn. Bhd.",
           "items": [{"id": f"R-{i:03d}", "finding": f"Finding {i}", "status": "open", **it} for i, it in enumerate(items, 1)]}
    (folder / "register.json").write_text(json.dumps(reg), encoding="utf-8")
    return folder


def sample_project(folder, est=None, name=SAMPLE_ESTIMATE.name):
    """The made-up sample as a project in a temp folder, with the sample estimate (or `est`) in estimates/."""
    project = support.make_project(folder)
    (project / "estimates").mkdir()
    if est is None:
        shutil.copy(SAMPLE_ESTIMATE, project / "estimates" / name)
    else:
        (project / "estimates" / name).write_text(json.dumps(est), encoding="utf-8")
    return project


def snapshot(folder, skip=()):
    """{file: digest} of everything in a folder, to show that a command left it alone."""
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(folder).rglob("*")) if p.is_file() and p.relative_to(folder).parts[0] not in skip}


def sheet_rows(ws):
    return [[cell if cell is not None else "" for cell in row] for row in ws.iter_rows(values_only=True)]


@pytest.fixture
def run(monkeypatch, capsys):
    """Run `estimate.py --knowledge <folder> <args>` and return what it printed."""
    def call(knowledge, *args):
        monkeypatch.setattr(sys, "argv", ["estimate.py", "--knowledge", str(knowledge), *map(str, args)])
        estimate.main()
        return capsys.readouterr().out
    return call


# ====================================================================== rates from the knowledge base
@pytest.mark.parametrize("cell, expected", [
    ("TBD", None), ("–", None), ("", None),
    ("4", (4, 4)), ("2–4", (2, 4)), ("2-4", (2, 4)), ("1.5 – 2.5 MD", (1.5, 2.5)), ("0.5 to 1", (0.5, 1)),
    ("1 per migration", (1, 1)), ("2–3 per 10 fields", (2, 3)), ("10–15%", (10, 15)),
])
def test_rate_cell_is_read_as_written(cell, expected):
    assert estimate.parse_rate(cell) == expected
    assert estimate.rate_problem(cell) is None


@pytest.mark.parametrize("cell, expected", [
    ("3 (was 5)", (3, 3)), ("2 (calibrated on 3 projects)", (2, 2)), ("0.5 MD each (2023 rate)", (0.5, 0.5)),
    ("2–4, see BB-07", (2, 4)), ("about 2 to 3 days", (2, 3)), ("~3", (3, 3)), ("approx. 1.5", (1.5, 1.5)),
])
def test_only_the_figure_a_rate_cell_starts_with_counts(cell, expected):
    """Every number in the cell used to be collected, so a note turned a single rate into a range:
    "3 (was 5)" was read as 3 to 5 mandays, and "0.5 MD each (2023 rate)" as 0.5 to 2023."""
    assert estimate.parse_rate(cell) == expected
    assert estimate.rate_problem(cell) is None


@pytest.mark.parametrize("cell", ["1,5", "from 2", "up to 4", "1,5–2,5", "MD: 3"])
def test_a_rate_that_cannot_be_read_is_not_guessed(cell):
    """A decimal comma used to read as a range ("1,5" as 1 to 5). Now the cell is not priced, and says why."""
    assert estimate.parse_rate(cell) is None
    assert "is not a number or a range such as 2–4" in estimate.rate_problem(cell) and cell in estimate.rate_problem(cell)


def test_a_line_whose_rate_cannot_be_read_is_not_priced_and_says_why(tmp_path, capsys, monkeypatch):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "building-blocks.md").write_text(
        "## Platform: Joget DX\n\n| ID | Building block | What drives the effort | Rate (MD) | Confidence |\n|---|---|---|---|---|\n"
        "| BB-01 | Form | Fields | 1,5 | medium |\n| BB-02 | List | Columns | 2–4 | medium |\n\n"
        "## Other work\n\n| ID | Work | Share |\n|---|---|---|\n| OW-01 | Project management | 10,5% |\n", encoding="utf-8")
    est = {"project": "P", "platform": "Joget DX", "date": "2026-11-06", "basis": "spec v0.1", "basis_kind": "spec",
           "assumptions": ["One developer."],
           "lines": [{"id": "L01", "item": "Forms", "block": "BB-01", "count": 2}, {"id": "L02", "item": "Lists", "block": "BB-02", "count": 1},
                     {"id": "L03", "item": "Project management", "other": "OW-01"}]}
    res, errors = estimate.compute(est, tmp_path, kb)
    assert errors == []
    by_id = {l["id"]: l for l in res["lines"]}
    assert not by_id["L01"]["priced"] and "cannot be read ('1,5' is not a number or a range" in by_id["L01"]["rate_from"]
    assert not by_id["L03"]["priced"] and "the share in building-blocks.md cannot be read ('10,5%'" in by_id["L03"]["rate_from"]
    assert by_id["L02"]["priced"] and res["total"] == (2, 4), "the readable line is priced as before"
    monkeypatch.setattr(sys, "argv", ["estimate.py", "--knowledge", str(kb), "blocks", "Joget DX"])
    estimate.main()
    out = capsys.readouterr().out
    assert "BB-01  Form  [RATE NOT READ: '1,5' is not a number or a range" in out and "OW-01  Project management  [SHARE NOT READ: '10,5%'" in out


def test_the_newest_estimate_is_the_one_with_the_latest_date_then_the_highest_version(tmp_path):
    """It went by the file name as text, so on one day "spec v0.9" counted as newer than "spec v0.10"."""
    folder = tmp_path / "estimates"
    folder.mkdir()
    names = ["2026-11-06 estimate from spec v0.9.json", "2026-11-06 estimate from spec v0.10.json", "2026-11-06 estimate from brief.json",
             "2026-10-30 estimate from spec v0.20.json", "2026-11-07 estimate from sow.json"]
    for name in names:
        (folder / name).write_text("{}", encoding="utf-8")
    ordered = [p.name for p in sorted(folder.glob("*.json"), key=estimate.newest_first_key)]
    assert ordered == ["2026-10-30 estimate from spec v0.20.json", "2026-11-06 estimate from brief.json",
                       "2026-11-06 estimate from spec v0.9.json", "2026-11-06 estimate from spec v0.10.json", "2026-11-07 estimate from sow.json"]
    (folder / "2026-11-07 estimate from sow.json").unlink()
    assert sorted(folder.glob("*.json"), key=estimate.newest_first_key)[-1].name == "2026-11-06 estimate from spec v0.10.json"


def test_an_estimate_file_without_a_date_in_its_name_is_ordered_by_the_date_inside(tmp_path):
    folder = tmp_path / "estimates"
    folder.mkdir()
    (folder / "first try.json").write_text(json.dumps({"date": "2026-11-09"}), encoding="utf-8")
    (folder / "2026-11-06 estimate from spec v0.1.json").write_text("{}", encoding="utf-8")
    assert sorted(folder.glob("*.json"), key=estimate.newest_first_key)[-1].name == "first try.json"


def test_blocks_come_from_the_platform_section(kb):
    blocks, platforms = estimate.read_blocks(PLATFORM, kb)
    assert platforms == [PLATFORM, "Other Platform"]
    assert list(blocks) == [f"BB-0{n}" for n in range(1, 9)], "BB-99 sits outside a platform section"
    assert blocks["BB-04"] == {"name": "List with filters", "drivers": "Columns", "rate": (2, 4), "rate_problem": None,
                               "confidence": "medium"}
    assert blocks["BB-07"]["rate"] is None and blocks["BB-07"]["confidence"] is None

    other, _ = estimate.read_blocks("other platform", kb)  # the platform name is matched without regard to case
    assert {block_id: b["rate"] for block_id, b in other.items()} == {"BB-01": (10, 20)}
    assert estimate.read_blocks("Nowhere", kb) == ({}, [PLATFORM, "Other Platform"])


@pytest.mark.parametrize("block_id, per_unit, rate_from, calibrated", [
    ("BB-01", (3.6, 4.4), "knowledge base (high confidence)", True),      # high: -10% to +10%
    ("BB-02", (3, 5), "knowledge base (medium confidence)", True),        # medium: -25% to +25%
    ("BB-03", (3, 6), "knowledge base (low confidence)", False),          # low: -25% to +50%
    ("BB-08", (4.5, 9), "knowledge base (low confidence)", False),        # no confidence given counts as low
    ("BB-06", (0.9, 1.1), "knowledge base (high confidence)", True),      # "1 per migration" is a single figure too
])
def test_single_figure_is_widened_by_its_confidence(kb, block_id, per_unit, rate_from, calibrated):
    res = work_out(kb, estimate_of(block("L01", block_id, count=2)))
    assert rate(res, "L01") == pytest.approx(per_unit)
    assert mandays(res, "L01") == pytest.approx((per_unit[0] * 2, per_unit[1] * 2))
    assert line(res, "L01")["rate_from"] == rate_from
    assert line(res, "L01")["calibrated"] is calibrated


@pytest.mark.parametrize("block_id, per_unit", [("BB-04", (2, 4)), ("BB-05", (0.5, 1))])
def test_range_is_used_as_written(kb, block_id, per_unit):
    res = work_out(kb, estimate_of(block("L01", block_id, count=3)))
    assert rate(res, "L01") == per_unit, "a range is not widened again"
    assert mandays(res, "L01") == (per_unit[0] * 3, per_unit[1] * 3)
    assert line(res, "L01")["block_name"] in ("List with filters", "E-mail notification")


def test_block_without_a_rate_is_counted_but_not_priced(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5), block("L02", "BB-07", count=3)))
    unpriced = line(res, "L02")
    assert unpriced["priced"] is False and unpriced["count"] == 3
    assert mandays(res, "L02") == (0, 0) and rate(res, "L02") == (None, None)
    assert unpriced["rate_from"] == "no rate set: not priced"
    assert [l["id"] for l in res["unpriced"]] == ["L02"]
    assert res["total"] == (10, 20), "the total covers the priced lines only"
    assert res["blocks_used"] == ["BB-04", "BB-07"] and res["blocks_without_rate"] == ["BB-07"]


def test_rate_depends_on_the_platform(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-01", count=2), platform="Other Platform"))
    assert mandays(res, "L01") == (20, 40)
    assert errors_of(kb, estimate_of(block("L01", "BB-04"), platform="Other Platform")) == [
        "L01: BB-04 is not a building block for Other Platform in building-blocks.md"]


def test_platform_missing_from_the_knowledge_base_prices_nothing(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-01"), fixed("L02", 2, 4), platform="Nowhere"))
    assert res["platform_known"] is False and res["platforms"] == [PLATFORM, "Other Platform"]
    assert line(res, "L01")["priced"] is False
    assert res["total"] == (2, 4) and res["confidence"] == "low"


def test_knowledge_folder_without_files_prices_nothing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    res = work_out(empty, estimate_of(block("L01", "BB-01"), {"id": "L02", "item": "Project management", "other": "OW-01"}))
    assert [l["id"] for l in res["unpriced"]] == ["L01", "L02"]
    assert res["projects_logged"] == [] and res["other_work"] == {} and res["confidence"] == "low"


def test_other_work_table(kb):
    assert estimate.read_other_work(kb) == {
        "OW-01": {"name": "Project management", "share": (10, 15), "rate_problem": None, "unit": "percent"},
        "OW-02": {"name": "Requirement workshops", "share": (2, 3), "rate_problem": None, "unit": "md"},
        "OW-03": {"name": "Internal testing", "share": None, "rate_problem": None, "unit": "percent"}}


def test_delivered_projects_are_counted_once_each(kb):
    on_platform, everyone = estimate.logged_projects(PLATFORM, kb)
    assert on_platform == {"Sample One", "Sample Two", "Sample Three"}, "two phases of one project count once"
    assert everyone == on_platform | {"Sample Four"}
    assert estimate.logged_projects("Nowhere", kb)[0] == set()


def test_knowledge_folder_defaults_to_the_app_folder_then_the_starter(tmp_path):
    assert estimate.knowledge_dir("elsewhere") == Path("elsewhere")
    assert estimate.knowledge_dir() == STARTER, "no knowledge/ folder yet: the starter knowledge base"
    (tmp_path / "app" / "knowledge").mkdir(parents=True)
    assert estimate.knowledge_dir() == tmp_path / "app" / "knowledge"


# ====================================================================== provisional rates, shares, totals
def test_provisional_rate_prices_a_block_that_has_none(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-07", count=3, rate=[2, 4], rate_note="Given by the lead developer")))
    assert mandays(res, "L01") == (6, 12) and rate(res, "L01") == (2, 4)
    assert line(res, "L01")["rate_from"] == "provisional"
    assert line(res, "L01")["priced"] is True and line(res, "L01")["calibrated"] is False
    assert res["blocks_without_rate"] == ["BB-07"], "the knowledge base still has no rate for it"


def test_provisional_rate_overrides_the_knowledge_base(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-01", count=2, rate=[5, 8])))
    assert mandays(res, "L01") == (10, 16)
    assert line(res, "L01")["rate_from"] == "provisional (overrides the knowledge base)"
    assert line(res, "L01")["calibrated"] is False, "a figure given for one estimate is not a calibrated rate"


@pytest.mark.parametrize("given, error", [
    ("2-4", "L01: rate must be [low, high] mandays per unit"),
    ([2, 3, 4], "L01: rate must be [low, high] mandays per unit"),
    ([4, 2], "L01: rate low must not be above rate high"),
    ([-1, 2], "L01: rate low must not be above rate high"),
])
def test_provisional_rate_must_be_a_range(kb, given, error):
    assert errors_of(kb, estimate_of(block("L01", "BB-07", rate=given))) == [error]


def test_percent_line_is_a_share_of_the_building_blocks_only(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5), fixed("L02", 3, 6),
                                   {"id": "L03", "item": "Testing", "percent": [10, 20]}))
    assert mandays(res, "L03") == (1, 4), "10% of the low end of the blocks, 20% of their high end; L02 is not a block"
    assert line(res, "L03")["rate_from"] == "10 – 20% of building blocks"
    assert line(res, "L02")["rate_from"] == "lead developer's figure"


def test_other_work_takes_its_share_from_the_knowledge_base(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5),
                                   {"id": "L02", "item": "Project management", "other": "OW-01"},
                                   {"id": "L03", "item": "Workshops", "other": "OW-02"},
                                   {"id": "L04", "item": "Testing", "other": "OW-03"}))
    assert mandays(res, "L02") == (1, 3) and line(res, "L02")["rate_from"] == "10 – 15% of building blocks, knowledge base"
    assert mandays(res, "L03") == (2, 3) and line(res, "L03")["rate_from"] == "knowledge base"
    assert line(res, "L04")["priced"] is False and line(res, "L04")["rate_from"] == "no share set: not priced"
    assert errors_of(kb, estimate_of(fixed("L01", 1, 2), {"id": "L02", "item": "Training", "other": "OW-09"})) == [
        "L02: OW-09 is not in the Other work table of building-blocks.md"]


def test_totals_add_the_low_ends_and_the_high_ends(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5), block("L02", "BB-05", count=4), fixed("L03", 3, 6),
                                   {"id": "L04", "item": "Testing", "percent": [10, 20]},
                                   {"id": "L05", "item": "Workshops", "other": "OW-02"}))
    assert res["build"] == (12, 24)
    assert res["other"] == pytest.approx((3 + 1.2 + 2, 6 + 4.8 + 3))
    assert res["total"] == pytest.approx((18.2, 37.8))
    assert [d[0] for d in res["drivers"]] == ["L01", "L04", "L03", "L02", "L05"], "the widest lines first"


# ====================================================================== open questions (risks)
def test_sized_risk_widens_the_high_end_only(kb):
    lines = (block("L01", "BB-04", count=5), fixed("L02", 3, 6))
    plain = work_out(kb, estimate_of(*lines))
    res = work_out(kb, estimate_of(*lines, risks=[{"item": "A second approval level", "md": [0, 4]},
                                                  {"ref": "R-012", "item": "Reports may grow", "note": "Not sized yet"}]))
    assert res["total"] == plain["total"] == (13, 26), "risks stay out of the total"
    assert res["risk"] == (0, 4)
    assert [(r["id"], r["sized"], r["low"], r["high"]) for r in res["risks"]] == [("K01", True, 0, 4), ("R-012", False, 0, 0)]
    assert ("K01", "A second approval level", 4) in res["drivers"]
    assert "R-012" not in [d[0] for d in res["drivers"]], "an unsized question adds no mandays"


def test_questions_are_ordered_by_the_range_they_cover(kb):
    res = work_out(kb, estimate_of(
        block("L01", "BB-04", count=5), fixed("L02", 3, 6), risks=[{"item": "A second approval level", "md": [0, 4]}],
        questions=[{"question": "Narrows nothing"}, {"question": "Narrows L02", "narrows": ["L02"]},
                   {"question": "Narrows L01 and the risk", "source": "GP-02", "narrows": ["L01", "K01"]}]))
    assert [(q["question"], q["addresses"]) for q in res["questions"]] == [
        ("Narrows L01 and the risk", 14), ("Narrows L02", 3), ("Narrows nothing", 0)]


@pytest.mark.parametrize("risk, error", [
    ({"md": [0, 4]}, "risk #1: needs item, and md must be [low, high] when given"),
    ({"item": "Reports may grow", "md": "a lot"}, "risk #1: needs item, and md must be [low, high] when given"),
    ({"item": "Reports may grow", "md": [4, 0]}, "risk #1: needs item, and md must be [low, high] when given"),
    ({"item": "Reports may grow", "ref": "L01"}, "risk L01: id already used"),
])
def test_risk_checks(kb, risk, error):
    assert errors_of(kb, estimate_of(fixed("L01", 1, 2), risks=[risk])) == [error]


# ====================================================================== against the scope of work
SOW_LINES = [
    {"ref": "1", "item": "Lists", "mandays": 5},
    {"ref": "2", "item": "Data migration", "mandays": 30},
    {"ref": "3", "item": "Reports", "mandays": 6},
    {"ref": "4", "item": "Training", "mandays": 7},
    {"ref": "5", "item": "Integration", "mandays": 9},
    {"ref": "6", "item": "Hosting", "mandays": "TBC"},
]


def sow_estimate():
    return estimate_of(
        block("L01", "BB-04", count=5, sow_ref="1"),   # 10–20 against 5
        fixed("L02", 3, 6, sow_ref=2),                 # 3–6 against 30; a number matches the SOW's "2"
        fixed("L03", 3, 6, sow_ref="3"),               # with L04: 4–8 against 6
        fixed("L04", 1, 2, sow_ref="3"),
        block("L05", "BB-07", count=2, sow_ref="5"),   # no rate
        fixed("L06", 2, 3, sow_ref="6"),               # the SOW has no figure
        fixed("L07", 4, 9),                            # not sold
        block("L08", "BB-07"),                         # not sold and no rate
        sow={"source": "docs/2026-11-02 SOW.xlsx", "lines": copy.deepcopy(SOW_LINES)})


def test_scope_of_work_is_compared_line_by_line(kb):
    res = work_out(kb, sow_estimate())
    by_line = {c["lines"] or c["ref"]: c for c in res["comparison"]}
    assert by_line["L01"] == {"ref": "1", "item": "Lists", "sow": 5, "low": 10, "high": 20, "lines": "L01",
                              "verdict": "Scope of work is 5 MD below the low end", "diff": -5}
    assert by_line["L02"]["verdict"] == "Scope of work is 24 MD above the high end" and by_line["L02"]["diff"] == 24
    assert by_line["L03, L04"]["verdict"] == "Within the range" and (by_line["L03, L04"]["low"], by_line["L03, L04"]["high"]) == (4, 8)
    assert by_line["4"]["verdict"] == "Not estimated: no line of the estimate covers it" and by_line["4"]["sow"] == 7
    assert by_line["L05"]["verdict"] == "Cannot compare: L05 not priced"
    assert by_line["L06"]["verdict"] == "No mandays in the scope of work"
    assert by_line["L07"] == {"ref": "–", "item": "Item L07", "sow": None, "low": 4, "high": 9, "lines": "L07",
                              "verdict": "Not in the scope of work", "diff": -4}
    assert by_line["L08"]["verdict"] == "Not in the scope of work (not priced)"
    assert len(res["comparison"]) == 8


def test_largest_differences_come_first(kb):
    res = work_out(kb, sow_estimate())
    assert [c["lines"] or c["ref"] for c in res["comparison"]][:3] == ["L02", "L01", "L07"]
    assert all(c["diff"] == 0 for c in res["comparison"][3:])


def test_scope_of_work_totals(kb):
    res = work_out(kb, sow_estimate())
    assert res["sow_total"] == 57, "every line with a figure"
    assert res["sow_covered"] == 41, "only the lines this estimate prices in full: 1, 2 and 3"


@pytest.mark.parametrize("sold, verdict", [
    (9, "Scope of work is 1 MD below the low end"), (10, "Within the range"), (20, "Within the range"),
    (20.5, "Scope of work is 0.5 MD above the high end"),
])
def test_ends_of_the_range_count_as_within(kb, sold, verdict):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5, sow_ref="1"),
                                   sow={"lines": [{"ref": "1", "item": "Lists", "mandays": sold}]}))
    assert res["comparison"][0]["verdict"] == verdict


def test_no_scope_of_work_no_comparison(kb):
    res = work_out(kb, estimate_of(block("L01", "BB-04", count=5, sow_ref="1")))
    assert res["comparison"] == [] and res["sow_total"] is None and res["sow_covered"] is None


def test_line_must_point_at_a_line_of_the_scope_of_work(kb):
    est = estimate_of(block("L01", "BB-04", sow_ref="9"), sow={"lines": [{"ref": "1", "item": "Lists", "mandays": 5}]})
    assert errors_of(kb, est) == ["L01: sow_ref '9' is not a line of the scope of work"]


# ====================================================================== confidence
CALIBRATED = block("L01", "BB-04", count=5)  # 10–20 MD at a medium-confidence rate


def test_high_confidence_needs_every_rule_met(kb):
    res = work_out(kb, estimate_of(CALIBRATED))
    assert res["confidence"] == "high"
    assert res["reasons"] == ["The rates are calibrated, the count comes from the spec and no high-severity question is open."]
    assert res["projects_logged"] == ["Sample One", "Sample Three", "Sample Two"] and res["uncalibrated_share"] == 0


@pytest.mark.parametrize("delivered, words", [(0, "0 delivered projects"), (1, "1 delivered project "), (2, "2 delivered projects")])
def test_fewer_than_three_delivered_projects_is_low(tmp_path, delivered, words):
    kb = write_knowledge(tmp_path / "knowledge", delivered=[(f"Sample {n}", PLATFORM) for n in range(delivered)]
                         + [("Sample Four", "Other Platform")] * 3)
    res = work_out(kb, estimate_of(CALIBRATED))
    assert res["confidence"] == "low"
    assert res["reasons"] == [f"The rates rest on {words.strip()} on {PLATFORM}. Until 3 are logged, every estimate is low-confidence."]


@pytest.mark.parametrize("kind, level", [("brief", "low"), ("sow", "low"), ("notes", "low"), ("spec", "high"),
                                         ("requirements-document", "high")])
def test_counting_before_the_requirements_are_known_is_low(kb, kind, level):
    res = work_out(kb, estimate_of(CALIBRATED, basis_kind=kind))
    assert res["confidence"] == level
    assert ("before the requirements are known" in " ".join(res["reasons"])) == (level == "low")


def test_line_not_priced_is_low(kb):
    res = work_out(kb, estimate_of(CALIBRATED, block("L02", "BB-07")))
    assert res["confidence"] == "low"
    assert res["reasons"] == ["1 of 2 lines have no rate or share set and are not priced: the total leaves them out, "
                              "so it is not the whole project."]


@pytest.mark.parametrize("high_end, level", [(5, "high"), (6, "medium"), (20, "medium"), (21, "low")])
def test_share_of_uncalibrated_mandays_caps_the_level(kb, high_end, level):
    """L01 is 20 MD at its high end, so the lead developer's figure is 20%, 23%, 50% and 51% of the mandays."""
    res = work_out(kb, estimate_of(CALIBRATED, fixed("L02", 1, high_end)))
    assert res["confidence"] == level
    assert res["uncalibrated_share"] == pytest.approx(high_end / (20 + high_end))
    assert ("not rates calibrated from delivered projects" in " ".join(res["reasons"])) == (level != "high")


@pytest.mark.parametrize("uncalibrated", [block("L02", "BB-03", count=4), block("L02", "BB-07", count=4, rate=[3, 6])])
def test_low_confidence_and_provisional_rates_count_as_uncalibrated(kb, uncalibrated):
    res = work_out(kb, estimate_of(CALIBRATED, uncalibrated))  # 24 MD of 44 at the high end
    assert res["confidence"] == "low" and res["uncalibrated_share"] == pytest.approx(24 / 44)
    assert res["reasons"][0].startswith("55% of the priced mandays use low-confidence rates")


def test_percent_lines_do_not_count_towards_the_share(kb):
    res = work_out(kb, estimate_of(CALIBRATED, {"id": "L02", "item": "Testing", "percent": [50, 300]}))
    assert res["confidence"] == "high" and res["uncalibrated_share"] == 0


def test_open_high_severity_item_caps_at_medium(kb, tmp_path):
    project = register_project(tmp_path / "project", {"severity": "high"}, {"severity": "medium", "effort_impact": "high"},
                               {"severity": "low"}, {"severity": "high", "status": "resolved"})
    res = work_out(kb, estimate_of(CALIBRATED), project)
    assert res["confidence"] == "medium"
    assert res["reasons"] == ["1 high-severity register item is still open."]
    assert [it["id"] for it in res["register_flagged"]] == ["R-001", "R-002"], "open, and high severity or a real effort impact"


def test_closed_and_minor_register_items_leave_the_level_alone(kb, tmp_path):
    project = register_project(tmp_path / "project", {"severity": "high", "status": "resolved"},
                               {"severity": "high", "status": "wont-fix"}, {"severity": "medium", "effort_impact": "high"})
    res = work_out(kb, estimate_of(CALIBRATED), project)
    assert res["confidence"] == "high" and [it["id"] for it in res["register_flagged"]] == ["R-003"]


def test_estimator_can_lower_the_level(kb):
    res = work_out(kb, estimate_of(CALIBRATED, confidence="medium"))
    assert res["confidence"] == "medium" and res["reasons"] == ["The estimator set the confidence to medium."]
    res = work_out(kb, estimate_of(CALIBRATED, confidence="low", confidence_reason="The integration is new to the team."))
    assert res["confidence"] == "low" and res["reasons"] == ["The integration is new to the team."]


def test_estimator_cannot_raise_the_level(kb):
    res = work_out(kb, estimate_of(CALIBRATED, basis_kind="brief", confidence="high"))
    assert res["confidence"] == "low"


def test_lowest_rule_wins(kb, tmp_path):
    project = register_project(tmp_path / "project", {"severity": "high"})
    res = work_out(kb, estimate_of(CALIBRATED, fixed("L02", 1, 6), basis_kind="notes"), project)
    assert res["confidence"] == "low"
    assert len(res["reasons"]) == 3, "every rule that applies is given as a reason"


# ====================================================================== checks on the estimate file
def test_good_estimate_has_no_errors(kb):
    assert errors_of(kb, sow_estimate()) == []


@pytest.mark.parametrize("key", ["project", "platform", "date", "basis", "basis_kind", "lines", "assumptions"])
def test_missing_key_is_rejected(kb, key):
    assert f"missing {key}" in errors_of(kb, estimate_of(CALIBRATED, **{key: None}))


def test_empty_assumptions_are_rejected(kb):
    assert errors_of(kb, estimate_of(CALIBRATED, assumptions=[])) == ["missing assumptions"]


def test_unknown_basis_kind_is_rejected(kb):
    errors = errors_of(kb, estimate_of(CALIBRATED, basis_kind="guess"))
    assert errors == ["basis_kind 'guess' not in ['brief', 'sow', 'notes', 'spec', 'requirements-document']"]


def test_unknown_block_is_rejected(kb):
    assert errors_of(kb, estimate_of(CALIBRATED, block("L02", "BB-42"))) == [
        f"L02: BB-42 is not a building block for {PLATFORM} in building-blocks.md"]


def test_duplicate_id_is_rejected(kb):
    assert errors_of(kb, estimate_of(CALIBRATED, fixed("L01", 1, 2))) == ["L01: duplicate id"]


def test_missing_rate_is_not_an_error(kb):
    """A block with no rate in the knowledge base and none given is listed, not rejected: nothing is invented."""
    res, errors = estimate.compute(estimate_of(block("L01", "BB-07", count=4)), kb / "no-project", kb)
    assert errors == []
    assert res["total"] == (0, 0) and [l["id"] for l in res["unpriced"]] == ["L01"]


@pytest.mark.parametrize("ranges", [[(5, 5)], [(5, 5), (2, 2)]])
def test_total_that_is_a_single_number_is_rejected(kb, ranges):
    lines = [fixed(f"L0{n}", low, high) for n, (low, high) in enumerate(ranges, 1)]
    assert errors_of(kb, estimate_of(*lines)) == [
        "the total is a single number: an estimate is a range, so give the lines a low and a high end"]


def test_one_line_with_a_range_is_enough(kb):
    assert errors_of(kb, estimate_of(fixed("L01", 5, 5), fixed("L02", 2, 3))) == []


@pytest.mark.parametrize("bad, error", [
    ({"id": "L02", "item": "Nothing to price"}, "L02: needs exactly one of block (with count), other, md or percent"),
    ({"id": "L02", "item": "Two ways", "block": "BB-04", "count": 1, "md": [1, 2]},
     "L02: needs exactly one of block (with count), other, md or percent"),
    ({"id": "L02", "item": "No count", "block": "BB-04"}, "L02: count must be a number above 0"),
    ({"id": "L02", "item": "Zero", "block": "BB-04", "count": 0}, "L02: count must be a number above 0"),
    ({"id": "L02", "item": "Text", "block": "BB-04", "count": "three"}, "L02: count must be a number above 0"),
    ({"id": "L02", "item": "Yes", "block": "BB-04", "count": True}, "L02: count must be a number above 0"),
    ({"id": "L02", "item": "Backwards", "md": [6, 3]}, "L02: md must be [low, high] mandays"),
    ({"id": "L02", "item": "Text", "md": "3-6"}, "L02: md must be [low, high] mandays"),
    ({"id": "L02", "item": "Backwards", "percent": [20, 10]}, "L02: percent must be [low, high] percent of the building-block subtotal"),
])
def test_bad_line_is_rejected(kb, bad, error):
    assert errors_of(kb, estimate_of(CALIBRATED, bad)) == [error]


def test_question_checks(kb):
    est = estimate_of(CALIBRATED, questions=[{"source": "GP-02"}, {"question": "Which systems?", "narrows": ["L01", "L09"]}])
    assert errors_of(kb, est) == ["question #1: needs question", "question #2: narrows ['L09'], which are not line or risk ids"]


def test_every_problem_is_reported_at_once(kb):
    est = estimate_of(CALIBRATED, block("L02", "BB-42"), fixed("L01", 1, 2), fixed("L03", 9, 1), basis_kind="guess",
                      assumptions=None)
    assert errors_of(kb, est) == [
        "missing assumptions", "basis_kind 'guess' not in ['brief', 'sow', 'notes', 'spec', 'requirements-document']",
        f"L02: BB-42 is not a building block for {PLATFORM} in building-blocks.md", "L01: duplicate id",
        "L03: md must be [low, high] mandays"]


# ---------------------------------------------------------------------- inputs that once broke the tool
def test_unknown_confidence_is_reported_not_raised(kb):
    assert errors_of(kb, estimate_of(CALIBRATED, confidence="certain")) == ["confidence 'certain' not in ['low', 'medium', 'high']"]


@pytest.mark.parametrize("bad, error", [
    ({"item": "No id", "md": [1, 2]}, "line #2: needs id and item"),
    ({"id": "L02", "md": [1, 2]}, "L02: needs id and item"),
])
def test_line_without_an_id_or_item_is_reported_not_raised(kb, bad, error):
    assert errors_of(kb, estimate_of(CALIBRATED, bad)) == [error]


def test_share_of_an_unpriced_build_is_not_rejected(kb):
    est = estimate_of(block("L01", "BB-07", count=4), {"id": "L02", "item": "Project management", "other": "OW-01"})
    assert errors_of(kb, est) == []


# ====================================================================== the sample estimate
SAMPLE_RATES = {"BB-01": ("3–5", "medium"), "BB-03": ("2–4", "medium"), "BB-06": ("1–2", "high"),
                "BB-12": ("0.5 to 1", "medium"), "BB-18": ("1 per migration", "low")}
SAMPLE_SHARES = {"OW-01": "20–30%"}


@pytest.fixture
def rated(tmp_path):
    """The starter knowledge base with five rates and one share set: the rest of the sample stays not priced."""
    return starter_knowledge(tmp_path / "rated", SAMPLE_RATES, SAMPLE_SHARES)


def sample():
    return json.loads(SAMPLE_ESTIMATE.read_text(encoding="utf-8"))


def test_sample_estimate_carries_no_figures_of_its_own():
    est = sample()
    assert all("rate" not in l and "md" not in l and "percent" not in l for l in est["lines"])
    assert all("md" not in r for r in est["risks"]) and "sow" not in est


def test_sample_against_the_starter_knowledge_base_is_a_count_only():
    res = work_out(STARTER, sample())
    assert len(res["lines"]) == 13 and len(res["unpriced"]) == 13, "the starter knowledge base sets no rate or share"
    assert res["total"] == (0, 0) and res["confidence"] == "low"
    assert res["platform_known"] and res["blocks_without_rate"] == res["blocks_used"]
    assert [r["id"] for r in res["risks"]] == ["K01", "K02", "K03", "K04"] and not any(r["sized"] for r in res["risks"])


def test_starter_knowledge_base_sets_no_figures():
    for platform in estimate.read_blocks("", STARTER)[1]:
        blocks, _ = estimate.read_blocks(platform, STARTER)
        assert blocks and all(b["rate"] is None for b in blocks.values()), f"{platform}: a starter rate would be made up"
    other = estimate.read_other_work(STARTER)
    assert other and all(o["share"] is None for o in other.values())
    assert estimate.logged_projects("Joget DX", STARTER) == (set(), set())


def test_sample_is_priced_where_the_knowledge_base_has_rates(rated):
    res = work_out(rated, sample())
    priced = {l["id"]: (l["low"], l["high"]) for l in res["lines"] if l["priced"]}
    expected = {"L01": (3, 5), "L02": (2, 4), "L03": (2, 4), "L04": (3, 6), "L08": (2, 4), "L11": (1.5, 3), "L13": (2.7, 7.8)}
    # Line by line: newer pytest versions refuse approx() on a dictionary whose values are pairs.
    assert sorted(priced) == sorted(expected)
    for line, pair in expected.items():
        assert priced[line] == pytest.approx(pair), line
    assert [l["id"] for l in res["unpriced"]] == ["L05", "L06", "L07", "L09", "L10", "L12"]
    assert res["build"] == (13.5, 26) and res["total"] == pytest.approx((16.2, 33.8))
    assert res["confidence"] == "low" and len(res["reasons"]) == 2, "no delivered project, and lines not priced"
    assert res["uncalibrated_share"] == pytest.approx(3 / 26), "only L11 rests on a low-confidence rate"
    assert [d[0] for d in res["drivers"]] == ["L13", "L04", "L01", "L02", "L03", "L08", "L11"]
    assert res["questions"][0]["source"] == "building-blocks" and res["questions"][0]["addresses"] == pytest.approx(16.1)
    assert [q["source"] for q in res["questions"][1:]] == ["GP-04", "GP-03", "GP-08", "GP-02", "GP-03", "GP-12"]


# ====================================================================== the commands: blocks
def test_blocks_command_lists_rates_shares_and_evidence(kb, run):
    out = run(kb, "blocks", PLATFORM).splitlines()
    for expected in (
            "BB-01  Simple form  [4 MD per unit, high confidence]  driven by: Fields",
            "BB-04  List with filters  [2 – 4 MD per unit, medium confidence]  driven by: Columns",
            "BB-05  E-mail notification  [0.5 – 1 MD per unit, high confidence]  driven by: Template",
            "BB-07  Integration, per endpoint  [no rate yet]  driven by: Mapping",
            "BB-08  Dashboard  [6 MD per unit, low confidence]  driven by: Status counts",
            "OW-01  Project management  [10 – 15%]",
            "OW-02  Requirement workshops  [2 – 3 MD]",
            "OW-03  Internal testing  [not set: left out]",
            f"Delivered projects logged on {PLATFORM}: 3 (Sample One, Sample Three, Sample Two); on any platform: 4. "
            "Below 3, every estimate is low-confidence."):
        assert expected in out
    assert any(l.startswith("7 of 8 building blocks have a rate.") for l in out)
    assert not any(l.startswith("BB-99") for l in out)


def test_blocks_command_names_the_platforms_it_does_have(kb, run):
    out = run(kb, "blocks", "Nowhere")
    assert "No building blocks for 'Nowhere'" in out and f"Platforms there: {PLATFORM}, Other Platform." in out
    assert "0 of 0 building blocks have a rate." in out
    assert "Delivered projects logged on Nowhere: 0; on any platform: 4." in out


def test_blocks_command_on_the_starter_knowledge_base(run):
    out = run(STARTER, "blocks", "Joget DX")
    listed = [l for l in out.splitlines() if l.startswith("BB-")]
    assert listed and all("[no rate yet]" in l for l in listed)
    assert f"0 of {len(listed)} building blocks have a rate." in out
    assert "Delivered projects logged on Joget DX: 0; on any platform: 0." in out


def test_blocks_command_without_an_other_work_table(tmp_path, run):
    kb = write_knowledge(tmp_path / "knowledge", blocks=BLOCKS.split("## Other work")[0])
    assert "Other work: no 'Other work' table in building-blocks.md, so nothing is added around the build." in run(kb, "blocks", PLATFORM)


# ====================================================================== the commands: inventory
def test_inventory_of_the_sample_project(tmp_path, kb, run):
    project = sample_project(tmp_path / "leave-request")
    (project / "docs").mkdir()
    (project / "docs" / "2026-11-02 brief.txt").write_text("A made-up brief.", encoding="utf-8")
    out = run(kb, "inventory", project).splitlines()
    assert out[0] == f"Inventory of {project.as_posix()}"
    for expected in (
            "Documents in docs/: 1", "  2026-11-02 brief.txt",
            "Spec v0.1, platform Joget DX",
            "Roles: 3 (Employee, Line Manager, HR Admin)", "Statuses: 5",
            "Screens: 7 (1 dashboard, 2 detail, 1 form, 2 list, 1 login)",
            "  login [login] for everyone: –",
            "  my-applications [dashboard] for employee: 4 stat cards; list: 6 columns, 2 filters, 1 row actions",
            "  new-application [form] for employee: 1 page, 7 fields, 1 file, 1 calculated, 2 with a validation rule",
            "  review-application [detail] for manager: shows the fields of new-application, read-only; opens reject-dialog, approve-dialog",
            "Dialogs: 3", "  reject-dialog: 1 fields", "  cancel-dialog: confirmation only",
            "Integrations: 2", "  Active Directory (Inbound): User sign-in and line manager lookup",
            "Notifications: 0 (none listed; check the requirements for e-mails)",
            "Requirements: 3 groups, 10 items, 0 waiting on a decision",
            "NFRs: 4; timeline in the spec: no",
            "Register: no items",
            f"Earlier estimates: {SAMPLE_ESTIMATE.name}"):
        assert expected in out


def test_inventory_lists_the_register_items_that_can_move_the_estimate(tmp_path, kb, run):
    project = support.make_project(tmp_path / "wide", support.WIDE)
    out = run(kb, "inventory", project).splitlines()
    for expected in (
            "Spec v1.2, platform Joget DX", "Statuses: 6",
            "  new-booking [form] for requester: 2 pages, 9 fields, 1 signature, 2 with a validation rule",
            "Process flow: 4 steps (Submit booking, Approve, Issue equipment, Record return)",
            "Notifications: 2", "Requirements: 3 groups, 6 items, 1 waiting on a decision",
            "NFRs: 2; timeline in the spec: yes",
            "Register: 3 open (1 high, 2 medium, 0 low)",
            "  R-001 [high, GP-02] The brief does not say what happens when two bookings overlap."):
        assert expected in out
    assert not any(l.startswith(("  R-002", "  R-003", "  R-004")) for l in out), "medium without an effort impact, or resolved"
    assert not any(l.startswith("Earlier estimates") for l in out)


def test_inventory_before_there_is_a_spec(tmp_path, kb, run):
    project = register_project(tmp_path / "early", {"severity": "medium", "effort_impact": "high", "category": "GP-10"})
    out = run(kb, "inventory", project)
    assert "No spec yet: count from the brief or scope of work in docs/." in out
    assert "Documents in docs/: 0" in out
    assert "  R-001 [medium, high effort impact, GP-10] Finding 1" in out


# ====================================================================== the commands: render
def full_estimate():
    """One of everything: a priced block, a block with no rate, a figure, a share, risks, a SOW, questions."""
    return estimate_of(
        block("L01", "BB-04", count=5, group="Lists", sow_ref="1", note="Five lists."),
        block("L02", "BB-07", count=2, group="Integration", sow_ref="2"),
        fixed("L03", 3, 6, note="Given by the lead developer."),
        {"id": "L04", "item": "Project management", "other": "OW-01", "sow_ref": "3"},
        project="Equipment Booking System", sources=["spec/app.yaml v1.2", "register.json"],
        risks=[{"ref": "R-001", "item": "Overlapping bookings need a rule", "md": [0, 4]}, {"item": "Reports may grow"}],
        gap_patterns=[{"id": "GP-02", "why": "No rule for overlapping bookings."}],
        questions=[{"question": "Which systems must it exchange data with?", "source": "GP-10", "narrows": ["L02"]},
                   {"question": "May two bookings overlap?", "source": "R-001", "narrows": ["R-001", "L01"]}],
        sow={"source": "docs/2026-11-02 SOW.xlsx", "lines": [{"ref": "1", "item": "Forms and lists", "mandays": 5},
                                                             {"ref": "2", "item": "Integration", "mandays": 9},
                                                             {"ref": "3", "item": "Project management", "mandays": 2}]})


def full_project(folder, est=None):
    """A temp project with the fixture's register (R-002 given an effort impact) and one estimate file."""
    reg = json.loads((support.WIDE / "register.json").read_text(encoding="utf-8"))
    reg["items"][1]["effort_impact"] = "high"
    (folder / "estimates").mkdir(parents=True)
    (folder / "register.json").write_text(json.dumps(reg), encoding="utf-8")
    path = folder / "estimates" / "2026-11-06 estimate from spec v1.2.json"
    path.write_text(json.dumps(est or full_estimate()), encoding="utf-8")
    return path


@pytest.fixture
def rendered(tmp_path, kb, run):
    """The full estimate rendered in a temp project: (what was printed, the workbook)."""
    path = full_project(tmp_path / "project")
    out = run(kb, "render", tmp_path / "project")
    return out, load_workbook(path.with_suffix(".xlsx"))


def test_render_reports_the_figures(rendered, tmp_path):
    """The full estimate has a building block with no rate: it leads with that, and gives no total."""
    out = rendered[0].splitlines()
    for expected in (
            f"Estimate for Equipment Booking System ({PLATFORM}), counted from spec v0.1",
            "  The build is not priced: 1 of 2 building-block lines have no rate yet, so there is no total for the project yet.",
            "  Priced so far (not a project figure):",
            "    Building blocks: 10 – 20 MD (1 of 2 lines)",
            "    Other work:      4 – 9 MD (shares of the building blocks are understated: they cover the priced lines only)",
            "    Open questions answered the costly way would add up to 4 MD more",
            "  Not priced (1 of 4 lines, left out of the figures above):",
            "    - L02 Item L02: 2 x BB-07 Integration, per endpoint",
            "  Open questions not sized: 1 (K02)",
            "  Confidence: low",
            "    - 1 of 4 lines have no rate or share set and are not priced: the total leaves them out, so it is not the whole project.",
            "    - 1 high-severity register item is still open.",
            "    - L01 Item L01: 10 MD of range",
            "  Scope of work (16 MD in all): 2 of 3 lines cannot be compared yet, because the build is not priced:",
            "    - 2 Integration (9 MD)",
            "    - 3 Project management (2 MD)",
            "  Lines that can be compared now:",
            "    - 1 Forms and lists: 5 MD against 10 – 20 MD. Scope of work is 5 MD below the low end",
            "    - – Item L03: not in the SOW against 3 – 6 MD. Not in the scope of work",
            "    - (14 MD) May two bookings overlap?",
            "    - Which systems must it exchange data with?",
            f"Wrote {tmp_path / 'project' / 'estimates' / '2026-11-06 estimate from spec v1.2.xlsx'}",
            INTERNAL + "."):
        assert expected in out
    assert not any("Total" in line for line in out), "with the build not priced, nothing reads as a total"


def test_a_priced_build_still_gives_a_total(tmp_path, kb, run):
    """Only an unpriced building block takes the total away: an unpriced item of other work leaves it, said so."""
    est = full_estimate()
    est["lines"][1] = fixed("L02", 2, 4, sow_ref="2")
    path = full_project(tmp_path / "project", est)
    out = run(kb, "render", tmp_path / "project").splitlines()
    assert "  Total: 16 – 33 MD" in out and "  With open questions answered the costly way: up to 37 MD" in out
    assert "  Scope of work: 16 MD for the lines this estimate prices (16 MD in all), against 16 – 33 MD" in out
    assert not any("build is not priced" in line for line in out)
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(load_workbook(path.with_suffix(".xlsx"))["Summary"]) if r[0]}
    assert summary["Total, as understood today"][:2] == (16, 33)


def test_workbook_sheets_are_all_marked_internal(rendered):
    wb = rendered[1]
    assert wb.sheetnames == ["Summary", "Estimate", "Against SOW", "Uncertainty", "Assumptions", "Questions"]
    for ws in wb:
        assert ws.oddHeader.center.text == INTERNAL, f"{ws.title} must print with the internal warning on every page"
    assert wb["Summary"]["A1"].value == "Estimate: Equipment Booking System" and wb["Summary"]["A2"].value == INTERNAL


def test_summary_sheet(rendered):
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(rendered[1]["Summary"]) if r[0]}
    assert summary["The build is not priced"] == ("", "", "1 of 2 building-block lines have no rate yet, so there is no "
                                                  "total for the project: the figures below are what is priced so far")
    assert summary["Building blocks, priced lines only"] == (10, 20, "1 of 2 lines")
    assert summary["Other work"] == (4, 9, "Shares of the building blocks are understated: they cover the priced lines only")
    assert summary["Priced so far (not a project figure)"] == (14, 29, "Leaves out the lines not priced")
    assert summary["Lines not priced (no rate or share set)"] == (1, "", "L02: left out of the figures above")
    assert summary["Open questions, if answered the costly way"] == (0, 4, "")
    assert not any(str(label).startswith("Total") for label in summary), "no total while the build is not priced"
    assert summary["Scope of work, lines that can be compared"] == (
        5, "", "Compare line by line on the Against SOW sheet; 2 line(s) cannot be compared until the build is priced: 2, 3")
    assert summary["Scope of work, all lines"] == (16, "", "docs/2026-11-02 SOW.xlsx")
    assert summary["Confidence"][0] == "Low"
    assert summary["Delivered projects logged on this platform"][0] == 3
    assert summary["Building blocks used"][0] == 2
    assert summary["… of which have no rate in the knowledge base"] == (1, "", "BB-07")
    assert summary["L01  Item L01"][0] == 10, "the widest line"
    assert "Total, as understood today" not in summary, "with a line not priced, the total must not read as the whole project"
    assert not any(str(label).startswith("Cost at") for label in summary), "no day rate in the company profile, no cost"


def test_estimate_sheet(rendered):
    rows = sheet_rows(rendered[1]["Estimate"])
    assert rows[0] == ["ID", "Group", "Item", "Block", "Building block", "Count", "Rate low", "Rate high", "Rate from",
                       "MD low", "MD high", "SOW ref", "Notes"]
    assert rows[1] == ["L01", "Lists", "Item L01", "BB-04", "List with filters", 5, 2, 4,
                       "knowledge base (medium confidence)", 10, 20, "1", "Five lists."]
    assert rows[2] == ["L02", "Integration", "Item L02", "BB-07", "Integration, per endpoint", 2, "", "",
                       "no rate set: not priced", "", "", "2", ""], "a line not priced shows no mandays, not zero"
    assert [(r[0] or r[2], r[9], r[10]) for r in rows[3:]] == [
        ("Subtotal: building blocks", 10, 20), ("L03", 3, 6), ("L04", 1, 3), ("Subtotal: other work", 4, 9),
        ("Priced so far (the build is not priced)", 14, 29)]
    assert rows[5][8] == "10 – 15% of building blocks, knowledge base, of the priced ones only: understated while 1 are not priced"


def test_against_sow_sheet(rendered):
    rows = sheet_rows(rendered[1]["Against SOW"])
    assert rows[0] == ["SOW ref", "Scope of work item", "SOW MD", "Estimate low", "Estimate high", "Difference", "Estimate lines"]
    assert rows[1] == ["1", "Forms and lists", 5, 10, 20, "Scope of work is 5 MD below the low end", "L01"]
    assert rows[2] == ["–", "Item L03", "", 3, 6, "Not in the scope of work", "L03"]
    assert {r[0]: r[5] for r in rows[3:5]} == {
        "2": "Cannot compare: L02 not priced",
        "3": "Cannot compare yet: L04 is a share of building blocks that are not all priced"}, "a share of too little is not compared"
    assert rows[5] == ["", "Priced so far (the build is not priced)", 5, 14, 29, "", ""]


def test_uncertainty_sheet(rendered):
    rows = sheet_rows(rendered[1]["Uncertainty"])
    assert [(r[0], r[1]) for r in rows[1:] if r[0] != "Why"] == [
        ("Confidence", ""), ("Open question, sized", "R-001"), ("Open question, not sized", "K02"),
        ("Line not priced", "L02"), ("Open register item", "R-002"), ("Gap pattern that applies", "GP-02"),
        ("Building block with no rate yet", "BB-07")], "R-001 is sized as an open question, so it is not listed twice"
    by_ref = {r[1]: r for r in rows if r[1]}
    assert by_ref["R-001"][2:5] == ["Overlapping bookings need a rule", 0, 4]
    assert by_ref["K02"][3:5] == ["", ""]
    assert by_ref["R-002"][2:] == ["No e-mail is listed for the Storekeeper.", "", "", "medium severity, high effort impact"]
    assert len([r for r in rows if r[0] == "Why"]) == 3


def test_assumptions_and_questions_sheets(rendered):
    assert sheet_rows(rendered[1]["Assumptions"])[1:] == [[1, "One approval level."]]
    assert sheet_rows(rendered[1]["Questions"])[1:] == [
        [1, "May two bookings overlap?", "R-001", "R-001, L01", 14],
        [2, "Which systems must it exchange data with?", "GP-10", "L02", 0]]


def test_no_scope_of_work_no_sheet_for_it(tmp_path, kb, run):
    path = full_project(tmp_path / "project", estimate_of(CALIBRATED))
    out = run(kb, "render", tmp_path / "project")
    wb = load_workbook(path.with_suffix(".xlsx"))
    assert wb.sheetnames == ["Summary", "Estimate", "Uncertainty", "Assumptions", "Questions"]
    assert "Scope of work" not in out
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(wb["Summary"]) if r[0]}
    assert summary["Total, as understood today"][:2] == (10, 20)
    assert "Total with open questions" not in summary


def test_cost_uses_the_company_day_rate(tmp_path, kb, run, temp_workspace):
    (temp_workspace / "company.yaml").write_text("name: Sample Company\nday_rate: 1000\ncurrency: XYZ\n", encoding="utf-8")
    path = full_project(tmp_path / "project")
    run(kb, "render", tmp_path / "project")
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(load_workbook(path.with_suffix(".xlsx"))["Summary"]) if r[0]}
    assert summary["Cost at XYZ 1,000 a day"] == ("", "", "Not worked out: the build is not priced")
    est = full_estimate()
    est["lines"][1] = fixed("L02", 2, 4, sow_ref="2")
    path = full_project(tmp_path / "priced", est)
    run(kb, "render", tmp_path / "priced")
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(load_workbook(path.with_suffix(".xlsx"))["Summary"]) if r[0]}
    assert summary["Cost at XYZ 1,000 a day"] == (16000, 37000, "Low end to the high end including open questions")


def test_risk_with_a_low_end_still_widens_the_high_end_only(tmp_path, kb, run):
    est = estimate_of(CALIBRATED, risks=[{"item": "A second approval level", "md": [2, 4]}])
    path = full_project(tmp_path / "project", est)
    run(kb, "render", tmp_path / "project")
    summary = {r[0]: tuple(r[1:3]) for r in sheet_rows(load_workbook(path.with_suffix(".xlsx"))["Summary"]) if r[0]}
    assert summary["Total with open questions"] == (10, 24)


def test_share_of_an_unpriced_build_is_shown_as_not_priced(tmp_path, kb, run):
    est = estimate_of(block("L01", "BB-07", count=4), {"id": "L02", "item": "Project management", "other": "OW-01"})
    path = full_project(tmp_path / "project", est)
    run(kb, "render", tmp_path / "project")
    summary = {r[0]: tuple(r[1:4]) for r in sheet_rows(load_workbook(path.with_suffix(".xlsx"))["Summary"]) if r[0]}
    assert summary["Lines not priced (no rate or share set)"] == (2, "", "L01, L02: left out of the totals")


def test_estimate_that_fails_the_checks_is_not_rendered(tmp_path, kb, run, capsys):
    path = full_project(tmp_path / "project", estimate_of(CALIBRATED, block("L02", "BB-42"), fixed("L01", 1, 2)))
    with pytest.raises(SystemExit) as stop:
        run(kb, "render", tmp_path / "project")
    assert stop.value.code == 1
    out = capsys.readouterr().out
    assert f"{path.name} needs fixing:" in out and "  - L01: duplicate id" in out
    assert f"  - L02: BB-42 is not a building block for {PLATFORM} in building-blocks.md" in out
    assert not path.with_suffix(".xlsx").exists()


def test_render_takes_the_newest_estimate_or_the_one_named(tmp_path, kb, run):
    newest = full_project(tmp_path / "project")
    older = newest.with_name("2026-10-01 estimate from brief.json")
    older.write_text(json.dumps(estimate_of(CALIBRATED, basis="the brief", basis_kind="brief")), encoding="utf-8")

    assert "counted from spec v0.1" in run(kb, "render", tmp_path / "project")
    assert newest.with_suffix(".xlsx").exists() and not older.with_suffix(".xlsx").exists()
    assert "counted from the brief" in run(kb, "render", tmp_path / "project", older.name), "a name alone is looked up in estimates/"
    assert older.with_suffix(".xlsx").exists()
    newest.with_suffix(".xlsx").unlink()
    assert "counted from spec v0.1" in run(kb, "render", tmp_path / "project", newest), "or the path of the file"
    assert newest.with_suffix(".xlsx").exists()


def test_render_needs_an_estimate(tmp_path, kb, run):
    (tmp_path / "bare").mkdir()
    with pytest.raises(SystemExit, match="No estimate in"):
        run(kb, "render", tmp_path / "bare")
    full_project(tmp_path / "project")
    with pytest.raises(SystemExit, match="No estimate file"):
        run(kb, "render", tmp_path / "project", "missing.json")


def test_render_of_the_sample_with_some_rates_set(tmp_path, rated, run):
    project = sample_project(tmp_path / "leave-request")
    out = run(rated, "render", project).splitlines()
    for expected in (
            "Estimate for Leave Request System (Joget DX), counted from spec v0.1",
            "  The build is not priced: 5 of 11 building-block lines have no rate yet, so there is no total for the project yet.",
            "    Building blocks: 13.5 – 26 MD (6 of 11 lines)",
            "    Other work:      2.7 – 7.8 MD (shares of the building blocks are understated: they cover the priced lines only)",
            "  Not priced (6 of 13 lines, left out of the figures above):",
            "    - L05 My Leave Applications dashboard: 1 x BB-07 Operational dashboard",
            "    - L12 Internal testing and fixes before UAT: OW-03",
            "  Open questions not sized: 4 (K01, K02, K03, K04)",
            "  Confidence: low",
            "    - L13 Project management: 5.1 MD of range"):
        assert expected in out
    assert not any("Scope of work" in l or "costly way" in l for l in out), "the sample has no SOW and no sized question"


def test_render_of_the_sample_with_no_rates_is_a_count_only(tmp_path, run):
    project = sample_project(tmp_path / "leave-request")
    out = run(STARTER, "render", project)
    assert "  Nothing is priced: none of the 13 lines has a rate or share. This is a count only." in out
    assert "Total" not in out and "Building blocks:" not in out
    wb = load_workbook(project / "estimates" / SAMPLE_ESTIMATE.with_suffix(".xlsx").name)
    lines = [r for r in sheet_rows(wb["Estimate"])[1:] if r[0]]
    assert len(lines) == 13 and all(r[9] == "" and r[10] == "" for r in lines), "no mandays against any line"


# ====================================================================== estimates stay internal
def test_render_writes_only_its_excel_file_in_the_project(tmp_path, rated, run):
    project = sample_project(tmp_path / "leave-request")
    before, source = snapshot(project), snapshot(support.EXAMPLE)
    run(rated, "render", project)
    after = snapshot(project)
    excel = f"estimates/{SAMPLE_ESTIMATE.with_suffix('.xlsx').name}"
    # Besides the Excel file only the project's overview page (and its mock-up shortcuts) is written, and the page
    # never shows a figure of the estimate (tests/test_overview.py).
    page = {"Project overview.html", "Open the mock-up.cmd", "Open the mock-up.command"}
    assert set(after) - set(before) - page == {excel}
    assert {name: digest for name, digest in after.items() if name not in {excel, *page}} == before, "spec, mock-up and estimate file untouched"
    assert snapshot(support.EXAMPLE) == source, "the sample in the app folder is never written to"


def test_nothing_of_the_estimate_reaches_the_requirements_document(tmp_path, rated, run):
    project = sample_project(tmp_path / "leave-request")
    run(rated, "render", project)
    text = support.all_text(support.generate(project).doc)
    assert "Leave Request System" in text
    for internal in ("manday", "not priced", "estimate from", INTERNAL.lower(), "building block", "day rate"):
        assert internal not in text.lower(), f"'{internal}' belongs to the estimate, not to a client document"
    assert not re.search(r"\bMD\b", text), "mandays never go to the client"
    assert sorted(p.suffix for p in (project / "output").iterdir() if p.is_file()) == [".docx", ".yaml"], "and no Excel file beside it"


def test_estimate_keys_are_not_part_of_the_spec():
    """The estimate's figures live in estimates/ only: neither made-up spec carries mandays, rates or cost."""
    for source in (support.EXAMPLE, support.WIDE):
        text = (source / "spec" / "app.yaml").read_text(encoding="utf-8")
        assert "manday" not in text.lower() and "day_rate" not in text and not re.search(r"\bMD\b", text)


# ====================================================================== the commands: weeks
def test_weeks_per_scope_of_work_line(tmp_path, kb, run):
    full_project(tmp_path / "project")
    out = run(kb, "weeks", tmp_path / "project", "--team", "2").splitlines()
    assert out[0] == "Working weeks for 2 developers, 5 days a week, from 2026-11-06 estimate from spec v1.2.json"
    for expected in (
            "  1 Forms and lists: 10 – 20 MD -> 1 – 2 weeks",
            "  2 Integration: not priced: no weeks",
            "  Item L03 (not in the scope of work): 3 – 6 MD -> 0.5 – 1 weeks",
            "  3 Project management: 1 – 3 MD -> 0.5 weeks  (a share of the build: it usually runs alongside it)",
            "Build in all: 10 – 20 MD -> 1 – 2 weeks",
            "Open questions answered the costly way could add up to 0.5 weeks.",
            "1 of 4 lines are not priced, so these weeks are not the whole project.",
            "Confidence of the estimate: low."):
        assert expected in out


def test_weeks_round_up_to_half_a_week_and_group_without_a_sow(tmp_path, kb, run):
    est = estimate_of(block("L01", "BB-04", count=5, group="Lists"), block("L02", "BB-05", count=2, group="Lists"),
                      fixed("L03", 5, 5))
    full_project(tmp_path / "project", est)
    out = run(kb, "weeks", tmp_path / "project", "--team", "1", "--days", "4").splitlines()
    assert out[0].startswith("Working weeks for 1 developer, 4 days a week")
    assert "  Lists: 11 – 22 MD -> 3 – 5.5 weeks" in out, "11 MD at 4 days a week is 2.75 weeks, rounded up to 3"
    assert "  Item L03: 5 MD -> 1.5 weeks" in out


def test_weeks_needs_a_team(tmp_path, kb, run):
    full_project(tmp_path / "project")
    with pytest.raises(SystemExit, match="--team and --days must be above 0"):
        run(kb, "weeks", tmp_path / "project", "--team", "0")


# ====================================================================== how to read the total
def test_an_estimate_with_many_lines_says_what_the_ends_of_its_total_mean(tmp_path, kb):
    """The total adds every low end and every high end. No narrower figure is given (an estimate is never a
    midpoint or a most-likely number); from five lines with a range, the estimate says what the ends mean."""
    lines = [{"id": f"L{n:02d}", "item": f"Work {n}", "md": [2, 4]} for n in range(1, 6)]
    est = {"project": "P", "platform": PLATFORM, "date": "2026-11-06", "basis": "spec v0.1", "basis_kind": "spec",
           "assumptions": ["One developer."], "lines": lines}
    res, errors = estimate.compute(est, tmp_path, kb)
    assert errors == [] and res["total"] == (10, 20)
    assert res["reading"].startswith("The total adds the low end of every line and the high end of every line. With 5 lines")
    assert "expect the outcome inside the range" in res["reading"] and "not narrowed" in res["reading"]
    fewer, _ = estimate.compute({**est, "lines": lines[:4]}, tmp_path, kb)
    assert fewer["reading"] == "", "with a handful of lines the total needs no explaining"


def test_the_note_on_reading_the_total_is_printed_and_in_the_excel_file(tmp_path, kb, run):
    from openpyxl import load_workbook

    folder = tmp_path / "project" / "estimates"
    folder.mkdir(parents=True)
    est = {"project": "P", "platform": PLATFORM, "date": "2026-11-06", "basis": "spec v0.1", "basis_kind": "spec",
           "assumptions": ["One developer."], "lines": [{"id": f"L{n:02d}", "item": f"Work {n}", "md": [2, 4]} for n in range(1, 7)]}
    path = folder / "2026-11-06 estimate from spec v0.1.json"
    path.write_text(json.dumps(est), encoding="utf-8")
    out = run(kb, "render", tmp_path / "project")
    assert "With 6 lines that each have a range" in out
    sheet = load_workbook(path.with_suffix(".xlsx"))["Uncertainty"]
    notes = [row[2] for row in sheet.iter_rows(values_only=True) if row[0] == "How to read the total"]
    assert len(notes) == 1 and notes[0].startswith("The total adds the low end of every line")

