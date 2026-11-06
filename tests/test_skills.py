"""The skills against the tools and the evaluation suite.

Skills leave exact options to each tool's `--help` (docs/maintaining.md, "Writing a skill"), so every tool a
skill sends Claude to with `--help` must print its usage. The evaluation suite in evals/ is only run on
demand (it costs money), so its shape is checked here: it must parse and pass the documentation check's
rules. Only app files are read: the skills, the tools' help and evals/. Never the workspace.
"""
import re
import subprocess
import sys

import pytest
import yaml

import support

ROOT = support.ROOT
SKILLS = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
HELP = re.compile(r"python -I\s+tools/([\w]+\.py) --help")


def tools_sent_to_help():
    found = {}
    for path in SKILLS:
        for tool in HELP.findall(path.read_text(encoding="utf-8")):
            found.setdefault(tool, path.parent.name)
    return sorted(found.items())


def test_skills_send_claude_to_tool_help():
    assert len(tools_sent_to_help()) >= 3, "the trimmed skills point to the tools' --help for the exact options"


@pytest.mark.parametrize("tool, skill", tools_sent_to_help())
def test_every_tool_a_skill_points_to_prints_its_usage_on_help(tool, skill):
    assert (ROOT / "tools" / tool).exists(), f"the {skill} skill points to tools/{tool}, which does not exist"
    result = subprocess.run([sys.executable, "-I", str(ROOT / "tools" / tool), "--help"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", cwd=ROOT, timeout=60)
    shown = result.stdout + result.stderr
    assert "Usage:" in shown and f"tools/{tool}" in shown, f"{tool} --help does not print its usage"


def frontmatter(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")  # a checkout with Windows line endings
    assert text.startswith("---\n"), f"{path}: no frontmatter"
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head) or {}, body


def cases():
    suite = ROOT / "evals"
    return sorted(p.parent for p in suite.glob("*/prompt.md"))


def test_the_suite_has_cases_and_a_plugin_around_the_skills():
    import json

    meta = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert meta["name"] and meta["skills"] == "./.claude/skills"
    assert len(cases()) >= 6


@pytest.mark.parametrize("case", cases(), ids=lambda p: p.name)
def test_each_case_parses_and_is_well_formed(case):
    sys.path.insert(0, str(ROOT / "tools"))
    import check_docs

    meta, body = frontmatter(case / "prompt.md")
    assert set(meta) <= check_docs.PROMPT_KEYS and body.strip()
    assert meta.get("runs", 3) <= 3, "keep cases cheap: one to three runs"
    assert "Bash" not in meta.get("allowed_tools", []), "Bash needs a sandbox the evaluator lacks on Windows"
    graders = sorted((case / "graders").glob("*.md"))
    assert graders, f"{case.name} has no grader"
    for grader in graders:
        g, g_body = frontmatter(grader)
        assert g["type"] in check_docs.GRADER_NEEDS
        if g["type"] == "regex":
            re.compile(g["pattern"], re.I if "i" in str(g.get("flags", "")) else 0)
        if g["type"] == "llm":
            assert "PASS" in g_body and "FAIL" in g_body


def test_the_suite_passes_the_documentation_check():
    sys.path.insert(0, str(ROOT / "tools"))
    import check_docs

    errors = []
    check_docs.check_evals(errors)
    assert errors == []
