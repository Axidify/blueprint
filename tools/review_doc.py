"""The review of a requirements document as a Word file, for the BA.

Usage:
    python -I tools/review_doc.py projects/<slug> [<review>]

<review> is the review's folder among the project's reviews (its name, or its path); without it, the review
written last. The tool reads <review>/review.md, which the review-requirements skill writes (in
_blueprint/reviews/, or reviews/ in a project not yet moved to the new folder layout), and writes
"<document> review.docx" (for example "SRS v1.0 review.docx") into the project's "2 Reviews" folder (beside
review.md in the old layout): headings,
lists, tables, bold, italic and code spans, in the company's Word template and document format, the way the
workshop documents are made. Every page says it is internal: the review holds your team's reasons, risks
and commercial notes. The client gets the register's "For client" sheet, never the review.

review.md stays the source: change it (or ask Claude to), then run this again. The project's overview page
links the Word file when there is one.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import layout  # noqa: E402  (where everything is in a project folder)
import workspace  # noqa: E402

INTERNAL_MARK = "Internal: not for the client"
# Words in a review folder's name that are written in capitals: srs-v1.0 is "SRS v1.0".
ACRONYMS = {"srs", "urs", "fsd", "frs", "brs", "brd", "sow", "sds", "prd", "uat", "cr", "crs", "ui", "ux", "api", "bpm", "nfr"}
INLINE = re.compile(r"(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\s][^*]*\*|(?<![\w])_[^_\s][^_]*_(?![\w])|\[[^\]]+\]\([^)]*\))")


def readable_name(folder_name):
    """A review folder's name as people read it: "srs-v1.0" is "SRS v1.0", "requirements-v0.2-generated"
    is "Requirements v0.2 generated"."""
    words = [w for w in re.split(r"[-_ ]+", str(folder_name)) if w]
    out = []
    for i, word in enumerate(words):
        if word.lower() in ACRONYMS:
            out.append(word.upper())
        elif re.fullmatch(r"v?\d+(\.\d+)*", word, re.I):
            out.append(word.lower() if word.lower().startswith("v") else word)
        else:
            out.append(word.capitalize() if i == 0 else word)
    return " ".join(out) or str(folder_name)


def docx_name(review_dir):
    return f"{readable_name(Path(review_dir).name)} review.docx"


def docx_path(project, review_dir):
    """Where a review's Word file is (or goes)."""
    return layout.review_reports_dir(project, review_dir) / docx_name(review_dir)


def find_review(project, name=None):
    """The review folder named (by name or path), or the one whose review.md was written last."""
    project = Path(project)
    reviews = layout.reviews_dir(project)
    if name:
        for candidate in (Path(name), project / name, reviews / Path(name).name):
            if (candidate / "review.md").exists():
                return candidate
        sys.exit(f"No review.md in {name}. Reviews of this project: "
                 + (", ".join(p.parent.name for p in sorted(reviews.glob("*/review.md"))) or "none"))
    found = sorted(reviews.glob("*/review.md"), key=lambda p: p.stat().st_mtime) if reviews.exists() else []
    if not found:
        sys.exit(f"No review in {reviews} yet: review a document first (say 'review the requirements document').")
    return found[-1].parent


# ---------------------------------------------------------------- reading the markdown
def inline(text):
    """[(text, kind)] with kind "", "bold", "italic" or "code". Links keep their words."""
    parts = []
    for piece in INLINE.split(text.replace("\\|", "|")):
        if not piece:
            continue
        if piece.startswith(("**", "__")) and len(piece) > 4:
            parts.append((piece[2:-2], "bold"))
        elif piece.startswith("`") and len(piece) > 2:
            parts.append((piece[1:-1], "code"))
        elif piece.startswith(("*", "_")) and len(piece) > 2:
            parts.append((piece[1:-1], "italic"))
        elif piece.startswith("[") and "](" in piece:
            parts.append((piece[1:piece.index("](")], ""))
        else:
            parts.append((piece, ""))
    return parts


def table_cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]


