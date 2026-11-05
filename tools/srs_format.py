"""Inspect, learn and preview the SRS format.

Usage:
    python -I tools/srs_format.py show                 the format in effect (defaults + workspace overrides)
    python -I tools/srs_format.py learn <sample.docx>  read a company's existing SRS and print what it uses
    python -I tools/srs_format.py preview              generate the sample project and render page images

The format lives in templates/srs-format.yaml (defaults) and workspace/branding/srs-format.yaml (your
overrides, key by key). See docs/srs-format.md.
"""
import collections
import re
import sys
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import workspace  # noqa: E402


def show():
    import generate_srs

    fmt = generate_srs.load_format()
    own = workspace.workspace_dir() / "branding" / "srs-format.yaml"
    print(f"# Defaults: templates/srs-format.yaml\n# Overrides: {own if own.exists() else 'none (workspace/branding/srs-format.yaml)'}\n")
    print(yaml.safe_dump(fmt, sort_keys=False, allow_unicode=True))


def learn(sample):
    """Report the fonts, sizes, colours, page set-up and chapter structure a sample document uses."""
    z = zipfile.ZipFile(sample)
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
    h1_texts = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", h)).strip() for h in headings]

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Sample: {sample}\n")
    print(f"Theme fonts:      headings {major.group(1) if major else '?'}, body {minor.group(1) if minor else '?'}")
    print(f"Normal style:     {normal_font.group(1) if normal_font else '(theme font)'} {int(normal_size.group(1)) / 2 if normal_size else '?'} pt")
    print(f"Heading 1:        {int(h1_size.group(1)) / 2 if h1_size else '?'} pt, colour {h1_color.group(1) if h1_color else 'default'}")
    print(f"Fonts in text:    {top(r'w:ascii=\"([^\"]+)\"', doc)}")
    print(f"Text sizes (pt):  {[(int(s) / 2, n) for s, n in top(r'<w:sz w:val=\"(\d+)\"', doc)]}")
    print(f"Table fills:      {top(r'w:fill=\"([0-9A-Fa-f]{6})\"', doc, 6)}")
    print(f"Text colours:     {top(r'<w:color w:val=\"([0-9A-Fa-f]{6})\"', doc, 6)}")
    if pg:
        print(f"Page:             {int(pg.group(1)) / 567:.1f} x {int(pg.group(2)) / 567:.1f} cm"
              + (f", margins top {int(mar.group(1)) / 567:.1f} right {int(mar.group(2)) / 567:.1f} bottom {int(mar.group(3)) / 567:.1f} left {int(mar.group(4)) / 567:.1f} cm" if mar else ""))
    print("Chapters (Heading 1):")
    for t in h1_texts:
        if t:
            print(f"  - {t}")
    print("\nUse these to write workspace/branding/srs-format.yaml (only the keys that differ from the defaults),"
          "\nand copy the sample to workspace/branding/srs-template.docx if its header, footer or styles should be kept.")


def preview():
    import generate_srs
    import pymupdf

    project = ROOT / "examples" / "leave-request"
    out = generate_srs.build(str(project))
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
    if len(sys.argv) < 2 or sys.argv[1] not in ("show", "learn", "preview") or (sys.argv[1] == "learn" and len(sys.argv) != 3):
        sys.exit(__doc__)
    {"show": show, "preview": preview}.get(sys.argv[1], lambda: learn(sys.argv[2]))()


if __name__ == "__main__":
    main()
