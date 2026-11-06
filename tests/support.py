"""Helpers shared by the tests: make a project in a temp folder, generate its document, read the result.

Nothing here touches the real workspace. Projects are built in temp folders from the made-up sample in
examples/leave-request/ or from tests/fixtures/, with plain grey images standing in for the mock-up
screenshots (taking real ones needs Node and a browser).
"""
import contextlib
import copy
import io
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import generate_requirements  # noqa: E402
import layout  # noqa: E402  (where everything is in a project folder, in either layout)
import mockup  # noqa: E402

EXAMPLE = ROOT / "examples" / "leave-request"
WIDE = ROOT / "tests" / "fixtures" / "wide-project"
FIELD_HEADER = ["Field", "Type", "Required", "Rule or source"]


# ---------------------------------------------------------------------- projects
def load_spec(source):
    """The spec of a project folder as a dict, for a test to change before making a project from it."""
    return yaml.safe_load(layout.spec_file(source).read_text(encoding="utf-8"))


def write_spec(project, spec):
    layout.spec_dir(project).mkdir(parents=True, exist_ok=True)
    layout.spec_file(project).write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")


def make_project(folder, source=EXAMPLE, spec=None, new=False):
    """A project folder ready for the generator: the spec, the register if the source has one, and one
    placeholder screenshot for every shot the mock-up tool would take. `spec` replaces the source's spec.
    `new` makes it in the new folder layout (_blueprint/ and the numbered folders), else in the old one."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if new:
        layout.create_new(folder)
    layout.spec_dir(folder).mkdir(parents=True, exist_ok=True)
    if spec is None:
        shutil.copy(layout.spec_file(source), layout.spec_file(folder))
    else:
        write_spec(folder, spec)
    if layout.register_json(source).exists():
        shutil.copy(layout.register_json(source), layout.register_json(folder))
    fake_screenshots(folder)
    return folder


def migrated_copy(folder, source=EXAMPLE):
    """A copy of a project (the made-up sample by default) moved to the new folder layout by the migration. What
    is built from the sample (git-ignored: its mock-up, comments, output and Excel files) is left out."""
    folder = Path(folder)
    shutil.copytree(source, folder, ignore=shutil.ignore_patterns("mockup", "feedback", "output", "*.xlsx"))
    result = layout.migrate(folder, rebuild_page=False)
    assert not result["refusals"], result["refusals"]
    return folder


def fake_screenshots(project):
    shots = mockup.shot_list(mockup.load_spec(project))  # load_spec also validates the spec
    shot_dir = layout.screenshots_dir(project)
    shot_dir.mkdir(parents=True, exist_ok=True)
    layout.shots_plan(project).parent.mkdir(parents=True, exist_ok=True)
    layout.shots_plan(project).write_text(json.dumps(shots, indent=2), encoding="utf-8")
    for shot in shots:
        Image.new("RGB", (320, 200), "#dfe3ea").save(shot_dir / f"{shot['name']}.png")
    mockup.record_screenshots(project, mockup.load_spec(project))  # as the real screenshot step does
    return shots


@dataclass
class Built:
    project: Path
    path: Path      # the .docx
    doc: object     # the .docx opened with python-docx
    spec: dict
    shots: list
    log: str        # what the generator printed


def generate(project):
    """Run the generator on a project and open what it wrote."""
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        path = generate_requirements.build(project)
    return Built(Path(project), path, Document(str(path)), mockup.load_spec(project),
                 json.loads(layout.shots_plan(project).read_text(encoding="utf-8")), log.getvalue())


def changed(spec, **keys):
    """A copy of a spec with top-level keys replaced; None removes a key."""
    out = copy.deepcopy(spec)
    for key, value in keys.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------- reading a generated document
def clean(text):
    return text.replace("​", "")  # the generator allows a line break after "/" in table headers


def all_text(doc):
    """Every piece of text in the document body, tables included, one paragraph per line."""
    hyphen = qn("w:noBreakHyphen")  # IDs are written with Word's non-breaking hyphen: read it as "-"
    return "\n".join("".join("-" if t.tag == hyphen else t.text or "" for t in p.iter(qn("w:t"), hyphen))
                     for p in doc.element.body.iter(qn("w:p")))


def is_heading(block, level):
    return isinstance(block, Paragraph) and block.style.name == f"Heading {level}"


def headings(doc, level):
    return [p.text for p in doc.paragraphs if p.style.name == f"Heading {level}"]


def split_at_headings(blocks, level):
    """[(heading text, [blocks under it])]; blocks before the first heading come first under None."""
    parts = [(None, [])]
    for block in blocks:
        if is_heading(block, level):
            parts.append((block.text, []))
        else:
            parts[-1][1].append(block)
    return parts


def chapters(doc):
    """[(chapter heading, [paragraphs and tables in it])]: the front matter first, under None."""
    return split_at_headings(list(doc.iter_inner_content()), 1)


def chapter(doc, title):
    """The blocks of the chapter whose heading ends with this title (headings carry their number)."""
    found = [blocks for heading, blocks in chapters(doc) if heading and heading.endswith(title)]
    assert len(found) == 1, f"expected one chapter '{title}', found {len(found)}"
    return found[0]


def tables(blocks):
    return [b for b in blocks if isinstance(b, Table)]


def paragraphs(blocks):
    return [b.text for b in blocks if isinstance(b, Paragraph) and b.text.strip()]


def rows(table):
    return [[clean(c.text) for c in r.cells] for r in table.rows]


def header(table):
    return rows(table)[0]


def column(table, i=0, skip_header=True):
    return [r[i] for r in rows(table)[1 if skip_header else 0:]]


def is_figure(table):
    """A screenshot: one column, the picture in the first row and its caption in the second."""
    return (len(table.columns) == 1 and len(table.rows) == 2
            and bool(table.rows[0].cells[0]._tc.xpath(".//w:drawing")))


def captions(blocks):
    return [t.rows[1].cells[0].text for t in tables(blocks) if is_figure(t)]


def tables_with_header(blocks, wanted):
    return [t for t in tables(blocks) if not is_figure(t) and header(t) == wanted]


def table_starting(blocks, first_header_cell, nth=None):
    """The table whose header starts with that cell. `nth` picks one when there are several (0 is the first)."""
    found = [t for t in tables(blocks) if not is_figure(t) and header(t)[0] == first_header_cell]
    if nth is not None:
        return found[nth]
    assert len(found) == 1, f"expected one table starting with '{first_header_cell}', found {len(found)}"
    return found[0]


def signature_forms(blocks):
    """The sign-off forms: label rows Name, Designation, Signature, Date."""
    return [t for t in tables(blocks) if len(t.columns) == 3 and column(t, 0, skip_header=False) == ["Name", "Designation", "Signature", "Date"]]


def rotated(cell):
    """True when the cell's text is turned to read bottom to top."""
    return bool(cell._tc.xpath('./w:tcPr/w:textDirection[@w:val="btLr"]'))
