"""Extract a client document into reviewable text plus images.

Usage:
    python -I tools/extract.py <document> <output_dir>

Supports .docx, .pdf, .xlsx, .md and .txt. Writes:
    <output_dir>/text.md     document text in reading order, with markers (see below)
    <output_dir>/meta.json   metadata and counts
    <output_dir>/images/     embedded images, numbered in document order

Markers in text.md:
    [IMAGE 03: images/img03.png]   an embedded image at this position
    {+inserted+} / [-deleted-]     unaccepted tracked changes (docx)
    [[C4: anchored text]]          text anchored to comment 4 (comments listed at the end)
    | a | b | c |                  a table row
    === PAGE 12 ===                page break (pdf)
"""
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
V = "{urn:schemas-microsoft-com:vml}"
OPEN_ITEM = re.compile(r"\bTBC\b|\bTBD\b|to be confirmed|to be determined|if applicable", re.I)


# ---------------------------------------------------------------- docx
class Docx:
    def __init__(self, path, out):
        self.z = zipfile.ZipFile(path)
        self.out = out
        self.images = []
        self.counts = {"tracked_insertions": 0, "tracked_deletions": 0, "tables": 0}
        rels = ET.fromstring(self.z.read("word/_rels/document.xml.rels"))
        self.rels = {r.get("Id"): r.get("Target") for r in rels}

    def image(self, rid):
        target = self.rels.get(rid)
        if not target:
            return ""
        name = "word/" + target.lstrip("/").removeprefix("word/")
        if name not in self.z.namelist():
            return ""
        n = len(self.images) + 1
        dest = f"images/img{n:02d}{Path(target).suffix.lower()}"
        (self.out / dest).write_bytes(self.z.read(name))
        self.images.append({"n": n, "file": dest, "source": target})
        return f" [IMAGE {n:02d}: {dest}] "

    def inline(self, el):
        tag = el.tag
        if tag == W + "t":
            return el.text or ""
        if tag == W + "delText":
            return el.text or ""
        if tag in (W + "tab",):
            return "\t"
        if tag in (W + "br", W + "cr"):
            return " "
        if tag == W + "commentRangeStart":
            return f"[[C{el.get(W + 'id')}: "
        if tag == W + "commentRangeEnd":
            return "]]"
        if tag == A + "blip":
            return self.image(el.get(R + "embed"))
        if tag == V + "imagedata":
            return self.image(el.get(R + "id"))
        inner = "".join(self.inline(c) for c in el)
        if tag == W + "ins":
            self.counts["tracked_insertions"] += 1
            return "{+" + inner + "+}"
        if tag == W + "del":
            self.counts["tracked_deletions"] += 1
            return "[-" + inner + "-]"
        return inner

    def paragraph(self, p):
        style = p.find(f"{W}pPr/{W}pStyle")
        style = style.get(W + "val") if style is not None else ""
        text = "".join(self.inline(c) for c in p if c.tag != W + "pPr").strip()
        if not text:
            return ""
        s = style.lower()
        if s == "title":
            return "# " + text
        m = re.match(r"heading(\d)", s)
        if m:
            return "#" * (int(m.group(1)) + 1) + " " + text
        if s.startswith("toc"):
            return "  (TOC) " + text
        if s == "caption":
            return "*Caption:* " + text
        if "list" in s or p.find(f"{W}pPr/{W}numPr") is not None:
            return "- " + text
        return text

    def table(self, tbl):
        self.counts["tables"] += 1
        rows = []
        for tr in tbl.findall(W + "tr"):
            cells = []
            for tc in tr.findall(W + "tc"):
                parts = [self.block(c) for c in tc]
                cells.append(" / ".join(x for x in parts if x).replace("\n", " / "))
            rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)

    def block(self, el):
        if el.tag == W + "p":
            return self.paragraph(el)
        if el.tag == W + "tbl":
            return self.table(el)
        if el.tag == W + "sdt":
            content = el.find(W + "sdtContent")
            return "\n".join(x for x in (self.block(c) for c in content) if x) if content is not None else ""
        return ""

    def run(self):
        body = ET.fromstring(self.z.read("word/document.xml")).find(W + "body")
        lines = [x for x in (self.block(c) for c in body) if x]
        comments = []
        if "word/comments.xml" in self.z.namelist():
            for c in ET.fromstring(self.z.read("word/comments.xml")).findall(W + "comment"):
                txt = " ".join("".join(t.text or "" for t in p.iter(W + "t")) for p in c.findall(W + "p"))
                comments.append(f"- C{c.get(W + 'id')} ({c.get(W + 'author')}, {c.get(W + 'date')}): {txt}")
        if comments:
            lines += ["", "## Comments in the document", *comments]
        meta = {}
        if "docProps/core.xml" in self.z.namelist():
            core = ET.fromstring(self.z.read("docProps/core.xml"))
            for el in core:
                if el.text:
                    meta[el.tag.split("}")[1]] = el.text
        self.counts["comments"] = len(comments)
        return "\n\n".join(lines), meta


