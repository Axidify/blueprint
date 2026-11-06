# Design language

How everything Blueprint draws should look: the `desk` mock-up theme, the client looks set on top of a theme,
and Blueprint's own pages (the project overview, the page that lists every mock-up, the presenter's bar). Read
it before designing anything; the `mockup-design` skill follows it.

**The reference is Apple:** the polish of Apple's own apps and Apple's Human Interface Guidelines. Calm,
ordered, nothing extra. Where this page settles something, follow it. Where it says nothing, do what Apple's
own apps would do, then add the decision here.

**This is the default look.** Every new project that is not on Joget starts in `desk`, drawn to this page:
Cobalt as the one accent, teal and pink for data, greys, Geist, the sizes below. It was agreed on screens of the
sample; change it only once a change is agreed the same way, and keep this page and `desk` in step.

The `joget` theme is the one exception: it shows what Joget gives without custom work, so it follows Joget, not
this page. A project that already has a mock-up keeps its theme until someone asks to move it.

## Principles

| Principle | In practice |
|---|---|
| **Less, then less again** | Every element earns its place. Fewer blocks per screen, fewer controls per block, fewer words per label. |
| **Balanced and repeated** | Equal columns, rows that end level, the same sizes on every screen. Calm comes from order, not decoration. |
| **One focus per screen** | At most one accent-coloured thing that says "do this now": the main button, or one card. |
| **Quiet interface, loud content** | The interface is greys. Colour is spent only on actions, selection, status and data, so it always means something. |
| **Structure from hairlines and space** | White cards on a soft grey ground, thin separators that start where the text starts. No heavy boxes. |
| **Type and status stay simple** | A few sizes, two weights, two greys. Status is a dot and a word, never colour alone. |
| **Nothing that promises a feature** | A mock-up shows what is in the spec. A search box, bell or export button the spec does not have would become something the client expects, then a change request. |

## Colour

### One loud accent, a complementary pair for data, greys for the rest

| Role | Default | Where it goes | Never |
|---|---|---|---|
| **Accent** (the loud colour, `primary_color`) | Cobalt `#1F5FBF` | The one main button, links, selection, the selected tab, focus, the one card that needs attention | More than one accent-coloured surface on a screen |
| **Data pair** (`data_colors`) | Teal `#1597B0` and pink `#D55181` | People's initials, chart series, the small square beside a type | Words, buttons, large fills |
| **Greys** | see below | Everything else | Tinted (blue or warm) greys |

- **Accent and data colours are never green, orange or red** (they mean status) and **never violet or
  indigo** (they read as the generic look of AI-made interfaces).
- **White words on the accent read at 4.5 : 1 or more.** Check a new accent before using it.
- **Accents to choose from:** Cobalt `#1F5FBF`, Petrol `#0E6E7E`, Ocean `#0B6E99`, Spruce `#2F6B6A`,
  Deep teal `#00796B`, Steel `#4A6378`, Ink `#1F3A5F`, Apple blue `#0071E3`, Plum `#8E3B78`, Graphite `#1D1D1F`.
- **Data colours to choose from, in this order:** cobalt `#3478D4`, pink `#D55181`, teal `#1597B0`, ochre
  `#C98500` (charts only, never beside a late item). A pair is two of them far apart on the colour wheel, so
  two series never blur. Colour follows the thing (the same person, the same leave type), never its rank.
- **The accent's softer shades are calculated, never picked:** tint 8% accent on white (secondary button,
  focus card, selected menu item), tint ring 22%, text on tint the accent mixed 85% with black, focus halo
  the accent at 25%, 3px.

### Greys

| Role | Colour | Use |
|---|---|---|
| Ground | `#F5F5F7` | The page behind cards |
| Card | `#FFFFFF` | Cards, panels, fields |
| Text | `#1D1D1F` | Primary text |
| Secondary text | `#6E6E73` | Details, captions, column headers |
| Separator | `#E5E5EA` | Hairlines between rows |
| Strong line | `#D2D2D7` | Field and quiet-button outlines |
| Field fill | `#E9E9EE` | Segmented controls, tags |
| Track | `#EDEDF0` | Progress and bar tracks |

