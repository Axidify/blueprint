"""tools/generate_requirements.py: the structure of the generated Word document.

Documents are generated in temp folders, the way a machine without Microsoft Word does it (see conftest.py),
and read back with python-docx. What a page looks like, the table of contents, page numbers and the PDF
are made by Word and are not checked here, except by the one opt-in test at the end.
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
import yaml
from docx import Document

import support
from support import FIELD_HEADER, all_text, chapter, column, header, rows, tables

import generate_requirements
import project as project_tool

FORMAT = yaml.safe_load((support.ROOT / "templates" / "document-format.yaml").read_text(encoding="utf-8"))
TITLES = FORMAT["titles"]
PLACEHOLDER = re.compile(r"\{[a-z_]+(?::[^}]*)?\}")  # {ref:screen:x}, {client}, {system} ...


@pytest.fixture(params=["example", "wide"])
def built(request):
    """Each of the two generated documents in turn."""
    return request.getfixturevalue(request.param)


def expected_chapter_titles(spec, fmt=FORMAT):
    out = []
    for key in fmt["chapters"]:
        if key == "extras":
            out += [e["title"] for e in spec.get("extra_sections") or [] if not e.get("appendix")]
        elif key not in ("timeline", "scope") or spec.get(key):
            out.append(fmt["titles"][key])
    return out


def chapter_headings(doc):
    """(numbered chapter headings, the sign-off heading, appendix headings), as written."""
    all_ = support.headings(doc, 1)
    appendices = [h for h in all_ if h.startswith("Appendix ")]
    rest = [h for h in all_ if h not in appendices]
    return rest[:-1], rest[-1], appendices


def screen_sections(built):
    """[(screen from the spec, its heading, the blocks under it)] for the Screens chapter."""
    parts = support.split_at_headings(chapter(built.doc, TITLES["screens"]), 2)[1:]
    assert len(parts) == len(built.spec["screens"])
    return [(screen, heading, blocks) for screen, (heading, blocks) in zip(built.spec["screens"], parts)]


def section_of(built, screen_id):
    return next(blocks for screen, _, blocks in screen_sections(built) if screen["id"] == screen_id)


def label_before(blocks, table):
    """The text of the nearest paragraph above a table."""
    at = next(i for i, b in enumerate(blocks) if getattr(b, "_tbl", None) is table._tbl)
    return next(b.text for b in reversed(blocks[:at]) if hasattr(b, "text") and b.text.strip())


def project_from_example(folder, **keys):
    """A project like the sample with some top-level spec keys replaced."""
    return support.make_project(folder, spec=support.changed(support.load_spec(support.EXAMPLE), **keys))


SHORT_TIMELINE = {
    "stages": [
        {"name": "Build", "items": [
            {"ref": "1", "name": "Workshops", "start": 1, "end": 2, "client": True},
            {"ref": "2", "name": "Development", "start": 3, "end": 10},
            {"milestone": "M1", "name": "Go-live", "week": 12, "client_action": "Confirm the go-live date"}]}],
    "assumptions": ["One developer."],
}


# ====================================================================== where the output goes
def test_writes_into_the_project_output_folder_only(example):
    assert example.path.parent == example.project / "output"
    assert example.path.name == "Leave Request System – Requirements Specification v0.1.docx"
    assert support.ROOT not in example.path.parents, "tests must not write into the repository"
    snapshot = example.project / "output" / "spec-v0.1.yaml"
    assert snapshot.read_bytes() == (support.EXAMPLE / "spec" / "app.yaml").read_bytes()


def test_document_properties_header_and_footer(example):
    props = example.doc.core_properties
    assert props.title == "Leave Request System – Requirements Specification v0.1"
    assert props.author == "Your Company"  # the neutral profile: no workspace company in tests
    section = example.doc.sections[0]
    assert section.header.paragraphs[0].text == "Leave Request System · v0.1\tDraft for client review"
    assert section.footer.paragraphs[0].text.startswith("Your Company · Confidential\t")
    assert "PAGE" in section.footer._element.xml  # the page number field


def test_needs_screenshots_first(tmp_path):
    project = tmp_path / "no-shots"
    (project / "spec").mkdir(parents=True)
    shutil.copy(support.EXAMPLE / "spec" / "app.yaml", project / "spec" / "app.yaml")
    with pytest.raises(SystemExit, match="No screenshots yet"):
        generate_requirements.build(project)
    assert not (project / "output").exists()


# ====================================================================== chapters
def test_chapters_follow_the_document_format(built):
    numbered, signoff, _ = chapter_headings(built.doc)
    assert [h.split(" ", 1)[1] for h in numbered] == expected_chapter_titles(built.spec)[:-1]
    assert [h.split(" ", 1)[0] for h in numbered] == [str(n) for n in range(1, len(numbered) + 1)]
    assert signoff == TITLES["signoff"], "sign-off is the last chapter and is never numbered"


def test_example_has_exactly_the_default_chapters(example):
    assert support.headings(example.doc, 1) == [
        "1 Users and access", "2 Scope and assumptions", "3 Requirements by role", "4 Functional requirements", "5 Screens",
        "6 Non-functional requirements", "7 Decisions needed before sign-off", "Client acknowledgement and sign-off"]


def test_extra_sections_and_appendix(wide):
    numbered, _, appendices = chapter_headings(wide.doc)
    assert "7 Data migration" in numbered
    assert appendices == ["Appendix A  Reference data"]
    assert support.headings(wide.doc, 1)[-1] == "Appendix A  Reference data", "appendices come after sign-off"
    migration = chapter(wide.doc, "Data migration")
    assert rows(support.table_starting(migration, "No")) == [["No", "Step", "Owner"], ["1", "Export the spreadsheet", "Client"],
                                                             ["2", "Load and check", "Supplier"]]
    assert "Existing bookings of Sample Client Sdn. Bhd. are loaded once before go-live." in support.paragraphs(migration)


def test_unquoted_yes_and_no_in_a_table_stay_words(tmp_path):
    """YAML reads an unquoted No or Yes as false or true; a table in the document must show the word."""
    checklist = yaml.safe_load("""
        title: Go-live checklist
        content:
          - table:
              header: [No, Item, Needed]
              rows:
                - [1, Test data, Yes]
                - [2, Training room, No]
    """)
    assert checklist["content"][0]["table"]["header"][0] is False, "this is what YAML makes of it"
    result = support.generate(project_from_example(tmp_path / "yes-no", extra_sections=[checklist]))
    table = support.table_starting(chapter(result.doc, "Go-live checklist"), "No")
    assert rows(table) == [["No", "Item", "Needed"], ["1", "Test data", "Yes"], ["2", "Training room", "No"]]
    assert round(table.columns[0].width.cm, 1) == 1.3, "a 'No' column is the narrow numbering column"
    assert "False" not in all_text(result.doc) and "True" not in all_text(result.doc)


def test_front_matter_comes_first_in_order(built):
    front = support.paragraphs(support.chapters(built.doc)[0][1])
    order = [front.index(text) for text in (built.spec["project"]["name"], TITLES["at_a_glance"], TITLES["about"], "Contents")]
    assert order == sorted(order)
    assert 'TOC \\o "1-2"' in built.doc.element.xml, "the contents page is a field Word fills in"


def test_company_format_reorders_renumbers_and_renames(temp_workspace, tmp_path):
    (temp_workspace / "branding").mkdir()
    (temp_workspace / "branding" / "document-format.yaml").write_text(yaml.safe_dump({
        "document": {"title": "Functional Specification", "short": "FS"},
        "numbering": "decimal",
        "chapters": ["users_access", "screens", "requirements", "signoff"],
        "titles": {"screens": "Screen designs"},
    }), encoding="utf-8")
    result = support.generate(support.make_project(tmp_path / "leave-request"))
    assert result.path.name == "Leave Request System – Functional Specification v0.1.docx"
    assert support.headings(result.doc, 1) == ["1.0 Users and access", "2.0 Screen designs", "3.0 Functional requirements",
                                              "Client acknowledgement and sign-off"]
    assert support.headings(result.doc, 2)[:2] == ["1.1 User roles", "1.2 Access matrix"]
    assert "Functional Specification (FS)" in all_text(result.doc)  # the cover: the title as the company writes it


# ====================================================================== cross-references
def test_no_placeholder_is_left_in_the_document(built):
    assert PLACEHOLDER.findall(all_text(built.doc)) == []
    section = built.doc.sections[0]
    for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
        assert PLACEHOLDER.findall("".join(p.text for p in part.paragraphs)) == []
    assert "WARNING" not in built.log


def test_references_resolve_to_the_sections_they_name(wide):
    number = {h.split(" ", 1)[1]: h.split(" ", 1)[0] for level in (1, 2) for h in support.headings(wide.doc, level) if " " in h}
    overview = support.paragraphs(chapter(wide.doc, TITLES["users_access"]))[:2]
    assert overview[0] == ("Equipment Booking System lets the staff of Sample Client Sdn. Bhd. book shared equipment. "
                           f"The roles are described in section {number['User roles']} and what each role may do in "
                           f"section {number['Access matrix']}.")
    assert overview[1] == (f"The booking form is specified in section {number['New Booking']} and its rules in FR-BKG-001. "
                           f"The plan is in section {number['Project timeline']}, the migration approach in "
                           f"section {number['Data migration']} and the lists of values in Appendix A.")
    text = all_text(wide.doc)
    assert f"Booking form split into two steps, see section {number['New Booking']}" in text  # version history
    assert f"they are listed in section {number['Decisions needed before sign-off']}." in text  # timeline assumption
    assert "As agreed for FR-BKG-002" in text  # notification template


def test_unknown_and_literal_references_are_reported(tmp_path):
    project = project_from_example(tmp_path / "bad-refs", overview=["Details are in {ref:screen:nowhere}.", "See section 3.2 for the rules."])
    result = support.generate(project)
    assert "2 WARNING(S)" in result.log
    assert "overview: unknown reference {ref:screen:nowhere}" in result.log
    assert "overview: literal cross-reference 'section 3.2'" in result.log
    assert "Details are in {ref:screen:nowhere}." in all_text(result.doc), "an unknown reference stays visible"


# ====================================================================== users and access
def test_access_matrix_has_one_column_per_role(built):
    matrix = support.table_starting(chapter(built.doc, TITLES["users_access"]), "Menu or action")
    roles = [r["name"] for r in built.spec["roles"]]
    assert len(matrix.columns) == 1 + len(roles)
    assert header(matrix) == ["Menu or action"] + roles
    assert all(len(row) == 1 + len(roles) and set(row[1:]) <= {"✓", ""} for row in rows(matrix)[1:])


def test_access_matrix_ticks_follow_the_screens(example):
    matrix = rows(support.table_starting(chapter(example.doc, TITLES["users_access"]), "Menu or action"))
    ticks = {row[0]: row[1:] for row in matrix[1:]}  # Employee, Line Manager, HR Admin
    assert ticks["My Applications"] == ["✓", "", ""]
    assert ticks["Pending Approvals"] == ["", "✓", ""]
    assert ticks["Leave Types"] == ["", "", "✓"]
    assert ticks["Leave Application Details: Cancel Application"] == ["✓", "", ""], "a button's own roles win over the screen's"
    assert ticks["Review Leave Application: Approve"] == ["", "✓", ""]
    assert ticks["Leave Types: Add Leave Type"] == ["", "", "✓"]
    assert not any(label.endswith((": Back", ": Cancel", ": View")) for label in ticks), "navigation is not an access right"


def test_access_matrix_leaves_out_demo_and_excluded_buttons(wide):
    labels = column(support.table_starting(chapter(wide.doc, TITLES["users_access"]), "Menu or action"))
    assert "Equipment: Edit" in labels
    assert "Equipment: Print label" not in labels      # access: false
    assert "Booking Details: Show loan terms" not in labels  # example: true
    assert len(labels) == len(set(labels))


def test_access_matrix_turns_role_names_when_there_are_many(example, wide):
    def role_cells(result):
        return support.table_starting(chapter(result.doc, TITLES["users_access"]), "Menu or action").rows[0].cells

    assert [support.rotated(c) for c in role_cells(wide)] == [False] + [True] * 9
    assert not any(support.rotated(c) for c in role_cells(example))


def test_users_and_access_sections(wide):
    blocks = chapter(wide.doc, TITLES["users_access"])
    assert [h for h, _ in support.split_at_headings(blocks, 2)[1:]] == [
        "1.1 User roles", "1.2 Access matrix", "1.3 Process and statuses", "1.4 External systems",
        "1.5 E-mail notifications", "1.6 Terms"]
    assert column(support.table_starting(blocks, "Role")) == [r["name"] for r in wide.spec["roles"]]
    assert column(support.table_starting(blocks, "Status")) == [s["name"] for s in wide.spec["statuses"]]
    assert support.captions(blocks) == ["Figure 1 · Booking process"]


def test_requirements_by_role(wide):
    parts = dict(support.split_at_headings(chapter(wide.doc, TITLES["by_role"]), 2)[1:])
    assert list(parts) == [f"2.{i} {r['name']}" for i, r in enumerate(wide.spec["roles"], 1)]
    storekeeper = support.paragraphs(parts["2.3 Storekeeper"])
    assert "Issue Equipment" in storekeeper[storekeeper.index("Can do") + 1]
    assert any(p.startswith("● Decision needed R-002") for p in storekeeper), "open questions that name the role are shown"
    supervisor = support.paragraphs(parts["2.2 Supervisor"])
    assert supervisor[supervisor.index("E-mails received") + 1].startswith("Booking submitted")
    screens = rows(tables(parts["2.1 Requester"])[0])
    assert ["My Bookings", "4.2"] in screens and ["New Booking", "4.3"] in screens


# ====================================================================== functional requirements
def test_requirement_items_are_numbered_under_their_group(example):
    parts = support.split_at_headings(chapter(example.doc, TITLES["requirements"]), 2)[1:]
    groups = example.spec["requirements"]
    number = next(h for h in support.headings(example.doc, 1) if h.endswith(TITLES["requirements"])).split(" ")[0]
    assert [h for h, _ in parts] == [f"{number}.{i} {g['title']}" for i, g in enumerate(groups, 1)]
    for group, (_, blocks) in zip(groups, parts):
        table = tables(blocks)[0]
        assert header(table) == ["ID", "Requirement"]
        assert column(table, 0) == [f"{group['id']}.{i}" for i in range(1, len(group["items"]) + 1)]
        assert column(table, 1) == group["items"]


def test_requirements_show_priority_screens_and_open_decisions(wide):
    table = rows(tables(support.split_at_headings(chapter(wide.doc, TITLES["requirements"]), 2)[1][1])[0])
    assert table[0] == ["ID", "Requirement", "Priority", "Screen"]
    assert [r[2].strip() for r in table[1:]] == ["Must", "Must", "Should"], "an item's priority overrides its group's"
    assert [r[3] for r in table[1:]] == ["4.3", "4.3", "4.4"]
    assert table[2][1].endswith("● Decision needed R-001")
    assert table[3][1] == "System shall show the booking as specified in section 4.4."


# ====================================================================== screens
def test_one_section_per_screen_in_spec_order(built):
    number = next(h for h in support.headings(built.doc, 1) if h.endswith(" " + TITLES["screens"])).split(" ")[0]
    assert [heading for _, heading, _ in screen_sections(built)] == [
        f"{number}.{i} {s['title']}" for i, s in enumerate(built.spec["screens"], 1)]


def test_every_screen_has_its_figures(built):
    for screen, _, blocks in screen_sections(built):
        shots = [s for s in built.shots if s["screen"] == screen["id"]]
        assert shots, f"no screenshot planned for {screen['id']}"
        assert len(support.captions(blocks)) == len(shots), screen["id"]
        assert all(screen["title"] in c for c in support.captions(blocks)), screen["id"]


def test_figures_are_numbered_through_the_document(built):
    found = support.captions(list(built.doc.iter_inner_content()))
    assert [c.split(" · ")[0] for c in found] == [f"Figure {n}" for n in range(1, len(found) + 1)]
    with_image = [s for s in built.shots if s["screen"] != "__flow" or built.spec.get("statuses")]
    assert len(found) == len(with_image)
    assert f"{len(found)} figures" in built.log


def test_figure_captions_name_steps_and_dialogs(example, wide):
    assert support.captions(section_of(wide, "new-booking")) == ["Figure 4 · New Booking, step 1 of 2", "Figure 5 · New Booking, step 2 of 2"]
    assert support.captions(section_of(example, "review-application")) == [
        "Figure 6 · Review Leave Application", "Figure 7 · Review Leave Application, reject application dialog"]


def test_every_form_has_its_field_table(built):
    forms = [(screen, blocks) for screen, _, blocks in screen_sections(built) if screen.get("sections")]
    assert forms
    for screen, blocks in forms:
        sections = screen["sections"]
        expected = []
        for sec in sections:
            if len(sections) > 1 or sec.get("title"):
                expected.append(sec["title"])  # a group row across the table
            expected += [f["label"] for f in sec["fields"]]
        table = support.tables_with_header(blocks, FIELD_HEADER)[0]
        assert column(table) == expected, screen["id"]


def test_field_table_groups_fields_by_section(wide):
    table = support.tables_with_header(section_of(wide, "new-booking"), FIELD_HEADER)[0]
    group_rows = [r[0] for r in rows(table)[1:] if len(set(r)) == 1]  # one merged cell across the row
    assert group_rows == ["Booking Details", "Equipment", "Declaration"]
    first_group = table.rows[1].cells
    assert all(c._tc is first_group[0]._tc for c in first_group)


def test_field_table_describes_each_field(example):
    table = support.tables_with_header(section_of(example, "new-application"), FIELD_HEADER)[0]
    fields = {r[0]: r[1:] for r in rows(table)[1:]}
    assert fields["Employee"] == ["Text, 100 (read-only)", "✓", "System: signed-in user"]
    assert fields["Leave Type"] == ["Drop-down", "✓", "Leave Types maintained by HR Admin"]
    assert fields["From Date"] == ["Date", "✓", "–"]
    assert fields["To Date"] == ["Date", "✓", "To Date must be on or after From Date"]
    assert fields["Number of Days"] == ["Calculated", "", "Calculated: working days between From and To"]
    assert fields["Reason"] == ["Long text, 500", "✓", "–"]
    assert fields["Supporting Document"] == ["Attachment", "", "File size must be less than 5 MB"]


def test_field_options_become_the_rule(wide):
    table = support.tables_with_header(section_of(wide, "new-booking"), FIELD_HEADER)[0]
    fields = {r[0]: r[1:] for r in rows(table)[1:]}
    assert fields["Equipment"] == ["Drop-down", "✓", "From Equipment"]
    assert fields["Accessories"] == ["Checkboxes", "", "Options: Tripod, Spare battery, Carry case"]
    assert fields["Signature"] == ["Signature", "✓", "–"]


def test_every_list_screen_has_its_column_table(built):
    lists = [(screen, blocks) for screen, _, blocks in screen_sections(built) if screen.get("list") and not screen.get("sections")]
    assert lists
    for screen, blocks in lists:
        table = support.tables_with_header(blocks, ["Column", "Search and filter"])[0]
        assert column(table) == [c["label"] for c in screen["list"]["columns"]], screen["id"]


def test_list_screen_shows_search_filter_sort_and_actions(wide):
    blocks = section_of(wide, "my-bookings")
    marks = {r[0]: r[1].strip() for r in rows(support.tables_with_header(blocks, ["Column", "Search and filter"])[0])[1:]}
    assert marks == {"Booking No": "Search", "Equipment": "", "From": "", "Status": "Filter"}
    text = support.paragraphs(blocks)
    assert "Also filtered by Purpose" in text  # a filter that is not a column
    assert "Sorted by booking date, newest first" in text
    assert "Actions New Booking, View" in text


def test_dialog_fields_are_listed_under_the_screen_that_opens_them(example, wide):
    blocks = section_of(example, "review-application")
    found = support.tables_with_header(blocks, FIELD_HEADER)
    assert [label_before(blocks, t) for t in found] == ["Reject Application", "Approve Application"]
    assert rows(found[0])[1] == ["Reason for rejection", "Long text, 500", "✓", "Please provide a reason for rejection"]
    blocks = section_of(wide, "booking-details")
    found = support.tables_with_header(blocks, FIELD_HEADER)
    assert [label_before(blocks, t) for t in found] == ["Approve Booking", "Reject Booking"]
    assert "Hidden terms field" not in all_text(wide.doc), "doc_table: false keeps a dialog's fields out"


def test_screen_lists_the_requirements_it_covers(wide):
    assert "Requirements · FR-BKG-001" in support.paragraphs(section_of(wide, "new-booking"))
    assert not any(p.startswith("Requirements · ") for p in support.paragraphs(section_of(wide, "audit-log")))


# ====================================================================== decisions and the register
def test_no_register_means_no_open_decisions(example):
    blocks = chapter(example.doc, TITLES["decisions"])
    assert support.paragraphs(blocks) == ["● There are no open decisions in this version."]
    assert tables(blocks) == []


def test_decisions_list_only_open_client_items(wide):
    table = rows(support.table_starting(chapter(wide.doc, TITLES["decisions"]), "ID", nth=0))
    assert table[0] == ["ID", "Question", "Impact", "Owner", "Due"]
    assert [r[0] for r in table[1:]] == ["R-001", "R-002"]
    assert table[1][1:] == ["May two people book the same equipment for overlapping dates?  FR-BKG-001.2",
                            "● Blocks sign-off", "Operations", "2026-11-20"]
    assert table[2][2:] == ["● Needs an answer", "SAMPLE", "–"], "owner defaults to the client, due to a dash"
    assert "2 decisions needed" in wide.log


def test_decisions_columns_are_wide_enough_for_what_they_hold(wide):
    """The owner and due columns had fixed widths narrower than a date: "Operations" printed as "Operation"
    and "s", and "2026-11-20" as "2026-11-" and "20". The widths below are the text in Geist 9 pt plus the
    cell padding (0.39 cm), measured from the font."""
    table = support.table_starting(chapter(wide.doc, TITLES["decisions"]), "ID", nth=0)
    width = dict(zip(header(table), (column.width / 360000 for column in table.columns)))  # cm
    assert width["Due"] >= 1.71 + 0.39, "2026-11-20 on one line"
    assert width["Owner"] >= 1.63 + 0.39, "Operations on one line"
    assert width["Impact"] >= 2.55 + 0.25 + 0.39, "the dot and 'Needs an answer' on one line"
    assert width["Question"] == max(width.values()) and width["Question"] >= 5
    section = wide.doc.sections[0]
    text_width = (section.page_width - section.left_margin - section.right_margin) / 360000
    assert abs(sum(width.values()) - text_width) < 0.05, "the table is as wide as the text"


def test_ids_and_references_never_break_at_a_hyphen(wide):
    """Word breaks a line at an ordinary hyphen, so "FR-BKG-001.2" could end a line as "FR-". IDs and
    references are written with Word's non-breaking hyphen; ordinary words keep theirs."""
    table = support.table_starting(chapter(wide.doc, TITLES["decisions"]), "ID", nth=0)
    cells = table.rows[1].cells
    hyphens = lambda cell: (cell._tc.xml.count("<w:noBreakHyphen/>"), sum("-" in (t.text or "") for t in cell._tc.iter(support.qn("w:t"))))
    assert cells[0].text == "R-001" and hyphens(cells[0]) == (1, 0)
    assert cells[1].text.endswith("FR-BKG-001.2") and hyphens(cells[1]) == (2, 0)
    assert cells[2].text == "● Blocks sign-off" and hyphens(cells[2]) == (0, 1), "a word may still break at its hyphen"
    first_group = rows(tables(chapter(wide.doc, TITLES["requirements"]))[0])
    assert first_group[1][0] == "FR-BKG-001.1", "and it still reads as a plain hyphen"
    assert "FR-BKG-001.1" in all_text(wide.doc)


