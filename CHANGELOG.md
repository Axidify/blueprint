# Changelog

All notable changes to Blueprint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a major version for changes that need people to change how
they work or migrate their workspace, a minor version for new features, a patch for fixes.

Add every change to **Unreleased** as you make it, under Added, Changed, Deprecated, Removed, Fixed or
Security. Write for the people using Blueprint: say what they can now do, or what behaves differently.
See [docs/maintaining.md](docs/maintaining.md).

## [Unreleased]

## [1.4.0] - 2026-11-07

### Added
- **A register file made to send: `Questions for the client.xlsx`.** Each time the register is rendered, this
  file is written beside `Questions and fixes register.xlsx`. It holds the client's questions and nothing else,
  in no sheet, hidden or not. Send it instead of cutting the register by hand: the register's own file also
  holds the internal fixes and a hidden record of every item's answer, which deleting sheets did not remove.
  When the client sends it back filled in, take their answers in as before (`render --from`). The project
  overview now marks the register Internal and this file For the client.
- **Comments in layers.** Only open comments are marked on the screen: once applied or noted for follow-up a
  comment moves to **Done** at the bottom of the Feedback panel, and **Show on the screen** brings those marks
  back, faded. A box no longer blocks what is inside it: click the thing to comment on it, or the box's pin to
  open its comment. Commenting on something already commented on lists the earlier comments and what became of
  them, and the new comment is saved as following them (`follows`), so Claude reads "a bit smaller" or "put it
  back" against the change already made; the live session and `mockup.py feedback` show the link.
- **Minimise the Feedback and What changed panels.** **–** in a panel's corner puts its list away while
  Feedback stays on, so nothing covers the screen; **Comments** (or **What changed**) on the bar, or a click on
  a pin, brings it back. The Feedback panel remembers it.
- **References in the requirements document are links.** Click a screen number (5.13), a requirement group
  (FR-AUTH-001) or requirement (FR-DSP-001.1), a decision (R-019) or a section ("section 7", also in How to
  review it and on the sign-off page's "see section 7") and Word or the PDF goes to that place. Links work in both the Word file and the PDF; a reference to something the document
  leaves out stays plain text.

### Changed
- **Phone screens are readable and take half the pages.** The empty canvas around a phone screenshot is cut
  away, two phone screens of the same screen sit side by side, and every phone is drawn at the same scale.
  The sample field-service document went from 77 pages to 62.
- **A phone screen and its fields share a page.** A phone screen on its own has its field table (or its
  list's columns) beside it instead of under it; there a required field is marked with an asterisk, as on
  the screen. Most phone screens now take one page instead of two.
- **Portal screens print larger.** The screenshots for the document leave out the side menu and are taken
  800 pixels wide, so a desktop screen's text prints about a quarter larger (the access matrix still lists
  each role's menu). Take the screenshots again (`mockup.py screenshots`) to get them.
- **No more half-empty pages before tables.** Longer tables may run on to the next page (with their header
  repeated, and never leaving a single row behind) instead of jumping whole to a new page.
- **Click a comment in the Feedback panel to see what it is about.** Like a change in What changed, the card
  stays marked and the thing on the screen it names (its element, the box drawn for it, or its pin) is
  brought into view and outlined for a moment. Works with the keyboard too (Tab, then Enter).
- **The requirements document's timeline can show the scope of work's mandays.** Give each timeline activity
  the mandays the client agreed in the scope of work (`mandays`), and the timeline lists them per item with
  their total. Pricing stays strictly internal: the estimate's mandays, rates and cost never go into the
  document, and a `rate`, `cost` or `price` in the timeline stops the generator.
- **A shorter access matrix.** A screen's actions open to the same roles share one row ("Job Details:
  Navigate, Call Customer, Accept Job"), so the matrix fits on one or two pages instead of three. It is kept on
  one page when it fits on one.
- **Requirements by role list each role's open decisions as one line of numbers** pointing to the decisions
  chapter, instead of writing the same questions out under every role they mention.
- **The contents stay on one page.** When chapters and sections would not fit, the screens are left out of
  the contents (each still starts a page, with a heading that looks the same).
- **A priority only a few requirements have is shown after their text** instead of in a column that was
  otherwise blank.
- Glossary terms are set in the body font, like the first column of every other table.

### Fixed
- **Nothing of the Word template but its look reaches a generated document.** The requirements document, the
  UAT document, the client's change request note, the workshop agenda and the review kept the template's body
  text, comments and file properties (title, subject, last saved by). A template made from an earlier client's
  requirements document, as the document format tool suggested, put that document, with its mandays and
  rates, into every new one. Only the template's styles, page set-up, header and footer are used now.
- **The mock-up no longer carries the team's notes.** A requirement's internal `note`, any `_note` of your own
  and the timeline with its mandays were written into the built mock-up, where anyone in the room could read
  them in the page source. They stay in the spec (and the timeline in the requirements document).
- **Archiving or restoring a project with a file open no longer splits it in two.** When the register was open
  in Excel, a document in Word or OneDrive was syncing, the move copied the project and then deleted it part
  way, so client documents went missing from the active folder and both commands then refused. The project
  now moves in one step or not at all, and the message says to close its files.
- **Mock-up comments can no longer be lost to a half-written file.** The comments file is written in one step,
  so a mock-up asking for the comments never reads half of it, and a program stopped while saving leaves the
  file as it was instead of a broken one that stopped every later comment.
- **A mock-up whose comments failed to load once still saves comments to the project.** It used to switch to
  keeping comments in that browser for good, without a word, so Claude never saw them. Two comments saved
  while the server is slow are each saved once (the first was saved twice and the second could be dropped),
  and two tabs of the same mock-up no longer wipe each other's unsaved comments.
- **Writing the UAT scripts again never wipes the testers' results.** When the workbook already has results,
  an actual result, a tester, a date or a defect typed in, `uat.py render` stops and says so; with `--force`
  it keeps the filled-in workbook beside the new one ("… - results kept <date> <time>.xlsx").
- **Undo in a live session no longer deletes the spec** when the copy kept before the change is missing; it
  stops and changes nothing.
- **Issuing a version takes exactly that version, with its PDF.** Issuing v1 also locked v1.0 and v1.1, and
  Word's hidden `~$` file when the document was open. A version whose PDF was never made (the Word step did not
  finish) was locked for good: `issue` now stops and says to generate it again (`--without-pdf` issues the Word
  file alone). A version written without quotes in the spec (`version: 1.10`, which YAML reads as 1.1) is
  refused with how to write it, by `issue` and by the generator.
- **An issued version stays locked when two people issue at once.** The record of what was issued is written
  in one step, and a copy OneDrive or SharePoint keeps under another name (`issued-<computer>.json`) counts too.
- **Filing a document that is open no longer leaves it in two places.** It used to be copied into the project,
  then could not be removed from the inbox, with a raw error. Now nothing is filed and the message says to close
  it. A `--date` that is not a date is refused, and a colon in `--responds-to` no longer makes a hidden file.
- **No effort, rates or prices in the timeline's own words.** The summary figures, the intro, the activity and
  milestone names and the assumptions were printed in the requirements document as they were, so "45–60
  mandays" or a price could reach the client. The generator now refuses them; only the scope of work's
  `mandays` on each activity go in.
- **The workshop agenda and the client's register items are checked for the team's words.** The agenda check
  now reads everything the client's agenda prints (a question added without a register reference skipped it).
  Rendering the register warns about a client item that speaks of mandays, rates or building blocks. The
  client's request is checked in the change request note too.
- **Rendering an estimate again keeps the rates typed into its Rates needed sheet.** It stops and says to take
  them in first (`estimate.py rates-from`); `--force` keeps the filled-in file beside the new one.
- **One mock-up server per project.** Starting the mock-up of a project that is already open now opens the
  running one instead of a second server, which lost track of where comments go. A program saving comments
  never removes another program's lock on the comments file.
- **Smaller fixes.** Asking the client about an Ambiguous change request writes the register and the CR log
  together or not at all. UAT counts every register item that is not for the client as internal. `uat.py
  render` writes the workbook and the document both or neither (one open in Excel or Word stops it first).
  A folder move that could not be undone fully now says which parts are left half moved, instead of "put
  back". Writing a change request note that exists already says it replaced the earlier one.
- **Edit and Delete in the Feedback panel always act on the comment they sit on.** A card, its buttons and its
  pin now name their comment instead of counting its place in the list, so a comment saved or taken back in
  another browser at the same moment can never shift them onto a neighbour. (The mock-up's comment code was
  also tidied: the page-position logic has a part of its own, and the comment states are worded in one place.)
- **Saving an edit in the mock-up changes the record.** Save on a form opened on a record (Edit User, Edit
  Part …) used to show its message and leave the list as it was. It now keeps what was typed in that record,
  so the list and every screen that shows it follow, for the rest of the walk-through.
- **Opening the Feedback or What changed panel no longer moves the page.** The panel lies over the right of the
  screen instead of pushing the page aside, so boxes and pins drawn on the page stay where they were put; they
  used to land beside what they were about when a panel opened or closed.
- **No marks pointing at nothing.** A comment about something no longer on the screen (changed or removed
  since) or in a part folded away has no pin or box on the page; its card in the Feedback panel says why. A pin
  used to sit in the top-left corner, or at the comment's old place over something else. Unfold the part and
  the marks come back. A comment made as another role, about something only drawn for that role, says to
  View as that role.
- **A comment box no longer stretches across the screen when something it was drawn around is hidden.** A box
  drawn around several things (say a filter area) follows them; when one of them was hidden, for example in
  a section folded away, the box stretched from the top-left corner of the page. It now stays round the things
  on show, and where it was drawn when none are.
- **Screenshots always fit on their page in the requirements document.** A tall screenshot was placed at the
  full width of the page, so it ran over the footer, its caption was pushed to the next page and the page
  before it was often left blank. Every figure is now sized to fit on its page with its caption.
- **Requirement IDs stay on one line.** The ID column is as wide as the longest ID ("FR-AUTH-001.1" used to
  break after the dot), and a field's type ("Text (read-only)") no longer wraps.
## [1.3.3] - 2026-11-07

### Fixed
- **A box drawn for something new stays beside what it was drawn next to.** A box drawn just left of a
  button stays just left of that button when the Feedback or What changed panel opens or closes, or the
  window changes width, even where the toolbar moves from under the filters to beside them. Before, it could
  end up a row lower and further left. It keeps its distance from a thing in the same row, else from one in
  the same column (a box under the sign-in card stays under it).
- **Dragging a box never picks the page background.** While a box is drawn nothing on the screen is marked,
  and a box over an empty part of the page is "something new here" rather than a comment on the background.
  Clicking still comments on the page itself.

## [1.3.2] - 2026-11-07

### Fixed
- **Setup no longer changes `package-lock.json`.** It used to rewrite the file whenever the machine's npm
  was another version than the one that wrote it, so a fresh copy of Blueprint showed a changed file and the
  next `git pull` was refused. If `git pull` stops at that file, run `git checkout package-lock.json` once,
  then pull (see Troubleshooting).
- **Screenshots that fail keep the last ones that worked.** Taking screenshots without a browser, or a run
  that stopped at a screen, used to delete the pictures already in `4 Mock-up screenshots`, so the next
  requirements document had no figures. The new pictures now replace the old ones only once all are taken.
- **When no browser starts on a Mac or Linux,** the message quotes why Google Chrome did not start, not
  Microsoft Edge.
- **The check before a commit passes on a new workspace.** It took the placeholder company name that setup
  puts in `company.yaml` for a real one and blocked every commit until the name was changed. It now also
  checks the client names of projects in the new folder layout, which it missed.
- **Claude Code no longer asks before running seven of Blueprint's tools** (the tour, UAT scripts, change
  requests, platform fit, review documents, the project overview and the folder layout): they now have the
  same standing permission as the others, on Windows, macOS and Linux.

