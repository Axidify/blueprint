"""tools/document_format.py: showing the format in effect (with any mistakes in it), reading a sample
document, and that the tools still run on the oldest Python that setup accepts."""
import ast
import sys

import pytest

import support

import document_format
import generate_requirements


@pytest.fixture
def show(capsys):
    def run():
        try:
            document_format.show()
            code = 0
        except SystemExit as stop:
            code = stop.code
        return code, capsys.readouterr().out

    return run


def test_show_prints_the_format_in_effect(temp_workspace, show):
    (temp_workspace / "branding").mkdir()
    (temp_workspace / "branding" / "document-format.yaml").write_text('colors:\n  accent: "#0b6e4f"\nnumbering: decimal\n', encoding="utf-8")
    code, out = show()
    assert code == 0 and "MISTAKES" not in out
    assert "document-format.yaml" in out.splitlines()[1], "it names the company's file"
    assert "accent: 0B6E4F" in out and "numbering: decimal" in out
    assert "body: Geist" in out, "the settings the company did not change keep the defaults"


def test_show_without_a_company_file_says_so(temp_workspace, show):
    code, out = show()
    assert code == 0 and "# Overrides: none" in out


def test_show_lists_the_mistakes_and_fails(temp_workspace, show):
    (temp_workspace / "branding").mkdir()
    (temp_workspace / "branding" / "document-format.yaml").write_text("colours:\n  accent: 0A66C2\nnumbering: roman\n", encoding="utf-8")
    code, out = show()
    assert code == 1
    assert "MISTAKES in the format" in out
    assert "'colours' is not a setting (did you mean 'colors'?)" in out and "numbering: 'roman' must be plain or decimal" in out


def test_learn_reads_a_sample_document(capsys):
    document_format.learn(str(support.ROOT / "templates" / "document-template.docx"))
    out = capsys.readouterr().out
    assert "Theme fonts:" in out and "Normal style:" in out and "Page:             21.0 x 29.7 cm" in out
    assert "Chapters (Heading 1):" in out


def test_learn_reports_what_a_generated_document_uses(example, capsys):
    document_format.learn(str(example.path))
    out = capsys.readouterr().out
    assert "Geist" in out
    assert "1 Users and access" in out and "Client acknowledgement and sign-off" in out


def formatted_values_with_a_backslash(path):
    """Lines of a Python file where an f-string has a backslash inside its braces: allowed from Python 3.12."""
    source = path.read_text(encoding="utf-8")
    return sorted({node.lineno for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FormattedValue)
                   and "\\" in (ast.get_source_segment(source, node.value) or "")})


@pytest.mark.skipif(sys.version_info < (3, 12), reason="on an older Python a file with this syntax does not even import")
def test_the_tools_use_no_syntax_newer_than_python_3_10():
    """Setup, the docs and the machine check accept Python 3.10. document_format.py had f-strings that only
    3.12 can read, so none of its commands started on 3.10 or 3.11."""
    found = {path.name: lines for path in sorted((support.ROOT / "tools").glob("*.py")) if (lines := formatted_values_with_a_backslash(path))}
    assert found == {}


@pytest.mark.skipif(sys.version_info < (3, 12), reason="an older Python cannot parse the example at all")
def test_the_backslash_check_finds_one(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('import re\nx = f"{re.findall(r\'\\d+\', \'a1\')}"\n', encoding="utf-8")
    assert formatted_values_with_a_backslash(bad) == [2]


def test_the_default_format_lists_every_setting_the_generator_reads():
    fmt = generate_requirements.default_format()
    assert set(fmt) == {"document", "fonts", "sizes", "colors", "tables", "numbering", "layout", "header_footer", "front", "chapters",
                        "titles", "labels", "required"}
    assert set(fmt["tables"]) == {"header_fill", "header_text", "borders"} and "heading" in fmt["colors"]


def heading_sample(path, *titles):
    """A Word file with these chapter headings, made with python-docx."""
    from docx import Document

    doc = Document()
    for title in titles:
        doc.add_heading(title, level=1)
    doc.save(str(path))
    return path


def test_learn_prints_chapter_names_as_written(tmp_path, capsys):
    """"&" was printed as "&amp;", the way the file stores it."""
    sample = heading_sample(tmp_path / "sample.docx", "Disclaimer, Confidentiality & Concept Acknowledgement", "Scope <draft> – \"v1\"")
    document_format.learn(str(sample))
    out = capsys.readouterr().out
    assert "  - Disclaimer, Confidentiality & Concept Acknowledgement" in out and "&amp;" not in out
    assert '  - Scope <draft> – "v1"' in out


@pytest.mark.parametrize("name, content, said", [
    ("sample.pdf", b"%PDF-1.7", "sample.pdf is a PDF. learn reads the fonts, colours and chapters from a Word file (.docx). "
                               "Ask for the Word version of the sample document"),
    ("sample.doc", b"\xd0\xcf\x11\xe0", "sample.doc is a Word 97-2003 file (.doc). learn reads the fonts, colours and chapters from a "
                                       "Word file (.docx). Open it in Word and save it as a Word Document (.docx)"),
    ("sample.docx", b"not a zip at all", "sample.docx could not be read as a Word document"),
    (None, None, "No file at "),
])
def test_learn_says_plainly_what_it_cannot_read(tmp_path, name, content, said):
    """A PDF sample ended in a BadZipFile traceback."""
    path = tmp_path / (name or "missing.docx")
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(SystemExit) as stop:
        document_format.learn(str(path))
    assert said in str(stop.value)


def test_learn_prints_a_dash_on_an_old_windows_code_page(tmp_path):
    """Run as a person runs it: on a console with an old code page, "–" in a chapter name could stop the run
    or come out as "?"."""
    import subprocess

    sample = heading_sample(tmp_path / "sample.docx", "Scope – what is included ●")
    r = subprocess.run([sys.executable, "-I", str(support.ROOT / "tools" / "document_format.py"), "learn", str(sample)],
                       capture_output=True, timeout=60)  # a pipe: cp1252 on Windows
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "  - Scope – what is included ●" in r.stdout.decode("utf-8")