# ---------------------------------------------------------------- pdf
def extract_pdf(path, out):
    import pymupdf

    doc = pymupdf.open(path)
    parts, images, rendered = [], [], []
    (out / "pages").mkdir()
    for i, page in enumerate(doc, 1):
        text = page.get_text("text")
        parts.append(f"=== PAGE {i} ===\n{text}")
        # Render pages whose content the text layer cannot carry: diagrams, screenshots, formulas
        # (math fonts extract as fragments), or pages with almost no text.
        has_math = any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in text)
        if page.get_images() or has_math or len(text.strip()) < 200:
            dest = f"pages/p{i:03d}.png"
            page.get_pixmap(dpi=130).save(out / dest)
            rendered.append(i)
            parts.append(f"[PAGE RENDER: {dest}]")
        for j, img in enumerate(page.get_images(full=True), 1):
            info = doc.extract_image(img[0])
            if len(info["image"]) < 15000:  # skip logos, icons, signature stamps
                continue
            n = len(images) + 1
            dest = f"images/img{n:02d}_p{i}.{info['ext']}"
            (out / dest).write_bytes(info["image"])
            images.append({"n": n, "file": dest, "page": i})
            parts.append(f"[IMAGE {n:02d}: {dest}]")
    meta = {k: v for k, v in doc.metadata.items() if v}
    return "\n".join(parts), meta, images, {"pages": doc.page_count, "pages_rendered": len(rendered)}


# ---------------------------------------------------------------- xlsx
def extract_xlsx(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=False)
    parts = []
    for ws in wb:
        parts.append(f"## Sheet: {ws.title} ({ws.dimensions})")
        for row in ws.iter_rows():
            cells = [f"{c.coordinate}={c.value}" for c in row if c.value is not None]
            if cells:
                parts.append(" | ".join(cells))
    props = wb.properties
    meta = {k: str(getattr(props, k)) for k in ("title", "creator", "lastModifiedBy", "modified") if getattr(props, k, None)}
    return "\n".join(parts), meta


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    ext = src.suffix.lower()
    images, counts = [], {}
    if ext == ".docx":
        d = Docx(src, out)
        text, meta = d.run()
        images, counts = d.images, d.counts
    elif ext == ".pdf":
        text, meta, images, counts = extract_pdf(src, out)
    elif ext == ".xlsx":
        text, meta = extract_xlsx(src)
    elif ext in (".md", ".txt"):
        text, meta = src.read_text(encoding="utf-8"), {}
    else:
        sys.exit(f"Unsupported file type: {ext}")

    open_items = []
    for n, line in enumerate(text.splitlines(), 1):
        if OPEN_ITEM.search(line) and "(TOC)" not in line:
            open_items.append({"line": n, "text": line.strip()[:200]})

    (out / "text.md").write_text(text, encoding="utf-8")
    info = {
        "source": str(src),
        "metadata": meta,
        "counts": {**counts, "images": len(images), "characters": len(text), "open_item_markers": len(open_items)},
        "images": images,
        "open_items": open_items,
    }
    (out / "meta.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Wrote {out / 'text.md'} ({len(text):,} characters)")
    print("Metadata:", json.dumps(meta, ensure_ascii=False))
    print("Counts:", json.dumps(info["counts"]))
    print(f"Open-item markers (TBC/TBD/if applicable): {len(open_items)} - see meta.json")


if __name__ == "__main__":
    main()