### Changed
- **Setup downloads about 460 MB less.** The font package Blueprint uses named a web framework (Next.js)
  that npm installed alongside it and Blueprint never runs; the Node packages are now 22 MB. Running setup
  again removes it from an existing installation.
- **The README and Getting started** name Git as something to install, show the clone command, point Mac
  and Linux users to their differences, and say how to update Blueprint. On Linux, Google Chrome is the
  browser for screenshots (Chromium is not used).
- **The tests on GitHub** install the Node packages, so the screenshot tests run there in Google Chrome on
  Linux, and fail if installing changed `package-lock.json`. A screenshot-size test allows for text that
  wraps a little differently in Chrome on Linux than in Edge on Windows.

## [1.3.1] - 2026-11-07

### Fixed
- **A box drawn for something new stays in its place** when the Feedback or What changed panel opens or
  closes, or the window changes size: it keeps its place across the area it was drawn in, and its distance
  from the nearest thing on the screen (a box drawn under a centred sign-in card stays under it).
- **The page makes room for the What changed panel** as it does for Feedback, so the panel no longer covers
  the right of the screen; visiting a comment drawn as a box outlines the box.

### Changed
- **The README** describes the mock-up design skill, comments drawn as a box, What changed and the comments
  workbook, and the release skill now brings the README up to date with every release.

## [1.3.0] - 2026-11-07

### Added
- **Comment with a box.** In feedback mode, drag a box instead of clicking: around several things, it is one
  comment about all of them ("make these one date range"); where there is nothing yet, it marks where
  something new should go ("an Export button here"). The box stays drawn on the screen with its number,
  follows the things it was drawn around when the window changes, and reads as "2 things: …" or "New, in …"
  in the Feedback panel, the comments list and the comments workbook.
- **Every mock-up comment in one workbook.** `Mock-up comments.xlsx` in `2 Reviews` lists every comment on
  a project's mock-up, one row each across all versions: where it was made, who wrote it, what became of it
  (applied, decision, question, possible change request), the note, the register item and the version it was
  worked into, with filters and a summary. It is written as each comment is marked, so what is still open is
  one filter away, and the project overview lists it with the number not worked in yet.
- **What changed, after Update ready.** Pressing **Update ready** in an open mock-up now shows a list of what
  the update changed since the version on screen: new or changed screens, fields, buttons, columns, figures,
  dialogs, statuses, roles, sample data and the look, each with the comments worked in for it. Click a change,
  or press Start and Next, to open its screen with the element outlined, so the room can go through the
  changes one by one. Nothing has to be written for it: the mock-up compares the two versions itself.

## [1.2.1] - 2026-11-07

### Fixed
- **Search boxes in the `desk` mock-up no longer look disabled.** They were filled grey; they are now white with
  an outline like every other field, with a small search icon at the left.

## [1.2.0] - 2026-11-07

### Changed
- **The workbooks follow the design language:** the questions and fixes register, the UAT workbook and the CR
  log now look like the estimate workbook. A quiet grey header row in place of white on navy, hairlines
  instead of gridlines, cells middle-aligned (in the estimate workbook too), severity, status and test results as a dot and a coloured word that follows the word
  when it is changed in Excel, and the cells to fill in (the client's response, the testers' results, the
  rates the lead developer gives) as pale Cobalt fields. They print landscape, one page wide, with page
  numbers. Only the look changed: the client's answers and the testers' results are read back as before.

## [1.1.0] - 2026-11-07

### Added
- **Make the mock-up look like the client's own systems.** Say "use their logo", "dark menu", "squarer
  corners" or "make it look like their intranet": the new `mockup-design` skill sets the look, or learns it
  from screenshots of the client's systems, their brand guidelines or their website. It shows the main screens
  before and after (`python -I tools/mockup.py look <project> --try ...`) and changes the project only once
  you are happy. It warns when white words are hard to read on the brand colour, and when the look is custom
  work on a Joget platform.
- **Guidelines for phones and tablets** in the design language and the design skill: which device each role
  uses (asked, never guessed), how a web system changes on a phone (one column, lists as rows, filters and
  dialogs as sheets from the bottom), how a mobile app's screens are drawn (Apple's own apps as the
  reference: tab bar, large titles, the main action within thumb reach, 44px targets, the sync state), and
  the questions a phone raises for the register.
- **Blueprint's design language is written down** in `docs/design-language.md`: Apple as the reference,
  the colours, type sizes, spacing, corners, buttons, tables and words that mock-ups and Blueprint's own pages
  follow. The design skill reads it before every change of look.
- **The `desk` mock-up follows Apple's sizes more closely:** the row of buttons a screen ends with is 44px
  and level (Back, Reject and Approve together), dashboard figures sit 24px apart like every other card, and
  lists use the same 15px text as the rest of the screen, with short values kept on one line while the list
  fits, so every list still fits the 1000px screenshots.
