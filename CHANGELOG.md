# Changelog

All notable changes to Blueprint are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a major version for changes that need people to change how
they work or migrate their workspace, a minor version for new features, a patch for fixes.

Add every change to **Unreleased** as you make it, under Added, Changed, Deprecated, Removed, Fixed or
Security. Write for the people using Blueprint: say what they can now do, or what behaves differently.
See [docs/maintaining.md](docs/maintaining.md).

## [Unreleased]

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

[Unreleased]: https://github.com/Axidify/blueprint/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Axidify/blueprint/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Axidify/blueprint/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Axidify/blueprint/releases/tag/v0.1.0