def test_decisions_columns_stay_within_limits_for_long_owners(tmp_path):
    """A long owner or due text wraps at its spaces; it does not squeeze the question out."""
    project = support.make_project(tmp_path / "long-owner", support.WIDE)
    register = json.loads((project / "register.json").read_text(encoding="utf-8"))
    for item in register["items"]:
        item["owner"], item["due"] = "Procurement and Administration Department", "Before the second workshop"
    (project / "register.json").write_text(json.dumps(register), encoding="utf-8")
    result = support.generate(project)
    table = support.table_starting(chapter(result.doc, TITLES["decisions"]), "ID", nth=0)
    width = dict(zip(header(table), (column.width / 360000 for column in table.columns)))
    assert width["Owner"] <= 3.6 and width["Due"] <= 3.2 and width["Question"] >= 5


def test_internal_items_never_reach_the_document(wide):
    text = all_text(wide.doc)
    assert "R-004" not in text and "INTERNAL-ONLY-MARKER" not in text, "internal fixes are not for the client"


def test_answered_questions_are_recorded_as_decisions_made(wide):
    """The client's answers used to stay in the register, which the client never sees: once resolved, a
    question vanished from the document. They are now on record in the document that is signed."""
    blocks = chapter(wide.doc, TITLES["decisions"])
    made = rows(support.table_starting(blocks, "ID", nth=1))
    assert made == [["ID", "Question", "Decision", "Agreed in"],
                    ["R-003", "How long must closed bookings be kept?", "Seven years.", "v1.2"]]
    assert label_before(blocks, support.table_starting(blocks, "ID", nth=1)).startswith("Questions raised during the requirement study")
    assert "Decisions made" in support.paragraphs(blocks)
    still_open = rows(support.table_starting(blocks, "ID", nth=0))
    assert [r[0] for r in still_open[1:]] == ["R-001", "R-002"], "a resolved question is not also listed as open"
    assert "2 decisions needed, 1 decisions made" in wide.log


