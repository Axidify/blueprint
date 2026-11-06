# Troubleshooting

Start with the machine check. It lists what is missing and how to fix it:

```bash
python -I tools/doctor.py
```

| Problem | Fix |
|---|---|
| `python` is not recognised | Install Python 3.12 from python.org and tick "Add python.exe to PATH", then open a new terminal and run `setup.cmd` |
| A Python package is MISSING | Run `setup.cmd` again (on a Mac: `./setup.sh`) |
| On a Mac: "permission denied" or "cannot be opened" when starting `setup.sh`, `setup.command` or the present scripts | In Terminal, in the Blueprint folder, run `chmod +x setup.sh setup.command present.sh present.command`. If macOS blocks a double-clicked `.command` file, right-click it and choose Open |
| On a Mac: `python` is not found | Blueprint uses its own Python in `.venv`. Run `./setup.sh` once; to run a tool by hand, write `.venv/bin/python` where the guides write `python` |
| On a Mac: no PDF, and the table of contents is empty | Word for Mac cannot be driven by Blueprint. Open the document in Word, click the table of contents, choose Update Table, then File > Save As and pick PDF |
| Blueprint's status does not appear when a session starts, or the check before a commit does not run | Both are started through Node.js. Install Node.js LTS and run setup again |
| Screenshots say neither Microsoft Edge nor Google Chrome could be started | Install one of them. Edge is used when both are there |
| Screenshots fail, or "playwright-core" is missing | Install Node.js LTS, then run `setup.cmd` again. Screenshots also need Microsoft Edge |
| `projects/`, `knowledge/` or `inbox/` is missing or not linked | Run `setup.cmd` again. This happens after moving or renaming the app folder, or changing `workspace_dir` |
| "projects is a real folder with files in it" | Move the files into the workspace's `projects/` folder, delete the empty folder, run `setup.cmd` |
| The requirements document shows a different font from the design | Run `setup.cmd` to install Geist and Geist Mono, restart Word, and generate again |
| The requirements document has an old table of contents | Word was not available. Open the document, right-click the table of contents and choose Update Field |
| An answer I typed into `register.xlsx` is gone | Fixed in this version: Blueprint now reads the Excel file before writing it again. For an answer lost earlier, type it in again and tell Blueprint the client answered |
| Blueprint says `register.xlsx` and `register.json` disagree | The same item was changed in Excel and by Blueprint. It shows both values: tell Blueprint which one is right |
| Blueprint says it cannot write `register.xlsx` | The file is open in Excel. Save and close it, then ask again |
| Extraction says the folder already holds files that are not an earlier extraction | It was pointed at a folder with other files in it, and touched nothing. Ask Blueprint to review the document again; it uses a folder of its own under `reviews/` |
| A line of an estimate is "not priced" and says the rate cannot be read | The rate cell in `knowledge/building-blocks.md` does not start with a number or a range. Write it as `3` or `2–4`, with a point for decimals; a note may follow the figure |
| The start-up summary shows "! register.json could not be read" under a project | That project's file is damaged, often a half-synced copy from OneDrive or SharePoint. The other projects are unaffected. Ask Blueprint to check the file, or restore the last good version from the shared folder's version history |
| The generator prints warnings | Fix them in the spec, not in the Word file (literal "section 3.2" references, requirements that mention the mock-up, missing images), then generate again |
| The generator warns that the screens changed after the screenshots were taken, or that a screen has no picture | Take the screenshots again (ask Blueprint to, or run the command in the warning), then generate again. Until then the pictures may not show what the tables describe |
| The text inside the document's screenshots is too small to read | The screenshots were taken with an older Blueprint, 1440 pixels wide. Take them again and regenerate: screens are now captured 1000 pixels wide, so their text prints about 40% larger |
| One screenshot's text is smaller than the others | That screen did not fit in 1000 pixels (the screenshot command names it), usually a list with many columns. Fewer or shorter columns bring it back to the normal size |
| The generator says the Word step FAILED | The reason is in the message. Most often the document or its PDF is open: close it and generate again. The Word file is complete either way; only the PDF and the table of contents are missing |
| The generator says Word did not finish within 4 minutes | Word is stuck and may still be running where you cannot see it. Open Task Manager, go to the Details tab, end the `WINWORD.EXE` you did not open yourself (save your own Word documents first), then generate again |
| The generator says the document format has mistakes | It lists them: a setting that does not exist, a colour that is not six hex digits, an unknown chapter. Fix them in `workspace/branding/document-format.yaml`, or ask Blueprint to. `python -I tools/document_format.py show` checks the file without generating anything |
| The generator says the spec has errors in the parts the document prints | It lists them, for example a requirement group with no items or two extra sections with the same title. Ask Blueprint to fix them in the spec, then generate again |
| The generator says it cannot replace the document | The document or its PDF is open in Word or a PDF viewer. Close it and generate again |
| The file name of the document is not exactly the system name | Windows cannot store `\ / : * ? " < > \|` in a file name, so each becomes a hyphen in the file name. The name inside the document is unchanged |
| The generator says a version is issued and locked | That version went to the client. Bump `project.version` in the spec (and add a history entry), then generate again |
| The build says a version was issued and its saved mock-up is kept | That version went to the client, so its saved copy is not replaced. What you built is the working mock-up. Bump `project.version` in the spec (ask Blueprint to) to keep it as a new version |
| The build lists spec errors such as "column 'x' is not a field of the data" | A name in the spec does not match the sample data, or a setting is misspelt. The message suggests the likely name; ask Blueprint to fix the spec |
| I need to show the client an earlier mock-up | `present.cmd <project> --version 0.2` (every mock-up version is kept in `mockup/versions/`) |
| `present.cmd` says no mock-up spec found | The project has no `spec/app.yaml` yet. Ask Blueprint to "build a mock-up" first |
| Feedback comments are not saved | The mock-up was opened as a file instead of through `present.cmd`. Comments are kept in the browser: press **Export feedback** and drop the file in `inbox/` |
| A red message says a comment was NOT saved, or the Feedback button says "1 not saved" | The window that started the mock-up was closed, or the network dropped. The comment is kept in that browser. Start `present.cmd` for the project again, then press **Feedback** → **Try again**. If that is not possible, press **Export unsaved** and drop the file in `inbox/` |
| `present.cmd` says the port is already in use | Another mock-up is still open. Close its window and start again, or run both at once with a different port for the second: `present.cmd <project> --port 8766` |
| A status has the wrong colour in the mock-up | Give that status a `color` (`green`, `amber`, `red` or `grey`) in the spec's `statuses`, or ask Blueprint to. Then rebuild |
| Others in the room cannot open the mock-up | Start it with `present.cmd <project> --lan` and share the address it prints. Allow Python through the firewall when your system asks, and make sure everyone is on the same network (a guest Wi-Fi often keeps laptops apart) |
| Claude Code keeps asking permission for Blueprint's scripts | Open Claude Code in the app folder itself, so `.claude/settings.json` applies |
| Two people's changes clash in a shared workspace | Agree who works on which project; synced folders cannot merge simultaneous edits to the same file |
