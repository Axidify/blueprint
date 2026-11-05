"""Where the workspace lives and what the company profile says.

The app (this repo) is separate from the workspace: the company profile and branding, the knowledge base,
the projects and the inbox. projects/, knowledge/ and inbox/ in the repo are links into the workspace,
created by setup. The workspace is ./workspace unless .blueprint-local.json sets "workspace_dir" (for
example a shared OneDrive or SharePoint folder, so a whole team shares projects and knowledge).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
DEFAULT_COMPANY = {"name": "Your Company", "short_name": "YourCo", "day_rate": None, "currency": "", "platforms": []}


def local_config():
    p = ROOT / ".blueprint-local.json"
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}


def workspace_dir():
    configured = local_config().get("workspace_dir")
    return Path(configured) if configured else ROOT / "workspace"


def company():
    import yaml

    p = workspace_dir() / "company.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {**DEFAULT_COMPANY, **(data or {})}


def asset(name):
    """A branding file from the workspace if present, otherwise the app's neutral template (or None)."""
    own = workspace_dir() / "branding" / name
    if own.exists():
        return own
    neutral = TEMPLATES / name
    return neutral if neutral.exists() else None
