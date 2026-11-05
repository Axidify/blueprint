# Maintaining Blueprint

## The rule

**Every change to the app ships with its documentation and a changelog entry, in the same commit.**

"The app" is everything in the repository except the documentation itself: `tools/`, `.claude/`,
`templates/`, `examples/`, `setup.*`, `present.cmd`, `requirements.txt`, `package.json`, `CLAUDE.md`.
The workspace is never part of a change.

| If you change … | Also update |
|---|---|
| Anything people will notice | `CHANGELOG.md` → Unreleased |
| A skill (new, renamed, removed, or what it does) | `docs/skills.md`, the skills list in `CLAUDE.md` |
| A tool or its options | `docs/tools.md` |
| The spec format or mock-up engine | `docs/spec-format.md` |
| Register fields or the Excel layout | `docs/register.md` |
| Setup, workspace, company profile or branding | `docs/workspace.md`, `docs/getting-started.md`, `docs/troubleshooting.md` if relevant |
| The starter knowledge base | `docs/knowledge.md` if its structure changes |
| The overall process | `docs/workflow.md`, `README.md` |

## Writing changelog entries

Add entries under **Unreleased** in `CHANGELOG.md`, in one of: Added, Changed, Deprecated, Removed, Fixed,
Security. Write for the people using Blueprint, not for developers:

- Good: "Generated requirements documents now include the copyright and page-number footer."
- Not useful: "Fix footerReference in sectPr."

Mention anything people must do (run `setup.cmd` again, move a file in their workspace) at the start of
the entry.

## The documentation check

```bash
python -I tools/check_docs.py
```

It fails when:
- a skill in `.claude/skills/` has no `### <name>` section in `docs/skills.md`, or is missing from the
  skills list in `CLAUDE.md`;
- a script in `tools/` has no `### <script>` section in `docs/tools.md`;
- `CHANGELOG.md` has no Unreleased section, versions are out of order, or the newest version does not
  match `VERSION`;
- a relative link in `README.md`, `CHANGELOG.md` or `docs/` points to a file that does not exist;
- an app file contains a company or client name from the current workspace profile.

`--pre-commit` also fails when app files are staged without `CHANGELOG.md`.

### Where it runs

- **Before every commit made through Claude Code**: a hook in `.claude/settings.json` runs
  `check_docs.py --pre-commit` and blocks the commit if it fails, with the reason.
- **On GitHub**: `.github/workflows/docs.yml` runs the check on every push and pull request.

If you commit outside Claude Code, run the check yourself first.

## Releasing a version

Ask Blueprint to "release a new version" (the `release` skill), or by hand:

1. Pick the version: **patch** (0.1.1) for fixes only, **minor** (0.2.0) for new features, **major** (1.0.0)
   for changes that need people to change how they work or migrate their workspace.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [x.y.z] - YYYY-MM-DD`, add a new empty
   `## [Unreleased]` above it, and update the comparison links at the bottom.
3. Put the version in `VERSION`.
4. Run `python -I tools/check_docs.py`.
5. Commit ("Release x.y.z"), tag `vx.y.z`, push the commit and the tag.
6. Optionally publish a GitHub release with the changelog section as its notes.

People pick up a release with `git pull`, then run `setup.cmd` if the changelog says so.
