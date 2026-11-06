"""Check that Blueprint's documentation and changelog are in step with the code.

Usage:
    python -I tools/check_docs.py               full check (also run on GitHub)
    python -I tools/check_docs.py --pre-commit  also require CHANGELOG.md when app files are staged

Exit codes: 0 all good; 1 problems found; 2 problems found in --pre-commit mode (blocks the commit when
run from the Claude Code hook). Uses only the standard library. See docs/maintaining.md.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_FILES = ("README.md", "CHANGELOG.md", "VERSION")
SEMVER = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - (\d{4}-\d{2}-\d{2})\s*$")


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def check_skills(errors):
    skills = sorted(p.name for p in (ROOT / ".claude" / "skills").iterdir() if (p / "SKILL.md").exists())
    skills_doc = (ROOT / "docs" / "skills.md").read_text(encoding="utf-8")
    claude_md = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^### `?([a-z0-9-]+)`?\s*$", skills_doc, re.M))
    for s in skills:
        if s not in documented:
            errors.append(f"docs/skills.md: no '### {s}' section for the skill .claude/skills/{s}")
        if f"`{s}`" not in claude_md:
            errors.append(f"CLAUDE.md: skill `{s}` is missing from the skills list")
    for s in sorted(documented - set(skills)):
        errors.append(f"docs/skills.md: documents '{s}', but there is no .claude/skills/{s}/SKILL.md")


HAND_OVER = "## Hand over"
MAINTAINER_SKILLS = {"release"}  # for the people who maintain the app itself: nothing to hand to a BA


def headings(text):
    """The '## ' headings of a Markdown text, outside code blocks."""
    found, fenced = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("## "):
            found.append(line.rstrip())
    return found


def check_hand_over(errors):
    """Every skill people use ends with the shared hand-over: what was made, where, for whom, the next step."""
    for path in sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        name = path.parent.name
        if name in MAINTAINER_SKILLS:
            continue
        found = headings(path.read_text(encoding="utf-8"))
        rel = f".claude/skills/{name}/SKILL.md"
        if HAND_OVER not in found:
            errors.append(f"{rel}: no '{HAND_OVER}' section; every skill ends by telling the person what was made, "
                          "where it is, who it is for and the next step (see 'Writing a skill' in docs/maintaining.md)")
        elif found[-1] != HAND_OVER:
            errors.append(f"{rel}: '{HAND_OVER}' must be the last section, but '{found[-1]}' comes after it")


def check_tools(errors):
    tools = sorted(p.name for p in (ROOT / "tools").iterdir() if p.suffix in (".py", ".mjs"))
    tools_doc = (ROOT / "docs" / "tools.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^### `?([\w.-]+\.(?:py|mjs))`?\s*$", tools_doc, re.M))
    for t in tools:
        if t not in documented:
            errors.append(f"docs/tools.md: no '### {t}' section for tools/{t}")
    for t in sorted(documented - set(tools)):
        errors.append(f"docs/tools.md: documents '{t}', but tools/{t} does not exist")


def check_changelog(errors):
    path = ROOT / "CHANGELOG.md"
    if not path.exists():
        errors.append("CHANGELOG.md is missing")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if "## [Unreleased]" not in lines:
        errors.append("CHANGELOG.md: no '## [Unreleased]' section")
    versions = []
    for n, line in enumerate(lines, 1):
        if line.startswith("## [") and line != "## [Unreleased]":
            m = SEMVER.match(line)
            if not m:
                errors.append(f"CHANGELOG.md:{n}: version heading must look like '## [1.2.3] - 2026-11-06': {line}")
                continue
            versions.append((tuple(int(x) for x in m.groups()[:3]), m.group(4), n))
    for (a, da, _), (b, db, n) in zip(versions, versions[1:]):
        if not (a > b and da >= db):
            errors.append(f"CHANGELOG.md:{n}: versions must go newest first (found {'.'.join(map(str, b))} after {'.'.join(map(str, a))})")
    version_file = ROOT / "VERSION"
    if not version_file.exists():
        errors.append("VERSION is missing")
    elif versions:
        current = version_file.read_text(encoding="utf-8").strip()
        newest = ".".join(map(str, versions[0][0]))
        if current != newest:
            errors.append(f"VERSION says {current} but the newest version in CHANGELOG.md is {newest}")
    text = "\n".join(lines)
    for v, _, _ in versions:
        tag = ".".join(map(str, v))
        if f"[{tag}]:" not in text:
            errors.append(f"CHANGELOG.md: no comparison link '[{tag}]: …' at the bottom")


def check_links(errors):
    files = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").glob("*.md"))]
    for f in files:
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)  # ignore code blocks
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            file_part = target.split("#")[0]
            if file_part and not (f.parent / file_part).resolve().exists():
                errors.append(f"{f.relative_to(ROOT).as_posix()}: broken link '{target}'")


def workspace_names():
    """Company and client names from the local workspace, which must never appear in app files."""
    names = set()
    local = ROOT / ".blueprint-local.json"
    ws = ROOT / "workspace"
    if local.exists():
        configured = json.loads(local.read_text(encoding="utf-8-sig")).get("workspace_dir")
        ws = Path(configured) if configured else ws
    company = ws / "company.yaml"
    if company.exists():
        for key in ("name", "short_name"):
            m = re.search(rf"^{key}:\s*(.+?)\s*$", company.read_text(encoding="utf-8"), re.M)
            if m and not m.group(1).startswith("#"):
                names.add(m.group(1).strip("\"'"))
    regs = list((ws / "projects").glob("*/register.json")) + list((ws / "projects").glob("_archive/*/register.json")) if (ws / "projects").exists() else []
    for reg in regs:
        try:
            r = json.loads(reg.read_text(encoding="utf-8"))
        except Exception:
            continue
        names.update(v for v in (r.get("project"), r.get("client")) if v)
    return {n for n in names if len(n) >= 2 and n not in ("Your Company", "YourCo")}


def check_no_workspace_names(errors):
    names = workspace_names()
    if not names:
        return
    patterns = [(n, re.compile(rf"(?<![\w-]){re.escape(n)}(?![\w-])")) for n in names]
    for rel in git("ls-files") + git("ls-files", "--others", "--exclude-standard"):
        p = ROOT / rel
        if p.suffix in (".docx", ".png", ".jpg", ".jpeg", ".pdf", ".xlsx") or rel == "package-lock.json" or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for name, pat in patterns:
            if pat.search(text):
                errors.append(f"{rel}: contains '{name}' from your workspace; app files must not name companies or clients")


def check_staged(errors):
    staged = git("diff", "--cached", "--name-only")
    app = [f for f in staged if not (f.startswith("docs/") or f in DOC_FILES)]
    if app and "CHANGELOG.md" not in staged:
        shown = ", ".join(app[:5]) + (" …" if len(app) > 5 else "")
        errors.append(f"App files are staged ({shown}) but CHANGELOG.md is not: add an entry under [Unreleased] "
                      "and update the docs this change affects (see docs/maintaining.md)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if "--hook" in sys.argv or ("--pre-commit" in sys.argv and not sys.stdin.isatty()):
        # Called by the Claude Code hook before every shell command, with the command as JSON on stdin:
        # act only on `git commit`. The hook's own filter is not relied on, so a failing check can never
        # block ordinary commands.
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except Exception:
            payload = {}
        command = (payload.get("tool_input") or {}).get("command")
        if command is not None and not re.search(r"\bgit\b[^|;&]*\bcommit\b", command):
            sys.exit(0)
    pre_commit = "--pre-commit" in sys.argv or "--hook" in sys.argv
    errors = []
    check_skills(errors)
    check_hand_over(errors)
    check_tools(errors)
    check_changelog(errors)
    check_links(errors)
    check_no_workspace_names(errors)
    if pre_commit:
        check_staged(errors)
    if errors:
        print("Documentation check failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2 if pre_commit else 1)
    print("Documentation check passed.")


if __name__ == "__main__":
    main()