# ====================================================================== sign-off
def test_one_signoff_form_per_signatory(example, wide):
    assert len(support.signature_forms(chapter(example.doc, TITLES["signoff"]))) == 2  # the default: client and supplier
    assert len(support.signature_forms(chapter(wide.doc, TITLES["signoff"]))) == len(wide.spec["signoff"]) == 3
    assert "3 signatories" in wide.log


def test_signoff_forms_name_the_signatories_client_first(wide):
    blocks = chapter(wide.doc, TITLES["signoff"])
    forms = support.signature_forms(blocks)
    assert [rows(f)[0][1] for f in forms] == ["Aminah Yusof", "Rajesh Kumar", "Tan Wei Ling"]
    assert [rows(f)[1][1] for f in forms] == ["Head of Operations, Operations", "IT Manager", "Project Lead"]
    assert [label_before(blocks, f) for f in forms] == [
        "Client · Sample Client Sdn. Bhd.  ·  signing for Business owner",
        "Client · Sample Client Sdn. Bhd.  ·  signing for IT",
        "Supplier · Your Company"]
    for form in forms:
        assert rows(form)[2][:2] == ["Signature", ""] and rows(form)[3][:2] == ["Date", ""]
        assert rows(form)[0][2] == "Company stamp"


def test_default_signoff_forms_are_blank(example):
    blocks = chapter(example.doc, TITLES["signoff"])
    forms = support.signature_forms(blocks)
    assert [label_before(blocks, f) for f in forms] == ["Client · Sample Client Sdn. Bhd.  ·  signing for Business owner",
                                                        "Supplier · Your Company"]
    assert all(rows(f)[0][1] == "" for f in forms)


def test_at_a_glance_lists_every_signatory(wide):
    front = support.chapters(wide.doc)[0][1]
    table = rows(support.table_starting(front, "Name"))
    assert table[0] == ["Name", "Organisation", "Signing for", "Status"]
    assert sorted(r[0] for r in table[1:]) == sorted(s["name"] for s in wide.spec["signoff"])
    assert [r[1] for r in table[1:]] == ["Sample Client Sdn. Bhd.", "Sample Client Sdn. Bhd.", "Your Company"], \
        "the client first, as in the sign-off chapter (the spec lists the supplier first)"
    assert all(r[3] == "● Pending" for r in table[1:])


# ====================================================================== timeline
def test_no_timeline_in_the_spec_means_no_timeline_chapter(example):
    assert "timeline" not in example.spec
    assert not any(TITLES["timeline"] in h for h in support.headings(example.doc, 1))
    assert support.tables_with_header(list(example.doc.iter_inner_content()), ["ID", "Milestone", "Week", "Client action"]) == []


def test_timeline_in_the_spec_adds_the_chapter_after_the_nfrs(tmp_path):
    result = support.generate(project_from_example(tmp_path / "with-timeline", timeline=SHORT_TIMELINE))
    assert support.headings(result.doc, 1) == [
        "1 Users and access", "2 Scope and assumptions", "3 Requirements by role", "4 Functional requirements", "5 Screens",
        "6 Non-functional requirements", "7 Project timeline", "8 Decisions needed before sign-off",
        "Client acknowledgement and sign-off"]
    blocks = chapter(result.doc, TITLES["timeline"])
    chart = support.table_starting(blocks, "Week")
    assert len(chart.columns) == 1 + 12, "one column per week up to 40 weeks"
    assert column(chart, 0, skip_header=False) == ["Week", "Build", "1   Workshops", "2   Development", "M1  Go-live"]
    assert rows(support.table_starting(blocks, "ID")) == [["ID", "Milestone", "Week", "Client action"],
                                                          ["M1", "Go-live", "12", "Confirm the go-live date"]]
    assert "One developer." in support.paragraphs(blocks)


def test_long_timeline_groups_weeks_into_at_most_40_columns(wide):
    stages = wide.spec["timeline"]["stages"]
    chart = support.table_starting(chapter(wide.doc, TITLES["timeline"]), "Week")
    assert len(chart.columns) == 1 + 26, "52 weeks: one column per 2 weeks"
    assert len(chart.rows) == 1 + len(stages) + sum(len(s["items"]) for s in stages)
    labels = column(chart, 0, skip_header=False)
    assert [labels.index(s["name"]) for s in stages] == [1, 5, 9, 13], "each stage is a band above its items"

    def cells(label):
        return chart.rows[next(i for i, text in enumerate(labels) if text.endswith(label))].cells

    def bar(label):
        """(first column, columns spanned) of an activity's bar: the one merged cell in its row."""
        row = cells(label)
        first = next(i for i in range(1, len(row)) if row[i]._tc.grid_span > 1)
        return first, row[first]._tc.grid_span

    assert bar("Kick-off and workshops") == (1, 2)     # weeks 1-4
    assert bar("Booking and approval") == (5, 9)       # weeks 10-26
    assert bar("Training and data migration") == (25, 2)  # weeks 49-51
    assert [i for i, c in enumerate(cells("Requirements signed off")) if c.text == "◆"] == [5]  # week 9
    assert [i for i, c in enumerate(cells("MS4 Go-live")) if c.text == "◆"] == [26]             # week 52


def test_timeline_milestones_summary_and_assumptions(wide):
    blocks = chapter(wide.doc, TITLES["timeline"])
    assert rows(support.table_starting(blocks, "ID"))[1:] == [
        ["MS1", "Requirements document signed off", "9", "Review and sign within 5 working days"],
        ["MS2", "Development complete", "37", "–"],
        ["MS3", "UAT signed off", "49", "Sign the UAT report"],
        ["MS4", "Go-live", "52", "–"]]
    assert rows(tables(blocks)[0]) == [["48 – 52 weeks\nKick-off to go-live", "4\nMilestones"]]  # the summary cards
    assert "Two developers during development." in support.paragraphs(blocks)


# ====================================================================== issued versions are locked
def test_issued_version_refuses_to_regenerate(temp_workspace, monkeypatch, capsys):
    project = support.make_project(temp_workspace / "projects" / "leave-request")
    first = support.generate(project)
    before = first.path.read_bytes()
    monkeypatch.setattr(sys, "argv", ["project.py", "issue", "leave-request", "--date", "2026-11-10"])
    project_tool.main()
    assert "Issued v0.1 to SAMPLE on 2026-11-10" in capsys.readouterr().out

    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert "v0.1 was issued to SAMPLE on 2026-11-10 and is locked" in str(stop.value)
    assert first.path.read_bytes() == before

    spec = support.load_spec(project)
    spec["project"]["version"] = "0.2"
    support.write_spec(project, spec)
    second = support.generate(project)
    assert second.path.name == "Leave Request System – Requirements Specification v0.2.docx"
    assert first.path.read_bytes() == before, "the issued version is still there, untouched"


# ====================================================================== without Microsoft Word
def test_document_is_complete_without_word(example):
    assert "Word not available" in example.log
    assert list(example.project.glob("output/*.pdf")) == []
    assert "BPSIG" not in all_text(example.doc), "the invisible signing markers are removed"
    assert Document(str(example.path)).paragraphs  # opens again


def test_signing_markers_are_written_then_stripped(tmp_path, monkeypatch):
    project = support.make_project(tmp_path / "markers", support.WIDE)
    with monkeypatch.context() as m:
        m.setattr(generate_requirements, "strip_markers", lambda path: None)
        result = support.generate(project)
    forms = support.signature_forms(chapter(result.doc, TITLES["signoff"]))
    assert [rows(f)[2][1] for f in forms] == ["BPSIG1", "BPSIG2", "BPSIG3"], "one marker per signature box, for the PDF step"
    generate_requirements.strip_markers(result.path)
    assert "BPSIG" not in all_text(Document(str(result.path)))


@pytest.fixture
def on_windows(monkeypatch):
    """Word is driven on Windows only. The tests of that step fake the PowerShell call, so they run on any
    system by saying they are on Windows."""
    monkeypatch.setattr(generate_requirements.sys, "platform", "win32")


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_word_is_not_tried_on_a_mac_or_linux_even_with_powershell_installed(sandbox, tmp_path, monkeypatch, platform):
    """GitHub's Mac has PowerShell. The Windows script was run there and its failure reported as a fault."""
    monkeypatch.setattr(generate_requirements.sys, "platform", platform)
    run = FakeRun(returncode=1, stderr=b"New-Object: A parameter cannot be found that matches parameter name 'ComObject'.")
    monkeypatch.setattr(subprocess, "run", run)
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    assert sandbox.finish_in_word(docx) == (False, generate_requirements.NO_WORD)
    assert run.calls == [], "PowerShell is not started at all"


class FakeRun:
    """Stands in for subprocess.run: records the call, then fails or succeeds as told."""

    def __init__(self, returncode=0, error=None, write_pdf=None, stderr=b""):
        self.returncode, self.error, self.write_pdf, self.stderr, self.calls = returncode, error, write_pdf, stderr, []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if self.error:
            raise self.error
        if self.write_pdf:
            self.write_pdf.write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(command, self.returncode, b"", self.stderr)


NO_WORD_ERROR = (b"New-Object : Retrieving the COM class factory for component with CLSID {00000000-0000-0000-0000-000000000000} "
                 b"failed due to the following error: 80040154 Class not registered\r\nAt line:1 char:36\r\n+ ... ")
FILE_IN_USE_ERROR = (b'Exception calling "Open" with "1" argument(s): "This file is in use by another\r\napplication or user."'
                     b"\r\nAt line:1 char:90\r\n+ ... $d=$w.Documents.Open(...)\r\n    + CategoryInfo : NotSpecified")


@pytest.mark.parametrize("failure, why", [
    (FakeRun(error=FileNotFoundError("powershell")), generate_requirements.NO_WORD),            # Linux, macOS: no PowerShell
    (FakeRun(returncode=1, stderr=NO_WORD_ERROR), generate_requirements.NO_WORD),               # Windows without Word
    (FakeRun(error=subprocess.TimeoutExpired("powershell", 240)), "did not finish within 4 minutes"),  # Word hangs
    (FakeRun(returncode=0), "wrote no PDF"),                                                    # Word ran but wrote no PDF
    (FakeRun(returncode=1, stderr=FILE_IN_USE_ERROR), "This file is in use by another application or user."),
    (FakeRun(returncode=1), "PowerShell ended with code 1"),                                    # failed without saying why
], ids=["no-powershell", "no-word", "timeout", "no-pdf", "file-in-use", "silent"])
def test_word_step_says_why_it_failed_instead_of_raising(sandbox, tmp_path, monkeypatch, failure, why, on_windows):
    monkeypatch.setattr(subprocess, "run", failure)
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    done, reason = sandbox.finish_in_word(docx)
    assert done is False and why in reason
    assert "At line" not in reason, "PowerShell's location lines are not part of the reason"
    assert failure.calls and failure.calls[0][0] == "powershell"