### Status

| Meaning | Dot | Words |
|---|---|---|
| Done, approved, on time | `#34C759` | `#248A3D` |
| Late, needs attention | `#FF9500` | `#C93400` |
| Refused, blocked, failed | `#FF3B30` | `#D70015` |
| Not started, neutral | `#8E8E93` | secondary text |
| Waiting, in progress | the accent (a ring for waiting) | the accent's text |

- Always a dot and a word ("Waiting for approval"), never colour alone and never a large tinted panel.
- Late is orange, refused is red. Information is grey, not blue.

### A client's colours

Their main colour becomes the accent, darkened until white reads on it at 4.5 : 1. If it is red, orange or
green, use their second brand colour or the nearest accent above, and say why. The data pair is two of their
other brand colours far apart on the wheel, or teal and pink when they have none. A coloured top bar or dark
menu only when the client's own systems have one (`header`, `menu`).

## Type

**Geist** for everything; **Geist Mono** only for reference numbers, amounts in columns and times, so digits
line up. The mock-up carries both fonts, so every laptop shows them.

| Role | Size | Weight | Tracking |
|---|---|---|---|
| Page title | 28 | 600 | -0.02em |
| Focus line (the one card that needs attention) | 22 | 600 | -0.015em |
| Section title | 17 | 600 | -0.01em |
| Body, rows, fields | 15 | 400 | 0 |
| Buttons and labels | 14–15 | 500 | 0 |
| Details | 13 | 400 | 0 |
| Column headers, axis labels | 12 | 500 | 0 |

- Sizes scale with `text_size` (`large`, `larger`), as Apple's Dynamic Type does.
- Sentence case everywhere; no all-caps labels. Importance comes from size and weight, not colour.
- Tabular figures wherever numbers sit in columns.

## Layout and spacing

| Rule | Value |
|---|---|
| Spacing steps | 4, 8, 12, 16, 20, 24, 32, 40, 48, and nothing in between |
| Around the page | 40px (32px when the screen is narrow) |
| Between cards | 24px |
| Inside a card | 20–24px |
| Grid | Equal columns; rows of cards are always equal height and end level |

- **Repeat, don't vary:** every card has the same corner, padding, header height and row height.
- **Inset separators:** a row's line starts where its text starts.
- **Actions line up:** buttons in a list share one width and one right edge.

## Phones and tablets

Settle the device of each role first: who works at a desk, who on a tablet, who on a phone in the field. When
the brief does not say, it is a question for the client (a register item), never a guess: it changes screens,
requirements and the estimate.

### Sizes

| Device | Width | Margins | Navigation |
|---|---|---|---|
| Phone | below 640px (drawn at 390 × 844, a current iPhone) | 16px | A tab bar at the bottom, at most five items; more go under "More" |
| Tablet | 640–1023px | 24px | The side menu as a drawer behind a menu button, or narrowed to icons |
| Desktop | 1024px and up | 40px (32px below 1100px) | The side menu |

### A web system opened on a phone or tablet (responsive)

- **One column on a phone.** Cards, figures and form sections stack; rows of two become one. Nothing scrolls
  sideways except a wide table inside its own card, with a soft shadow at the edge that can still scroll.
- **Lists become rows, not tables:** the main value on the first line, one or two details under it in
  secondary grey, the status dot and word on the right, a chevron when the row opens something. Rows at least
  56px with two lines.
- **Filters collapse into one Filters button** that opens a sheet from the bottom; the search field stays
  visible at the top of the list.
- **Dialogs become sheets** that slide up from the bottom, with the action at the bottom of the sheet.
- **Forms are one field per row,** labels above, and each field asks for the right keyboard (numbers, phone,
  email) or picker (date, time, a choice). Fields are at least 16px text, so a phone does not zoom in on them.
