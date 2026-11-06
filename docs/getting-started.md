# Getting started

## What you need

| | Needed for | Get it |
|---|---|---|
| Claude Code (desktop app or command line) | Everything: you use Blueprint by talking to it | https://claude.com/claude-code |
| Python 3.10 or newer (3.12 recommended) | All tools | https://www.python.org/downloads/ (on Windows tick "Add python.exe to PATH") |
| Node.js LTS | Mock-up screenshots, and Blueprint's checks in Claude Code | https://nodejs.org/ |
| Microsoft Edge or Google Chrome | Mock-up screenshots | Edge is already on Windows machines; on a Mac either will do |
| Microsoft Word | Optional. On Windows it updates the requirements document's table of contents and makes the PDF | |

Blueprint is built on Windows and also runs on macOS and Linux (see [On a Mac](#on-a-mac)). It is tested
on all three.

## Set up

1. Clone the repository:
   ```bash
   git clone https://github.com/Axidify/blueprint.git
   ```
2. Double-click **`setup.cmd`** in the cloned folder. It installs the Python packages, the screenshot
   tool and the fonts the document uses (Geist and Geist Mono, for your Windows user only), creates your workspace, and finishes with a check of your machine. Anything missing is listed
   with the fix. Run it again whenever something seems wrong; it only installs what is missing.
3. If you are the first person in your company to use Blueprint, open `workspace/company.yaml` and put in
   your company name. If your team already has a shared workspace, see
   [Workspace and company profile](workspace.md#sharing-a-workspace-with-your-team) instead.

## On a Mac

Everything works as on Windows, with three differences.

- **Scripts.** Where these guides say `setup.cmd` and `present.cmd`, use `./setup.sh` and
  `./present.sh <project>` in Terminal, or double-click `setup.command` and `present.command` in Finder.
  The first time, macOS may ask you to confirm opening a file from the internet: right-click it and
  choose Open.
- **Python.** Setup puts Blueprint's Python packages in a folder of its own, `.venv`, and leaves the
  Python that came with your Mac alone. Blueprint runs its tools with it, so you never type it yourself;
  if you do run a tool by hand, write `.venv/bin/python` where the guides write `python`.
- **The table of contents and the PDF.** Word for Mac cannot be driven by Blueprint. After generating,
  open the document in Word, click the table of contents and choose **Update Table**, then
  **File > Save As** and pick PDF. The signing fields in the PDF are added on Windows only; on a Mac the
  sign-off pages are signed by hand, or the PDF is made on a Windows machine.

Linux works the same way as a Mac (without Word).

## First session

Open the folder in Claude Code. Blueprint greets you with the projects on your machine. Type:

```
/start
```

The start menu checks your setup, shows each project and what to do next, and asks what you want to do.
You never need to remember a command: say what you want in your own words, for example
"review this requirements document" or "build a mock-up from the brief".

## Your first project

1. Put the client's brief, SOW or draft requirements in the **`inbox/`** folder.
2. Say **"process my inbox"**. Blueprint works out what each file is, asks you which project it belongs to
   (or creates one), and runs the right next step.
3. Depending on what you gave it, you get a review with an Excel register of questions for the client, or
   a first clickable mock-up to take into a workshop.

See [Workflow](workflow.md) for the full journey from brief to sign-off.

## Presenting a mock-up

Double-click **`present.cmd`**, type the project name, and the mock-up opens in your browser. During the
session, press **Feedback** in the bottom-right corner (or F2), click anything on the screen and type the
client's comment. Comments are saved to the project automatically. Afterwards, say
**"apply the feedback"**.

Buttons such as Approve or Reject move the sample record to its next status when the mock-up was built
that way, so you can act the process out: approve as the manager, switch role, and see it approved. To
start the walk-through again, reload the page (F5): the sample data goes back to how it was.

Keep the window that `present.cmd` opened until the session is over: it is what saves the comments. If it
is closed, the mock-up says in red that a comment was not saved and keeps it in the browser; start
`present.cmd` again and press **Feedback** → **Try again**.

To let people in the room comment from their own laptops, start it with
`present.cmd <project> --lan` and share the address it prints. Everyone sees each other's comments appear
within a few seconds.
