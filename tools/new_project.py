"""Create a project folder.

Usage:
    python -I tools/new_project.py <slug> "<Project name>" "<Client name>" [--platform "Joget DX"]

Creates projects/<slug>/ with docs/, reviews/, spec/ and feedback/, and an empty register.json.
Refuses to overwrite an existing project.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("name")
    ap.add_argument("client")
    ap.add_argument("--platform", default="Joget DX")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.slug):  # also rules out names starting with "_"
        sys.exit("The slug must be lowercase words joined by hyphens, e.g. courier-booking")
    project = ROOT / "projects" / a.slug
    if project.exists():
        sys.exit(f"{project} already exists")
    for sub in ("docs", "reviews", "spec", "feedback"):
        (project / sub).mkdir(parents=True)
    (project / "register.json").write_text(json.dumps(
        {"project": a.name, "client": a.client, "platform": a.platform, "items": []}, indent=2), encoding="utf-8")
    print(f"Created {project}")
    print("  docs/      put the client's documents here (brief, SOW, notes, drafts)")
    print("  spec/      the mock-up and SRS spec (created by build-mockup)")
    print("  register.json  questions, gaps and decisions for this project")


if __name__ == "__main__":
    main()
