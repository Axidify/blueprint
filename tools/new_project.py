"""Create a project folder.

Usage:
    python -I tools/new_project.py <slug> "<Project name>" "<Client name>" [--platform "Joget DX"]

Creates projects/<slug>/ with docs/, reviews/, spec/ and feedback/, and an empty register.json.
Refuses to overwrite an existing project, and a name an archived project already has (restore that one
with `python -I tools/project.py restore <slug>`). Warns when an active or archived project, or a delivered
one in the knowledge base, has the same or a similar system name.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as project_tool  # noqa: E402  (where projects live, and finding earlier work)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("name")
    ap.add_argument("client")
    ap.add_argument("--platform", default="Joget DX")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.slug):  # also rules out names starting with "_"
        sys.exit("The slug must be lowercase words joined by hyphens, e.g. courier-booking")
    project = project_tool.PROJECTS / a.slug
    if project.exists():
        sys.exit(f"projects/{a.slug} already exists. Carry on with that project, or pick another name.")
    if (project_tool.ARCHIVE / a.slug).exists():
        sys.exit(f"An archived project is already called '{a.slug}' (projects/_archive/{a.slug}). To carry on with it: "
                 f"python -I tools/project.py restore {a.slug}. For a new phase, pick another name, e.g. {a.slug}-phase-2.")
    earlier = project_tool.find_earlier(a.name)
    for sub in ("docs", "reviews", "spec", "feedback"):
        (project / sub).mkdir(parents=True)
    (project / "register.json").write_text(json.dumps(
        {"project": a.name, "client": a.client, "platform": a.platform, "items": []}, indent=2), encoding="utf-8")
    print(f"Created projects/{a.slug}")
    print("  docs/          the client's documents (brief, SOW, notes, drafts)")
    print("  spec/          the project spec for the mock-up and the requirements document")
    print("  register.json  questions, gaps and decisions for this project")
    try:  # the look its mock-up starts with: the spec is written later, with this theme
        import mockup
        theme = mockup.default_theme(a.platform)
        print(f"Mock-up look: {theme}" + (" (what Joget gives without custom screens)" if theme == "joget" else " (calm and modern, in the project's colour)")
              + ". Any other look can be asked for when the mock-up is built.")
    except Exception:
        pass
    if earlier:
        print(f"Warning: earlier work on a system like '{a.name}':")
        for f in earlier:
            print(f"  - {project_tool.describe(f)}")
    print("Next: put the brief, scope of work or requirements document in the project's docs folder (or drop it "
          "into the inbox and say 'process my inbox'), then say 'review the requirements document' or 'build a mock-up'.")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