- **A colour system for mock-ups:** one loud accent for what to press, a complementary pair for data, and
  greys for everything else. In `desk` the pair (teal and pink unless the spec sets `data_colors`) draws
  people's initials beside their names, the same colour for the same person everywhere. The design skill
  picks a client's colours by the same rules, and `look` warns when an accent or data colour could be read
  as a status, or is violet or indigo.
- **The client's logo, font, corners, side menu and top bar** can be set in the spec (`logo`, `font`,
  `font_file`, `corners`, `menu`, `header`) and work with every theme. A project that sets none of them
  looks exactly as before, and a logo kept only for the document's cover stays off the mock-up until the
  spec names it.

### Fixed
- **The overview tests pass on a fresh checkout.** They expected the sample's estimate Excel file, which is
  not kept in git, so they failed wherever the sample's estimate had not been rendered (as on GitHub). The tests
  now render it themselves. The overview page itself was right all along.
- **The `desk` mock-up now looks the same on every laptop.** It carries its font (Geist) with it, so a client
  opening the mock-up on their own laptop, or over the network, no longer sees it in a fallback font.

## [1.0.0] - 2026-11-07

### Added
- **`project.py migrate <project>`** moves a project to the new folder layout (`--dry-run` lists every
  move, `--all` does every project, `--undo` moves it back exactly). It refuses, saying why, while the
  mock-up is open, a live session runs, or one of its Word, Excel or PDF files is open on anyone's computer.
  Issued files stay locked and comments keep their ids. The start menu offers it once for an older project,
  and `project.py check` and the start-up summary name the projects still in the old layout.
- **A guided tour for newcomers.** Say "give me a tour" for a ten-minute first run on a copy of the made-up
  sample: a quick review into the Excel register, the clickable mock-up, a comment turned into a live
  change, and the generated requirements document. It never touches your projects or client documents,
  and the copy is removed at the end.
- **"The client answered."** Drop the returned register or an answers e-mail into the inbox, or paste the
  answers. The new `client-answers` skill matches each answer to its question, records it, updates the spec
  where it changes behaviour, flags possible change requests, and says whether the requirements document or
  the estimate needs doing again. `register.py render --from <file>` reads the answers from the register
  Excel file the client sent back, without changing that file.
- **New mock-ups get the `desk` look:** calm greys and white cards in the client's colour, one main button
  per screen, statuses as a dot and a word. Joget projects still get `joget`, and projects that already have
  a mock-up keep their look.
- **A drop-down can offer only some records** (`options_from: {list, field, where}`), following the
  walk-through, and UAT scripts test it with only the records it offers.
- **A detail screen can show the records that belong to it**, such as a car's loan history (`list` with
  `where_record`), in the mock-up, its screenshot and the requirements document.
- **Status moves the system makes on its own** (`auto` on a status) are no longer listed as moves no button
  makes; the requirements document marks them "(automatic)" and UAT scripts give them a case of their own.
- **Change requests, checked against what the client signed.** Tell Blueprint "the client asked for…"
  during development or UAT and the new `change-request` skill checks the request against the version the
  client signed, quoting it: In scope, Ambiguous (a question for the client in the register) or New. A new
  change request is sized in building blocks for the team, kept in the project's CR log
  (`changes/CR log (internal).xlsx`), and written up as a Word note for the client that shows a price only
  once the project lead has set it.
- **UAT scripts from what the client signed.** The new `uat-scripts` skill writes test scenarios from the
  signed requirements: the main process acted as each role, rejections and cancellations, what each role may
  not do, field checks, access, notifications and integrations, with every requirement covered. They come as
  a workbook for the client's testers (Pass/Fail, actual result, defect reference) and a Word document in
  your company's format. After UAT, Blueprint lists the failed and blocked steps of the filled-in workbook.
- **A project overview page in every project folder.** Run `setup.cmd` (`setup.sh` on a Mac) once more.
  `Project overview.html` shows the next step in the words to say, the open client questions and internal
  fixes, and every document in process order with who it is for (From the client, For the client, Client
  sheet only, Show the client, Can be shared, Internal). It never shows mandays, rates or cost, and
  Blueprint keeps it up to date (`python -I tools/overview.py build`).
- **An "Open the mock-up" shortcut** in each project folder that has a mock-up, on Windows and on a Mac.
  It starts the mock-up so comments are saved, even from the shared folder; when Blueprint is not set up
  on that computer, it says what to do.
- **Reviews also come as a Word file** (`<document> review.docx`), in your template and marked internal on
  every page (`python -I tools/review_doc.py`).
- **What the platform can actually do, checked against its own documentation.** Give a project its tech
  stack (`project.platform`, and `project.stack` for the other products) and the new `platform-fit` skill
  checks the spec against it: every screen, field, list, figure, workflow step, notification, integration
  and piece of the project's own mock-up code is matched to what the product gives as standard, by
  configuration, by custom work or not at all. Anything not yet known is looked up in the product's own
  documentation online, using product and feature words only, never client details; what is found is kept
  in the knowledge base (`knowledge/platforms/`) with the page that says so, once you agree. The project's
  spec records what is custom work (internal: never in the document or the mock-up), custom work becomes
  internal register items, and the estimate carries it as its own lines. It runs when a project's tech
  stack is given, after a mock-up is built, in a review and before an estimate. A starter Joget DX sheet is
  included; none of it is checked yet, so the first project to use each row looks it up. Run `setup.cmd`
  (`./setup.sh` on a Mac) to add it to your workspace's knowledge base.
- **All your mock-ups on one page.** Double-click `present.cmd` (on a Mac `present.command`) and the browser
  opens a page that lists every project with a mock-up: its version, when it was built, how many comments
  are waiting, and its earlier versions. Click one to open it. You no longer type a folder name into a
  console window, and a mock-up is built for you when you open it if its spec changed. This page is only
  ever shown on your own computer; to share with the room you still present one project with `--lan`.
- **Ask Claude to present.** "Open the mock-up for …", "show me my mock-ups" or "present the mock-up" now
  starts it and gives you the address (the new `present` skill).
- **A mock-up follows its spec.** When the spec changes, every open mock-up offers **Update ready** on the
  presenter's bar within a few seconds. Nothing reloads by itself, so a walk-through is never interrupted:
  press it when you are ready and you stay on the same screen. A change with a mistake in it never shows
  in the room; the last good mock-up stays up.
- **A live session: comments acted on while the client is in the room.** Say "run a live session for …".
  Comments typed in the mock-up collect while you present, and nothing interrupts you. When you say "go",
  Claude works through them all, groups the ones asking for the same thing, and shows you one list of
  proposed changes; it makes the ones you approve and every open mock-up offers **Update ready**. Nothing
  is out of reach: what the spec cannot describe, Claude writes as the project's own mock-up code. A
  proposal that adds behaviour or goes beyond the scope of work is marked as such, and you decide. A change
  that adds behaviour also updates the requirements, so the document says what the client saw. The bar
  says **Live** while the session is open, each comment shows what became of it (Received, Working on it,
  Applied, Noted for follow-up), "undo that" puts things back exactly, and the mock-up as first presented
  is kept so it can be shown again. When the session ends, Claude releases the changes as a new version.