def test_word_step_succeeds_when_word_writes_the_pdf(sandbox, tmp_path, monkeypatch, on_windows):
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    monkeypatch.setattr(subprocess, "run", FakeRun(write_pdf=docx.with_suffix(".pdf")))
    assert sandbox.finish_in_word(docx) == (True, "")


def test_word_step_copes_with_an_apostrophe_in_the_name(sandbox, tmp_path, monkeypatch, on_windows):
    """The paths go into a PowerShell script in single quotes: an apostrophe used to end the quote early,
    and the broken script was reported as "Word not available"."""
    docx = tmp_path / "Staff's Claims System v0.1.docx"
    Document().save(str(docx))
    run = FakeRun(write_pdf=docx.with_suffix(".pdf"))
    monkeypatch.setattr(subprocess, "run", run)
    assert sandbox.finish_in_word(docx) == (True, "")
    script = run.calls[0][-1]
    assert script.count("Staff''s Claims System v0.1.docx'") == 1 and script.count("Staff''s Claims System v0.1.pdf'") == 1
    assert "Staff's" not in script


def test_generating_survives_a_missing_word(sandbox, tmp_path, monkeypatch, on_windows):
    """The whole run with the real Word step, on a machine where PowerShell cannot be started."""
    monkeypatch.setattr(generate_requirements, "finish_in_word", sandbox.finish_in_word)
    monkeypatch.setattr(subprocess, "run", FakeRun(error=FileNotFoundError("powershell")))
    result = support.generate(support.make_project(tmp_path / "no-word"))
    assert "Word not available" in result.log and "FAILED" not in result.log
    assert len(support.signature_forms(chapter(result.doc, TITLES["signoff"]))) == 2
    assert "BPSIG" not in all_text(result.doc)
    assert list(result.project.glob("output/*.pdf")) == []


def test_a_failed_word_step_is_not_called_word_not_available(sandbox, tmp_path, monkeypatch, on_windows):
    """Word is there but the step failed: the run says so, with the reason, and the document is still complete."""
    monkeypatch.setattr(generate_requirements, "finish_in_word", sandbox.finish_in_word)
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=1, stderr=FILE_IN_USE_ERROR))
    result = support.generate(support.make_project(tmp_path / "word-failed"))
    assert "The Word step FAILED" in result.log and "This file is in use by another application or user." in result.log
    assert "Word not available" not in result.log
    assert "BPSIG" not in all_text(result.doc)
    assert list(result.project.glob("output/*.pdf")) == []


@pytest.mark.skipif(shutil.which("powershell") is not None, reason="this machine has PowerShell; covered by the faked runs above")
def test_word_step_on_a_machine_without_powershell(sandbox, tmp_path):
    """Nothing faked: what really happens on Linux (and in CI)."""
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    assert sandbox.finish_in_word(docx) == (False, generate_requirements.NO_WORD)


# ====================================================================== the PDF of an earlier run
def test_an_old_pdf_is_removed_when_no_new_one_is_written(tmp_path):
    """Without this the new Word file sat beside the PDF of the previous content, under the same name."""
    project = support.make_project(tmp_path / "old-pdf")
    first = support.generate(project)
    pdf = first.path.with_suffix(".pdf")
    pdf.write_bytes(b"%PDF-1.4 the previous content")
    spec = support.load_spec(project)
    spec["overview"] = ["Reworded after the client's comments."]
    support.write_spec(project, spec)
    second = support.generate(project)
    assert second.path == first.path and "Reworded after the client's comments." in all_text(second.doc)
    assert not pdf.exists()


def test_a_pdf_that_cannot_be_replaced_stops_the_run(tmp_path, monkeypatch):
    """The PDF is open in a viewer: stop and say so, before a new Word file is written beside it."""
    project = support.make_project(tmp_path / "open-pdf")
    first = support.generate(project)
    before = first.path.read_bytes()
    pdf = first.path.with_suffix(".pdf")
    pdf.write_bytes(b"%PDF-1.4 open in a viewer")
    unlink = type(pdf).unlink

    def locked(self, *args, **kwargs):
        if self.suffix == ".pdf":
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(type(pdf), "unlink", locked)
    with pytest.raises(SystemExit, match="open in another program"):
        generate_requirements.build(project)
    assert first.path.read_bytes() == before and pdf.exists()


# ====================================================================== file names
def test_a_name_windows_cannot_store_is_cleaned_in_the_file_name_only(tmp_path):
    """A colon used to send the document into a hidden stream of an empty file, and a slash into a folder
    that does not exist. The name inside the document stays as the spec has it."""
    spec = support.load_spec(support.EXAMPLE)
    spec["project"]["name"] = "Import/Export: Permit System"
    result = support.generate(support.make_project(tmp_path / "awkward-name", spec=spec))
    assert result.path.name == "Import-Export- Permit System – Requirements Specification v0.1.docx"
    produced = sorted(p.name for p in (result.project / "output").iterdir())
    assert produced == [result.path.name, "spec-v0.1.yaml"]
    assert result.path.stat().st_size > 10_000
    assert result.doc.core_properties.title == "Import/Export: Permit System – Requirements Specification v0.1"
    assert "Import/Export: Permit System" in all_text(result.doc)


# ====================================================================== screenshots that no longer show the spec
def change_spec(project, change):
    spec = support.load_spec(project)
    change(spec)
    support.write_spec(project, spec)


def first_form(spec):
    return next(s for s in spec["screens"] if s["type"] == "form")


REPORTS = {"id": "reports", "type": "list", "title": "Reports", "menu": "Reports", "roles": ["hr"],
           "list": {"data": "applications", "columns": [{"field": "id", "label": "Ref No"}]}}
PHONE = {"id": "phone", "label": "Contact Number", "type": "text"}


def test_a_screen_changed_after_the_screenshots_is_reported(tmp_path):
    project = support.make_project(tmp_path / "new-field")
    change_spec(project, lambda spec: first_form(spec)["sections"][0]["fields"].append(PHONE))
    result = support.generate(project)
    assert "1 WARNING(S)" in result.log
    assert "screenshots: the screens in the spec changed after the screenshots were taken" in result.log
    assert f"python -I tools/mockup.py screenshots {project}" in result.log
    assert "Contact Number" in all_text(result.doc), "the document is still written, from the spec"


@pytest.mark.parametrize("change", [
    lambda spec: spec["requirements"][0]["items"].append("The system shall keep a history of every change."),
    lambda spec: spec["project"].update(version="0.2", status="Final draft", date="2026-12-01"),
    lambda spec: spec["screens"][1].update(description="Reworded description of the first screen."),
    lambda spec: first_form(spec)["sections"][0]["fields"][0].update(validation="Reworded rule", source="Reworded source"),
    lambda spec: spec["roles"][0].update(description="Reworded role.", scope="Own applications"),
    lambda spec: spec["statuses"][0].update(meaning="Reworded meaning."),
    lambda spec: spec.update(overview=["Reworded overview."], nfr=[{"area": "Security", "requirement": "Single sign-on."}]),
], ids=["requirement", "version-status-date", "screen-description", "field-rule", "role-text", "status-meaning", "overview-nfr"])
def test_text_only_the_document_prints_does_not_age_the_screenshots(tmp_path, change):
    project = support.make_project(tmp_path / "reworded")
    change_spec(project, change)
    assert "WARNING" not in support.generate(project).log


def test_a_new_screen_without_a_picture_is_reported(tmp_path):
    project = support.make_project(tmp_path / "new-screen")
    change_spec(project, lambda spec: spec["screens"].append(REPORTS))
    result = support.generate(project)
    assert "2 WARNING(S)" in result.log
    assert "screenshots: the screens in the spec changed after the screenshots were taken" in result.log
    assert "screenshots: no picture for reports: the document has no figure there" in result.log


def test_a_missing_picture_is_reported(tmp_path):
    project = support.make_project(tmp_path / "lost-picture")
    (project / "mockup" / "screenshots" / "approvals.png").unlink()
    result = support.generate(project)
    assert "1 WARNING(S)" in result.log and "screenshots: no picture for approvals:" in result.log


def test_the_projects_own_process_flow_picture_stands_in_for_the_screenshot(tmp_path):
    project = support.make_project(tmp_path / "own-flow", support.WIDE)  # the fixture project has a process flow
    shot = project / "mockup" / "screenshots" / "process-flow.png"
    shutil.move(str(shot), str(project / "spec" / "process-flow.png"))
    assert "WARNING" not in support.generate(project).log


def test_screenshots_from_an_older_blueprint_are_checked_by_their_list_only(tmp_path):
    """They carry no note of the screens they show: a changed field cannot be told, an added screen can."""
    project = support.make_project(tmp_path / "older")
    (project / "mockup" / "screenshots" / "taken-from.json").unlink()
    change_spec(project, lambda spec: first_form(spec)["sections"][0]["fields"].append(PHONE))
    assert "WARNING" not in support.generate(project).log
    change_spec(project, lambda spec: spec["screens"].append(REPORTS))
    assert "the screens in the spec changed after the screenshots were taken" in support.generate(project).log


def test_a_spec_with_errors_is_refused_with_the_errors(tmp_path):
    project = support.make_project(tmp_path / "broken")
    change_spec(project, lambda spec: spec["screens"][1].update(roles=["nobody"]))
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert "The spec has errors" in str(stop.value) and "unknown role 'nobody'" in str(stop.value)
    assert not (project / "output").exists()


# ====================================================================== signing fields in the PDF
def test_signature_fields_are_placed_over_the_markers(tmp_path):
    """The PDF step after Word, on a hand-made PDF: a signing field goes over each marker (inside the box
    drawn around it, or a default rectangle when there is no box) and the marker text is removed."""
    pymupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "signoff.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((101, 204), "BPSIG1", fontsize=4)
    for a, b in (((95, 195), (400, 195)), ((95, 260), (400, 260)), ((95, 195), (95, 260)), ((400, 195), (400, 260))):
        page.draw_line(a, b)
    page.insert_text((101, 404), "BPSIG2", fontsize=4)  # no box around this one
    doc.save(str(pdf))
    doc.close()

    assert generate_requirements.add_signature_fields(pdf, ["Aminah Yusof", "Supplier"]) == 2

    doc = pymupdf.open(str(pdf))
    page = doc[0]
    fields = {w.field_name: w for w in page.widgets()}
    assert sorted(fields) == ["Signature 1 - Aminah Yusof", "Signature 2 - Supplier"]
    assert all(w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE for w in fields.values())
    boxed = fields["Signature 1 - Aminah Yusof"].rect
    assert (round(boxed.x0), round(boxed.y0), round(boxed.x1), round(boxed.y1)) == (97, 197, 398, 258), "inside the box, 2pt in"
    assert "BPSIG" not in page.get_text()
    doc.close()


# ====================================================================== with Microsoft Word (opt-in)
@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("BLUEPRINT_TEST_WORD"),
                    reason="needs Microsoft Word: set BLUEPRINT_TEST_WORD=1 on a Windows machine that has it")
def test_with_word_writes_a_pdf_with_signing_fields(sandbox, tmp_path, monkeypatch):
    pymupdf = pytest.importorskip("pymupdf")
    monkeypatch.setattr(generate_requirements, "finish_in_word", sandbox.finish_in_word)
    result = support.generate(support.make_project(tmp_path / "with-word", support.WIDE))
    assert "PDF written" in result.log and "3 of 3 signing fields" in result.log
    pdf = pymupdf.open(str(result.path.with_suffix(".pdf")))
    fields = [w.field_name for page in pdf for w in page.widgets()]
    text = "".join(page.get_text() for page in pdf)
    pdf.close()
    assert fields == ["Signature 1 - Aminah Yusof", "Signature 2 - Rajesh Kumar", "Signature 3 - Tan Wei Ling"]
    assert "BPSIG" not in text and "BPSIG" not in all_text(result.doc)
    assert "Project timeline" in text


