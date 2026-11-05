# Troubleshooting

Start with the machine check. It lists what is missing and how to fix it:

```bash
python -I tools/doctor.py
```

| Problem | Fix |
|---|---|
| `python` is not recognised | Install Python 3.12 from python.org and tick "Add python.exe to PATH", then open a new terminal and run `setup.cmd` |
| A Python package is MISSING | Run `setup.cmd` again |
| Screenshots fail, or "playwright-core" is missing | Install Node.js LTS, then run `setup.cmd` again. Screenshots also need Microsoft Edge |
| `projects/`, `knowledge/` or `inbox/` is missing or not linked | Run `setup.cmd` again. This happens after moving or renaming the app folder, or changing `workspace_dir` |
| "projects is a real folder with files in it" | Move the files into the workspace's `projects/` folder, delete the empty folder, run `setup.cmd` |
| The requirements document shows a different font from the design | Run `setup.cmd` to install Geist and Geist Mono, restart Word, and generate again |
| The requirements document has an old table of contents | Word was not available. Open the document, right-click the table of contents and choose Update Field |
| The generator prints warnings | Fix them in the spec, not in the Word file (literal "section 3.2" references, requirements that mention the mock-up, missing images), then generate again |
| The generator says a version is issued and locked | That version went to the client. Bump `project.version` in the spec (and add a history entry), then generate again |
| I need to show the client an earlier mock-up | `present.cmd <project> --version 0.2` (every mock-up version is kept in `mockup/versions/`) |
| `present.cmd` says no mock-up spec found | The project has no `spec/app.yaml` yet. Ask Blueprint to "build a mock-up" first |
| Feedback comments are not saved | The mock-up was opened as a file instead of through `present.cmd`. Comments are kept in the browser: press **Export feedback** and drop the file in `inbox/` |
| Others in the room cannot open the mock-up | Start it with `present.cmd <project> --lan`, allow it through Windows Firewall, and share your machine's address |
| Claude Code keeps asking permission for Blueprint's scripts | Open Claude Code in the app folder itself, so `.claude/settings.json` applies |
| Two people's changes clash in a shared workspace | Agree who works on which project; synced folders cannot merge simultaneous edits to the same file |
