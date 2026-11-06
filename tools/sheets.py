"""The design language for Blueprint's Excel workbooks (docs/design-language.md, Spreadsheets).

True greys and hairlines, a quiet grey header row, Calibri (Geist cannot travel inside an Excel file, and
every Office has Calibri), status as a dot and a coloured word, and the one accent colour for what to fill in.
Used by the register, the UAT workbook, the CR log and the estimate workbook, so they read as one family.

Only the look is set here: the cells, their values, headers and positions stay as each tool writes them, so a
workbook read back by Blueprint (the register's Client response, the UAT results) reads as before.
"""
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

FONT = "Calibri"
INK, GREY = "1D1D1F", "6E6E73"
HEAD_FILL, HEAD_LINE, ROW_LINE = "F5F5F7", "D2D2D7", "E5E5EA"
GREEN, ORANGE, RED, ACCENT = "248A3D", "C93400", "D70015", "1F5FBF"
# A cell to fill in: the accent's tint (8% Cobalt on white), with the accent's hairline, so it reads as a field.
INPUT_FILL, INPUT_LINE = "EDF2FA", "A9C0E5"
DOT_FORMAT = '"● "@'  # a status: a dot before the word, the value itself unchanged

# Status words and their colour, for the conditional formats that follow the cell when someone changes it.
TONES = {"green": GREEN, "orange": ORANGE, "red": RED, "grey": GREY, "accent": ACCENT}


def font(color=INK, bold=False, size=11):
    return Font(name=FONT, size=size, bold=bold, color=color)


def hairline(color=ROW_LINE):
    return Side(style="thin", color=color)


def setup(ws, widths=None, freeze=None, internal=None, landscape=True, titles="1:1"):
    """A sheet in the design language: no gridlines, column widths, frozen panes, printed landscape on A4 one
    page wide, page numbers in the footer, and `internal` (a sentence) in the header when it is not for the client."""
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w
    ws.sheet_view.showGridLines = False
    if freeze:
        ws.freeze_panes = freeze
    if titles:
        ws.print_title_rows = titles
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.75, bottom=0.75, header=0.3, footer=0.3)
    ws.oddFooter.center.text, ws.oddFooter.center.size, ws.oddFooter.center.color = "Page &P of &N", 9, GREY
    if internal:
        ws.oddHeader.center.text, ws.oddHeader.center.size, ws.oddHeader.center.color = internal, 9, GREY
    return ws


def header(ws, row, columns, fill_in=()):
    """A table's header row: grey bold words on the soft grey, a stronger line under it. The headers of columns
    to fill in (`fill_in`, 1-based) are in the accent, so the eye finds where to type."""
    for c in range(1, columns + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = font(ACCENT if c in fill_in else GREY, bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor=HEAD_FILL)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        cell.border = Border(bottom=hairline(HEAD_LINE))
    ws.row_dimensions[row].height = 30


def rows(ws, first, last, columns, fill_in=()):
    """Body rows: ink on white, wrapped and middle-aligned, a hairline under each row. Columns in `fill_in`
    (1-based) are drawn as fields to fill in."""
    for r in range(first, last + 1):
        for c in range(1, columns + 1):
            cell = ws.cell(row=r, column=c)
            numeric = isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
            cell.font = font()
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right" if numeric else None)
            if c in fill_in:
                cell.fill = PatternFill("solid", fgColor=INPUT_FILL)
                cell.border = Border(left=hairline(INPUT_LINE), right=hairline(INPUT_LINE), top=hairline(INPUT_LINE),
                                     bottom=hairline(INPUT_LINE))
            else:
                cell.border = Border(bottom=hairline())
    # A column of numbers is right-aligned, its header (the row above) too, so they line up.
    if first > 1 and last >= first:
        for c in range(1, columns + 1):
            values = [ws.cell(row=r, column=c).value for r in range(first, last + 1)]
            if any(v is not None for v in values) and all(v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))
                                                          for v in values):
                head = ws.cell(row=first - 1, column=c)
                head.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right")


def status(ws, ref, tones):
    """Status as a dot and a coloured word, on every cell of `ref` (e.g. "E2:E40"). `tones` maps each word
    (as the cell holds it) to green, orange, red, grey or accent. Conditional formats, so the colour follows
    the word when someone changes it in Excel; the cell's value stays the word alone."""
    first = ref.split(":")[0]
    for row in ws[ref]:
        for cell in (row if isinstance(row, tuple) else (row,)):
            cell.number_format = DOT_FORMAT
    for word, tone in tones.items():
        ws.conditional_formatting.add(ref, CellIsRule(operator="equal", formula=[f'"{word}"'],
                                                      font=Font(name=FONT, color=TONES[tone])))
    return first


def title(ws, cell, text, sub=None):
    """A sheet's title (18pt, bold ink) and the line under it (grey)."""
    ws[cell] = text
    ws[cell].font = font(INK, bold=True, size=18)
    ws.row_dimensions[ws[cell].row].height = 28
    if sub is not None:
        below = ws.cell(row=ws[cell].row + 1, column=ws[cell].column, value=sub)
        below.font = font(GREY)


def label(cell, size=11):
    """A label in a summary: grey, as a detail beside its value."""
    cell.font = font(GREY, size=size)


def section(cell):
    """A section title inside a sheet: 13pt bold ink."""
    cell.font = font(INK, bold=True, size=13)


def value(cell, bold=False):
    cell.font = font(INK, bold=bold)
    cell.alignment = Alignment(horizontal="left", vertical="center")
