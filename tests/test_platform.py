"""tools/platform_fit.py: what a spec uses, what the platform sheets say about it, and writing the result into the
spec and the sheets.

The sheets come from the starter knowledge in templates/ or from folders the tests write. None is read from or
written to knowledge/ in the app folder, which is a link into the workspace. Nothing here goes online.
"""
import json
import sys

import pytest
import yaml

import support

import mockup
import platform_fit as platform_tool

STARTER = support.ROOT / "tests" / "fixtures" / "knowledge-with-a-platform"  # a starter knowledge base with a platform set up
STARTER_SHEET = STARTER / "platforms" / "joget-dx.md"


def sample():
    return json.loads(json.dumps(support.load_spec(support.EXAMPLE), default=str))


def sheet_folder(folder, rows, product="Acme Forms", docs="https://docs.acme-forms.test/manual/"):
    """A knowledge base with one sheet: rows as (feature, spec keys, support)."""
    path = folder / "platforms" / "acme-forms.md"
    path.parent.mkdir(parents=True)
    lines = [f"# Platform: {product}", "", f"Documentation: {docs}", "Version: 3", "Confirmed by: –", "",
             "| ID | Feature | Spec | Support | What it takes | Block | Source | Checked | Confirmed |", "|---|---|---|---|---|---|---|---|---|"]
    for n, (feature, keys, level) in enumerate(rows, 1):
        lines.append(f"| PF-{n:02d} | {feature} | {keys} | {level} | It takes something | BB-0{n % 9 + 1} | – | – | – |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "leave-request"
    spec = sample()
    spec["project"]["platform"] = "Acme Forms 3 Enterprise"
    support.write_spec(folder, spec)
    return folder


# ====================================================================== the starter sheet
def test_the_starter_sheet_is_complete_and_says_it_is_unchecked():
    sheet = platform_tool.read_sheet(STARTER_SHEET)
    assert sheet["product"] == "Joget DX" and sheet["documentation"].startswith("https://")
    ids = [r["id"] for r in sheet["rows"]]
    assert len(ids) == len(set(ids)) >= 30
    for r in sheet["rows"]:
        assert r["support"] in platform_tool.LEVELS and r["spec"] and r["feature"] and r["takes"], r["id"]
        assert platform_tool.blank(r["source"]) and platform_tool.blank(r["confirmed"]), "nothing in the starter sheet is claimed as checked"
    assert "none of it" in STARTER_SHEET.read_text(encoding="utf-8") and "checked yet" in STARTER_SHEET.read_text(encoding="utf-8")


def test_every_feature_of_the_sample_is_covered_by_the_starter_sheet():
    rows = platform_tool.read_sheet(STARTER_SHEET)["rows"]
    loose = [key for key in platform_tool.features(sample()) if not platform_tool.row_for(key, rows)]
    assert loose == []


def test_the_specific_row_wins_over_the_general_one():
    rows = platform_tool.read_sheet(STARTER_SHEET)["rows"]
    assert platform_tool.row_for("action:export to excel", rows)["feature"] == "Export to Excel"
    assert platform_tool.row_for("action:approve", rows)["feature"] == "Other buttons and actions"
    assert platform_tool.row_for("integration:active directory", rows)["support"] == "configuration"
    assert platform_tool.row_for("integration:sap", rows)["support"] == "custom"


# ====================================================================== what a spec uses
def test_the_features_of_a_spec_are_named_with_where_they_are_used(project):
    found = platform_tool.features(mockup.load_spec(project), project)
    assert found["screen:form"] == ["screen new-application"] and "screen:dashboard" in found
    assert found["stat:formula"] == ["screen my-applications"] and found["stat:count"] == ["screen my-applications"]
    assert "field:lookup" in found and "field:file" in found and "workflow" in found and "dialog" in found
    assert found["integration:active directory"] == ["integration Active Directory"]
    assert "role:data scope" in found and "approval progress" in found and "action:confirm approve" in found
    assert "code:project" not in found
    (project / "spec" / "mockup.js").write_text("// own\n", encoding="utf-8")
    assert platform_tool.features(mockup.load_spec(project), project)["code:project"] == ["spec/mockup.js"]


def test_a_task_inbox_and_a_list_per_role_are_told_apart():
    spec = sample()
    lst = next(s for s in spec["screens"] if s["id"] == "approvals")["list"]
    lst["where"] = {"status": "Pending Approval", "waiting_for_me": True}
    lst["where_by_role"] = {"hr": {"status": "Approved"}}
    found = platform_tool.features(spec)
    assert found["list:task inbox"] == ["screen approvals"] and found["list:filter by role"] == ["screen approvals"]


def test_the_stack_is_the_platform_then_the_rest():
    spec = sample()
    spec["project"].update(platform="Joget DX 9", stack=["Microsoft SQL Server", "Joget DX 9", " "])
    assert platform_tool.stack_of(spec) == ["Joget DX 9", "Microsoft SQL Server"]


@pytest.mark.parametrize("product, found", [("JOGET DX Platform", "Joget DX"), ("Joget DX 9 Enterprise", "Joget DX"), ("joget", None), ("OutSystems", None)])
def test_a_products_sheet_is_found_by_its_name(product, found):
    sheet = platform_tool.find_sheet(product, STARTER)
    assert (sheet["product"] if sheet else None) == found


# ====================================================================== check
def test_check_puts_custom_work_and_gaps_first(project, tmp_path, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Forms", "screen:*, field:*, form:*", "standard"), ("Calculated figures", "stat:formula", "custom"),
                                        ("Signatures", "field:signature", "not supported"), ("Lists", "list*", "configuration")])
    platform_tool.cmd_check(project, kb)
    out = capsys.readouterr().out
    assert "Platform check of Leave Request System, built with Acme Forms 3 Enterprise" in out
    assert "(Acme Forms, not yet confirmed by a lead developer)" in out
    custom = out.index("Custom work: 1")
    assert "PF-02 Calculated figures   [BB-03]" in out[custom:] and "used in: screen my-applications" in out[custom:]
    assert "Not covered by any sheet:" in out and "integration:active directory" in out and "workflow   used in: statuses" in out
    assert "Not yet checked against the documentation: 3 of the 3 kinds of feature used here" in out
    assert "https://docs.acme-forms.test/manual/" in out and "product and feature words only" in out
    assert "standard 1 · configuration 1 · custom 1 · not supported 0" in out


