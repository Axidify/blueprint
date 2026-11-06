"""Inspect, learn and preview the document format.

Usage:
    python -I tools/document_format.py show                 the format in effect (defaults + workspace overrides)
    python -I tools/document_format.py learn <sample.docx>  read a company's existing requirements document and print what it uses
    python -I tools/document_format.py preview              generate the sample project and render page images

The format lives in templates/document-format.yaml (defaults) and workspace/branding/document-format.yaml (your
overrides, key by key). See docs/document-format.md.
"""
import collections
import html
import re
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402


def show():
    import generate_requirements

    fmt = generate_requirements.load_format()
    own = generate_requirements.own_format_file()
    errors = generate_requirements.format_errors(fmt)
    print(f"# Defaults: templates/document-format.yaml\n# Overrides: {own or 'none (workspace/branding/document-format.yaml)'}\n")
    print(yaml.safe_dump(fmt, sort_keys=False, allow_unicode=True))
    if errors:
        print("MISTAKES in the format - documents cannot be generated until these are fixed:")
        for e in errors:
            print("  - " + e)
        sys.exit(1)


WORD_FILES = (".docx", ".dotx", ".docm", ".dotm")


def open_sample(sample):
    """The sample as a Word file, or a plain sentence saying why it cannot be read (and what to ask for)."""
    path = Path(sample)
    if not path.is_file():
        sys.exit(f"No file at {path}. Give the path of the sample requirements document, as a Word file (.docx).")
    suffix = path.suffix.lower()
    if suffix not in WORD_FILES:
        kind = {".pdf": "a PDF", ".doc": "a Word 97-2003 file (.doc)"}.get(suffix, f"a {suffix} file" if suffix else "a file without an extension")
        hint = (" Open it in Word and save it as a Word Document (.docx), then run learn on that." if suffix == ".doc"
                else " Ask for the Word version of the sample document and run learn on that.")
        sys.exit(f"{path.name} is {kind}. learn reads the fonts, colours and chapters from a Word file (.docx).{hint}")
    try:
        z = zipfile.ZipFile(path)
        z.getinfo("word/document.xml")
        return z
    except (zipfile.BadZipFile, KeyError, OSError):
        sys.exit(f"{path.name} could not be read as a Word document: it may be damaged, still downloading, or another kind "
                 "of file renamed to .docx. Open it in Word and save it again as a Word Document (.docx), then run learn on that.")


def learn(sample):
    """Report the fonts, sizes, colours, page set-up and chapter structure a sample document uses."""
    z = open_sample(sample)
    doc = z.read("word/document.xml").decode("utf-8", "replace")
    styles = z.read("word/styles.xml").decode("utf-8", "replace") if "word/styles.xml" in z.namelist() else ""
    theme = next((z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.startswith("word/theme/")), "")

    def top(pattern, text, n=5):
        return collections.Counter(re.findall(pattern, text)).most_common(n)

    major = re.search(r'<a:majorFont><a:latin typeface="([^"]*)"', theme)
    minor = re.search(r'<a:minorFont><a:latin typeface="([^"]*)"', theme)
    normal = re.search(r'w:styleId="Normal".*?</w:style>', styles, re.S)
    normal_font = re.search(r'w:ascii="([^"]+)"', normal.group(0)) if normal else None
    normal_size = re.search(r'<w:sz w:val="(\d+)"', normal.group(0)) if normal else None
    h1 = re.search(r'w:styleId="Heading1".*?</w:style>', styles, re.S)
    h1_size = re.search(r'<w:sz w:val="(\d+)"', h1.group(0)) if h1 else None
    h1_color = re.search(r'<w:color w:val="([0-9A-Fa-f]{6})"', h1.group(0)) if h1 else None
    pg = re.search(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', doc)
    mar = re.search(r'<w:pgMar w:top="(\d+)"[^>]*w:right="(\d+)"[^>]*w:bottom="(\d+)"[^>]*w:left="(\d+)"', doc)
    headings = re.findall(r'<w:pStyle w:val="Heading1"/>.*?</w:pPr>(.*?)</w:p>', doc, re.S)
    # The XML writes &, < and quotes as &amp; &lt; &quot;: they are printed as the characters they stand for.
    h1_texts = [html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", h))).strip() for h in headings]

    fonts = [(html.unescape(name), n) for name, n in top(r'w:ascii="([^"]+)"', doc)]
    text_sizes = [(int(s) / 2, n) for s, n in top(r'<w:sz w:val="(\d+)"', doc)]
    fills = top(r'w:fill="([0-9A-Fa-f]{6})"', doc, 6)
    text_colours = top(r'<w:color w:val="([0-9A-Fa-f]{6})"', doc, 6)
    print(f"Sample: {sample}\n")
    print(f"Theme fonts:      headings {html.unescape(major.group(1)) if major else '?'}, body {html.unescape(minor.group(1)) if minor else '?'}")
    print(f"Normal style:     {html.unescape(normal_font.group(1)) if normal_font else '(theme font)'} {int(normal_size.group(1)) / 2 if normal_size else '?'} pt")
    print(f"Heading 1:        {int(h1_size.group(1)) / 2 if h1_size else '?'} pt, colour {h1_color.group(1) if h1_color else 'default'}")
    print(f"Fonts in text:    {fonts}")
    print(f"Text sizes (pt):  {text_sizes}")
    print(f"Table fills:      {fills}")
    print(f"Text colours:     {text_colours}")
    if pg:
        print(f"Page:             {int(pg.group(1)) / 567:.1f} x {int(pg.group(2)) / 567:.1f} cm"
              + (f", margins top {int(mar.group(1)) / 567:.1f} right {int(mar.group(2)) / 567:.1f} bottom {int(mar.group(3)) / 567:.1f} left {int(mar.group(4)) / 567:.1f} cm" if mar else ""))
    print("Chapters (Heading 1):")
    for t in h1_texts:
        if t:
            print(f"  - {t}")
    print("\nUse these to write workspace/branding/document-format.yaml (only the keys that differ from the defaults),"
          "\nand copy the sample to workspace/branding/document-template.docx if its header, footer or styles should be kept.")


def preview():
    import generate_requirements
    import pymupdf

    project = ROOT / "examples" / "leave-request"
    out = generate_requirements.build(str(project))
    pdf = out.with_suffix(".pdf")
    if not pdf.exists():
        print("No PDF (Word not available): open the .docx to look at it.")
        return
    folder = project / "output" / "preview"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("page-*.png"):
        old.unlink()
    d = pymupdf.open(pdf)
    for i, page in enumerate(d, 1):
        page.get_pixmap(dpi=80).save(folder / f"page-{i:02d}.png")
    print(f"Preview: {d.page_count} pages in {folder}")


def main():
    # "–", "●" and other characters in chapter names and settings are printed as they are, not as "?" or "�", on
    # a Windows console or pipe that would otherwise use an old code page. Messages to stderr (sys.exit) too.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2 or sys.argv[1] not in ("show", "learn", "preview") or (sys.argv[1] == "learn" and len(sys.argv) != 3):
        sys.exit(__doc__)
    {"show": show, "preview": preview}.get(sys.argv[1], lambda: learn(sys.argv[2]))()


if __name__ == "__main__":
    main()
