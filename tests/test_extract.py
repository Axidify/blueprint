"""tools/extract.py: where it writes, and that it never deletes what is not its own."""
import json
import sys

import pytest

import support

import extract


def run(monkeypatch, document, out):
    monkeypatch.setattr(sys, "argv", ["extract.py", str(document), str(out)])
    extract.main()


@pytest.fixture
def notes(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Workshop notes\nApproval levels: TBC\nReports, if applicable\n", encoding="utf-8")
    return path


def test_text_is_extracted_with_its_open_items_counted(notes, tmp_path, monkeypatch, capsys):
    out = tmp_path / "reviews" / "first" / "extract"
    run(monkeypatch, notes, out)
    assert (out / "text.md").read_text(encoding="utf-8").startswith("Workshop notes")
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["counts"]["open_item_markers"] == 2 and [o["line"] for o in meta["open_items"]] == [2, 3]
    assert (out / "images").is_dir()
    assert "Open-item markers (TBC/TBD/if applicable): 2" in capsys.readouterr().out


def test_a_folder_with_other_files_is_refused_and_left_alone(notes, tmp_path, monkeypatch):
    """It used to delete the whole output folder before writing. Pointed at a project's docs/ by mistake,
    that deleted the client's documents."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "2026-11-01 signed SOW.pdf").write_bytes(b"%PDF the client's document")
    (docs / "2026-11-03 brief.docx").write_bytes(b"PK brief")
    with pytest.raises(SystemExit) as stop:
        run(monkeypatch, notes, docs)
    message = str(stop.value)
    assert "already holds files that are not an earlier extraction" in message and "2026-11-01 signed SOW.pdf" in message
    assert "Nothing was touched" in message and "reviews/<review>/extract" in message
    assert sorted(p.name for p in docs.iterdir()) == ["2026-11-01 signed SOW.pdf", "2026-11-03 brief.docx"]
    assert (docs / "2026-11-01 signed SOW.pdf").read_bytes() == b"%PDF the client's document"


def test_an_earlier_extraction_is_replaced_and_its_neighbours_kept(notes, tmp_path, monkeypatch):
    out = tmp_path / "extract"
    run(monkeypatch, notes, out)
    (out / "images" / "img01.png").write_bytes(b"from the first run")
    (out / "pages").mkdir()
    (out / "pages" / "p001.png").write_bytes(b"from the first run")
    (out / "review-notes.md").write_text("my notes on this extraction", encoding="utf-8")
    notes.write_text("Second version of the notes\n", encoding="utf-8")
    run(monkeypatch, notes, out)
    assert (out / "text.md").read_text(encoding="utf-8") == "Second version of the notes\n"
    assert not (out / "images" / "img01.png").exists() and not (out / "pages").exists(), "the earlier run's pictures are gone"
    assert (out / "review-notes.md").read_text(encoding="utf-8") == "my notes on this extraction", "a file that is not its own stays"


def test_an_empty_folder_and_a_new_folder_are_both_fine(notes, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    for out in (empty, tmp_path / "new" / "deep" / "extract"):
        run(monkeypatch, notes, out)
        assert (out / "text.md").is_file()


def test_a_folder_whose_meta_file_is_something_else_is_refused(notes, tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    (other / "meta.json").write_text(json.dumps({"title": "not an extraction"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not an earlier extraction"):
        run(monkeypatch, notes, other)
    assert json.loads((other / "meta.json").read_text(encoding="utf-8")) == {"title": "not an extraction"}


def test_a_missing_document_or_an_unsupported_one_stops_before_the_folder_is_touched(notes, tmp_path, monkeypatch):
    out = tmp_path / "extract"
    run(monkeypatch, notes, out)
    before = (out / "text.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="No such document"):
        run(monkeypatch, tmp_path / "missing.docx", out)
    slides = tmp_path / "slides.pptx"
    slides.write_bytes(b"PK")
    with pytest.raises(SystemExit, match="Unsupported file type: .pptx"):
        run(monkeypatch, slides, out)
    assert (out / "text.md").read_text(encoding="utf-8") == before, "the earlier extraction is still there"


def test_a_generated_document_is_extracted_with_its_headings_tables_and_pictures(example, tmp_path, monkeypatch):
    out = tmp_path / "docx" / "extract"
    run(monkeypatch, example.path, out)
    text = (out / "text.md").read_text(encoding="utf-8")
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert "## 1 Users and access" in text and "| Role | Responsibility | Sees |" in text
    assert meta["counts"]["images"] >= len(example.shots) and (out / "images" / "img01.png").is_file()


# ---------------------------------------------------------------------- spreadsheets and text encodings
def test_a_spreadsheet_formula_is_extracted_with_its_calculated_value(tmp_path, monkeypatch):
    """A scope of work totals its mandays with a formula. It was extracted as "=SUM(B2:B3)" only, so the
    figure a comparison needs was missing."""
    import openpyxl

    sheet = tmp_path / "sow.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SOW"
    for row in (["Item", "Mandays"], ["Booking module", 10], ["Reports", 5], ["Total", "=SUM(B2:B3)"]):
        ws.append(row)
    wb.save(sheet)
    real = openpyxl.load_workbook

    def as_excel_saved_it(path, data_only=False, **kw):
        """openpyxl does not calculate: stand in for the value Excel stores beside a formula."""
        book = real(path, data_only=data_only, **kw)
        if data_only:
            book["SOW"]["B4"].value = 15
        return book

    monkeypatch.setattr(openpyxl, "load_workbook", as_excel_saved_it)
    out = tmp_path / "extract"
    run(monkeypatch, sheet, out)
    lines = (out / "text.md").read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "A4=Total | B4=15 (formula =SUM(B2:B3))"
    assert lines[2] == "A2=Booking module | B2=10", "a plain cell is as before"


def test_a_formula_with_no_stored_value_says_so(tmp_path, monkeypatch):
    import openpyxl

    sheet = tmp_path / "sow.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Total", "=SUM(B2:B3)"])
    wb.save(sheet)  # written by a program, never opened in Excel: nothing calculated
    out = tmp_path / "extract"
    run(monkeypatch, sheet, out)
    assert "B1==SUM(B2:B3) (a formula; the file holds no calculated value for it)" in (out / "text.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("encoding, named", [("utf-8", "utf-8"), ("utf-8-sig", "utf-8"), ("cp1252", "windows-1252"), ("utf-16", "utf-16")])
def test_a_text_file_is_read_whatever_it_was_saved_as(tmp_path, monkeypatch, encoding, named):
    """A file saved by an older editor in the Windows encoding used to stop the extraction."""
    path = tmp_path / "notes.txt"
    path.write_bytes("Café meeting – notes\r\nApproval: TBC\r\n".encode(encoding))
    out = tmp_path / "extract"
    run(monkeypatch, path, out)
    assert (out / "text.md").read_text(encoding="utf-8") == "Café meeting – notes\nApproval: TBC\n"
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["metadata"] == {"encoding": named}


# ---------------------------------------------------------------------- the numbers Word shows but does not store
NUMBERED = support.ROOT / "tests" / "fixtures" / "word-numbering"


def test_headings_and_lists_carry_the_numbers_word_shows(tmp_path, monkeypatch):
    """The fixture was built by Microsoft Word with automatic numbering (headings 1, 1.1, 1.1.1, a roman
    list, a lettered list and a second roman list that starts again), and numbers.json is what Word itself
    reported as the number in front of each paragraph. Word stores none of those numbers in the text, so
    they used to be missing from the extraction and a finding could not say "section 2.1"."""
    out = tmp_path / "extract"
    run(monkeypatch, NUMBERED / "numbered.docx", out)
    lines = [line.lstrip("#- ").strip() for line in (out / "text.md").read_text(encoding="utf-8").splitlines() if line.strip()]
    word = json.loads((NUMBERED / "numbers.json").read_text(encoding="utf-8"))
    assert len(word) == 21 and sum(1 for w in word if w["label"]) == 18
    for paragraph in word:
        expected = f"{paragraph['label']} {paragraph['text']}".strip()
        assert expected in lines, expected
    text = (out / "text.md").read_text(encoding="utf-8")
    assert "## 2 Requirements" in text and "### 2.1 Roles" in text and "#### 2.1.2 Requester" in text
    assert "- III. LIST-A third" in text and "- b) LIST-B second" in text
    assert "- I. LIST-C first" in text, "a list that starts again starts again"
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["counts"]["numbered_headings"] == 11


def numbering(levels, nums, styles=""):
    """A Numbering built from hand-written definitions: levels is [(format, text, start)], nums {numId: start override or None}."""
    import io
    import zipfile

    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    lvls = "".join(f'<w:lvl w:ilvl="{i}"><w:start w:val="{start}"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/></w:lvl>'
                   for i, (fmt, text, start) in enumerate(levels))
    insts = "".join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="0"/>'
                    + (f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="{over}"/></w:lvlOverride>' if over else "") + "</w:num>"
                    for n, over in nums.items())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/numbering.xml", f'<w:numbering {w}><w:abstractNum w:abstractNumId="0">{lvls}</w:abstractNum>{insts}</w:numbering>')
        z.writestr("word/styles.xml", f"<w:styles {w}>{styles}</w:styles>")
    return extract.Numbering(zipfile.ZipFile(buffer))


def para(num_id=None, ilvl=None):
    from xml.etree import ElementTree as ET

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    inner = ""
    if num_id is not None:
        inner = f'<w:pPr xmlns:w="{w}"><w:numPr>' + (f'<w:ilvl w:val="{ilvl}"/>' if ilvl is not None else "") + f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>'
    return ET.fromstring(f'<w:p xmlns:w="{w}">{inner}</w:p>')


def test_number_styles_and_levels():
    n = numbering([("decimal", "%1.", 1), ("lowerLetter", "%1.%2)", 1), ("lowerRoman", "(%3)", 1)], {"1": None})
    seen = [n.label(para("1", level), "") for level in (0, 1, 1, 2, 2, 0, 1)]
    assert seen == ["1.", "1.a)", "1.b)", "(i)", "(ii)", "2.", "2.a)"], "a deeper level starts again under each new parent"


def test_a_level_reached_before_its_parent_shows_zero_as_word_does():
    n = numbering([("decimal", "%1", 1), ("decimal", "%1.%2", 1)], {"1": None})
    assert [n.label(para("1", level), "") for level in (1, 0, 1)] == ["0.1", "1", "1.1"]


def test_a_start_value_and_a_restart():
    n = numbering([("upperLetter", "Appendix %1", 3)], {"1": None, "2": 1})
    assert [n.label(para("1", 0), "") for _ in range(2)] == ["Appendix C", "Appendix D"], "the list starts at its start value"
    assert n.label(para("2", 0), "") == "Appendix A", "an instance with a start override starts again"
    assert n.label(para("2", 0), "") == "Appendix B"
    assert n.label(para("1", 0), "") == "Appendix C", "and the count is one for all instances of the definition, as in Word"


def test_bullets_no_numbering_and_unknown_lists_give_no_number():
    n = numbering([("bullet", "\u2022", 1)], {"1": None})
    assert n.label(para("1", 0), "") == "" and n.label(para(), "") == "" and n.label(para("0", 0), "") == "" and n.label(para("9", 0), "") == ""


def test_a_paragraph_takes_its_numbering_from_its_style_and_from_the_style_it_is_based_on():
    w = "w:style w:type=\"paragraph\""
    styles = (f'<{w} w:styleId="Clause"><w:pPr><w:numPr><w:numId w:val="1"/></w:numPr></w:pPr></w:style>'
              f'<{w} w:styleId="SubClause"><w:basedOn w:val="Clause"/><w:pPr><w:numPr><w:ilvl w:val="1"/></w:numPr></w:pPr></w:style>'
              f'<{w} w:styleId="Plain"></w:style>')
    n = numbering([("decimal", "%1", 1), ("decimal", "%1.%2", 1)], {"1": None}, styles)
    assert [n.label(para(), style) for style in ("Clause", "SubClause", "SubClause", "Plain", "Clause")] == ["1", "1.1", "1.2", "", "2"]


@pytest.mark.parametrize("n, upper_roman, letter", [(1, "I", "A"), (4, "IV", "D"), (9, "IX", "I"), (14, "XIV", "N"), (26, "XXVI", "Z"),
                                                     (27, "XXVII", "AA"), (40, "XL", "NN"), (1994, "MCMXCIV", None)])
def test_roman_numerals_and_letters(n, upper_roman, letter):
    assert extract.roman(n) == upper_roman
    if letter:
        assert extract.letters(n) == letter


def test_a_document_with_typed_numbers_is_left_as_it_is(example, tmp_path, monkeypatch):
    """Blueprint's own documents have their section numbers typed into the heading: nothing is added twice."""
    out = tmp_path / "extract"
    run(monkeypatch, example.path, out)
    text = (out / "text.md").read_text(encoding="utf-8")
    assert "## 1 Users and access" in text and "## 1 1 Users and access" not in text
    assert json.loads((out / "meta.json").read_text(encoding="utf-8"))["counts"]["numbered_headings"] == 0

