# Getting started

## What you need

| | Needed for | Get it |
|---|---|---|
| Claude Code (desktop app or command line) | Everything: you use Blueprint by talking to it | https://claude.com/claude-code |
| Python 3.10 or newer (3.12 recommended) | All tools | https://www.python.org/downloads/ (tick "Add python.exe to PATH") |
| Node.js LTS | Mock-up screenshots | https://nodejs.org/ |
| Microsoft Edge | Mock-up screenshots | Already on most Windows machines |
| Microsoft Word | Optional: updates the requirements document table of contents and makes PDFs | |

Blueprint is built and tested on Windows.

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

To let people in the room comment from their own laptops, start it with
`present.cmd <project> --lan` and share the address it prints.