- **Text never gets smaller on a phone:** body 15px at least; nothing under 12px.

### A mobile app (native or installed on the phone)

Follow Apple's own apps (Human Interface Guidelines), in the colours and words of this page:

- **Large title** (34px) at the top of a list screen, shrinking into the top bar as the list scrolls;
  body text 17px, details 13px.
- **A tab bar at the bottom** for the main places (at most five), always visible; a screen opened from a
  list has a back button at the top left saying where it goes back to.
- **The main action within thumb reach:** full width at the bottom of the screen (50px tall, 16px from the
  edges), or in the top bar's right corner when it is a quick one (Add, Done).
- **Everything pressed is at least 44 × 44px,** with at least 8px between two targets.
- **Leave the phone's own areas free:** the status bar at the top and the home indicator at the bottom (34px).
- **Say what the phone is doing:** offline, syncing or synced as a dot and a word in the top bar, and what was
  saved on the phone but not yet sent.

### Questions a phone raises

Put the ones the brief does not answer in the register, so they are settled before the requirements are
signed: which phones and versions (iPhone, Android, both), portrait only or also landscape, working without a
signal, the camera, location, signatures on the screen, push notifications, use outdoors (sunlight, gloves,
one hand), and shared or personal devices.

### What the mock-up can show today

The engine draws every screen at desktop width; `desk` only tightens its spacing below 1100px. Phone screens
are drawn in the project's own mock-up code (`mockup.js` and `mockup.css`): a phone frame 390px wide with the
tab bar at the bottom, as a mobile project's spec can describe. Write what differs on a phone into the spec's
requirements too ("On a phone, a technician sees their jobs as a list of rows …"), since the requirements
document is written from the spec. Screenshots are taken 1000px wide, so a phone screen sits in the middle of
its picture.

## Shape, depth and materials

| Corner | Use |
|---|---|
| 6px | Tags, checkboxes |
| 7px | Small controls, menu rows |
| 9px | Buttons and fields |
| 12px | Inner panels, menus |
| 16px | Cards |
| 20px | Dialogs |

Bigger things get rounder corners, so nesting always looks right (`corners` scales them all for a client).

| Depth | Shadow |
|---|---|
| Ground | none |
| Card | 1px ring `rgba(0,0,0,.05)` + `0 1px 3px rgba(0,0,0,.04)` |
| Raised (menus, toasts) | ring + `0 8px 24px rgba(0,0,0,.12)` |
| Dialog | ring + `0 24px 64px rgba(0,0,0,.2)`, page dimmed |

Frosted surfaces (`rgba(250,250,252,.75)` with a 20px blur) only on what stays above content: the top bar and
the side menu. Never on cards or dialogs, never two frosted layers on top of each other, solid when the viewer
asks for less transparency.

## Motion

120ms for hover and press, 200ms for menus and rows appearing, 320ms for dialogs and side panels. Easing
`cubic-bezier(.2, .8, .2, 1)`; nothing bounces. Motion only shows what changed; none when the viewer asks
for reduced motion.

## Icons and focus

- Line icons (Lucide), 1.8 stroke, rounded ends: 16px inline, 17px in the side menu, 20px in toolbars. No emoji,
  no filled icon sets. Menu items are words only.
- Everything that can be focused shows the accent focus halo.

## Components

### Buttons: three tiers, one job each

| Tier | Look | When |
|---|---|---|
| Primary | Solid accent, white words | The screen's main action. At most one per screen. |
| Secondary | Accent tint, accent words | The usual action on a row: Review, Approve |
| Quiet | Transparent, strong-line outline | The less likely choice: Reject, Cancel |
| Link | Accent words, no box | Goes somewhere and changes nothing: View, Show all |

