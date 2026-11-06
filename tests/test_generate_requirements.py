"""tools/generate_requirements.py: the structure of the generated Word document.

Documents are generated in temp folders, the way a machine without Microsoft Word does it (see conftest.py),
and read back with python-docx. What a page looks like, the table of contents, page numbers and the PDF
are made by Word and are not checked here, except by the one opt-in test at the end.
"""
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
        elif key != "timeline" or spec.get("timeline"):
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
        "1 Users and access", "2 Requirements by role", "3 Functional requirements", "4 Screens",
        "5 Non-functional requirements", "6 Decisions needed before sign-off", "Client acknowledgement and sign-off"]


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
    assert "Functional specification (FS)" in all_text(result.doc)  # the cover


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
    assert [h for h, _ in parts] == [f"3.{i} {g['title']}" for i, g in enumerate(groups, 1)]
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
    assert [heading for _, heading, _ in screen_sections(built)] == [
        f"4.{i} {s['title']}" for i, s in enumerate(built.spec["screens"], 1)]


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
    table = rows(support.table_starting(chapter(wide.doc, TITLES["decisions"]), "ID"))
    assert table[0] == ["ID", "Question", "Impact", "Owner", "Due"]
    assert [r[0] for r in table[1:]] == ["R-001", "R-002"]
    assert table[1][1:] == ["May two people book the same equipment for overlapping dates?  FR-BKG-001.2",
                            "● Blocks sign-off", "Operations", "2026-11-20"]
    assert table[2][2:] == ["● Needs an answer", "SAMPLE", "–"], "owner defaults to the client, due to a dash"
    assert "2 decisions needed" in wide.log


def test_internal_and_resolved_items_never_reach_the_document(wide):
    text = all_text(wide.doc)
    assert "R-004" not in text and "INTERNAL-ONLY-MARKER" not in text, "internal fixes are not for the client"
    assert "R-003" not in text and "How long must closed bookings be kept?" not in text


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
    assert [r[0] for r in table[1:]] == [s["name"] for s in wide.spec["signoff"]]
    assert all(r[3] == "● Pending" for r in table[1:])


# ====================================================================== timeline
def test_no_timeline_in_the_spec_means_no_timeline_chapter(example):
    assert "timeline" not in example.spec
    assert not any(TITLES["timeline"] in h for h in support.headings(example.doc, 1))
    assert support.tables_with_header(list(example.doc.iter_inner_content()), ["ID", "Milestone", "Week", "Client action"]) == []


def test_timeline_in_the_spec_adds_the_chapter_after_the_nfrs(tmp_path):
    result = support.generate(project_from_example(tmp_path / "with-timeline", timeline=SHORT_TIMELINE))
    assert support.headings(result.doc, 1) == [
        "1 Users and access", "2 Requirements by role", "3 Functional requirements", "4 Screens",
        "5 Non-functional requirements", "6 Project timeline", "7 Decisions needed before sign-off",
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
def test_word_step_says_why_it_failed_instead_of_raising(sandbox, tmp_path, monkeypatch, failure, why):
    monkeypatch.setattr(subprocess, "run", failure)
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    done, reason = sandbox.finish_in_word(docx)
    assert done is False and why in reason
    assert "At line" not in reason, "PowerShell's location lines are not part of the reason"
    assert failure.calls and failure.calls[0][0] == "powershell"


def test_word_step_succeeds_when_word_writes_the_pdf(sandbox, tmp_path, monkeypatch):
    docx = tmp_path / "doc.docx"
    Document().save(str(docx))
    monkeypatch.setattr(subprocess, "run", FakeRun(write_pdf=docx.with_suffix(".pdf")))
    assert sandbox.finish_in_word(docx) == (True, "")


def test_word_step_copes_with_an_apostrophe_in_the_name(sandbox, tmp_path, monkeypatch):
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


def test_generating_survives_a_missing_word(sandbox, tmp_path, monkeypatch):
    """The whole run with the real Word step, on a machine where PowerShell cannot be started."""
    monkeypatch.setattr(generate_requirements, "finish_in_word", sandbox.finish_in_word)
    monkeypatch.setattr(subprocess, "run", FakeRun(error=FileNotFoundError("powershell")))
    result = support.generate(support.make_project(tmp_path / "no-word"))
    assert "Word not available" in result.log and "FAILED" not in result.log
    assert len(support.signature_forms(chapter(result.doc, TITLES["signoff"]))) == 2
    assert "BPSIG" not in all_text(result.doc)
    assert list(result.project.glob("output/*.pdf")) == []


def test_a_failed_word_step_is_not_called_word_not_available(sandbox, tmp_path, monkeypatch):
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