def test_check_names_a_product_that_has_no_sheet(project, tmp_path, capsys):
    spec = sample()
    spec["project"].update(platform="Acme Forms", stack=["Contoso Reports"])
    support.write_spec(project, spec)
    platform_tool.cmd_check(project, sheet_folder(tmp_path / "kb", [("Forms", "*", "standard")]))
    out = capsys.readouterr().out
    assert 'No sheet for Contoso Reports: if it is a product with documentation of its own, find that online and start one: python -I tools/platform_fit.py sheet "Contoso Reports"' in out
    assert "belongs under integrations in the spec, not in project.stack" in out


def test_a_row_checked_online_is_no_longer_listed_as_unchecked(project, tmp_path, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Everything", "*", "standard")])
    platform_tool.cmd_record("Acme Forms", "PF-01", {"source": "https://docs.acme-forms.test/manual/forms"}, kb, given=True)
    capsys.readouterr()
    platform_tool.cmd_check(project, kb)
    assert "Not yet checked" not in capsys.readouterr().out


# ====================================================================== apply
def test_apply_writes_platform_fit_and_leaves_the_rest_of_the_spec_as_it_was(project, tmp_path, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Forms", "screen:*, field:*, form:*", "standard"), ("Calculated figures", "stat:formula", "custom"),
                                        ("Lists", "list*", "configuration")])
    spec_file = project / "spec" / "app.yaml"
    spec_file.write_text("# The team's own note at the top\n" + spec_file.read_text(encoding="utf-8"), encoding="utf-8")
    before = spec_file.read_text(encoding="utf-8")
    platform_tool.cmd_apply(project, kb)
    after = spec_file.read_text(encoding="utf-8")
    assert after.startswith(before.rstrip("\n")), "every line of the spec is kept, comments included"
    fit = yaml.safe_load(after)["platform_fit"]
    assert fit["stack"] == ["Acme Forms 3 Enterprise"] and fit["standard"] == 1
    first = fit["features"][0]
    assert first["what"] == "Calculated figures" and first["support"] == "custom" and first["row"] == "Acme Forms PF-02"
    assert first["source"] == "not yet checked against the documentation" and first["used_in"] == ["screen my-applications"]
    assert {f["support"] for f in fit["features"]} == {"custom", "configuration", "not covered"}
    assert "Wrote platform_fit into" in capsys.readouterr().out
    platform_tool.cmd_apply(project, kb)
    again = spec_file.read_text(encoding="utf-8")
    assert again.count("\nplatform_fit:") == 1 and again.count(platform_tool.FIT_MARK) == 1, "replaced, not added twice"


