# Changelog

All notable changes to Blueprint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a major version for changes that need people to change how
they work or migrate their workspace, a minor version for new features, a patch for fixes.

Add every change to **Unreleased** as you make it, under Added, Changed, Deprecated, Removed, Fixed or
Security. Write for the people using Blueprint: say what they can now do, or what behaves differently.
See [docs/maintaining.md](docs/maintaining.md).

## [Unreleased]

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

[Unreleased]: https://github.com/Axidify/blueprint/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/Axidify/blueprint/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/Axidify/blueprint/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Axidify/blueprint/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Axidify/blueprint/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Axidify/blueprint/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Axidify/blueprint/releases/tag/v0.1.0
