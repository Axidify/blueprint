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

New to Blueprint? Say **"give me a tour"**: ten minutes on a made-up sample project, with nothing touching
your projects or client documents.

Each project folder has a **`Project overview.html`**: every document in the order of the process, who it
is for (the client, or internal) and the next step. Once a project has a mock-up, **Open the mock-up** sits
beside it. The documents themselves are in numbered folders beside the page (`1 Client documents`,
`2 Reviews` … `7 Change requests`, and the internal estimates); `_blueprint` holds Blueprint's working
files, which you can leave alone. Projects made with an older Blueprint can be tidied the same way: say
"migrate the folders". If you set up Blueprint before this page existed, run `setup.cmd` (`setup.sh` on a Mac) once more
so the shortcut can find Blueprint.

## Your first project

1. Put the client's brief, SOW or draft requirements in the **`inbox/`** folder.
2. Say **"process my inbox"**. Blueprint works out what each file is, asks you which project it belongs to
   (or creates one), and runs the right next step.
3. Depending on what you gave it, you get a review with an Excel register of questions for the client, or
   a first clickable mock-up to take into a workshop.

See [Workflow](workflow.md) for the full journey from brief to sign-off.

## Presenting a mock-up

Double-click **`present.cmd`** and your browser opens a page listing every mock-up: click the project (or
one of its earlier versions). In Claude, "open the mock-up for …" does the same. During the
session, use the dark bar in the bottom-right corner. It is yours, not part of the client's system, and it
never appears in the document's pictures: it shows which mock-up version is open, **View as** switches the
role you are signed in as, and **Feedback** (or F2) starts commenting. The arrows at its left fold it away
to one small button when it is in the way, and while the Feedback panel is open the screen makes room for
it. Click anything on the screen and type the
client's comment. Or drag a box: around several things for one comment about all of them ("make these one
date range"), or where there is nothing yet for something new ("an Export button here"); the box stays drawn
on the screen with its number. Comments are saved to the project automatically. Afterwards, say
**"apply the feedback"**.

Buttons such as Approve or Reject move the sample record to its next status when the mock-up was built
that way, so you can act the process out: approve as the manager, switch role, and see it approved.
**Submit** on a new form adds the request to the lists: fill in what you like (the rest is filled with
sample values), submit, switch to the manager and it is waiting there.

The walk-through is kept: reloading the page or pressing **Update ready** does not lose it, and when people
in the room have the mock-up open on their own laptops, what one of them submits or approves shows on every
screen within a few seconds (each keeps their own role). To start again, press **Reset sample data** on the
bar: it asks first, then puts the sample data back for everyone.

Parts of a screen that would be custom development on the project's platform carry a small grey tag
**Custom development** (hover it to see what it takes), so nobody takes them for standard. Switch
**Custom work** off on the bar to hide the tags; they never appear in the document's pictures.

A few things behave as the real system would, so they can be shown and not just described:

- **Required fields.** The main button of a form, or a dialog's confirm button, first marks the required
  fields left empty. You are not made to fill in a whole form: press the same button again and it goes on,
  with a note that only the mock-up allows it.
- **Files and signatures.** Clicking a file field attaches a sample file; clicking a signature field signs
  as the person you are signed in as.
- **Dialogs** close with Cancel, Esc or a click outside them, and the browser's Back button goes to the
  screen before.
- **Lists** keep their filters while you open a record and come back.

When the spec changes while a mock-up is open, the bar offers **Update ready**. Nothing reloads by itself:
press it when you are ready and you stay on the same screen. After the update a **What changed** panel lists what is new or different since the version on screen:
screens, fields, buttons, list columns, figures, dialogs, statuses, roles, sample data and the look, each
with the comments worked in for it, and the comments dealt with elsewhere. Click a change, or press **Start**
and **Next**, to open its screen (as a role that can see it) with the element outlined; **What changed** on
the bar opens the list again until the next update.

**A live session.** To have comments acted on while the client is still in the room, say "run a live
session for …" in Claude. Comments collect as they are typed and nothing interrupts you. When you are ready,
say "go": Claude shows you one list of proposed changes, with any that add behaviour or go beyond the scope
of work marked, and makes the ones you approve. Press **Update ready** to show them. The bar says **Live**
while the session is open, each comment shows what became of it, and "undo that" puts things back.

**Just you looking?** In the Claude app, say "open the mock-up" and it can open in the app's own browser
pane beside the chat; then simply say what should change.

Pins mark the comments on a screen. Click a pin to see its comment; Ctrl + Enter saves the comment you are
typing, and Esc backs out of it. A comment can be changed with **Edit** or taken back with **Delete** in the
Feedback panel, by whoever wrote it (on the same laptop) or by you on the laptop running the mock-up, until
Claude starts on it; after that, add a new comment instead.

Keep the window that `present.cmd` opened until the session is over: it is what saves the comments. If it
is closed, the mock-up says in red that a comment was not saved and keeps it in the browser; start
`present.cmd` again and press **Feedback** → **Try again**.

To let people in the room comment from their own laptops, start it with
`present.cmd <project> --lan` and share the address it prints. Everyone sees each other's comments appear
within a few seconds.