# ====================================================================== Word is always closed
def test_the_word_script_closes_word_whatever_happens(sandbox, tmp_path, monkeypatch, on_windows):
    """A failure half-way used to leave Word running hidden with the document open, which locked it for the
    next run. The script now closes the document without saving and quits Word in a finally block, shows no
    alerts (a question nobody can see would hang it) and keeps the document out of the recent files."""
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    run = FakeRun(write_pdf=docx.with_suffix(".pdf"))
    monkeypatch.setattr(subprocess, "run", run)
    sandbox.finish_in_word(docx)
    script = run.calls[0][-1]
    assert script.index("try{") < script.index("Documents.Open(") < script.index("}finally{") < script.index("$w.Quit([ref]0)")
    assert "$d.Close([ref]0)" in script.split("}finally{")[1]
    assert "$w.DisplayAlerts=0" in script and ",$false,$false,$false);" in script


def test_word_saying_only_command_failed_is_explained(sandbox, tmp_path, monkeypatch, on_windows):
    monkeypatch.setattr(subprocess, "run", FakeRun(returncode=1, stderr=b"Command failed\r\nAt line:1 char:300\r\n+ ..."))
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    done, why = sandbox.finish_in_word(docx)
    assert not done and "could not save the document" in why and "open in another program" in why


def test_a_word_that_does_not_answer_says_how_to_close_it(sandbox, tmp_path, monkeypatch, on_windows):
    monkeypatch.setattr(subprocess, "run", FakeRun(error=subprocess.TimeoutExpired("powershell", 240)))
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    done, why = sandbox.finish_in_word(docx)
    assert not done and "Task Manager" in why and "WINWORD.EXE" in why