def blocks(markdown):
    """The markdown as blocks: ("heading", level, text), ("para", text), ("list", [(depth, numbered, text)]),
    ("table", header, rows), ("quote", text), ("code", text)."""
    lines = markdown.replace("\r\n", "\n").split("\n")
    out, i = [], 0
    is_table_rule = lambda s: bool(re.fullmatch(r"\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*", s))
    list_item = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
    while i < len(lines):
        line = lines[i]
        if not line.strip() or re.fullmatch(r"\s*(-{3,}|\*{3,}|_{3,})\s*", line):
            i += 1
            continue
        if line.lstrip().startswith("```"):
            code, i = [], i + 1
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(("code", "\n".join(code)))
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            out.append(("heading", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if "|" in line and i + 1 < len(lines) and is_table_rule(lines[i + 1]):
            header, rows, i = table_cells(line), [], i + 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(table_cells(lines[i]))
                i += 1
            out.append(("table", header, [(r + [""] * len(header))[:len(header)] for r in rows]))
            continue
        if list_item.match(line):
            items = []
            while i < len(lines) and lines[i].strip():
                m = list_item.match(lines[i])
                if m:
                    depth = len(m.group(1).replace("\t", "    ")) // 2
                    items.append([min(depth, 2), not m.group(2)[0] in "-*+", m.group(3)])
                elif items:  # a wrapped line belongs to the item above
                    items[-1][2] += " " + lines[i].strip()
                i += 1
            out.append(("list", [tuple(x) for x in items]))
            continue
        if line.lstrip().startswith(">"):
            quote = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                quote.append(lines[i].lstrip()[1:].strip())
                i += 1
            out.append(("quote", " ".join(quote)))
            continue
        para = []
        while (i < len(lines) and lines[i].strip() and not re.match(r"^#{1,6}\s", lines[i]) and not list_item.match(lines[i])
               and not lines[i].lstrip().startswith(("```", ">"))
               and not ("|" in lines[i] and i + 1 < len(lines) and is_table_rule(lines[i + 1]))):
            para.append(lines[i].strip())
            i += 1
        out.append(("para", " ".join(para)))
    return out


# ---------------------------------------------------------------- writing the Word file
def write_inline(w, paragraph, text, size=None):
    for words, kind in inline(text):
        w.runs(paragraph, [(words, "mono" if kind == "code" else "")], size)
        run = paragraph.runs[-1]
        if kind == "bold":
            run.bold = True
        elif kind == "italic":
            run.italic = True
    return paragraph


def cell_segments(text):
    """A table cell's markdown as the writer's segments: bold in the medium weight, code in mono."""
    return [(words, {"bold": "medium", "code": "mono"}.get(kind, "")) for words, kind in inline(text)] or [("", "")]


def column_widths(header, rows, total):
    longest = [max([len(str(header[c]))] + [len(str(r[c])) for r in rows]) for c in range(len(header))]
    weights = [min(max(n, 4), 60) for n in longest]
    widths = [total * w_ / sum(weights) for w_ in weights]
    least = min(1.6, total / len(header))
    short = [i for i, x in enumerate(widths) if x < least]
    if short and len(short) < len(widths):
        spare = sum(least - widths[i] for i in short)
        rest = [i for i in range(len(widths)) if i not in short]
        rest_total = sum(widths[i] for i in rest)
        for i in short:
            widths[i] = least
        for i in rest:
            widths[i] -= spare * widths[i] / rest_total
    return widths


def project_name(project):
    import json

    import yaml

    project = Path(project)
    try:
        spec = yaml.safe_load(layout.spec_file(project).read_text(encoding="utf-8")) or {}
        if (spec.get("project") or {}).get("name"):
            return str(spec["project"]["name"])
    except (OSError, ValueError, yaml.YAMLError, AttributeError):
        pass
    try:
        return str(json.loads(layout.register_json(project).read_text(encoding="utf-8")).get("project") or project.name)
    except (OSError, ValueError, AttributeError):
        return project.name


def render(project, review_dir):
    """Write the review's Word file (into 2 Reviews/, or beside its review.md in the old layout). Returns its path."""
    review_dir = Path(review_dir)
    return render_markdown(project, review_dir / "review.md", docx_path(project, review_dir),
                           "Review", f"Review of {readable_name(review_dir.name)}")


def render_note(project, note):
    """Write a note kept with the reviews (the mock-up's change notes) as a Word file in 2 Reviews/. Returns its
    path, or None in the old layout, where the note itself is linked."""
    out = layout.note_docx(project, note)
    if out is None:
        return None
    hit = re.match(r"mockup-(v.+)-changes$", Path(note).stem)
    label = "Mock-up changes" if hit else "Notes"
    return render_markdown(project, Path(note), out, label, out.stem)


def render_markdown(project, source, out, label, title):
    """A markdown file of the team's as an internal Word file: `label` above the page title (the file's first
    heading), `title` in the header. Returns `out`."""
    from docx import Document

    import generate_requirements as gen

    source, out = Path(source), Path(out)
    fmt = gen.load_format()
    problems = gen.format_errors(fmt)
    if problems:
        raise ValueError("The document format has mistakes:\n  " + "\n  ".join(problems))
    co = workspace.company()
    doc = Document(str(workspace.asset("document-template.docx")))
    w = gen.Writer(doc, fmt)
    w.setup_styles()
    doc.core_properties.title = title
    doc.core_properties.author = co["name"]
    doc.core_properties.keywords = "Internal"
    w.header_footer(f"{project_name(project)} · {title}", INTERNAL_MARK, f"{INTERNAL_MARK} · {co['name']}")
    styles = {s.name for s in doc.styles}
    body = blocks(source.read_text(encoding="utf-8"))
    titled = False
    for n, block in enumerate(body):
        kind = block[0]
        if kind == "heading":
            level, text = block[1], block[2]
            if level == 1 and not titled:
                w.para([(label, "sec")], size=w.s["body"] + 1, after=2)
                w.page_title(re.sub(r"^review\s*(?::|of\b)\s*", "", text, flags=re.I) or text, after=4)
                w.para([(project_name(project), "sec")], size=w.s["body"] + 1, after=8)
                w.para([("error", "dot"), (INTERNAL_MARK + ". It holds your team's findings, risks and commercial notes; "
                                           "the client gets the register's For client sheet.", "")], after=10)
                titled = True
            elif level <= 3:
                h = w.heading(" ".join(words for words, _ in inline(text)), max(level, 2) if titled else level, page_break=False)
                h.paragraph_format.page_break_before = False
            else:
                w.para([(" ".join(words for words, _ in inline(text)), "medium")], size=w.s["h3"], before=8, after=3, keep=True)
        elif kind == "para":
            write_inline(w, doc.add_paragraph(), block[1])
        elif kind == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = gen.Cm(0.6)
            for words, k in inline(block[1]):
                w.runs(p, [(words, "mono" if k == "code" else "sec")])
                if k == "bold":
                    p.runs[-1].bold = True
        elif kind == "code":
            for line in block[1].split("\n") or [""]:
                w.para([(line or " ", "mono")], after=0)
            doc.add_paragraph().paragraph_format.space_after = gen.Pt(2)
        elif kind == "list":
            counters = {}
            for depth, numbered, text in block[1]:
                base = "List Number" if numbered else "List Bullet"
                style = base + (f" {depth + 1}" if depth else "")
                style = style if style in styles else (base if base in styles else None)
                p = doc.add_paragraph(style=style) if style else doc.add_paragraph()
                if not style:  # a template without list styles: write the mark in front
                    counters[depth] = counters.get(depth, 0) + 1
                    w.runs(p, [(f"{counters[depth]}. " if numbered else "• ", "")])
                write_inline(w, p, text)
                p.paragraph_format.space_after = gen.Pt(2)
            doc.add_paragraph().paragraph_format.space_after = gen.Pt(0)
        elif kind == "table":
            header, rows = block[1], block[2]
            w.table([" ".join(words for words, _ in inline(h)) for h in header],
                    [[cell_segments(c) for c in r] for r in rows], column_widths(header, rows, w.text_width))
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    if len(args) not in (1, 2) or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    project = Path(args[0])
    if not project.is_dir():
        sys.exit(f"No project folder {project}")
    review_dir = find_review(project, args[1] if len(args) == 2 else None)
    try:
        out = render(project, review_dir)
    except PermissionError:
        sys.exit(f"Cannot write {docx_name(review_dir)}: close it in Word and run this again.")
    except ValueError as e:
        sys.exit(str(e))
    print(f"Wrote {out}")
    print("Internal: for your team, not for the client. The client gets the register's For client sheet.")
    try:  # the project's overview page links the new file; it never stops this command
        import overview
        overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
