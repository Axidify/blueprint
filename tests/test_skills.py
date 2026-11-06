"""The skills against the tools.

Skills leave exact options to each tool's `--help` (docs/maintaining.md, "Writing a skill"), so every tool a
skill sends Claude to with `--help` must print its usage. Only app files are read: the skills and the tools'
help. Never the workspace.
"""
import re
import subprocess
import sys

import pytest

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
