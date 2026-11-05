---
name: release
description: For maintainers of the Blueprint app itself. Publish a new version - check the docs, turn the changelog's Unreleased section into a version, update VERSION, commit and tag, and (after asking) push and publish a GitHub release. Use when the user asks to release, cut, tag or publish a new version of Blueprint.
---

# Release a version of Blueprint

This releases the **app** (this repository), never anything in the workspace. Follow
`docs/maintaining.md`.

## 1. Check it is ready

1. `git status`: the working tree must be clean apart from release edits. If there are uncommitted app
   changes, stop and ask whether to commit them first (with their changelog entries) or leave them out.
2. `python -I tools/check_docs.py` must pass.
3. Read `## [Unreleased]` in `CHANGELOG.md`. If it is empty, there is nothing to release: say so and stop.

## 2. Choose the version

Read the current version from `VERSION` and propose the next one from the Unreleased entries:
- **major** if anything needs people to change how they work or migrate their workspace (look for
  Removed entries and "run setup again / move … " instructions);
- **minor** if there is anything under Added;
- **patch** if there are only fixes.

Before 1.0.0, a breaking change may be a minor bump; say which you chose and why. Confirm the version with
the user (AskUserQuestion, recommended first).

## 3. Update the files

- `CHANGELOG.md`: rename `## [Unreleased]` to `## [x.y.z] - <today, YYYY-MM-DD>`; add a new empty
  `## [Unreleased]` above it; at the bottom, point `[Unreleased]` at `compare/vx.y.z...HEAD` and add
  `[x.y.z]: https://github.com/<owner>/<repo>/compare/v<previous>...vx.y.z` (take owner/repo from
  `git remote get-url origin`).
- `VERSION`: `x.y.z`.
- `python -I tools/check_docs.py` must pass.

## 4. Commit and tag

Commit `CHANGELOG.md` and `VERSION` with the message `Release x.y.z`, and create an annotated tag:
`git tag -a vx.y.z -m "Blueprint x.y.z"`.

## 5. Publish (ask first)

Ask the user before each of these, as they are visible to everyone with access to the repository:
- push the commit and the tag: `git push origin main --follow-tags`;
- publish a GitHub release: `gh release create vx.y.z --title "Blueprint x.y.z" --notes "<the changelog
  section for x.y.z>"`.

Tell the user what was released and how people update: `git pull`, then run `setup.cmd` if the changelog
says so.
