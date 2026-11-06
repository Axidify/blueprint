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
    B4=15 (formula =SUM(B2:B3))    a spreadsheet cell with a formula: its calculated value, then the formula

Headings and numbered paragraphs of a Word document carry the number Word shows for them ("## 3.2 Roles",
"- (a) ..."). Word does not store those numbers in the text: they are worked out here from the document's
numbering definitions, so a finding can point to "section 3.2" as the reader sees it.

The output folder is the extraction's own. An earlier extraction in it is replaced; any other file there
is left alone. A folder that holds files and is not an earlier extraction (a project's docs/, say) is
refused, and nothing in it is touched.
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
def roman(n):
    out = ""
    for value, letters in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                           (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out, n = out + letters, n - value
    return out


def letters(n):
    """1 -> A, 26 -> Z, 27 -> AA, 28 -> BB: Word repeats the letter."""
    return chr(ord("A") + (n - 1) % 26) * ((n - 1) // 26 + 1) if n > 0 else ""


FORMATS = {
    "decimal": str, "decimalZero": lambda n: f"{n:02d}",
    "upperRoman": roman, "lowerRoman": lambda n: roman(n).lower(),
    "upperLetter": letters, "lowerLetter": lambda n: letters(n).lower(),
    "none": lambda n: "",
}


class Numbering:
    """The numbers Word shows in front of headings and numbered paragraphs.

    Word keeps the definitions (word/numbering.xml: for each level a format such as "%1.%2", a number style
    and a start value) and which paragraphs use them (in the paragraph, or in its style), and counts as it
    lays the document out. This counts the same way, in document order."""

    def __init__(self, z):
        self.levels, self.nums, self.style_num, self.counters, self.used = {}, {}, {}, {}, set()
        val = lambda el, tag: (el.find(W + tag).get(W + "val") if el is not None and el.find(W + tag) is not None else None)
        if "word/numbering.xml" in z.namelist():
            root = ET.fromstring(z.read("word/numbering.xml"))
            for a in root.findall(W + "abstractNum"):
                levels = {}
                for lvl in a.findall(W + "lvl"):
                    levels[int(lvl.get(W + "ilvl"))] = {"start": int(val(lvl, "start") or 1), "fmt": val(lvl, "numFmt") or "decimal",
                                                       "text": val(lvl, "lvlText") or "", "style": val(lvl, "pStyle"),
                                                       "legal": lvl.find(W + "isLgl") is not None}
                self.levels[a.get(W + "abstractNumId")] = levels
            for n in root.findall(W + "num"):
                starts = {int(o.get(W + "ilvl")): int(val(o, "startOverride")) for o in n.findall(W + "lvlOverride")
                          if val(o, "startOverride") is not None}
                self.nums[n.get(W + "numId")] = {"abstract": val(n, "abstractNumId"), "starts": starts}
        if "word/styles.xml" in z.namelist():
            styles = {s.get(W + "styleId"): s for s in ET.fromstring(z.read("word/styles.xml")).findall(W + "style")}

            def numbering_of(style_id, depth=0):
                """(numId, ilvl) a style gives its paragraphs, looking through the styles it is based on."""
                style = styles.get(style_id)
                if style is None or depth > 20:
                    return None, None
                num_pr = style.find(f"{W}pPr/{W}numPr")
                num_id, ilvl = (val(num_pr, "numId"), val(num_pr, "ilvl")) if num_pr is not None else (None, None)
                if num_id is None:
                    base = val(style, "basedOn")
                    inherited = numbering_of(base, depth + 1) if base else (None, None)
                    num_id, ilvl = inherited[0], ilvl if ilvl is not None else inherited[1]
                return num_id, ilvl

            for style_id in styles:
                self.style_num[style_id] = numbering_of(style_id)

    def label(self, p, style_id):
        """The number in front of this paragraph ("3.2", "(a)", "Appendix B"), or "" when it has none.
        Call it once for every paragraph, in order: it counts."""
        num_pr = p.find(f"{W}pPr/{W}numPr")
        direct = lambda tag: (num_pr.find(W + tag).get(W + "val") if num_pr is not None and num_pr.find(W + tag) is not None else None)
        from_style = self.style_num.get(style_id, (None, None))
        num_id = direct("numId") if direct("numId") is not None else from_style[0]
        if num_id in (None, "0") or num_id not in self.nums:
            return ""
        levels = self.levels.get(self.nums[num_id]["abstract"]) or {}
        ilvl = direct("ilvl") if direct("ilvl") is not None else from_style[1]
        if ilvl is None:  # the list names the style of each level instead
            ilvl = next((i for i, lvl in levels.items() if lvl["style"] == style_id), 0)
        ilvl = int(ilvl)
        if ilvl not in levels:
            return ""
        # Word keeps one running count for all the list instances (w:num) that share a definition: applying
        # heading numbering paragraph by paragraph makes a new instance each time, and they still count on.
        # An instance restarts a level only when it carries a start override, the first time it is used.
        counts = self.counters.setdefault(self.nums[num_id]["abstract"], {})
        restart = self.nums[num_id]["starts"].get(ilvl) if (num_id, ilvl) not in self.used else None
        self.used.add((num_id, ilvl))
        if restart is not None:
            counts[ilvl] = restart
        else:
            counts[ilvl] = counts[ilvl] + 1 if ilvl in counts else levels[ilvl]["start"]
        for deeper in [i for i in counts if i > ilvl]:
            del counts[deeper]
        level = levels[ilvl]
        if level["fmt"] == "bullet":
            return ""

        def shown(match):
            i = int(match.group(1)) - 1
            fmt = "decimal" if level["legal"] and i != ilvl else (levels[i]["fmt"] if i in levels else "decimal")
            return FORMATS.get(fmt, str)(counts.get(i, 0))  # a level not reached yet shows 0, as in Word

        return re.sub(r"%(\d)", shown, level["text"]).strip()


class Docx:
    def __init__(self, path, out):
        self.z = zipfile.ZipFile(path)
        self.out = out
        self.images = []
        self.counts = {"tracked_insertions": 0, "tracked_deletions": 0, "tables": 0}
        rels = ET.fromstring(self.z.read("word/_rels/document.xml.rels"))
        self.rels = {r.get("Id"): r.get("Target") for r in rels}
        self.numbering = Numbering(self.z)
        self.counts["numbered_headings"] = 0

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
        number = self.numbering.label(p, style)  # before the empty check: Word counts an empty numbered paragraph too
        text = "".join(self.inline(c) for c in p if c.tag != W + "pPr").strip()
        if not text:
            return ""
        numbered = f"{number} {text}" if number else text
        s = style.lower()
        if s == "title":
            return "# " + text
        m = re.match(r"heading(\d)", s)
        if m:
            self.counts["numbered_headings"] += bool(number)
            return "#" * (int(m.group(1)) + 1) + " " + numbered
        if s.startswith("toc"):
            return "  (TOC) " + text
        if s == "caption":
            return "*Caption:* " + text
        if number or "list" in s or p.find(f"{W}pPr/{W}numPr") is not None:
            return "- " + numbered
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
    (out / "pages").mkdir(exist_ok=True)
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
    # The same file once more for what Excel last calculated: a total is a formula, and a review needs its
    # figure ("15"), not only "=SUM(B2:B3)".
    try:
        values = openpyxl.load_workbook(path, data_only=True)
    except Exception:
        values = None

    def shown(ws, c):
        if not (isinstance(c.value, str) and c.value.startswith("=")):
            return f"{c.coordinate}={c.value}"
        result = values[ws.title][c.coordinate].value if values is not None and ws.title in values.sheetnames else None
        if result is None:
            return f"{c.coordinate}={c.value} (a formula; the file holds no calculated value for it)"
        return f"{c.coordinate}={result} (formula {c.value})"

    parts = []
    for ws in wb:
        parts.append(f"## Sheet: {ws.title} ({ws.dimensions})")
        for row in ws.iter_rows():
            cells = [shown(ws, c) for c in row if c.value is not None]
            if cells:
                parts.append(" | ".join(cells))
    props = wb.properties
    meta = {k: str(getattr(props, k)) for k in ("title", "creator", "lastModifiedBy", "modified") if getattr(props, k, None)}
    return "\n".join(parts), meta


def read_text(path):
    """A text file, whatever it was saved as: UTF-8 (with or without a byte-order mark), UTF-16 from Notepad's
    "Unicode", or the Windows encoding older editors use. Returns (text, {"encoding": ...})."""
    raw = path.read_bytes()
    lines = lambda text: text.replace("\r\n", "\n").replace("\r", "\n")  # Windows and old Mac line ends
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return lines(raw.decode("utf-16")), {"encoding": "utf-16"}
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return lines(raw.decode(encoding)), {"encoding": "utf-8" if encoding == "utf-8-sig" else "windows-1252"}
        except UnicodeDecodeError:
            continue
    return lines(raw.decode("latin-1")), {"encoding": "latin-1"}


OURS = ("text.md", "meta.json", "images", "pages")  # what an extraction writes into its folder


def prepare_output(out):
    """Get the output folder ready, removing only what an earlier extraction wrote there. It used to delete
    the whole folder first: pointed at a project's docs/ by mistake, that deleted the client's documents."""
    if out.exists() and not out.is_dir():
        sys.exit(f"{out} is a file. Give the extraction a folder of its own.")
    if out.exists() and any(out.iterdir()):
        try:
            earlier = json.loads((out / "meta.json").read_text(encoding="utf-8"))
            ours = isinstance(earlier, dict) and {"source", "counts"} <= set(earlier)
        except (OSError, ValueError):
            ours = False
        if not ours:
            names = sorted(p.name for p in out.iterdir())
            listed = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
            sys.exit(f"{out} already holds files that are not an earlier extraction ({listed}). Nothing was touched.\n"
                     "Give the extraction a folder of its own, for example projects/<slug>/reviews/<review>/extract.")
        for name in OURS:
            target = out / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
    (out / "images").mkdir(parents=True, exist_ok=True)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        sys.exit(f"No such document: {src}")
    if src.suffix.lower() not in (".docx", ".pdf", ".xlsx", ".md", ".txt"):
        sys.exit(f"Unsupported file type: {src.suffix.lower()}")  # before the output folder is touched
    prepare_output(out)
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
        text, meta = read_text(src)
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