def test_platform_fit_in_the_middle_of_a_spec_is_replaced_in_place():
    text = "project:\n  name: X\nplatform_fit:\n  checked: old\n  features:\n  - what: old\n\nroles:\n- id: a\n"
    out = platform_tool.replace_fit(text, {"checked": "new", "features": []})
    assert yaml.safe_load(out)["platform_fit"] == {"checked": "new", "features": []}
    assert yaml.safe_load(out)["roles"] == [{"id": "a"}] and "old" not in out


def test_the_platform_notes_never_reach_the_mockup_or_its_screenshots(project, tmp_path, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Calculated figures", "stat:formula", "custom")])
    spec = mockup.load_spec(project)
    plain = mockup.fingerprint(spec, project)
    platform_tool.cmd_apply(project, kb)
    mockup.build(project)
    assert "platform_fit" not in (project / "mockup" / "spec.js").read_text(encoding="utf-8")
    assert mockup.fingerprint(mockup.load_spec(project), project) == plain, "the screenshots are still pictures of the spec"


def test_the_requirements_document_never_prints_the_platform_notes(tmp_path, capsys):
    built = support.make_project(tmp_path / "leave-request")
    kb = sheet_folder(tmp_path / "kb", [("Calculated figures", "stat:formula", "custom")])
    platform_tool.cmd_apply(built, kb)
    result = support.generate(built)
    text = support.all_text(result.doc)
    assert "It takes something" not in text and "Calculated figures" not in text and "platform_fit" not in text


# ====================================================================== the sheets
def test_record_adds_and_changes_rows_and_dates_a_check(tmp_path, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Forms", "screen:*", "standard")])
    platform_tool.cmd_record("acme forms", "new", {"feature": "Signature | pad", "spec": "field:signature", "support": "custom",
                                                   "takes": "A plugin", "block": "BB-04"}, kb, given=True)
    rows = platform_tool.read_sheet(kb / "platforms" / "acme-forms.md")["rows"]
    assert rows[-1]["id"] == "PF-02" and rows[-1]["feature"] == "Signature / pad" and rows[-1]["spec"] == ["field:signature"]
    assert platform_tool.blank(rows[-1]["checked"])
    platform_tool.cmd_record("Acme Forms", "pf-02", {"support": "configuration", "source": "https://docs.acme-forms.test/manual/signature",
                                                    "confirmed": "A. Lead 2026-11-06"}, kb, given=True)
    row = platform_tool.read_sheet(kb / "platforms" / "acme-forms.md")["rows"][-1]
    assert row["support"] == "configuration" and row["source"].endswith("/signature") and row["confirmed"] == "A. Lead 2026-11-06"
    assert row["checked"] == platform_tool.dt.date.today().isoformat() and row["takes"] == "A plugin", "what was not given is kept"
    out = capsys.readouterr().out
    assert "Added PF-02 Signature / pad to the Acme Forms sheet." in out and "Updated PF-02" in out


@pytest.mark.parametrize("args, said", [
    (("Acme Forms", "new", {"feature": "X"}), "A new row needs --spec, --support"),
    (("Acme Forms", "PF-09", {"takes": "x"}), "No row PF-09 in the Acme Forms sheet"),
    (("Acme Forms", "PF-01", {"support": "maybe"}), "Support must be one of standard, configuration, custom, not supported"),
    (("Contoso Reports", "new", {}), 'No sheet for Contoso Reports: start one with  python -I tools/platform_fit.py sheet "Contoso Reports"'),
])
def test_record_says_what_is_wrong(tmp_path, args, said):
    kb = sheet_folder(tmp_path / "kb", [("Forms", "screen:*", "standard")])
    with pytest.raises(SystemExit) as stop:
        platform_tool.cmd_record(*args, kb, given=True)
    assert said in str(stop.value.code)


def test_a_new_sheet_starts_empty_and_is_not_made_twice(tmp_path, capsys):
    kb = tmp_path / "kb"
    platform_tool.cmd_sheet("Contoso Reports 2", "https://learn.contoso.test/reports/", kb, given=True)
    sheet = platform_tool.read_sheet(kb / "platforms" / "contoso-reports-2.md")
    assert sheet["product"] == "Contoso Reports 2" and sheet["documentation"] == "https://learn.contoso.test/reports/" and sheet["rows"] == []
    platform_tool.cmd_record("Contoso Reports 2", "new", {"feature": "Report", "spec": "screen:dashboard", "support": "standard"}, kb, given=True)
    assert platform_tool.read_sheet(kb / "platforms" / "contoso-reports-2.md")["rows"][0]["id"] == "PF-01"
    with pytest.raises(SystemExit) as stop:
        platform_tool.cmd_sheet("Contoso Reports 2", "https://elsewhere.test/", kb, given=True)
    assert "already has a sheet" in str(stop.value.code)


def test_the_starter_knowledge_in_the_app_is_never_written_to_by_accident(monkeypatch):
    monkeypatch.setattr(platform_tool, "ROOT", support.ROOT / "no-such-app-folder")   # no knowledge base in a workspace
    with pytest.raises(SystemExit) as stop:
        platform_tool.cmd_record("Joget DX", "PF-01", {"takes": "changed"}, None, given=False)
    assert "no knowledge base in the workspace" in str(stop.value.code)
    assert "changed" not in STARTER_SHEET.read_text(encoding="utf-8")


def test_show_summarises_a_sheet(capsys):
    platform_tool.cmd_show("Joget DX 9", STARTER)
    out = capsys.readouterr().out
    assert out.startswith("Joget DX: 33 features.") and "0 checked against the documentation" in out
    assert "Custom:" in out and "[not checked]" in out


def test_the_commands_from_the_command_line(project, tmp_path, monkeypatch, capsys):
    kb = sheet_folder(tmp_path / "kb", [("Everything", "*", "standard")])
    run = lambda *args: (monkeypatch.setattr(sys, "argv", ["platform_fit.py", *map(str, args)]), platform_tool.main())
    run("check", project, "--knowledge", kb)
    assert "standard 1" in capsys.readouterr().out
    run("record", "Acme Forms", "new", "--feature", "Charts", "--spec", "screen:chart", "--support", "Custom", "--knowledge", kb)
    assert platform_tool.read_sheet(kb / "platforms" / "acme-forms.md")["rows"][-1]["support"] == "custom"
    with pytest.raises(SystemExit):
        run("sheet", "Contoso", "--knowledge", kb)   # no --docs
    with pytest.raises(SystemExit) as stop:
        run("check", tmp_path / "nowhere", "--knowledge", kb)
    assert "No spec at" in str(stop.value.code)


# ====================================================================== the client's own systems and user management
def test_a_stack_entry_that_names_the_client_is_not_offered_a_sheet(project, tmp_path, capsys):
    """A client's in-house system has no public documentation, and a sheet named after it would put the
    client's name into the shared knowledge base."""
    spec = sample()
    spec["project"].update(platform="Acme Forms", client="Sample Client Sdn. Bhd.", client_short="SCL",
                           stack=["MariaDB 10.11", "SCL DMS (3-in-1)", "Sample Client Sdn. Bhd. mail gateway"])
    support.write_spec(project, spec)
    result = platform_tool.cmd_check(project, sheet_folder(tmp_path / "kb", [("Forms", "*", "standard")]))
    out = capsys.readouterr().out
    assert [p for p, _ in result["own"]] == ["SCL DMS (3-in-1)", "Sample Client Sdn. Bhd. mail gateway"]
    assert "SCL DMS (3-in-1): looks like the client's own system (it names the client), not a product" in out
    assert "describe it under integrations in the spec" in out
    assert 'sheet "SCL DMS' not in out and 'sheet "Sample Client' not in out
    assert 'No sheet for MariaDB 10.11: if it is a product' in out, "a real product is still offered a sheet"
    assert platform_tool.client_system("Microsoft Active Directory", spec) == "", "a product is not the client's"
    assert platform_tool.client_system("SCLX Reports", spec) == "", "only the whole name counts"


def test_a_sheet_named_after_the_client_is_refused(project, tmp_path):
    spec = sample()
    spec["project"].update(client_short="SCL")
    support.write_spec(project, spec)
    with pytest.raises(SystemExit) as stop:
        platform_tool.cmd_sheet("SCL DMS", "https://dms.example.test/", tmp_path / "kb", given=True, project=project)
    assert "looks like the client's own system" in str(stop.value.code)
    assert not (tmp_path / "kb" / "platforms").exists(), "nothing written"
    platform_tool.cmd_sheet("Contoso DMS", "https://learn.contoso.test/dms/", tmp_path / "kb", given=True, project=project)
    assert (tmp_path / "kb" / "platforms" / "contoso-dms.md").exists()


def test_screens_for_managing_users_and_roles_are_found(project):
    spec = sample()
    spec["roles"].append({"id": "sysadmin", "name": "System Administrator"})
    spec["data"]["users"] = [{"id": 1, "name": "A"}]
    spec["screens"] += [
        {"id": "users", "type": "list", "title": "Users", "menu": "Users", "roles": ["sysadmin"], "list": {"data": "users", "columns": []}},
        {"id": "user-form", "type": "form", "title": "User form", "roles": ["sysadmin"], "sections": []},
        {"id": "roles", "type": "list", "title": "Roles", "roles": ["sysadmin"], "list": {"data": "role_table", "columns": []}},
        {"id": "user-access-request", "type": "form", "title": "User Access Request", "sections": []},
    ]
    found = platform_tool.features(spec)
    assert found["screen:user management"] == ["screen users", "screen user-form", "screen roles"], \
        "a form anyone can open is a business form, not user management"
    rows = platform_tool.read_sheet(STARTER_SHEET)["rows"]
    assert platform_tool.row_for("screen:user management", rows)["id"] == "PF-33"


def test_apply_names_the_parts_of_the_mockup_each_feature_is_drawn_in(project, tmp_path, capsys):
    """So the mock-up can tag them "Custom development" while presenting: the element as the mock-up names it."""
    kb = sheet_folder(tmp_path / "kb", [("Calculated figures", "stat:formula", "custom"), ("Approval history", "approval progress", "custom"),
                                        ("Filters", "list:filters", "not supported"), ("Reject reasons", "field:textarea", "configuration")])
    platform_tool.cmd_apply(project, kb)
    fit = {f["what"]: f for f in yaml.safe_load((project / "spec" / "app.yaml").read_text(encoding="utf-8"))["platform_fit"]["features"]}
    assert fit["Calculated figures"]["elements"] == [{"screen": "my-applications", "element": "stat:Leave balance (days)"}]
    assert fit["Calculated figures"]["used_in"] == ["screen my-applications"], "used_in is kept as it was"
    assert {"screen": "application-details", "element": "section:Approval Progress"} in fit["Approval history"]["elements"]
    assert {"screen": "my-applications", "element": "filter:Leave Type"} in fit["Filters"]["elements"], "a filter by the label the list shows"
    assert {"dialog": "reject-dialog", "element": "field:reason"} in fit["Reject reasons"]["elements"]
    tags = mockup.custom_work(mockup.load_spec(project))["tags"]
    assert {"screen": "my-applications", "element": "stat:Leave balance (days)", "label": "Custom development",
            "title": "Calculated figures. It takes something"} in tags
    assert any(t["label"] == "Not standard on Acme Forms" for t in tags) and not any("Reject reasons" in t["title"] for t in tags)