# ====================================================================== mistakes in the format file
def company_format(workspace_folder, text, name="document-format.yaml"):
    (workspace_folder / "branding").mkdir(exist_ok=True)
    (workspace_folder / "branding" / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("text, said", [
    ("colors:\n  accent: 12345G\n", "colors.accent: '12345G' is not a colour"),
    ("colors:\n  accent: 1122\n", "Put it in quotes"),
    ("colours:\n  accent: 0A66C2\n", "'colours' is not a setting (did you mean 'colors'?)"),
    ("colors:\n  acent: 0A66C2\n", "colors: 'acent' is not a setting (did you mean 'accent'?)"),
    ("chapters: [users_access, screens, glossary, signoff]\n", "chapters: 'glossary' is not one of users_access"),
    ("front: [cover, summary, contents]\n", "front: 'summary' is not one of cover, at_a_glance, about, contents"),
    ("numbering: decimals\n", "numbering: 'decimals' must be plain or decimal"),
    ("header_footer: mine\n", "header_footer: 'mine' must be generated or template"),
    ("sizes:\n  body: large\n", "sizes.body: 'large' must be a point size"),
    ("fonts:\n  body: 12\n", "fonts.body: must be the name of a font"),
    ("tables:\n  borders: boxes\n", "tables.borders: 'boxes' must be hairline or grid"),
    ("layout:\n  screens_new_page: sometimes\n", "layout.screens_new_page: must be true or false"),
    ("titles:\n  screens: ''\n", "titles.screens: needs a title"),
    ("chapters: users_access\n", "chapters: must be a list"),
], ids=["bad-colour", "number-colour", "british-spelling", "typo-in-a-key", "unknown-chapter", "unknown-front-part", "numbering",
        "header-footer", "size", "font", "borders", "layout", "empty-title", "chapters-not-a-list"])
def test_a_mistake_in_the_format_file_is_named(temp_workspace, tmp_path, text, said):
    """Each of these used to end in a Python traceback, or was silently ignored."""
    company_format(temp_workspace, text)
    project = support.make_project(tmp_path / "leave-request")
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    message = str(stop.value)
    assert "The document format has mistakes" in message and "document-format.yaml" in message
    assert said in message
    assert not (project / "output").exists(), "nothing is written from a broken format"


def test_all_mistakes_in_the_format_are_listed_together():
    fmt = generate_requirements.default_format()
    fmt["colors"]["accent"], fmt["numbering"], fmt["extra"] = "blue", "roman", 1
    errors = generate_requirements.format_errors(fmt)
    assert len(errors) == 3


@pytest.mark.parametrize("written, used", [('"#0a66c2"', "0A66C2"), ("0a66c2", "0A66C2"), ("112233", "112233"), ('" 1F5FBF "', "1F5FBF")],
                         ids=["hash", "lower-case", "all-digits", "spaces"])
def test_a_colour_may_be_written_the_usual_ways(temp_workspace, tmp_path, written, used):
    company_format(temp_workspace, f"colors:\n  accent: {written}\n")
    assert generate_requirements.format_errors(fmt := generate_requirements.load_format()) == []
    assert fmt["colors"]["accent"] == used
    support.generate(support.make_project(tmp_path / "leave-request"))


def test_the_default_format_has_no_mistakes():
    assert generate_requirements.format_errors(generate_requirements.default_format()) == []


def test_the_format_file_is_still_read_under_its_old_name(temp_workspace, tmp_path):
    """branding/srs-format.yaml, the name before 0.4.0: the changelog promised it keeps working."""
    company_format(temp_workspace, "document:\n  title: System Requirement Specifications\n  short: SRS\n", name="srs-format.yaml")
    result = support.generate(support.make_project(tmp_path / "leave-request"))
    assert result.path.name == "Leave Request System – System Requirement Specifications v0.1.docx"


# ====================================================================== mistakes in the spec's document parts
@pytest.mark.parametrize("change, said", [
    (lambda s: s["requirements"].append({"id": "FR-NEW-001", "title": "New group"}), "requirement group FR-NEW-001: needs 'items'"),
    (lambda s: s["requirements"].append({"id": "FR-NEW-001", "title": "New group", "items": ["", {"note": "x"}]}), "requirement group FR-NEW-001, item 2: needs its text"),
    (lambda s: s["requirements"].append(dict(s["requirements"][0])), "the id is used twice"),
    (lambda s: s.update(notifications=[{"event": "Submitted"}]), "notification 1: missing 'recipient'"),
    (lambda s: s.update(nfr=[{"area": "Security"}]), "non-functional requirement 1: missing 'requirement'"),
    (lambda s: s.update(glossary=[{"term": "LM"}]), "glossary entry 1: missing 'meaning'"),
    (lambda s: s["screens"][1].pop("title"), "missing 'title'"),
    (lambda s: s.update(extra_sections=[{"title": "Notes", "content": [{"text": "a"}]}, {"title": "Notes", "content": [{"text": "b"}]}]),
     "extra section 'Notes': two sections have this title"),
    (lambda s: s.update(extra_sections=[{"title": "Data", "content": [{"table": {"header": ["A", "B"], "rows": [["1"]]}}]}]), "every table row needs 2 cells"),
    (lambda s: s.update(timeline={"stages": [{"name": "Start", "items": [{"milestone": "M0", "name": "Kick-off", "week": 0}]}]}), "'week' must be week numbers from 1"),
    (lambda s: s.update(timeline={"stages": [{"name": "Build", "items": [{"name": "Development", "start": 5, "end": 2}]}]}), "'end' is before 'start'"),
], ids=["no-items", "empty-item", "duplicate-group", "notification", "nfr", "glossary", "screen-title", "twin-extra-sections", "ragged-table",
        "week-zero", "end-before-start"])
def test_a_mistake_in_the_document_parts_of_the_spec_is_named(tmp_path, change, said):
    """The mock-up's check does not look at these parts; they used to end in a traceback (or, for two extra
    sections with one title, in the first section printed twice)."""
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    change(spec)
    support.write_spec(project, spec)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert "The spec has errors in the parts the document prints" in str(stop.value) and said in str(stop.value)
    assert not (project / "output").exists()


def test_the_sample_specs_have_no_document_mistakes():
    for source in (support.EXAMPLE, support.WIDE):
        spec = generate_requirements.json.loads(generate_requirements.json.dumps(support.load_spec(source), default=str))
        assert generate_requirements.document_errors(spec) == [], source.name


# ====================================================================== references in every text
def test_references_and_names_are_resolved_wherever_the_spec_has_text(tmp_path):
    """They used to be resolved in some places only: a role's description, a status meaning, a non-functional
    requirement, a glossary meaning and an integration printed {ref:...} and {client} as typed."""
    spec = support.load_spec(support.WIDE)
    spec["roles"][0]["description"] = "Books equipment for {client}, see {ref:screen:new-booking}."
    spec["roles"][0]["scope"] = "Own bookings in {system}"
    spec["statuses"][0]["meaning"] = "Explained in {ref:section:roles}."
    spec["nfr"][0]["requirement"] = "As listed in {ref:section:access} for {client_short}."
    spec["glossary"][0]["meaning"] = "A term of {company}, see {ref:req:FR-BKG-001}."
    spec["integrations"][0]["purpose"] = "Sign-in for {system}"
    spec["integrations"][0]["notes"] = "See {ref:section:integrations}"
    spec["notifications"][0]["event"] = "Booking submitted in {system}"
    spec["requirements"][0]["title"] = "Book Equipment in {system}"
    result = support.generate(support.make_project(tmp_path / "refs", spec=spec))
    text = all_text(result.doc)
    assert PLACEHOLDER.findall(text) == []
    for expected in ("Books equipment for Sample Client Sdn. Bhd., see section 4.3.", "Own bookings in Equipment Booking System",
                     "Explained in section 1.1.", "As listed in section 1.2 for SAMPLE.", "see FR-BKG-001.",
                     "Sign-in for Equipment Booking System", "See section 1.4", "Booking submitted in Equipment Booking System",
                     "Book Equipment in Equipment Booking System"):
        assert expected in text, expected
    assert "WARNING" not in result.log


def test_a_bad_reference_outside_the_requirements_is_reported_once(tmp_path):
    spec = support.load_spec(support.WIDE)
    spec["roles"][0]["description"] = "See {ref:screen:nowhere} and section 3.2."   # printed in two chapters
    spec["nfr"][0]["requirement"] = "As in Figure 4."
    result = support.generate(support.make_project(tmp_path / "bad-refs", spec=spec))
    assert "3 WARNING(S)" in result.log
    assert result.log.count("unknown reference {ref:screen:nowhere}") == 1
    assert "literal cross-reference 'section 3.2'" in result.log and "literal cross-reference 'Figure 4'" in result.log


# ====================================================================== the cover
@pytest.mark.parametrize("status, settled", [
    ("Signed off", True), ("Approved", True), ("Final", True), ("Approved by the client", True), ("Accepted", True),
    ("Draft for client review", False), ("Not approved", False), ("Unsigned draft", False), ("Awaiting final review", False),
    ("Final draft", False), ("Pending approval", False), ("For approval", False), ("Not yet signed", False),
])
def test_only_a_settled_status_gets_the_green_dot(status, settled):
    assert generate_requirements.status_is_settled(status) is settled


def test_the_cover_dot_follows_the_status(tmp_path):
    def dot_colour(status):
        spec = support.load_spec(support.EXAMPLE)
        spec["project"]["status"] = status
        doc = support.generate(support.make_project(tmp_path / status.replace(" ", "-"), spec=spec)).doc
        para = next(p for p in doc.paragraphs if p.text == f"● {status}")
        return str(para.runs[0].font.color.rgb)

    assert dot_colour("Not approved") == FORMAT["colors"]["warning"]
    assert dot_colour("Signed off") == FORMAT["colors"]["ok"]


def test_the_summary_counts_every_screen_of_the_screens_chapter(wide):
    front = support.chapters(wide.doc)[0][1]
    cards = rows(tables(front)[2])[0]  # after the cover's logo and details tables
    assert cards[1] == f"{len(wide.spec['screens'])}\nScreens"
    assert len(support.split_at_headings(chapter(wide.doc, TITLES["screens"]), 2)[1:]) == len(wide.spec["screens"])


# ====================================================================== house styles: filled headers, grids, coloured headings
def test_tables_can_have_a_filled_header_a_grid_and_coloured_headings(temp_workspace, tmp_path):
    company_format(temp_workspace, 'colors:\n  heading: "1F3864"\ntables:\n  header_fill: "1F3864"\n  borders: grid\n')
    result = support.generate(support.make_project(tmp_path / "house-style", support.WIDE))
    table = support.table_starting(chapter(result.doc, TITLES["decisions"]), "ID", nth=0)
    head, body = table.rows[0].cells[0], table.rows[1].cells[0]
    assert 'w:fill="1F3864"' in head._tc.xml, "the header row is filled"
    assert str(head.paragraphs[0].runs[-1].font.color.rgb) == "FFFFFF", "white text on the fill, unless header_text says otherwise"
    assert 'w:fill=' not in body._tc.xml
    for cell in (head, body):
        borders = cell._tc.tcPr.find(support.qn("w:tcBorders"))
        assert [b.tag.split("}")[1] for b in borders] == ["top", "left", "bottom", "right"], "a box round every cell"
    heading = next(p for p in result.doc.paragraphs if p.style.name == "Heading 1")
    assert str(heading.style.font.color.rgb) == "1F3864"
    assert str(result.doc.styles["Heading 2"].font.color.rgb) == "1F3864"
    title = next(p for p in result.doc.paragraphs if p.text == TITLES["at_a_glance"])
    assert str(title.runs[0].font.color.rgb) == "1F3864", "front-matter page titles follow the headings"


def test_the_header_text_colour_can_be_set(temp_workspace, tmp_path):
    company_format(temp_workspace, 'tables:\n  header_fill: "E9EEF7"\n  header_text: "1F3864"\n')
    result = support.generate(support.make_project(tmp_path / "pale-header", support.WIDE))
    head = support.table_starting(chapter(result.doc, TITLES["decisions"]), "ID", nth=0).rows[0].cells[0]
    assert 'w:fill="E9EEF7"' in head._tc.xml and str(head.paragraphs[0].runs[-1].font.color.rgb) == "1F3864"


def test_the_default_look_is_unchanged(wide):
    table = support.table_starting(chapter(wide.doc, TITLES["decisions"]), "ID", nth=0)
    head, body = table.rows[0].cells[0], table.rows[1].cells[0]
    assert 'w:fill=' not in head._tc.xml and str(head.paragraphs[0].runs[-1].font.color.rgb) == FORMAT["colors"]["secondary"]
    assert [b.tag.split("}")[1] for b in body._tc.tcPr.find(support.qn("w:tcBorders"))] == ["bottom"], "hairlines only"
    assert str(wide.doc.styles["Heading 1"].font.color.rgb) == FORMAT["colors"]["text"]


# ====================================================================== contents and summary cards
def test_contents_lines_are_set_close_together(example):
    """They used the body text's spacing, so a contents of 36 lines ran three lines onto an empty page."""
    for name, before in (("toc 1", 5), ("toc 2", 0)):
        style = example.doc.styles[name]
        assert style.paragraph_format.space_after.pt == 1 and style.paragraph_format.space_before.pt == before
        assert style.paragraph_format.line_spacing == 1.0


def test_summary_cards_are_as_wide_as_the_text(wide):
    front = support.chapters(wide.doc)[0][1]
    cards = tables(front)[2]
    section = wide.doc.sections[0]
    text_width = (section.page_width - section.left_margin - section.right_margin) / 360000
    widths = [column.width / 360000 for column in cards.columns]
    assert abs(sum(widths) + 0.32 * (len(widths) - 1) - text_width) < 0.05, "the cards and the gaps between them fill the line"


# ====================================================================== status rules
def status_tables(doc):
    blocks = chapter(doc, TITLES["users_access"])
    return blocks, [t for t in tables(blocks) if not support.is_figure(t) and header(t)[0] == "Status"]


def test_status_rules_say_who_may_change_a_record_and_where_it_moves(example):
    """The requirements standard asks who may edit, cancel or delete in each status. The document had a
    place for a status's meaning only."""
    blocks, (meanings, rules) = status_tables(example.doc)
    assert header(meanings) == ["Status", "Meaning"]
    assert rows(rules) == [
        ["Status", "May edit", "May cancel", "May delete", "Moves to"],
        ["Draft", "Employee", "Nobody", "Employee", "Pending Approval"],
        ["Pending Approval", "Nobody", "Employee", "Nobody", "Approved, Rejected, Cancelled"],
        ["Approved", "Nobody", "Employee", "Nobody", "Cancelled"],
        ["Rejected", "Employee", "Nobody", "Nobody", "Pending Approval"],
        ["Cancelled", "Nobody", "Nobody", "Nobody", "None: a final status"]]
    assert "Status rules" in support.paragraphs(blocks)
    assert "WARNING" not in example.log and "Note:" not in example.log


def test_all_roles_and_several_roles_are_named(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    spec["statuses"][0].update(edit="all", cancel=["manager", "employee"], delete=["hr"])
    result = support.generate(support.make_project(tmp_path / "rules", spec=spec))
    assert rows(status_tables(result.doc)[1][1])[1] == ["Draft", "All roles", "Employee, Line Manager", "HR Admin", "Pending Approval"]


def test_a_rule_not_yet_given_is_shown_and_warned_about(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    for key in ("cancel", "next"):
        del spec["statuses"][1][key]
    result = support.generate(support.make_project(tmp_path / "open-rules", spec=spec))
    assert rows(status_tables(result.doc)[1][1])[2] == ["Pending Approval", "Nobody", "● To be confirmed", "Nobody", "● To be confirmed"]
    assert "1 WARNING(S)" in result.log
    assert "statuses: rules still to be confirmed for Pending Approval" in result.log


def test_automatic_moves_a_filtered_drop_down_and_a_related_list_are_described(tmp_path):
    """`auto` in the status rules, `options_from` with a filter and a list on a detail screen (where_record)."""
    spec = support.load_spec(support.EXAMPLE)
    spec["statuses"][2].update(next=["cancelled", "rejected"], auto=["rejected"])
    form = next(s for s in spec["screens"] if s["id"] == "new-application")
    next(f for f in form["sections"][0]["fields"] if f["id"] == "leave_type").update(
        options_from={"list": "leave_types", "field": "name", "where": {"requires_attachment": "No"}}, source="")
    spec["screens"].append({"id": "leave-type", "type": "detail", "title": "Leave Type", "data": "leave_types", "record": "Annual Leave",
                            "sections": [{"title": "Leave type", "fields": [{"id": "name", "label": "Name"}]}],
                            "list": {"data": "applications", "title": "Applications of this type", "where_record": {"leave_type": "name"},
                                     "columns": [{"field": "id", "label": "Ref No"}, {"field": "status", "label": "Status"}]}})
    result = support.generate(support.make_project(tmp_path / "auto", spec=spec))
    assert rows(status_tables(result.doc)[1][1])[3][-1] == "Cancelled, Rejected (automatic)"
    text = all_text(result.doc)
    assert "From Leave types where Requires attachment is No" in text
    assert "Applications of this type" in text and "The applications whose leave type is this leave type's name." in text


def test_a_spec_without_status_rules_gets_a_note_not_a_warning(wide):
    """Projects written before status rules existed still generate cleanly; the note says what is missing."""
    assert len(status_tables(wide.doc)[1]) == 1, "no rules table"
    assert "Note: no status rules in the spec" in wide.log and "WARNING" not in wide.log


@pytest.mark.parametrize("change, said", [
    (lambda s: s["statuses"][0].update(edit=["nobody"]), "status Draft: 'edit' names an unknown role 'nobody'"),
    (lambda s: s["statuses"][0].update(delete="employee"), "status Draft: 'delete' must be a list of role ids, or all, or none"),
    (lambda s: s["statuses"][0].update(next=["submitted"]), "status Draft: 'next' names an unknown status 'submitted'"),
    (lambda s: s["statuses"][0].update(next="pending"), "status Draft: 'next' must be a list of status ids"),
], ids=["unknown-role", "role-not-in-a-list", "unknown-status", "next-not-a-list"])
def test_a_mistake_in_a_status_rule_is_named(tmp_path, change, said):
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    change(spec)
    support.write_spec(project, spec)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert said in str(stop.value)


def test_status_rules_do_not_age_the_screenshots(tmp_path):
    """They are printed in the document only: changing one must not ask for new screenshots."""
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    spec["statuses"][0].update(edit="all", next=[])
    spec["scope"]["assumptions"].append("One more assumption.")
    support.write_spec(project, spec)
    assert "WARNING" not in support.generate(project).log


# ====================================================================== scope and assumptions
def test_the_scope_chapter_lists_what_is_in_out_and_assumed(example):
    numbered, _, _ = chapter_headings(example.doc)
    assert numbered[:3] == ["1 Users and access", "2 Scope and assumptions", "3 Requirements by role"]
    blocks = chapter(example.doc, TITLES["scope"])
    text = support.paragraphs(blocks)
    assert text[0].startswith("What this version of Leave Request System covers")
    spec = example.spec["scope"]
    assert text[1:] == (["In scope"] + spec["in_scope"] + ["Out of scope"] + spec["out_of_scope"] + ["Assumptions"] + spec["assumptions"])


def test_no_scope_in_the_spec_means_no_scope_chapter(wide):
    numbered, _, _ = chapter_headings(wide.doc)
    assert TITLES["scope"] not in " ".join(numbered) and numbered[1] == "2 Requirements by role"


def test_the_scope_chapter_can_be_referred_to_and_holds_references(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    spec["overview"] = ["What is delivered is listed in {ref:section:scope}."]
    spec["scope"]["out_of_scope"] = ["Reports beyond the list in {ref:screen:approvals} for {client}."]
    result = support.generate(support.make_project(tmp_path / "scope-refs", spec=spec))
    text = all_text(result.doc)
    assert "What is delivered is listed in section 2." in text
    assert "Reports beyond the list in section 5.5 for Sample Client Sdn. Bhd." in text
    assert "WARNING" not in result.log


@pytest.mark.parametrize("scope, said", [
    (["everything"], "scope: must have in_scope, out_of_scope and assumptions"),
    ({"included": ["Leave"]}, "scope: 'included' is not one of in_scope, out_of_scope, assumptions"),
    ({"in_scope": "Leave applications"}, "scope: 'in_scope' must be a list of sentences"),
], ids=["a-list", "unknown-part", "not-a-list"])
def test_a_mistake_in_the_scope_is_named(tmp_path, scope, said):
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    spec["scope"] = scope
    support.write_spec(project, spec)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert said in str(stop.value)


def test_a_company_that_lists_its_own_chapters_adds_scope_to_get_it(temp_workspace, tmp_path):
    company_format(temp_workspace, "chapters: [users_access, requirements, screens, decisions, signoff]\n")
    result = support.generate(support.make_project(tmp_path / "own-chapters"))
    assert TITLES["scope"] not in " ".join(support.headings(result.doc, 1))


# ====================================================================== decisions made
def test_only_answered_client_questions_are_listed_as_made(tmp_path):
    project = support.make_project(tmp_path / "made", support.WIDE)
    register = json.loads((project / "register.json").read_text(encoding="utf-8"))
    template = next(it for it in register["items"] if it["id"] == "R-003")
    register["items"] += [
        {**template, "id": "R-010", "answer": "", "question": "RESOLVED-WITHOUT-AN-ANSWER"},
        {**template, "id": "R-011", "status": "wont-fix", "question": "DROPPED-QUESTION"},
        {**template, "id": "R-012", "audience": "internal", "question": "INTERNAL-RESOLVED"},
        {**template, "id": "R-013", "answer": "Yes, by e-mail.", "resolved_in": "", "question": "A second answered question?"}]
    (project / "register.json").write_text(json.dumps(register), encoding="utf-8")
    result = support.generate(project)
    made = rows(support.table_starting(chapter(result.doc, TITLES["decisions"]), "ID", nth=1))
    assert [r[0] for r in made[1:]] == ["R-003", "R-013"]
    assert made[2] == ["R-013", "A second answered question?", "Yes, by e-mail.", "–"]
    text = all_text(result.doc)
    for hidden in ("RESOLVED-WITHOUT-AN-ANSWER", "DROPPED-QUESTION", "INTERNAL-RESOLVED"):
        assert hidden not in text


def test_no_answered_questions_means_no_decisions_made_table(example):
    blocks = chapter(example.doc, TITLES["decisions"])
    assert "Decisions made" not in support.paragraphs(blocks) and "0 decisions made" in example.log


# ====================================================================== what the figures on a screen count
def figures_of(built, screen_id):
    blocks = section_of(built, screen_id)
    return rows(next(t for t in tables(blocks) if not support.is_figure(t) and header(t) == ["Figure", "What it counts"]))


def test_every_figure_on_a_dashboard_says_what_it_counts(example):
    """The requirements standard asks for the formula of every KPI (GP-03). Dashboard figures appeared in the
    screenshot only; the document had nowhere to say what each one counts."""
    assert figures_of(example, "my-applications") == [
        ["Figure", "What it counts"],
        ["Pending", "The number of records in the list on this screen where Status is Pending Approval."],
        ["Approved", "The number of records in the list on this screen where Status is Approved."],
        ["Rejected", "The number of records in the list on this screen where Status is Rejected."],
        ["Leave balance (days)", "The employee's entitlement for the year, less the days of approved applications."]]
    assert label_before(section_of(example, "my-applications"), next(
        t for t in tables(section_of(example, "my-applications")) if not support.is_figure(t) and header(t)[0] == "Figure")) == "Figures"


def dashboard(spec):
    return next(s for s in spec["screens"] if s.get("stats"))


def test_counted_figures_are_described_from_their_rule(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    dashboard(spec)["stats"] = [{"label": "All", "count": "all"},
                                {"label": "Open", "count": {"status": ["Pending Approval", "Approved"], "leave_type": "Annual Leave"}},
                                {"label": "Long", "count": {"days": 7}}]
    result = support.generate(support.make_project(tmp_path / "counted", spec=spec))
    assert figures_of(result, "my-applications")[1:] == [
        ["All", "The number of records in the list on this screen."],
        ["Open", "The number of records in the list on this screen where Status is Pending Approval or Approved and Leave Type is Annual Leave."],
        ["Long", "The number of records in the list on this screen where Days is 7."]]
    assert "WARNING" not in result.log and "Note:" not in result.log


def test_a_typed_in_figure_without_a_formula_is_shown_and_warned_about(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    dashboard(spec)["stats"].append({"label": "Carried forward", "value": 3})
    result = support.generate(support.make_project(tmp_path / "no-formula", spec=spec))
    assert figures_of(result, "my-applications")[-1] == ["Carried forward", "● To be confirmed"]
    assert "1 WARNING(S)" in result.log
    assert "screen my-applications: no formula for Carried forward (add `formula` to each figure in stats)" in result.log


def test_a_spec_that_never_gives_a_formula_gets_a_note_not_a_warning(wide):
    """Projects written before formulas existed still generate cleanly."""
    assert figures_of(wide, "my-bookings")[1:] == [["Pending", "● To be confirmed"], ["Returned", "● To be confirmed"]]
    assert "Note: the figures Pending, Returned have no formula" in wide.log and "WARNING" not in wide.log


def test_a_formula_may_hold_references(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    dashboard(spec)["stats"][-1]["formula"] = "As agreed for {client}, see {ref:screen:leave-types}."
    result = support.generate(support.make_project(tmp_path / "formula-refs", spec=spec))
    assert figures_of(result, "my-applications")[-1][1].startswith("As agreed for Sample Client Sdn. Bhd., see section ")


@pytest.mark.parametrize("stat, said", [
    ({"value": 3}, "screen my-applications: every figure in 'stats' needs a label"),
    ({"label": "Balance", "value": 3, "formula": ""}, "screen my-applications, figure Balance: 'formula' must say in words how it is worked out"),
], ids=["no-label", "empty-formula"])
def test_a_mistake_in_a_figure_is_named(tmp_path, stat, said):
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    dashboard(spec)["stats"].append(stat)
    support.write_spec(project, spec)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(project)
    assert said in str(stop.value)


def test_a_formula_does_not_age_the_screenshots(tmp_path):
    project = support.make_project(tmp_path / "leave-request")
    spec = support.load_spec(project)
    dashboard(spec)["stats"][-1]["formula"] = "Reworded: entitlement less approved days."
    spec["integrations"][0]["on_failure"] = "Reworded."
    support.write_spec(project, spec)
    assert "WARNING" not in support.generate(project).log


# ====================================================================== how each integration works
def integration_tables(doc):
    blocks = chapter(doc, TITLES["users_access"])
    return blocks, [t for t in tables(blocks) if not support.is_figure(t) and header(t)[0] == "System"]


def test_integrations_say_what_triggers_them_what_goes_across_and_what_happens_on_failure(example):
    """The requirements standard asks for trigger, fields and failure handling per integration (GP-10). The
    document had a purpose and a direction only."""
    blocks, (summary, details) = integration_tables(example.doc)
    assert header(summary) == ["System", "Purpose", "Direction", "Notes"]
    assert rows(details) == [
        ["System", "Trigger", "Data exchanged", "If it fails"],
        ["Active Directory", "Sign-in, and submitting an application", "Network ID in; name, e-mail and line manager back",
         "Sign-in is refused with a message; an application cannot be submitted without a line manager"],
        ["SMTP", "A status change of an application", "Recipient, subject and the application's details",
         "The e-mail is retried three times; the application's status is not affected"]]
    assert label_before(blocks, details) == "How each exchange works"


def test_an_integration_detail_not_yet_given_is_shown_and_warned_about(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    del spec["integrations"][1]["on_failure"]
    result = support.generate(support.make_project(tmp_path / "open-integration", spec=spec))
    assert rows(integration_tables(result.doc)[1][1])[2][3] == "● To be confirmed"
    assert "1 WARNING(S)" in result.log
    assert "integrations: trigger, data or failure handling still to be confirmed for SMTP" in result.log


def test_integrations_without_details_get_a_note_not_a_warning(wide):
    assert len(integration_tables(wide.doc)[1]) == 1, "the summary table only"
    assert "Note: no integration details in the spec" in wide.log and "WARNING" not in wide.log


# ====================================================================== screens nothing refers to
def test_screens_that_no_requirement_refers_to_are_noted(wide):
    """Where the spec links requirements to screens, a screen nothing points at may mean a missing requirement."""
    assert "Note: no requirement refers to these screens: My Bookings, Audit Log." in wide.log


def test_no_note_when_every_screen_is_referred_to_or_the_spec_does_not_link_at_all(tmp_path, example):
    assert "no requirement refers to" not in example.log, "the sample does not link requirements to screens"
    spec = support.load_spec(support.WIDE)
    spec["requirements"][0]["screens"] += ["my-bookings"]
    spec["requirements"][0]["items"].append({"text": "System shall keep an audit log.", "screens": ["audit-log"]})
    result = support.generate(support.make_project(tmp_path / "all-linked", spec=spec))
    assert "no requirement refers to" not in result.log


# ====================================================================== a role's page
def test_a_roles_introduction_stays_with_the_list_under_it(wide):
    """A role's heading and its one line of description used to end a page on their own."""
    blocks = chapter(wide.doc, TITLES["by_role"])
    intro = next(b for b in blocks if hasattr(b, "text") and b.text.startswith("Books equipment and returns it."))
    assert intro.paragraph_format.keep_with_next is True


# ====================================================================== pictures in the PDF
def test_the_pdf_gets_its_pictures_back_at_full_size(tmp_path):
    """Word's PDF export reduces every picture to about 200 dots per inch. After it, each figure in the PDF
    is replaced by the file it was made from. On a hand-made PDF: two wide figures and a small logo."""
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    def picture(name, size, colour):
        path = tmp_path / name
        Image.new("RGBA", size, colour).save(path)
        return path

    originals = [picture("one.png", (2000, 1000), "#336699"), picture("two.png", (2000, 500), "#993333")]
    reduced = [picture("one-small.png", (400, 200), "#336699"), picture("two-small.png", (400, 100), "#993333")]
    logo = picture("logo.png", (300, 100), "#000000")
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(40, 40, 110, 63), filename=str(logo))            # 2.5 cm wide: not a figure
    page.insert_image(pymupdf.Rect(90, 100, 498, 304), filename=str(reduced[0]))    # 14.4 cm wide
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(90, 100, 498, 202), filename=str(reduced[1]))
    doc.save(str(pdf))
    doc.close()

    assert generate_requirements.sharpen_pdf_pictures(pdf, originals) == (2, "")
    doc = pymupdf.open(str(pdf))
    widths = [sorted(img[2] for img in page.get_images(full=True)) for page in doc]
    doc.close()
    assert widths == [[300, 2000], [2000]], "the figures are full size, each stored once; the logo is as it was"


def test_pictures_that_cannot_be_matched_are_left_alone(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    small, big, other = tmp_path / "small.png", tmp_path / "big.png", tmp_path / "other-shape.png"
    Image.new("RGB", (400, 200), "#336699").save(small)
    Image.new("RGB", (2000, 1000), "#336699").save(big)
    Image.new("RGB", (2000, 2000), "#336699").save(other)
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_image(pymupdf.Rect(90, 100, 498, 304), filename=str(small))
    doc.save(str(pdf))
    doc.close()
    before = pdf.read_bytes()
    count, why = generate_requirements.sharpen_pdf_pictures(pdf, [big, big])
    assert count == 0, "two figures expected, one in the PDF"
    assert why == "the PDF has 1 wide pictures for 2 figures: the pictures could not be matched to the figures, so the PDF keeps Word's reduced pictures"
    assert generate_requirements.sharpen_pdf_pictures(pdf, [other]) == (0, "1 picture did not match the shape of its figure, so the PDF keeps Word's reduced version"),         "a picture of another shape would be the wrong one"
    assert generate_requirements.sharpen_pdf_pictures(pdf, [small]) == (0, "1 picture was already as sharp as the original"),         "nothing to gain from a picture that is no larger"
    assert pdf.read_bytes() == before


def test_every_figure_is_remembered_for_the_pdf(example):
    assert "8 figures" in example.log  # each of them a file the PDF step can put back


# ====================================================================== the standard wording
BOILERPLATE = yaml.safe_load((support.ROOT / "templates" / "document-boilerplate.yaml").read_text(encoding="utf-8"))


def test_the_default_wording_is_short_and_says_each_thing_once(example):
    """It ran to twelve paragraphs that said twice that screens may be refined and that the client
    acknowledges the document, and never said the signed document is the basis for acceptance."""
    assert [len(BOILERPLATE[k]) for k in ("disclaimer", "confidentiality", "concept", "signoff")] == [1, 1, 1, 4]
    words = sum(len(p.split()) for k in ("disclaimer", "confidentiality", "concept", "signoff") for p in BOILERPLATE[k])
    assert words < 240
    everything = " ".join(p for k in ("disclaimer", "confidentiality", "concept", "signoff") for p in BOILERPLATE[k])
    assert everything.count("refined") == 1 and "basis for development and for acceptance testing" in everything
    assert "change request" in everything
    signoff = support.paragraphs(chapter(example.doc, TITLES["signoff"]))
    assert signoff[0] == ("By signing, the client confirms that this document, the Leave Request System – Requirements Specification, "
                          "describes the requirements agreed for the system. It is the basis for development and for acceptance testing.")


def test_a_company_wording_file_without_the_newer_entries_still_works(temp_workspace, tmp_path):
    """A company's own wording file replaces the default as a whole. One written before the scope chapter
    and the decisions-made list existed has no intro for them: the built-in sentence is used."""
    old = {k: v for k, v in BOILERPLATE.items() if k not in ("scope_intro", "decisions_made_intro")}
    (temp_workspace / "branding").mkdir()
    (temp_workspace / "branding" / "document-boilerplate.yaml").write_text(yaml.safe_dump(old, allow_unicode=True), encoding="utf-8")
    result = support.generate(support.make_project(tmp_path / "old-wording"))
    assert support.paragraphs(chapter(result.doc, TITLES["scope"]))[0].startswith("What this version of Leave Request System covers")



def test_identical_figures_share_one_picture_and_are_both_sharpened(tmp_path):
    """Word stores two identical screenshots once, so the PDF had one picture fewer than the figures and
    none of them was put back at full size ("0 of 34"). The shared picture is now replaced once."""
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    big, small = tmp_path / "empty.png", tmp_path / "empty-small.png"
    Image.new("RGB", (2000, 1000), "#336699").save(big)
    Image.new("RGB", (400, 200), "#336699").save(small)
    twin = tmp_path / "empty-again.png"
    twin.write_bytes(big.read_bytes())  # a second screenshot, byte for byte the same
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page().insert_image(pymupdf.Rect(90, 100, 498, 304), filename=str(small))
    doc.save(str(pdf))
    doc.close()
    doc = pymupdf.open(str(pdf))
    assert len({img[0] for page in doc for img in page.get_images(full=True)}) == 1, "one picture, used on both pages"
    doc.close()

    assert generate_requirements.sharpen_pdf_pictures(pdf, [big, twin]) == (2, "")
    doc = pymupdf.open(str(pdf))
    assert [[img[2] for img in page.get_images(full=True)] for page in doc] == [[2000], [2000]]
    doc.close()


def test_one_picture_for_figures_that_differ_is_left_alone_with_the_reason(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from PIL import Image

    small, one, two = tmp_path / "small.png", tmp_path / "one.png", tmp_path / "two.png"
    Image.new("RGB", (400, 200), "#336699").save(small)
    Image.new("RGB", (2000, 1000), "#336699").save(one)
    Image.new("RGB", (2000, 1000), "#993333").save(two)
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for _ in range(2):
        doc.new_page().insert_image(pymupdf.Rect(90, 100, 498, 304), filename=str(small))
    doc.save(str(pdf))
    doc.close()
    before = pdf.read_bytes()
    assert generate_requirements.sharpen_pdf_pictures(pdf, [one, two]) == (
        0, "the pictures could not be matched to the figures, so the PDF keeps Word's reduced pictures")
    assert pdf.read_bytes() == before


def test_the_pdf_step_says_why_pictures_were_not_sharpened(tmp_path, monkeypatch):
    project = support.make_project(tmp_path / "unsharp")

    def word(docx_path):
        docx_path.with_suffix(".pdf").write_bytes(b"")
        return True, ""

    monkeypatch.setattr(generate_requirements, "finish_in_word", word)
    monkeypatch.setattr(generate_requirements, "add_signature_fields", lambda pdf, signers: len(signers))
    monkeypatch.setattr(generate_requirements, "sharpen_pdf_pictures", lambda pdf, pictures: (0, "the PDF has 7 wide pictures for 8 figures: "
                        "the pictures could not be matched to the figures, so the PDF keeps Word's reduced pictures"))
    log = support.generate(project).log
    assert "and 0 of 8 pictures at full size" in log
    assert "Pictures: the PDF has 7 wide pictures for 8 figures: the pictures could not be matched to the figures" in log


# ====================================================================== team-only text
def test_team_only_text_anywhere_in_the_document_is_warned_about(tmp_path):
    """Found in a generated document: a status meaning that began "Proposed:" and named a register item and a
    requirement id of the client's original document, a screen description about the mock-up, and mock-up
    comment ids (from the register's resolved_in) under Decisions made. Each is named with where it is."""
    spec = support.load_spec(support.WIDE)
    spec["statuses"][0]["meaning"] = "Proposed: saved but not sent. Not in the SRS; to be confirmed (R-010, FR-REM-002)."
    spec["screens"][1]["description"] = "Lists bookings; the mock-up shows the table only."
    spec["overview"] = ["The proposed system replaces a paper form.", "See {ref:req:FR-BKG-001} and FR-BKG-001.2."]
    spec["glossary"][0]["meaning"] = "As FR-BKG-001.9 says."
    project = support.make_project(tmp_path / "team-only", support.WIDE, spec=spec)
    register = json.loads((project / "register.json").read_text(encoding="utf-8"))
    register["items"][2]["resolved_in"] = "FB-001"
    register["items"][2]["answer"] = "Seven years, see R-004."
    (project / "register.json").write_text(json.dumps(register), encoding="utf-8")
    log = support.generate(project).log
    assert "status Draft: says 'proposed' ('Proposed: saved but not sent" in log
    assert "status Draft: names R-010, which is not among the decisions needed in this document" in log
    assert "status Draft: names FR-REM-002, which is not a requirement in this spec" in log
    assert "screen my-bookings: mentions the mock-up ('Lists bookings; the mock-up shows the table only.')" in log
    assert "glossary Restricted equipment: names FR-BKG-001.9, which is not a requirement in this spec" in log
    assert "register R-003, resolved_in: names the mock-up comment FB-001" in log
    assert "register R-003, answer: names R-004, an internal register item the client never sees" in log
    assert "overview" not in log, "'the proposed system', a {ref:req:...} and an id of this spec are fine"
    assert "7 WARNING(S)" in log


def test_the_timeline_may_speak_of_the_mock_up(wide):
    assert any("Mock-up" in it.get("name", "") for st in wide.spec["timeline"]["stages"] for it in st["items"])
    assert "WARNING" not in wide.log


def test_team_notes_on_their_own():
    known = {"FR-A-001", "FR-A-001.1"}
    assert generate_requirements.team_notes("Shown in the mockup.", known) == [
        "mentions the mock-up ('Shown in the mockup.'); the document should describe the real system"]
    assert generate_requirements.team_notes("Kept for R-001, see FR-A-001.1 and {ref:req:FR-B-002}.", known, listed={"R-001"}) == []
    assert generate_requirements.team_notes("Mock-up review, proposed date", known, system=False) == []
    assert generate_requirements.team_notes("Agreed in FB-012", known, system=False) == [
        "names the mock-up comment FB-012, which the client cannot look up; say in words what was agreed"]


# ====================================================================== where a decision applies
def test_a_decision_points_at_this_documents_requirements_never_at_another_documents(tmp_path):
    """The register's source names where an item was found, often in the client's original document: its
    requirement ids were printed in Decisions needed, pointing at the wrong requirement or at none."""
    project = support.make_project(tmp_path / "sources", support.WIDE)
    register = json.loads((project / "register.json").read_text(encoding="utf-8"))
    register["items"][0]["source"] = "FR-HQ-001.7"  # R-001 is linked to FR-BKG-001.2 with `tbc` in the spec
    register["items"][1]["source"] = "FR-LR-001.16, FR-BKG-002.2, FR-BKG-002.8"
    (project / "register.json").write_text(json.dumps(register), encoding="utf-8")
    result = support.generate(project)
    table = rows(support.table_starting(chapter(result.doc, TITLES["decisions"]), "ID", nth=0))
    assert table[1][1].endswith("overlapping dates?  FR-BKG-001.2"), "where the spec links it with tbc"
    assert table[2][1].endswith("approved?  FR-BKG-002.2"), "only the ids this spec has"
    text = all_text(result.doc)
    assert "FR-HQ" not in text and "FR-LR" not in text and "FR-BKG-002.8" not in text
    assert "Note: the register's source for R-002 (FR-LR-001.16, FR-BKG-002.8) names requirement ids that are not in this spec" in result.log
    assert "WARNING" not in result.log


# ====================================================================== parts still missing
def test_parts_the_standard_asks_for_are_listed_before_issuing(example, wide):
    assert "2 PART(S) MISSING - add these to the spec before issuing:" in example.log
    assert "- timeline: none in the spec" in example.log
    assert "- sign-off: nobody is named, so the forms are blank" in example.log
    assert "1 PART(S) MISSING" in wide.log and "- scope: nothing says what is in scope, out of scope and assumed" in wide.log


def test_empty_scope_lists_no_nfrs_and_unnamed_signatories_are_listed(tmp_path):
    spec = support.load_spec(support.WIDE)
    spec["scope"] = {"in_scope": ["Bookings."], "out_of_scope": [], "assumptions": []}
    spec.pop("nfr")
    spec["signoff"][1]["name"] = "TBC"
    spec["signoff"][2]["name"] = ""
    log = support.generate(support.make_project(tmp_path / "gaps", support.WIDE, spec=spec)).log
    for said in ("scope: nothing listed as out of scope", "scope: nothing listed as assumptions",
                 "non-functional requirements: none recorded", "sign-off: no name for Business owner", "sign-off: no name for IT"):
        assert "- " + said in log, said
    assert "5 PART(S) MISSING" in log


def test_nothing_is_listed_as_missing_when_the_spec_has_every_part(tmp_path):
    spec = support.changed(support.load_spec(support.EXAMPLE), timeline=SHORT_TIMELINE,
                           signoff=[{"name": "Aminah Yusof", "organisation": "Sample Client Sdn. Bhd.", "signing_for": "Business owner"}])
    log = support.generate(support.make_project(tmp_path / "complete", spec=spec)).log
    assert "MISSING" not in log and "WARNING" not in log


# ====================================================================== captions of extra screenshots
def test_extra_screenshots_of_a_screen_get_captions_that_tell_them_apart(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    spec["screenshots"] += [{"screen": "approvals", "role": "hr", "name": "approvals-hr"},
                            {"screen": "application-details", "record": "LV-2026-013", "name": "details-approved"}]
    result = support.generate(support.make_project(tmp_path / "extra-shots", spec=spec))
    caps = support.captions(chapter(result.doc, TITLES["screens"]))
    assert len(caps) == len({c.split(" · ", 1)[1] for c in caps}), caps
    assert any(c.endswith(", as seen by HR Admin") for c in caps), caps
    assert any(c.endswith(", showing record LV-2026-013") for c in caps), caps
    assert "two figures have the caption" not in result.log


def test_two_figures_with_the_same_caption_are_warned_about(tmp_path):
    spec = support.load_spec(support.EXAMPLE)
    spec["screenshots"] += [{"screen": "approvals", "name": "approvals-again"}]
    log = support.generate(support.make_project(tmp_path / "same-caption", spec=spec)).log
    assert "screen approvals: two figures have the caption 'Pending Approvals'" in log and "name approvals-again" in log


# ====================================================================== plain messages
def test_a_project_without_a_spec_gets_a_plain_sentence(tmp_path):
    (tmp_path / "new-project" / "docs").mkdir(parents=True)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(tmp_path / "new-project")
    assert str(stop.value).startswith("No spec at ") and "Build a mock-up first" in str(stop.value)
    with pytest.raises(SystemExit) as stop:
        generate_requirements.build(tmp_path / "no-such-project")
    assert str(stop.value).startswith("No project at ")


def test_the_usage_prints_its_dash_on_an_old_windows_code_page():
    """Run as a person runs it, on a console with an old code page: the "–" in the usage came out as "\\u2013"."""
    r = subprocess.run([sys.executable, "-I", str(support.ROOT / "tools" / "generate_requirements.py")],
                       capture_output=True, timeout=60)  # a pipe: cp1252 on Windows
    assert r.returncode == 1
    assert "<System> – <document title>" in r.stderr.decode("utf-8")


# ====================================================================== what is signed
def test_the_signoff_says_what_is_signed_and_what_is_not(example, wide):
    """It read "v0.2 / Document, 2026-11-06" and "23 (section 7) / Open decisions excluded": a client could not
    tell what was being signed and what was left out."""
    cards = rows(tables(chapter(example.doc, TITLES["signoff"]))[0])[0]
    assert cards == ["Version 0.1\nWhat you are signing \u00b7 6\u00a0November\u00a02026", "No open decisions\nNothing is left out of it",
                     "By hand or digitally\nHow to sign (see below)"]
    cards = rows(tables(chapter(wide.doc, TITLES["signoff"]))[0])[0]
    decisions = next(h for h in support.headings(wide.doc, 1) if h.endswith(TITLES["decisions"])).split()[0]
    assert cards[1] == f"2 decisions still open\nNot part of this sign-off: see section {decisions}"


def test_dates_read_the_same_way_everywhere(example):
    assert generate_requirements.readable_date("2026-11-06") == "6 November 2026"
    assert generate_requirements.readable_date("November 2026") == "November 2026"
    assert generate_requirements.readable_date(None) == ""
    front = support.chapters(example.doc)[0][1]
    assert ["Date", "6 November 2026"] in rows(tables(front)[1])
