"""Create a project folder.

Usage:
    python -I tools/new_project.py <slug> "<Project name>" "<Client name>" [--platform "<platform>"]

Creates projects/<slug>/ in the folder layout people browse: "1 Client documents" for the client's documents,
and _blueprint/ for Blueprint's working files (spec/, feedback/ and an empty register.json, with a README).
The other folders (2 Reviews, 3 Workshops ...) appear when the project has something for them.
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
import layout  # noqa: E402  (where everything is in a project folder)
import project as project_tool  # noqa: E402  (where projects live, and finding earlier work)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("name")
    ap.add_argument("client")
    # No default: a project is on the platform its brief or scope of work names. A default once made every new
    # project a Joget project, and its estimate, platform check and mock-up look followed.
    ap.add_argument("--platform", default="")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.slug):  # also rules out names starting with "_"
        sys.exit("The slug must be lowercase words joined by hyphens, e.g. courier-booking")
    project = project_tool.PROJECTS / a.slug
    if project.exists():
        sys.exit(f"projects/{a.slug} already exists. Carry on with that project, or pick another name.")
    if (project_tool.ARCHIVE / a.slug).exists():
        sys.exit(f"An archived project is already called '{a.slug}' (projects/_archive/{a.slug}). To carry on with it: "
                 f"python -I tools/project.py restore {a.slug}. For a new phase, pick another name, e.g. {a.slug}-phase-2.")
    earlier = project_tool.find_earlier(a.name, client=a.client)
    layout.create_new(project)
    layout.register_json(project).write_text(json.dumps(
        {"project": a.name, "client": a.client, "platform": a.platform, "items": []}, indent=2), encoding="utf-8")
    print(f"Created projects/{a.slug}")
    print(f"  {layout.DOCS}/   the client's documents (brief, SOW, notes, drafts)")
    print(f"  {layout.MACHINE}/           Blueprint's working files: the spec, the register, comments (leave them as they are)")
    print("  The other folders (2 Reviews, 3 Workshops, 4 Mock-up screenshots ...) appear when there is something for them.")
    try:  # the look its mock-up starts with: the spec is written later, with this theme
        import mockup
        theme = mockup.default_theme(a.platform)
        print(f"Mock-up look: {theme}" + (" (what Joget gives without custom screens)" if theme == "joget" else " (calm and modern, in the project's colour)")
              + ". Any other look can be asked for when the mock-up is built.")
    except Exception:
        pass
    if not a.platform.strip():
        print("Platform: not set. Nothing assumes one: set it (the spec's project.platform) once the brief, scope of "
              "work or the lead developer says what it is built on.")
    if earlier:
        print(f"Warning: earlier work on a system like '{a.name}':")
        for f in earlier:
            print(f"  - {project_tool.describe(f)}")
    print(f"Next: put the brief, scope of work or requirements document in the project's \"{layout.DOCS}\" folder (or drop it "
          "into the inbox and say 'process my inbox'), then say 'review the requirements document' or 'build a mock-up'.")
    try:  # the project's overview page follows what was just written; it never stops this command
        import overview; overview.refresh(project)
    except Exception:
        pass


if __name__ == "__main__":
    main()