- **Heights:** 44px for the row of buttons a screen ends with (Apple's smallest comfortable target), all of
  them together so the main action and its alternatives stay level; 36px in a list's toolbar and elsewhere;
  34px small buttons in rows.
- **Never green for Approve or red for Reject:** both are normal choices. A destructive action is red words in
  a quiet button; solid red only inside its confirmation dialog.
- **No greyed-out buttons.** Hover and press go one and two shades darker. Verb first: "Submit application",
  not "OK".

### Fields

36px tall, 9px corners, a strong-line outline, the label above (13px, weight 500), never a placeholder as the
label. Help text below in secondary grey; an error is a red outline and a sentence saying what to do. A search
field is a field like any other, white with its outline, and a search icon at its left: a grey fill reads as
disabled.

### Tables and lists

- **A list is one card:** its filters and buttons in one row at the top, the table, then the record count.
- **Rows at least 48px**, 15px text, inset separators, a light grey on hover, a selected row in the accent tint.
- **Columns 16px apart** (8px each side), so a list fits the 1000px screenshots. A one-word value (a reference, a
  date) stays on one line; a two-word one (a type) too, while the list fits.
- **Column headers** 12px, weight 500, secondary grey, no fill.
- **Status** as a dot and a word; **people** as initials in a data colour beside the name (every name in a
  column that holds people); **types** as a grey tag with a small data-colour square.
- **Tabs** are words with a 2px accent underline under the selected one; a count beside a word is a grey tag.

### Cards, dialogs and messages

- **The focus card:** the one thing that needs the viewer, in the accent tint with a 22% ring, its words in
  the focus line size. At most one per screen.
- **Dialogs** only for what can't easily be undone: the title states the consequence, then Cancel (quiet) and
  the action. Everything else confirms with a short message at the bottom of the screen.
- **Empty states invite:** a short title, one line, one action, inside the card.

### Charts

The data pair, then the next data colours in order; context in grey. Green, orange and red only when they
mean done, late and refused. Labelled bars are one colour. A donut is a thin ring with a list beside it, not
leader lines.

## Spreadsheets

The register, the estimate, the UAT workbook and the CR log share one look (`tools/sheets.py`), so they read as
one family:

| Part | Look |
|---|---|
| Font | Calibri: every copy of Office has it, and Geist cannot travel inside an Excel file |
| Title | 18pt bold ink; the line under it in secondary grey |
| Header row | 10pt bold secondary grey on the ground grey `#F5F5F7`, a strong line `#D2D2D7` under it |
| Rows | 11pt ink, wrapped and middle-aligned, a hairline `#E5E5EA` under each; no gridlines |
| Status, severity, result | A dot and a coloured word (green, orange, red, grey, the accent), by conditional formats so the colour follows the word when someone changes it; the cell holds the word alone |
| Cells to fill in | Cobalt tint `#EDF2FA` with a thin Cobalt edge `#A9C0E5`, and the column's header in Cobalt |
| Numbers | Right-aligned |
| Printing | Landscape A4, one page wide, the header row repeated, "Page n of n"; a sheet that is not for the client says "Internal: not for the client" at the top |

Only the look is set by the shared style: the sheets, columns, values and their places stay as each tool writes
them, so what Blueprint reads back from a returned workbook (the client's answers, the testers' results) does
not move.

## Words

Sentence case for buttons, titles, labels and menu items. Plain words, verb first on buttons. No "please",
"successfully" or exclamation marks. Errors say what happened and what to do, in one sentence. "Late", not
"overdue". A real ellipsis for something in progress ("Saving…").

## Where `desk` differs today

The `desk` theme follows this page, except for what has not been built yet:

- No phone or tablet layout of its own: phone screens are drawn in the project's own mock-up code (see
  Phones and tablets).
- Not drawn yet: icons, the focus card, tabs with counts, a type's colour square, charts, a header card on a
  record's page, empty states that invite.

## Changing it

Agree the change first (show it as a picture or a small mock-up), then update this page in the same commit as
the code, and say what changed in the changelog.