- **A project's own mock-up code.** `spec/mockup.js` and `spec/mockup.css` in a project are loaded after
  the mock-up engine, for anything the spec cannot describe. They belong to that project alone and count
  as part of what its screenshots show. See [Spec format](docs/spec-format.md#the-projects-own-mock-up-code).
- **Larger text.** `text_size: large` (or `larger`) under `project` in the spec makes the text of the
  client's screens bigger, in the mock-up and in the document's pictures. The presenter's bar keeps its
  size. Say "make the text larger" to have it set.
- **The mock-up shows required fields, files and signatures working.** The main button of a form, and a
  dialog's confirm button, now mark the required fields left empty before going on, on whichever step of
  the form they are. A presenter is not made to fill in a whole form: pressing the button again goes on
  without them. Clicking a file field attaches a sample file, and clicking a signature field signs as the
  person signed in. Until now an empty form was "submitted" and those two fields did nothing.
- **A presenter's bar.** The mock-up's version, **View as** (the role switch, which used to sit in the
  system's own top bar and looked like a feature of it) and **Feedback** now sit together in one dark bar
  at the bottom right. It is clearly not part of the client's system and never appears in screenshots.
- **One button can move a record through a chain of approvals.** Where a single Approve button serves
  several approvers, `set_status` now takes where each status moves to, for example
  `{Submitted: verified, Verified: approved, Approved: deployed}`, so the mock-up can act out every step
  of a multi-step approval with the one dialog the real system has.

- **A task list can show each role its own work.** `waiting_for_me: true` in a list's filter keeps the
  records whose approval progress is waiting at the signed-in person's step, and follows as a record moves
  on, also where a chain skips steps. A button can go by that step too:
  `set_status: {Verification: verified, Approval: approved}`. For records without a progress table,
  `where_by_role` gives a role a filter of its own. Until now a list had one filter for everyone, so every
  role saw the first approver's tasks and the later roles could not open theirs by clicking.
- **Blueprint spots earlier work on the same system.** Starting a project or processing the inbox lists
  active and archived projects and systems delivered before with a similar name
  (`python -I tools/project.py find "<name>"`), and offers to carry on, start a new phase or start fresh.
  For a system delivered before, its change requests and actual effort come along as context. A new
  project can no longer take the name of an archived one.
- **Processing the inbox never files a document on a guess.** Each file is checked against every project:
  a comments export made on its mock-up, register, UAT and change request numbers with their topic, its
  roles and screens (`python -I tools/project.py match "<file>"`). Only a clear match goes straight into
  the plan; for any other file you are asked which project it is for, with the best guesses and why. The
  client's name alone is never enough. A file you leave in the inbox keeps a note of why
  (`project.py hold`), and the start-up summary says "1 file waiting: not sure which project". The inbox
  also recognises change request and UAT defect lists, and filled-in UAT workbooks.
- **Submit on a new form adds the request to the mock-up.** It shows in every list, count and task list it
  matches, with a new reference number, sample values for anything left empty, and its first approval step
  done by whoever submitted it. The build says which forms do this; `creates` in the spec turns it on or
  off for a button.
- **The walk-through is kept.** Records submitted or moved stay through a reload and **Update ready**.
  Presented with `present` (also `--lan`), every laptop in the room sees them within a few seconds, each in
  its own role. **Reset sample data** on the presenter's bar starts again for everyone.
- **Comments can be edited or deleted** from the Feedback panel while they wait, by whoever wrote them or by
  the presenter. Once Claude is working on one it is locked and says why. Nothing is erased: a deleted
  comment is kept, marked as taken back, and an edit keeps the earlier wording.
- **Custom work is labelled in the mock-up.** Parts that are custom development on the project's platform
  carry a small "Custom development" tag while presenting, showing on hover what they take. **Custom work**
  on the bar hides them; they never appear in screenshots or the document. Building a mock-up and live
  sessions now follow "build everything, label custom work": what the spec cannot describe is built in the
  project's own mock-up code rather than left out, and the platform check records which parts of the
  mock-up each custom feature appears in.
- **A button can move a linked record too**, such as the courtesy car of a loan when the loan is approved,
  with `also_move` in the spec. The build checks the move against the linked record's status rules.
- **A form can open on a record of its own** (`record`), as a detail screen does.
- **The page that lists every mock-up names the projects without one** and says what to tell Claude to
  make it.
- **The platform check recognises screens for managing users, roles and permissions**, and the starter
  Joget DX sheet has a row for them.
- **The requirements document is checked for text meant for your team.** The generator warns about the
  mock-up, "proposed", mock-up comment numbers (FB-…), register numbers not listed under Decisions needed
  and requirement numbers that are not in this spec, anywhere the client reads them, and says where to
  fix each in the spec or register. It also warns when two figures have the same caption.
- **The generator lists the parts still missing before issuing:** non-functional requirements, the
  timeline, scope items and the names of the signatories.
- **Register items are added and closed with commands, not by editing the file.**
  `python -I tools/register.py add` takes new items from a file or standard input, gives them the next
  numbers, fills the date raised and the status, checks every item and refuses the whole batch if one is
  wrong; it names likely duplicates of items already in the register, and `--check` reports without
  writing. `register.py similar` lists the items that read most like a question or finding, and
  `register.py update` answers, resolves or changes items (`--set status=resolved --set answer="..."`).
  Reviews, workshop preparation and estimates use them, and `register.json` is now written whole or not
  at all.

### Changed
- **Project folders are laid out for the people who browse them.** Nothing to do for new projects. For an
  existing project, say "migrate the folders" (or leave it: both layouts work, also for teammates on this
  version). What people open is now at the top, numbered in the order of the process: `Project
  overview.html`, `Questions and fixes register.xlsx`, `1 Client documents`, `2 Reviews` (each review and the
  mock-up's change notes as Word files), `3 Workshops`, `4 Mock-up screenshots`, `5 Requirements document`,
  `6 UAT`, `7 Change requests`, and `Internal – estimates and change requests` (estimates and the CR log,
  never sent). Blueprint's working files (spec, register.json, comments, the mock-up and its versions,
  review extracts, .json sources, issued versions) are in `_blueprint`, with a README saying to leave them
  alone. Folders appear only when a project has something for them. New projects start this way.
- **The presenter's bar, the pins and the feedback buttons are a burnt orange** on a dark bar, deep enough
  for white text to be read on it.
- **Feedback mode is calmer and clearer, and any part of a screen can be commented on:** the header, the
  side menu, the page background, a row or a single cell, not only named fields, columns and buttons. A
  comment says what it is about in plain words ("Comment on the Status cell of LV-2026-011", not
  "column:Status"), the thing commented on stays marked while you type, Ctrl + Enter
  saves and Esc backs out. Pins on the same thing sit side by side, and clicking a pin shows its comment.
  The panel opens above the bar, so the bar no longer jumps.
- **Messages are quieter and never cover each other.** They are stacked, a longer one stays longer, and
  only a small dot carries the colour: green for done, orange for something to look at, red for a failure.
- **Dialogs behave as dialogs do.** Esc and a click outside close them, the cursor starts in the first
  field, and the browser's Back button no longer reopens a dialog you closed.
- **Reject no longer looks like Approve.** With a red brand colour the danger button and the main button
  were two near-identical reds side by side. The danger button is then drawn as an outline. Screenshots of
  such a project look slightly different the next time they are taken.
- **Small touches:** rows highlight under the pointer, buttons and dialogs move gently (not at all for
  people who ask their system for less motion, and never in a screenshot), keyboard focus shows as a soft
  ring in the project's colour, and a new screen starts at its top.
- **The start-up summary gives each project's next step by stage, in the words to say:** review or build a
  mock-up, prepare the workshop, apply the feedback, generate the requirements document, review it, issue
  it, close the project. It also tells the lead developer when the spec has changed since the last
  estimate.
- **An estimate whose building blocks are not all priced no longer shows a total.** It says the build is
  not priced, shows what is priced so far (not a project figure), and lists the scope-of-work lines that
  cannot be compared yet.
- **A review always ends with the next step,** and covers documents the client has already signed
  (findings become possible change requests) and manday tables inside the document.
- **Closing a project shows the proposed knowledge-base changes first** and writes only what you agree to.
- **Extracting a document catches "pending", "subject to confirmation" and "subject to change"**, renders
  PDF pages that are mostly figures and tables, and prints a plain summary.
- **The sign-off page says plainly what is signed:** the version and date, how many decisions are still
  open and that they are not part of the sign-off, and how to sign. The wording can be changed in the
  document format (`labels`).
- **Dates print as "6 November 2026"** on the cover, in the version history and at sign-off.
- **Extra screenshots of a screen get captions that say what they show** (the role or the record).
- **After Update ready the mock-up comes back with feedback mode off**, so the presenter's next click does
  what it says.
- **Settings the mock-up ignores are listed when it is built**, such as a misspelling or a stray key from a
  comma in unquoted text. Start a note of your own with `_` to keep it quiet.
- **Versions kept at a live session read "v1.4 as presented 6 Nov 19:00"** on the page that lists every
  mock-up, which also explains in plain words how to let the room comment.
- **In a live session each comment is finished with its own note.**
- **Where a register item was found is easy to read.** The register's Excel file replaces the Reference
  column with **Document** ("SRS v1.0", said once) and **Where**: each place on a line of its own, in plain
  words ("Section 2.1", "Figure 5 · page 30", "comment FB-001") instead of the reviewer's shorthand
  ("§2.1/§2.2", "(p30)"). `register.json` keeps the note as written.
- **The estimate's Excel file is easier to read and prints properly.** It opens on a one-page **Overview**
  that says the answer in one sentence (the likely effort, or that the build is not priced yet), with each
  figure explained on its own row, the confidence, and what to do next. The **Lines** sheet groups the
  lines and shows what was counted and each line's status in plain words. A new **Rates needed** sheet is a
  form the lead developer fills in; say "save these rates" and Blueprint reads it
  (`estimate.py rates-from`) and saves the rates to the knowledge base once you agree. **Risks and
  questions** replaces the Uncertainty and Questions sheets. Every sheet prints landscape, one page wide,
  with its headings repeated and marked internal: 10 pages for a typical estimate instead of 28.
- **Every skill ends the same way:** what was made, where it is, who it is for (the client or internal), and
  the next step in the words to say. The documentation check requires it.
- **The estimate, review and requirements-document skills are shorter.** Exact options come from each
  tool's `--help`, so they cannot drift; `estimate.py --help` and `generate_requirements.py --help` now
  print their usage.
- **Starting a project asks less.** The system, client, short name and platform are worked out from the
  brief or document and confirmed in one question; only what cannot be found is asked.
- **The presenter's bar, Feedback panel and comment box are dark with a blue accent** instead of orange.
  The bar folds away to one button, and the open Feedback panel no longer covers the last columns.
- **The page listing every mock-up shows one card per project**, plus the projects still without one and
  what to say to Claude.
- **A form in steps shows Submit on the last step only**, with Next and Previous on the others.

### Security
- **Internal notes on a comment are no longer sent to the room.** A mock-up was sent each comment's note,
  its register item and whether it was called a possible change request, where anyone with the room's
  link could read them. It is now sent only the comment itself and one of four plain words for what became
  of it.

### Fixed
- **A user field in the mock-up offers people.** The approval steps of a form showed empty drop-downs; a
  `user` field now offers the people of its `roles` (or everyone the spec names).
- **Submit on a new form starts the request after its draft status** even when the draft lists no `next`; it
  used to add the request as a draft.
- **Going on with required fields empty says so.** The second press of a form's main button still goes on, so
  a session is never stuck, but the mock-up now says that the real system would not send the form.
- **Filters are kept when you open a record and come back.** The list used to show every row again.
- **The Feedback button no longer covers the last buttons of a page**, such as Export or Approve.
- **The outline in feedback mode is no longer cut off** on a column heading or anything else inside a table.
- **Switching role from a page opened by a link that names a role** was undone straight away. It now holds.
- **A dialog opened on a later step of a form** no longer sends the form back to its first step.
- **A row action limited to some roles is now hidden from the others in the mock-up.** `roles` on a row
  action already decided who had it in the document's access matrix, but the mock-up showed it to
  everyone who could open the list.
- **A step marked Skipped is no longer taken for the one that is waiting.** When a button moved a record,
  the approval progress filled in the first step without a date, even one marked Skipped or Not required.
  It now fills in the first step that is really waiting.
- **View as switches role even when both roles start on the same screen.** The page used to stay as the
  previous role.
- **Buttons with a `when` now show on a form opened on a record.**
- **A text where the spec needs a list** (such as `process_flow` notes) is caught by the build, instead of
  leaving an empty page and failing the screenshots. When screenshots stop, they name the screen and the
  error the browser reported.
- **A tick box with no options shows its box.**
- **Undoing a change in a live session puts its comments back to Received** instead of leaving them
  Applied, and says which register changes must be put back by hand.
- **The "(n high)" next to client questions counted internal items too.**
- **Archiving a project whose name an archived project already had** moved it inside that folder. It is
  now refused.
- **The platform check no longer suggests a knowledge-base sheet for the client's own systems**, which
  would have put a client's name into the shared knowledge base.
- **Pictures in the PDF are full size when two screenshots are identical.** None were sharpened before,
  and the run said "0 of 34" with no reason; when pictures stay as Word made them, it now says why.
- **Decisions needed no longer shows requirement numbers from the document a question was found in.** It
  points at the requirement the question is linked to (`tbc`), and a note lists the questions with no
  place in this document.
- **Plain messages instead of error traces** when building, screenshotting or serving the mock-up of a
  project with no spec (or a folder that does not exist), when generating for a project with no spec, and when learning
  the format from a PDF, an old `.doc` or a damaged file. Chapter names show "&", not "&amp;".
- **The generator and the format tool no longer stop or show "?"** for characters like "●" or "–" in a
  Windows console.
- **PDF document properties no longer show garbled characters** ("MicrosoftÂ®") when extracted.
- **Creating a project prints its folder and the next step**, not a full Windows path.
- **The starter Joget DX sheet named an old tool.**
- **Comments deleted in the mock-up no longer count as waiting** at start-up, in `live list` or on the page
  that lists every mock-up.
- **Approval steps still to come read "Waiting"** instead of a blank.
- **A new request in the mock-up is no longer the twin of one already waiting.** Fields left empty used to be
  copied from the first open record at the same stage, so a new loan had the same customer and the same car.
  They now come from a finished record, or one at another stage; a car or other asset is one no open record
  holds, with its own details (such as its model).
- **The page listing every mock-up names projects without one by their name and client**, not their folder
  name.
- **The start-up summary writes workshop dates for people** ("13 Nov 2026").
- **A read-only field no longer shows the required star.**
- **The empty corner beside the open Feedback panel no longer blocks clicks** on the page underneath.

## [0.10.0] - 2026-11-06

### Added
- **The mock-up can act the process out.** Give a button `set_status` in the spec and clicking it moves the
  record to that status: approve an application as the manager and it shows as Approved on every screen,
  leaves the list of pending approvals, changes the counts on the dashboards, loses its Approve and Reject
  buttons, and its approval progress records who handled it, when, and the comment typed into the dialog.
  Until now the button showed a message and the record stayed as it was. Nothing is saved: reload the page
  (F5) to put the sample data back and run the walk-through again. Screenshots are not affected. The
  made-up sample project does it for Approve, Reject and Cancel; say "make the buttons move the record"
  to have it added to a project of your own. See [Spec format](docs/spec-format.md#status-moves).
- **The mock-up and the status rules can no longer disagree.** The build stops when a button moves a
  record somewhere the status rules do not allow (for example out of a final status), and it lists the
  moves the rules allow that no button makes, so you know what the walk-through cannot show.

### Fixed
- **A button label starting with Yes, No, On or Off is no longer shown as "true" or "false".** Written
  without quotes, YAML reads such a label as true or false, and the mock-up showed that word on the
  button; the sample project's "Yes, cancel it" button did. The build now stops and says to put the label
  in quotes.

## [0.9.0] - 2026-11-06

### Added
- **Prepare a workshop.** Say "prepare the workshop" or "what should we ask the client next?" and Blueprint
  builds the agenda for a requirement workshop, mock-up review or sign-off meeting: the open questions from
  the register, what the spec does not say yet (status rules, integration details, formulas, scope) and the
  questions of the gap patterns that apply, ordered so the most costly come first and sized to fit the
  time. You get two Word documents in the project's new `workshops/` folder. The **agenda** is for the
  client: the questions, with room to write each decision. The **facilitator notes** are for the BA: the
  same questions with why each one matters, your recommendation, and what was left for later. An agenda
  that leaves out an open high-severity question, or does not fit the time, is refused with the reason.

## [0.8.1] - 2026-11-06

### Fixed
- **The PDF is no longer twice the size it needs to be.** In 0.8.0, putting the screenshots back into the
  PDF at full size stored each of them twice. Each is now stored once, which roughly halves the PDF of a
  document with many screens. Generate the document again to get the smaller file.

## [0.8.0] - 2026-11-06

### Added
- **Blueprint runs on a Mac.** Run `./setup.sh` (or double-click `setup.command`) to set up, and
  `./present.sh <project>` (or `present.command`) to present a mock-up. Setup keeps Blueprint's Python
  packages in a folder of its own (`.venv`), installs the fonts for your user and links the workspace, as
  on Windows. Screenshots use Microsoft Edge, or Google Chrome when Edge is not installed (on Windows
  too). The machine check knows where things are on a Mac. One step stays manual there: Word for Mac
  cannot be driven by Blueprint, so you update the table of contents and save the PDF yourself, and the
  PDF's signing fields are added on Windows only. Linux works the same way as a Mac.
- **What each dashboard figure counts.** Every screen with figures now has a "Figures" table in the
  document. A figure the mock-up counts from its list is described automatically ("the number of records
  where Status is Pending Approval"); a figure typed in as a value takes a new `formula` in the spec, in
  words. A figure with neither shows "To be confirmed".
- **How each integration works.** An integration in the spec can now say what starts it (`trigger`), what
  goes across (`data`) and what happens when it fails (`on_failure`); the document prints them in a second
  table under the external systems. Something left out shows "To be confirmed" and is warned about.
- **A note of screens no requirement refers to.** Where the spec links requirements to screens, generating
  lists the screens nothing points at, which often means a requirement is missing. Notes do not hold a
  version back; warnings do.
- **Status rules in the document.** Each status in the spec can now say who may edit, cancel or delete a
  record while it is in that status, and which statuses it can move to (`edit`, `cancel`, `delete`,
  `next`). The document prints them as a "Status rules" table under the statuses. A rule you have not
  given yet is shown as "To be confirmed" and warned about; a spec with no rules at all still generates,
  with a note. These are the rules most often argued about after go-live when nobody wrote them down.
- **A scope chapter.** A new `scope` part of the spec (`in_scope`, `out_of_scope`, `assumptions`) becomes
  the chapter "Scope and assumptions", after "Users and access". It appears only when the spec has a
  scope. If your company file lists its own `chapters`, add `scope` to it to get the chapter.
- **Decisions made.** Client questions that are resolved and have an answer in the register are now listed
  in the document under "Decisions made", with the answer and where it was agreed. Until now a question
  vanished from the document once it was answered, so the client's answers were on record only in the
  register. Internal items and unanswered ones still never reach the document.

### Changed
- **Screenshots stay sharp in the PDF.** Word's PDF export reduces every picture, so the small text of a
  screenshot went soft when zoomed. After Word has made the PDF, Blueprint now puts each screenshot back
  at its full size. The PDF is larger for it: about as large as its screenshots together.
- **The default standard wording is shorter and says each thing once.** "About this document" and the
  sign-off text went from twelve paragraphs to seven. They no longer say twice that screens may be
  refined, and the sign-off now states that the signed document is the basis for development and for
  acceptance testing, that open decisions are not covered until resolved, and that a change after
  sign-off is a change request. **A company with its own `branding/document-boilerplate.yaml` keeps its
  wording**; copy what you want from `templates/document-boilerplate.yaml`.
- **An estimate with many lines says how to read its total.** The total adds every low end and every
  high end; from five lines with a range, the estimate now says that all of them landing low or all high
  is unlikely, so the outcome is to be expected inside the range. No narrower figure is given: an
  estimate is still never a midpoint or a "most likely" number.
- **Reviews can point to the section numbers the reader sees.** In many Word documents the numbers in
  front of headings and numbered paragraphs ("3.2", "(a)", "Appendix B") are produced by Word and are not
  in the text. They are now worked out when a document is read, so findings can say "section 3.2" and
  cross-references can be checked. Checked against Word itself: the numbers match what Word shows.
  Documents with the numbers typed in are read as before.
- **Everyone in the room sees every comment.** In a mock-up shared with `--lan`, a comment saved on one
  laptop now appears on the others within a few seconds, without reloading, and has the same number
  everywhere (the number it is saved under).
- **`--lan` prints the address to share.** Starting a mock-up for the room now shows the address others
  open, such as `http://192.168.1.20:8765/`; you no longer have to look up your machine's address.
- **Filters and search boxes in the mock-up work.** On a list, choosing a filter value or typing in a
  search box and pressing **Search** (or Enter) now narrows the sample rows, the line under the list
  counts what is shown, and **Clear Filters** brings everything back. They used to do nothing, which
  clients noticed the moment they clicked.
- **What you type in the mock-up stays.** Moving between the steps of a form, or opening and closing a
  dialog, no longer empties the fields already filled in. Opening the form again starts it clean.
- **Typing mistakes in the spec are reported when the mock-up is built.** A column, filter, search or
  condition that names a field the sample data does not have, an `options_from` that points nowhere, an
  unknown field type, a record or role that does not exist, and a setting that nearly spells a real one
  (`colums`, `tittle`) now stop the build with a message that suggests the right name. They used to build
  and show an empty column, an empty drop-down or the wrong record. Settings of your own that the format
  does not know are left alone.
- **Windows: Node.js is now needed for Blueprint's checks in Claude Code**, not only for screenshots. The
  status shown when a session starts and the check before a commit are started through Node, so the same
  settings work on Windows and on a Mac. Setup already asks for Node.js; run `setup.cmd` if the machine
  check says it is missing.

### Fixed
- In the document, a role's heading and its one line of description no longer end a page on their own.
- A comment without a time, for example one merged in from an exported file, no longer breaks the
  Feedback panel in the mock-up.
- **A note in a rate cell no longer changes the rate.** In `building-blocks.md`, every number in a rate
  cell was read, so a note turned a single rate into a range: "3 (was 5)" was priced as 3 to 5 mandays,
  and "0.5 MD each (2023 rate)" as 0.5 to 2023. Only the figure the cell starts with counts now. A cell
  that does not start with a plain number or range, such as "1,5" with a decimal comma (which used to be
  read as 1 to 5), is not priced, and the estimate says which cell could not be read. **Check your
  estimates if any rate cell holds a second number.**
- **The newest estimate is the newest.** With two estimates on one day, "spec v0.9" was taken as newer
  than "spec v0.10". Estimates are now ordered by date and then by version number.
- **One damaged project no longer hides all the others.** The summary shown when a session starts stopped
  with an error if any project had an unreadable register, spec or feedback file. It now lists every
  project and says which file of which project could not be read.
- **Spreadsheet totals are read as figures.** A cell with a formula, such as the total of a scope of work,
  was read as `=SUM(B2:B3)`. Its calculated value is now given with the formula.
- **Text files saved in the Windows encoding or as "Unicode" in Notepad can be read.** They used to stop
  the reading of the document with an error.
- **Answers typed into the Excel register are no longer lost.** The register's Excel file was written
  afresh from `register.json` every time, so a client's answer typed into **Client response**, or a
  changed **Status**, vanished at the next update without a word. Blueprint now reads the Excel file
  first and takes over what was typed since it was written; an answer also moves an open question to
  "answered". If the same item was changed in Excel and by Blueprint, it stops and shows both values. A
  register file that is open in Excel now gives a plain message asking you to close it.
- **Reading a document can no longer delete other files.** The tool that turns a document into text
  emptied its output folder first, whatever that folder was: pointed at a project's `docs/` by mistake,
  it deleted the client's documents. It now replaces only an earlier extraction of its own, leaves any
  other file in that folder alone, and refuses a folder that holds something else.
- **The mock-up of an issued version is kept as the client saw it.** Rebuilding replaced the saved copy in
  `mockup/versions/` every time, also after that version had been issued, so showing "the version the
  client saw" could show something newer. The saved copy of an issued version is no longer replaced; the
  build says so and asks you to bump the version.
- One of the estimate tests failed with the newest version of the test runner, so the test run on GitHub
  had been red since 0.6.0. The test is corrected; nothing in the estimate tool changed.

## [0.7.0] - 2026-11-06

### Added
- **Status colours you choose.** A status in the spec can now say which colour it is shown in:
  `color: green`, `amber`, `red` or `grey`. The mock-up uses it wherever that status appears, and a spec
  with any other colour is reported as an error. Statuses without one are still coloured from their
  wording. See [docs/spec-format.md](docs/spec-format.md).
- **A warning when the screenshots are older than the spec.** Generating the requirements document now
  warns when a screen, dialog, role, status or the sample data changed after the screenshots were taken,
  and when a screen has no picture, with the command that takes them again. Rewording a requirement, a
  description or a rule does not trigger it. For a project you already have, take the screenshots once
  more to switch the check on fully; until then only added and removed screens are noticed.
- **House styles with filled table headers.** The document format has three new settings for companies
  whose documents do not use Blueprint's hairline tables: `tables.header_fill` (a colour for the header
  row, with white header text unless `tables.header_text` says otherwise), `tables.borders: grid` (a box
  round every cell) and `colors.heading` (the colour of chapter and section headings). Ask "make our table
  headers navy" or see [docs/document-format.md](docs/document-format.md). The default look is unchanged.
- **The format and the spec are checked before a document is generated.** A mistake in
  `branding/document-format.yaml` (a misspelt setting such as `colours`, an unknown chapter, a size that
  is not a number) or in the parts of the spec only the document prints (a requirement group with no
  items, a notification with no recipient, two extra sections with one title, a timeline week before 1)
  now stops the run with a list of what to fix, in plain words. These used to end in a Python error or
  were silently ignored. `python -I tools/document_format.py show` lists format mistakes too.
- Automated tests for the mock-up: the build, the comment server and, on a machine with Node and Microsoft
  Edge, the mock-up itself clicked through in the browser. Automated tests for the format tool.

### Changed
- **Screenshots you can read in the document.** Screens are now captured 1000 pixels wide instead of 1440,
  so the text inside a screenshot prints about 40% larger (roughly 6 pt instead of 4 pt). A screen that
  does not fit, such as a list with many columns, is captured wider automatically, and the command says
  which. Each screenshot is cropped to its content, so a short list or the process flow is no longer half
  empty. Screens are laid out a little tighter in the document than in the live mock-up, which still fills
  the window. **Take the screenshots again and regenerate** to get this in a document you already have.
- **The cover shows your document title as you wrote it.** It used to be forced into sentence case, so
  "System Requirement Specifications" printed as "System requirement specifications".
- **The summary page agrees with the rest of the document.** It counts every screen of the Screens chapter
  (the login screen was left out), and lists the signatories client first, as the sign-off chapter does.
- The document generator now stops with the list of errors when the spec has any (an unknown screen,
  role or dialog, for example), the same check the mock-up runs. It used to carry on or crash.

### Fixed
- **A comment is no longer lost when the mock-up cannot save it.** If the window that started the mock-up
  was closed, or the network dropped, a comment used to disappear while the mock-up still said "Saved to
  the project folder". Now a red message says it was not saved, the Feedback button shows how many are
  waiting, and the comment is kept in the browser, also if the page is reloaded. It is saved with the next
  comment that gets through, or with **Try again** in the Feedback panel, and **Export unsaved** gives it as
  a file for `inbox/`.
- **Two mock-ups can no longer share an address.** Starting a second mock-up on Windows while one was
  open gave no error, and comments could then be saved to either project. The second one now stops and
  says the port is in use and how to pick another (`present.cmd <project> --port 8766`), and the
  `present.cmd` window stays open so the message can be read.
- **Negative statuses are no longer shown green.** "Inactive", "Not Approved", "Unavailable" and similar
  were coloured as if they were good news, in the mock-up and so in the screenshots of the requirements
  document. Rebuild the mock-up and take the screenshots again to correct a project that has them.
- **Dialogs close when confirmed.** A dialog whose confirm button only shows a message stayed open after
  the click, and the default OK button did nothing. Both now close the dialog.
- A comment with characters the Windows console cannot show is saved like any other.
- **An old PDF can no longer sit beside a new Word document.** When the Word step did not run, the PDF from
  the previous run stayed in `output/` under the same name as the new document, with different content. The
  old PDF is now removed before the new document is written. If the PDF or the document is open in another
  program, the generator stops and asks you to close it.
- **A failed Word step says why.** Every failure used to be reported as "Word not available", even with
  Word installed. Now the reason is shown (for example the file is in use, or Word did not answer), and
  "Word not available" is said only when Word is not installed.
- **Owners and dates no longer break in the decisions table.** The Owner and Due columns were narrower than
  a date, so "2026-11-20" printed on two lines and a name such as "Operations" broke before its last
  letter. The Impact, Owner and Due columns are now sized to what they hold, and the question takes the
  rest of the width. Requirement IDs and references such as "FR-BKG-001.2" are no longer split across two
  lines at a hyphen, anywhere in the document.
- **Word is no longer left running in the background.** When the Word step failed half-way, a hidden Word
  stayed open with the document locked, and the next run could not write it. Word is now always closed,
  shows no hidden questions, and no longer adds generated documents to your recent files. If Word does
  not answer for four minutes, the message says how to end it in Task Manager.
- **References work in every text.** `{ref:...}`, `{client}`, `{system}` and the other names were resolved
  in some places only; in a role's description, a status meaning, a non-functional requirement, a glossary
  meaning, an integration, a notification event, a requirement group title and the cells of an extra
  section's table they printed as typed. A hand-typed "section 3.2" is now warned about there too.
- **The cover's status dot is green only for a settled status.** "Not approved", "Unsigned draft" and
  "Awaiting final review" were shown green; they are amber now. "Signed off", "Approved" and "Final" stay
  green.
- **Colours in the format file can be written the usual ways:** with or without `#`, in capitals or not.
- **The format tool runs on Python 3.10 and 3.11.** `document_format.py` needed 3.12, though setup accepts
  3.10; none of its commands started on the older versions.
- **The contents fits on fewer pages.** Its lines used the body text's spacing, so a contents of 36 lines
  ran three lines onto an empty page.
- **The summary cards line up with the text.** They were narrower than the tables and text around them.
- A company format file still under its old name, `branding/srs-format.yaml`, is read again.
- **System names with a colon, a slash or an apostrophe.** A colon in the system name (such as
  "Phase 2: Claims System") made Windows hide the generated document inside an empty file, a slash stopped
  the run, and an apostrophe broke the Word step so no PDF was written. The file name now replaces the
  characters Windows cannot store with a hyphen; the name inside the document is unchanged.

## [0.6.0] - 2026-11-06

### Added
- **Estimates.** Say "estimate this project" to get a manday estimate for the lead developer, counted in the
  knowledge base's building blocks from whatever exists: a brief or scope of work early on, the project spec
  later. Every figure is a range, with the assumptions and a confidence level, and what makes it uncertain:
  open high-severity questions, the gap patterns that apply, lines with no rate and how few delivered
  projects the rates rest on. When the project has a scope of work, the sold mandays are compared line by
  line and the largest differences come first. It ends with the workshop questions that would narrow the
  range most, and offers to add them to the register. Each estimate is a dated Excel file in the project's
  new `estimates/` folder; it is internal and never goes into a client document. See
  [docs/estimates.md](docs/estimates.md).
- **Your rates, not Blueprint's.** Estimates use the rates you set in `knowledge/building-blocks.md`, or a
  range the lead developer gives for one estimate. Blueprint never makes up a figure: a line with no rate is
  counted, shown as not priced and left out of the total, and Blueprint offers to save the rates it is
  given.
- **Other work in estimates.** A new `Other work` table in `building-blocks.md` holds your shares for project
  management, testing, UAT support, training and the like, as a percentage of the build or fixed mandays.
  New workspaces get it with every item unset. To add it to an existing workspace, ask Blueprint or copy
  the table from `templates/knowledge/building-blocks.md`.
- A sample estimate for the Leave Request example (counts, assumptions and questions, no figures of its
  own), and `tools/estimate.py` to list the rates, list what a project contains, render an estimate and
  turn it into weeks.
- A third mock-up look, `vivid`, for demos, pitches and clients who want a bold branded UI: a dark gradient
  side menu, a coloured header band with the page floating over it, gradient buttons and a glass login
  screen. Set `theme: vivid` in the spec. All of it follows the project's `primary_color`.
- Automated tests for the tools, so a fix to one part of the requirements document can no longer quietly
  break another. They check the generated Word document (chapter order, cross-references, the access
  matrix, a figure and field table for every screen, the timeline, sign-off forms, locked issued versions,
  and that everything works on a machine without Microsoft Word), the register and its Excel file, project
  housekeeping (issue, file, archive, restore), estimates (rates read from the knowledge base, ranges, the
  comparison with the scope of work, the confidence rules, and that nothing of an estimate reaches a client
  document) and the commit check. Nothing changes for people using
  Blueprint. If you change Blueprint itself: `python -m pip install -r requirements-dev.txt` once, then
  `python -m pytest`; GitHub runs them on every push. See [docs/maintaining.md](docs/maintaining.md#tests).

### Changed
- The **project timeline** is now drafted from the project's estimate instead of the scope of work's
  mandays, which are a commercial figure and often lower than the likely effort. Generating the
  requirements document offers to draft a missing timeline from the latest estimate, in weeks for the team
  size the lead developer gives; mandays never reach the document. Existing timelines are unchanged.
- The `modern` mock-up look is more polished: stat cards with icons and their own accent colours, a menu
  with icons, a user badge in the top bar, softer shadows, clearer form fields with a focus ring, status
  chips with a dot, and row highlighting in lists. The `joget` look is unchanged.

### Fixed
- In the `modern` and `vivid` mock-up looks, long stat card values (for example "RM 48,920") are no longer
  hidden behind the card's icon.
- Tables in a requirements document's extra sections and appendices no longer print "False" or "True"
  where the spec says `No` or `Yes` without quotes, for example a numbering column headed "No" or a
  "Yes"/"No" cell. They now print the word, and a "No" column is narrow again.

## [0.5.0] - 2026-11-06

### Added
- The requirements document can include a **project timeline** chapter: summary figures, a week-by-week
  chart of stages, activities and milestones (activities where the client must take part are highlighted),
  a milestones table with what the client must do, and the assumptions behind the plan. Weeks count from
  the kick-off, so the plan holds until a start date is agreed. Fill in `timeline` in the project spec
  (see the spec format); when it is missing, generating the document offers to draft it from the scope of
  work, one line per SOW item. Projects without a timeline are unchanged.
- Document format: a `timeline` chapter (after the NFRs) and a `timeline_bar` colour. A company format
  that lists its own `chapters` must add `timeline` to show it.

### Changed
- The starter requirements standard describes what a timeline must contain: stages, activities and
  milestones by week, what the client must do, and the assumptions behind it.

## [0.4.1] - 2026-11-06

### Changed
- In the requirements document, each screen's "Requirements · FR-…" line now sits right under the screen's
  description, before its screenshots, so readers see up front what the screen covers.

### Fixed
- Role names in the access matrix header no longer break in the middle of a word. Columns are sized to the
  longest word, and when there are too many roles to fit side by side the names are turned on their side.
- A screen's requirements line can no longer be left alone at the top of a page.
- A group heading inside a field table (for example "Approval Process") is no longer left at the bottom of
  a page without the rows under it.

## [0.4.0] - 2026-11-06

### Changed
- Blueprint now says "requirements document" instead of "SRS", because companies name this document
  differently. **Skills and tools are renamed:** `review-srs` → `review-requirements`, `generate-srs` →
  `generate-requirements`, `srs-format` → `document-format`, `tools/generate_srs.py` →
  `tools/generate_requirements.py`, `tools/srs_format.py` → `tools/document_format.py`. Asking in plain
  words works as before.
- The generated document's title is a company setting: `document.title` and `document.short` in the
  document format, e.g. "System Requirement Specifications" and "SRS". It appears on the cover, in the
  sign-off wording and in file names. The default is "Requirements Specification".
- Workspace files are renamed: `branding/srs-template.docx`, `srs-boilerplate.yaml` and `srs-format.yaml`
  become `document-template.docx`, `document-boilerplate.yaml` and `document-format.yaml`, and
  `knowledge/srs-standard.md` becomes `requirements-standard.md`. **Run `setup.cmd` once** to rename them;
  until then the old branding names still work. Standard wording can name the document with `{document}`.
- Register stages `srs-draft` and `srs-final` are now `requirements-draft` and `requirements-final`; the
  old values remain valid. The spec key `srs_table` is now `doc_table`; the old key still works.

### Fixed
- Claude Code's start-up greeting and commit check failed when a session's current folder was not the
  app folder; they now find the app wherever the session is.

## [0.3.0] - 2026-11-06

### Added
- Issuing: "issue v1.3 to the client" (`tools/project.py issue`) records which SRS version went to whom
  and when, and locks it. Its files become read-only and the generator refuses to overwrite it, so later
  changes become a new version. The status list shows the last issued version.
- Every mock-up version is kept in `mockup/versions/`, and `present.cmd <project> --version 0.2` shows an
  earlier one again.
- Documents are filed with dated, descriptive names, e.g. `2026-11-12 client comments on v1.3.docx`
  (`tools/project.py file`, used by the inbox and new-project skills).
- Archiving: delivered projects move to `projects/_archive/` and leave the status list; they can be
  restored.
- `tools/project.py check` finds projects missing parts of the standard layout; `--fix` adds them.

### Changed
- SRS page flow: every screen starts on a new page (switch off with `layout.screens_new_page: false`),
  headings stay with what follows them, screenshots stay with their captions, tables don't start with a
  lone header at the foot of a page and short tables are kept whole, and paragraphs don't leave single
  lines stranded. Documents are a few pages longer.

### Fixed
- The documentation check that runs before commits made through Claude Code could block every shell
  command while the docs were incomplete. It now only ever acts on `git commit`.

## [0.2.0] - 2026-11-06

### Added
- Documentation in `docs/`: getting started, workflow, skills, tools, the register, knowledge base,
  workspace and company profile, spec format, troubleshooting and maintaining.
- This changelog and a `VERSION` file.
- `tools/check_docs.py`: checks that every skill and tool is documented, the changelog is well formed and
  in step with `VERSION`, and links in the documentation work.
- A check before every commit made through Claude Code: app changes must come with a changelog entry,
  and the documentation check must pass.
- A GitHub Actions workflow that runs the documentation check on every push and pull request.
- `release` skill for maintainers: turns Unreleased into a version, updates `VERSION`, commits and tags.
- A new SRS design, now the default: calm greys, one accent colour, Geist type, hairline tables, and status
  shown as a dot beside a word. New pages and chapters: Document at a glance (counts, how to review it,
  sign-off status, version history), Requirements by role, and Decisions needed before sign-off with
  impact, owner and due date.
- Sign-off for any number of people: list them in the spec's `signoff`, client signatories first. Each
  gets a form kept on one page: name, designation, signature and date rows (left empty to write in when
  not known yet) and a full-height company stamp box. The at-a-glance page shows who
  has signed.
- The PDF has a digital signing field over every signature box: clients can sign in Adobe Acrobat Reader
  instead of printing and scanning. The fields don't print, so paper copies stay clean.
- Requirements link to the screens they apply to (`screens` in the spec), and screens list their
  requirements. Optional `priority` (Must, Should, Could) per requirement.
- The SRS format is configurable without code: `templates/srs-format.yaml` holds the default design and
  `workspace/branding/srs-format.yaml` your changes (colours, fonts, sizes, numbering, section order,
  titles, header and footer).
- `srs-format` skill and `tools/srs_format.py`: change the format from a plain request, learn it from a
  company's existing SRS, and preview it before regenerating real documents.
- Setup installs the Geist and Geist Mono fonts for the current Windows user, and generated documents
  embed their fonts so clients see them as designed. **Run `setup.cmd` again to get the fonts.**

### Changed
- The spec format reference moved from `tools/mockup/SPEC.md` to `docs/spec-format.md`.
- "Open Issues" in the SRS is now "Decisions needed before sign-off", and only points to requirement IDs
  that exist in the current version.
- Requirement IDs, versions and reference formats are set in Geist Mono; field tables have four columns
  (field, type, required, rule or source) instead of seven.

## [0.1.0] - 2026-11-06

First release.

### Added
- Skills: `start`, `new-project`, `process-inbox`, `review-srs`, `build-mockup`, `apply-feedback`,
  `generate-srs`, `close-project`.
- Requirements review that cites every finding, keeps client questions and internal fixes apart, and
  writes an Excel register for the BA.
- Clickable mock-ups from a project spec, with Joget and modern themes, role switching, dialogs, and a
  Feedback mode that pins client comments to screen elements and saves them to the project.
- SRS generation from the same spec: version history, roles, an access matrix built from the screens, a
  process flow drawn from the statuses, requirements with resolvable cross-references, screenshots with
  data tables, NFRs, Open Issues from the register and appendices, in the company's Word template.
- App and workspace separation: company profile, branding, knowledge base, projects and inbox live in a
  workspace that is never committed and can be shared through OneDrive or SharePoint.
- Starter knowledge base: gap patterns with workshop questions, estimating building blocks and the SRS
  standard.
- One-step setup (`setup.cmd`) with a machine check, `present.cmd` for sessions, shared Claude Code
  permissions and a start-up status greeting.

[Unreleased]: https://github.com/Axidify/blueprint/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/Axidify/blueprint/compare/v1.3.3...v1.4.0
[1.3.3]: https://github.com/Axidify/blueprint/compare/v1.3.2...v1.3.3
[1.3.2]: https://github.com/Axidify/blueprint/compare/v1.3.1...v1.3.2
[1.3.1]: https://github.com/Axidify/blueprint/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/Axidify/blueprint/compare/v1.2.1...v1.3.0
[1.2.1]: https://github.com/Axidify/blueprint/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/Axidify/blueprint/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Axidify/blueprint/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Axidify/blueprint/compare/v0.10.0...v1.0.0
[0.10.0]: https://github.com/Axidify/blueprint/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/Axidify/blueprint/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/Axidify/blueprint/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/Axidify/blueprint/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Axidify/blueprint/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Axidify/blueprint/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Axidify/blueprint/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Axidify/blueprint/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Axidify/blueprint/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Axidify/blueprint/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Axidify/blueprint/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Axidify/blueprint/releases/tag/v0.1.0
