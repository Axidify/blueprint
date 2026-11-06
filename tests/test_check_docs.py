"""tools/check_docs.py: the hook mode acts only on `git commit`, and the check itself.

The script checks the repository it sits in, so each test copies it into a small made-up repository in a
temp folder and runs it there. The real repository, its git index and the workspace are never read.
"""
import json
import shutil
import subprocess
import sys

import pytest

import support

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Something new.

## [0.1.0] - 2026-01-01

### Added
- The first version.

[0.1.0]: https://example.invalid/releases/0.1.0
"""


SKILL = "---\nname: demo\n---\n\n# Demo\n\n## 1. Do it\n\nThe work.\n\n## Hand over\n\nWhat was made, where, for whom, the next step.\n"


@pytest.fixture
def repo(tmp_path):
    """A tiny repository that passes the documentation check."""
    root = tmp_path / "repo"
    files = {
        "tools/check_docs.py": (support.ROOT / "tools" / "check_docs.py").read_text(encoding="utf-8"),
        ".claude/skills/demo/SKILL.md": SKILL,
        "docs/skills.md": "# Skills\n\n### demo\nA demo skill.\n",
        "docs/tools.md": "# Tools\n\n### check_docs.py\nThe documentation check.\n",
        "CLAUDE.md": "Skills: `demo`.\n",
        "README.md": "See [the tools](docs/tools.md).\n",
        "CHANGELOG.md": CHANGELOG,
        "VERSION": "0.1.0\n",
        "setup.cmd": "rem setup\n",
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def check(repo, *flags, command=None, stdin=None):
    """Run the copied check; `command` is the shell command the hook is told about."""
    if command is not None:
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, "-I", str(repo / "tools" / "check_docs.py"), *flags], input=stdin or "",
                          capture_output=True, text=True, encoding="utf-8", cwd=repo)


@pytest.fixture
def unready(repo):
    """The repository with an app file staged and no changelog entry: a commit must be blocked."""
    (repo / "setup.cmd").write_text("rem changed\n", encoding="utf-8")
    git(repo, "add", "setup.cmd")
    return repo


# ====================================================================== the hook
@pytest.mark.parametrize("command", [
    "ls -la",
    "git status",
    "git add -A",
    "git push origin main",
    "git diff --cached",
    "python -I tools/register.py validate projects/demo",
    "echo commit",
    "git status; echo commit done",
    "git log | grep commit",
    "npm run commit-lint",
])
def test_hook_lets_other_commands_through(unready, command):
    result = check(unready, "--hook", command=command)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), "not a commit: say nothing, block nothing"


@pytest.mark.parametrize("command", [
    "git commit -m 'Change setup'",
    "git commit",
    "git add -A && git commit -m x",
    "git add -A; git commit -m x",
    "git -C . commit -m x",
    "git commit --amend --no-edit",
    'cd repo && git commit -m "x"',
])
def test_hook_blocks_a_commit_that_is_not_ready(unready, command):
    result = check(unready, "--hook", command=command)
    assert result.returncode == 2, "exit code 2 is what blocks the command in Claude Code"
    assert "Documentation check failed:" in result.stderr
    assert "App files are staged (setup.cmd) but CHANGELOG.md is not" in result.stderr


def test_hook_passes_a_commit_that_is_ready(unready):
    (unready / "CHANGELOG.md").write_text(CHANGELOG.replace("Something new.", "Something new.\n- Setup changed."), encoding="utf-8")
    git(unready, "add", "CHANGELOG.md")
    result = check(unready, "--hook", command="git commit -m 'Change setup'")
    assert (result.returncode, result.stdout.strip()) == (0, "Documentation check passed.")


def test_hook_passes_a_commit_of_docs_only(repo):
    (repo / "docs" / "tools.md").write_text("# Tools\n\n### check_docs.py\nThe documentation check, reworded.\n", encoding="utf-8")
    git(repo, "add", "docs/tools.md")
    assert check(repo, "--hook", command="git commit -m docs").returncode == 0


@pytest.mark.parametrize("stdin", ["", "not json", "{}", '{"tool_input": {}}'])
def test_hook_checks_when_it_cannot_tell_the_command(unready, stdin):
    """No command to look at (an unexpected payload): better to check than to wave a commit through."""
    assert check(unready, "--hook", stdin=stdin).returncode == 2


def test_pre_commit_flag_from_a_hook_behaves_the_same(unready):
    """--pre-commit with input piped in (how older hook settings call it) also acts only on commits."""
    assert check(unready, "--pre-commit", command="ls -la").returncode == 0
    assert check(unready, "--pre-commit", command="git commit -m x").returncode == 2


def test_real_hook_settings_call_the_hook_mode():
    """The check above is only useful if the hook in .claude/settings.json really runs --hook on commits."""
    settings = json.loads((support.ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = [h for group in settings["hooks"]["PreToolUse"] for h in group["hooks"]]
    assert {group["matcher"] for group in settings["hooks"]["PreToolUse"]} == {"Bash", "PowerShell"}
    assert all("check_docs.py" in h["command"] and "'--hook'" in h["command"] for h in hooks)
    assert all("git commit" in h["if"] for h in hooks)


# ====================================================================== the check itself
def test_plain_check_passes_and_ignores_what_is_staged(unready):
    result = check(unready)
    assert (result.returncode, result.stdout.strip()) == (0, "Documentation check passed.")


def test_undocumented_tool_fails(repo):
    (repo / "tools" / "new_tool.py").write_text("print('hi')\n", encoding="utf-8")
    result = check(repo)
    assert result.returncode == 1
    assert "docs/tools.md: no '### new_tool.py' section for tools/new_tool.py" in result.stderr


def test_undocumented_skill_fails(repo):
    (repo / ".claude" / "skills" / "extra").mkdir()
    (repo / ".claude" / "skills" / "extra" / "SKILL.md").write_text("---\nname: extra\n---\n", encoding="utf-8")
    result = check(repo)
    assert result.returncode == 1
    assert "docs/skills.md: no '### extra' section" in result.stderr
    assert "CLAUDE.md: skill `extra` is missing from the skills list" in result.stderr


def test_documented_but_missing_tool_fails(repo):
    (repo / "docs" / "tools.md").write_text("# Tools\n\n### check_docs.py\n\n### gone.py\n", encoding="utf-8")
    assert "docs/tools.md: documents 'gone.py', but tools/gone.py does not exist" in check(repo).stderr


def test_version_must_match_the_changelog(repo):
    (repo / "VERSION").write_text("0.2.0\n", encoding="utf-8")
    result = check(repo)
    assert result.returncode == 1
    assert "VERSION says 0.2.0 but the newest version in CHANGELOG.md is 0.1.0" in result.stderr


def test_changelog_needs_an_unreleased_section(repo):
    (repo / "CHANGELOG.md").write_text(CHANGELOG.replace("## [Unreleased]", "## Next"), encoding="utf-8")
    assert "CHANGELOG.md: no '## [Unreleased]' section" in check(repo).stderr


def test_broken_link_fails(repo):
    (repo / "README.md").write_text("See [the guide](docs/guide.md) and [the web](https://example.invalid/x).\n", encoding="utf-8")
    result = check(repo)
    assert result.returncode == 1
    assert "README.md: broken link 'docs/guide.md'" in result.stderr
    assert "example.invalid" not in result.stderr, "web links are not checked"


def test_workspace_names_must_not_appear_in_app_files(repo):
    (repo / "workspace").mkdir()
    (repo / "workspace" / "company.yaml").write_text("name: Borrowed Name Ltd\nshort_name: BNL\n", encoding="utf-8")
    (repo / ".gitignore").write_text("workspace/\n", encoding="utf-8")
    assert check(repo).returncode == 0, "the name is only in the (ignored) workspace"
    (repo / "docs" / "tools.md").write_text("# Tools\n\n### check_docs.py\nWritten for Borrowed Name Ltd.\n", encoding="utf-8")
    result = check(repo)
    assert result.returncode == 1
    assert "docs/tools.md: contains 'Borrowed Name Ltd' from your workspace" in result.stderr


# ====================================================================== the hand-over every skill ends with
def write_skill(repo, name, text):
    (repo / ".claude" / "skills" / name).mkdir(parents=True, exist_ok=True)
    (repo / ".claude" / "skills" / name / "SKILL.md").write_text(text, encoding="utf-8")


def test_a_skill_without_a_hand_over_fails(repo):
    write_skill(repo, "demo", "---\nname: demo\n---\n\n## 1. Do it\n\n## 6. Report\nTell them.\n")
    result = check(repo)
    assert result.returncode == 1
    assert ".claude/skills/demo/SKILL.md: no '## Hand over' section" in result.stderr


def test_the_hand_over_must_be_the_last_section(repo):
    write_skill(repo, "demo", SKILL + "\n## Rules\n\n- Something.\n")
    assert "'## Hand over' must be the last section, but '## Rules' comes after it" in check(repo).stderr


def test_a_hand_over_inside_a_code_block_does_not_count(repo):
    write_skill(repo, "demo", "---\nname: demo\n---\n\n## 1. Do it\n\n```\n## Hand over\n```\n")
    assert "no '## Hand over' section" in check(repo).stderr


def test_the_release_skill_for_maintainers_needs_no_hand_over(repo):
    write_skill(repo, "release", "---\nname: release\n---\n\n## 5. Publish (ask first)\n")
    (repo / "docs" / "skills.md").write_text("# Skills\n\n### demo\n\n### release\n", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("Skills: `demo`, `release`.\n", encoding="utf-8")
    assert check(repo).returncode == 0


# ====================================================================== the skill evaluations
PLUGIN = '{"name": "blueprint-evals", "skills": "./.claude/skills", "experimental": {"evals": "evals"}}\n'
PROMPT = "---\ntags: [smoke]\nruns: 1\nmax_turns: 6\nallowed_tools: [Read, Skill]\n---\n\nHello, what can you do?\n"
GRADERS = {
    "skill-fired.md": "---\ntype: tool_used\ntool: Skill\ninput_match: '\"skill\"\\s*:\\s*\"(?:[\\w-]+:)?demo\"'\n---\n",
    "says-next.md": "---\ntype: regex\npattern: next step\nflags: i\n---\n",
    "criteria.md": "---\ntype: llm\n---\n\nPASS if it names the next step.\nFAIL otherwise.\n",
}


@pytest.fixture
def evals(repo):
    """The repository with a small, well-formed evaluation suite."""
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "plugin.json").write_text(PLUGIN, encoding="utf-8")
    case = repo / "evals" / "says-next"
    (case / "graders").mkdir(parents=True)
    (case / "prompt.md").write_text(PROMPT, encoding="utf-8")
    for name, text in GRADERS.items():
        (case / "graders" / name).write_text(text, encoding="utf-8")
    return repo


def test_a_well_formed_suite_passes(evals):
    result = check(evals)
    assert (result.returncode, result.stderr) == (0, "")


def test_a_repository_without_a_suite_is_not_checked(repo):
    assert check(repo).returncode == 0


def test_results_of_a_run_are_not_cases(evals):
    (evals / "evals" / "results" / "2026-11-06").mkdir(parents=True)
    (evals / "evals" / "results" / "2026-11-06" / "prompt.md").write_text("copied by a run", encoding="utf-8")
    assert check(evals).returncode == 0


@pytest.mark.parametrize("change, message", [
    (lambda case: [g.unlink() for g in (case / "graders").glob("*.md")], "evals/says-next: no graders"),
    (lambda case: (case / "prompt.md").write_text("Hello\n", encoding="utf-8"), "no frontmatter"),
    (lambda case: (case / "prompt.md").write_text(PROMPT.replace("runs: 1", "repeat: 1"), encoding="utf-8"),
     "unknown frontmatter key 'repeat'"),
    (lambda case: (case / "prompt.md").write_text(PROMPT.split("Hello")[0], encoding="utf-8"), "no prompt after the frontmatter"),
    (lambda case: (case / "graders" / "says-next.md").write_text("---\ntype: guess\n---\n", encoding="utf-8"),
     "graders/says-next.md: type must be one of"),
    (lambda case: (case / "graders" / "says-next.md").write_text("---\ntype: regex\nflags: i\n---\n", encoding="utf-8"),
     "a regex grader needs 'pattern'"),
    (lambda case: (case / "graders" / "criteria.md").write_text("---\ntype: llm\n---\n", encoding="utf-8"),
     "an llm grader needs its PASS/FAIL criteria"),
    (lambda case: (case / "graders" / "skill-fired.md").write_text(GRADERS["skill-fired.md"].replace("demo", "gone"), encoding="utf-8"),
     "expects the skill 'gone', which does not exist"),
])
def test_a_malformed_case_fails(evals, change, message):
    change(evals / "evals" / "says-next")
    result = check(evals)
    assert result.returncode == 1 and message in result.stderr


def test_the_plugin_must_load_the_skills(evals):
    (evals / ".claude-plugin" / "plugin.json").write_text('{"name": "blueprint-evals"}', encoding="utf-8")
    assert "'skills' must be \"./.claude/skills\"" in check(evals).stderr
