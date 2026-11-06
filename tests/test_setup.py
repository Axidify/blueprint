"""Running on Windows, macOS and Linux: the commands Claude Code runs as hooks, the machine check, and the
setup and present scripts for macOS and Linux."""
import json
import os
import shutil
import subprocess
import sys

import pytest

import support

import doctor

SETTINGS = json.loads((support.ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
HOOKS = {"session start": (SETTINGS["hooks"]["SessionStart"][0]["hooks"][0]["command"], "status.py", "--brief"),
         "before a commit (Bash)": (SETTINGS["hooks"]["PreToolUse"][0]["hooks"][0]["command"], "check_docs.py", "--hook"),
         "before a commit (PowerShell)": (SETTINGS["hooks"]["PreToolUse"][1]["hooks"][0]["command"], "check_docs.py", "--hook")}
STUB = "import sys\nprint('ran with', sys.argv[1:], 'and got', sys.stdin.read().strip())\nsys.exit({code})\n"


def run_hook(command, folder, stdin="", **env):
    """Run a hook command through the shell, as Claude Code does, with `folder` as the project."""
    return subprocess.run(command, shell=True, input=stdin, capture_output=True, text=True, timeout=60,
                          env={**os.environ, "CLAUDE_PROJECT_DIR": str(folder), "BLUEPRINT_PYTHON": sys.executable, **env})


@pytest.mark.skipif(not shutil.which("node"), reason="the hooks are started with Node.js")
@pytest.mark.parametrize("name", HOOKS)
def test_a_hook_runs_its_tool_and_passes_on_the_input_and_the_result(tmp_path, name):
    """The hooks must work whatever the Python command is called: `python` on Windows, `python3` on a Mac,
    or the one in Blueprint's own .venv. A stand-in tool in a temp project shows the hook starts it with
    the right option, hands it what Claude Code sent, and returns its exit code (2 blocks a commit)."""
    command, script, option = HOOKS[name]
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / script).write_text(STUB.format(code=2), encoding="utf-8")
    result = run_hook(command, tmp_path, stdin='{"tool_input": {"command": "git commit"}}')
    assert result.returncode == 2, result.stderr
    assert f"ran with ['{option}'] and got" in result.stdout and '"git commit"' in result.stdout


@pytest.mark.skipif(not shutil.which("node"), reason="the hooks are started with Node.js")
def test_a_hook_does_nothing_outside_a_blueprint_folder(tmp_path):
    result = run_hook(HOOKS["session start"][0], tmp_path)
    assert result.returncode == 0 and result.stdout == ""


@pytest.mark.skipif(not shutil.which("node") or sys.platform == "win32", reason="the .venv layout tested here is the macOS and Linux one")
def test_a_hook_prefers_blueprints_own_python_environment(tmp_path):
    """setup.sh installs the packages into .venv: the hooks must use that Python, not the system's."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "status.py").write_text("import sys\nprint(sys.executable)\n", encoding="utf-8")
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, tmp_path / ".venv" / "bin" / "python")
    env = {k: v for k, v in os.environ.items() if k != "BLUEPRINT_PYTHON"}
    result = subprocess.run(HOOKS["session start"][0], shell=True, capture_output=True, text=True, timeout=60,
                            env={**env, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(tmp_path / ".venv" / "bin" / "python")


def test_every_python_permission_has_its_mac_form():
    """On a Mac the tools are run with .venv/bin/python; without these rules Claude Code would ask every time."""
    allow = SETTINGS["permissions"]["allow"]
    for rule in [r for r in allow if r.startswith("Bash(python -I tools/")]:
        assert rule.replace("Bash(python -I ", "Bash(.venv/bin/python -I ") in allow, rule


def test_every_tool_with_a_command_line_may_run_without_asking():
    """Seven tools (the tour's among them) had no rule, so Claude Code asked before every run of them."""
    allow = SETTINGS["permissions"]["allow"]
    tools = [p.name for p in sorted((support.ROOT / "tools").glob("*.py")) if "__main__" in p.read_text(encoding="utf-8")]
    for name in tools:
        for form in ("Bash(python -I", "PowerShell(python -I", "Bash(.venv/bin/python -I"):
            assert any(rule.startswith(f"{form} tools/{name}") for rule in allow), f"{form} tools/{name} ...)"


# ---------------------------------------------------------------------- the machine check
def test_the_machine_check_runs_on_this_system():
    results = doctor.check()
    labels = [label for _, _, label, _ in results]
    assert any(label.startswith("Python ") for label in labels) and "Node.js" in labels
    assert any("(screenshots)" in label and ("Edge" in label or "Chrome" in label) for label in labels)
    assert any(label.startswith("Microsoft Word (optional") for label in labels)
    for ok, required, label, fix in results:
        assert isinstance(ok, bool) and isinstance(required, bool) and (ok or fix), label


@pytest.mark.parametrize("platform, script", [("win32", "setup.cmd"), ("darwin", "./setup.sh"), ("linux", "./setup.sh")])
def test_the_machine_check_names_the_setup_script_of_the_system(monkeypatch, platform, script):
    monkeypatch.setattr(doctor, "WINDOWS", platform == "win32")
    monkeypatch.setattr(doctor, "MAC", platform == "darwin")
    monkeypatch.setattr(doctor, "SETUP", "setup.cmd" if platform == "win32" else "./setup.sh")
    monkeypatch.setattr(doctor.importlib, "import_module", lambda name: (_ for _ in ()).throw(ImportError(name)))
    fixes = [fix for ok, _, _, fix in doctor.check() if not ok]
    assert any(script in fix for fix in fixes) and not any(("setup.cmd" in fix) != (platform == "win32") for fix in fixes if "setup" in fix)


def test_word_on_a_mac_is_described_as_a_step_by_hand(monkeypatch):
    monkeypatch.setattr(doctor, "WINDOWS", False)
    monkeypatch.setattr(doctor, "MAC", True)
    found, meaning = doctor.word()
    assert isinstance(found, bool) and "on a Mac you update the table of contents and save the PDF yourself" in meaning


# ---------------------------------------------------------------------- the Node packages setup installs
@pytest.mark.parametrize("name", ["setup.sh", "setup.ps1"])
def test_setup_never_rewrites_the_lock_file(name):
    """`npm install` rewrote package-lock.json whenever the npm on the machine was another version than the one
    that wrote it, so a fresh clone showed a changed file after setup and the next git pull was refused."""
    script = (support.ROOT / name).read_text(encoding="utf-8")
    installs = [line.strip() for line in script.splitlines() if line.strip().startswith("npm ")]
    assert installs and all(line.startswith("npm install --no-save ") for line in installs), installs


def test_setup_installs_only_the_node_packages_blueprint_uses():
    """The geist font package names Next.js as a peer, which npm installed as well: about 450 MB never used."""
    assert "legacy-peer-deps=true" in (support.ROOT / ".npmrc").read_text(encoding="utf-8")
    lock = json.loads((support.ROOT / "package-lock.json").read_text(encoding="utf-8"))
    installed = sorted(p.split("node_modules/")[-1] for p in lock["packages"] if p)
    assert installed == ["geist", "playwright-core"], installed


# ---------------------------------------------------------------------- scripts for macOS and Linux
@pytest.mark.parametrize("name", ["setup.sh", "setup.command", "present.sh", "present.command"])
def test_shell_scripts_have_unix_line_endings_and_a_shebang(name):
    """A script with Windows line endings does not start on a Mac ("bad interpreter")."""
    raw = (support.ROOT / name).read_bytes()
    listed = subprocess.run(["git", "ls-files", "--eol", name], cwd=support.ROOT, capture_output=True, text=True).stdout
    assert raw.startswith(b"#!/usr/bin/env bash\n")
    assert "attr/text eol=lf" in listed, "kept with Unix line endings by .gitattributes on every machine"


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash scripts: checked on macOS and Linux")
@pytest.mark.parametrize("name", ["setup.sh", "setup.command", "present.sh", "present.command"])
def test_shell_scripts_parse(name):
    assert subprocess.run(["bash", "-n", str(support.ROOT / name)], capture_output=True, text=True).returncode == 0


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash scripts: checked on macOS and Linux")
def test_present_names_the_projects_and_refuses_an_unknown_one(tmp_path):
    app = tmp_path / "app"
    (app / "projects" / "leave-request" / "spec").mkdir(parents=True)
    (app / "projects" / "leave-request" / "spec" / "app.yaml").write_text("project: {}\n", encoding="utf-8")
    shutil.copy(support.ROOT / "present.sh", app / "present.sh")
    listed = subprocess.run(["bash", "present.sh", "nowhere"], cwd=app, capture_output=True, text=True, timeout=30)
    assert 'No mock-up spec found for "nowhere".' in listed.stdout and "  leave-request" in listed.stdout and listed.returncode == 1


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash scripts: checked on macOS and Linux")
@pytest.mark.parametrize("arguments, started", [
    ([], "-I tools/mockup.py serve"),                                       # nothing named: the page that lists every mock-up
    (["--port", "9001"], "-I tools/mockup.py serve --port 9001"),           # only options: the same page
    (["leave-request", "--lan"], "-I tools/mockup.py serve projects/leave-request --lan"),
])
def test_present_opens_the_list_of_mockups_unless_a_project_is_named(tmp_path, arguments, started):
    """A stand-in for Python shows what the script starts. It used to ask for a project name to be typed."""
    app = tmp_path / "app"
    (app / "projects" / "leave-request" / "spec").mkdir(parents=True)
    (app / "projects" / "leave-request" / "spec" / "app.yaml").write_text("project: {}\n", encoding="utf-8")
    (app / ".venv" / "bin").mkdir(parents=True)
    stand_in = app / ".venv" / "bin" / "python"
    stand_in.write_text('#!/usr/bin/env bash\necho "started: $*"\n', encoding="utf-8", newline="\n")
    stand_in.chmod(0o755)
    shutil.copy(support.ROOT / "present.sh", app / "present.sh")
    run = subprocess.run(["bash", "present.sh", *arguments], cwd=app, capture_output=True, text=True, timeout=30)
    assert f"started: {started}" in run.stdout, run.stdout + run.stderr


def test_present_cmd_opens_the_list_of_mockups_when_no_project_is_named():
    """On Windows the same: no name typed into a console window."""
    script = (support.ROOT / "present.cmd").read_text(encoding="utf-8")
    assert "python -I tools\\mockup.py serve\n" in script.replace("\r\n", "\n") and "set /p" not in script


def test_the_no_word_message_on_a_mac_says_what_to_do_by_hand(tmp_path, monkeypatch):
    import generate_requirements

    monkeypatch.setattr(generate_requirements.sys, "platform", "darwin")
    result = support.generate(support.make_project(tmp_path / "on-a-mac"))
    assert "Word not available to Blueprint on a Mac" in result.log
    assert "Update Table" in result.log and "Save As" in result.log and "signing fields are added on Windows only" in result.log
