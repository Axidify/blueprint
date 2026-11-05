---
name: generate-requirements
description: Generate the requirements document (Word and PDF) for a project from its spec and mock-up screenshots, in the company's format and under its own document title (SRS, functional specification …), then review it before it goes to the client. Use when the user asks to create, produce, update or issue the requirements document, SRS or specification for a project that has a spec and mock-up.
---

# Generate the requirements document

The requirements document is built from `projects/<slug>/spec/app.yaml` plus the mock-up screenshots, in the document format
(`docs/document-format.md`; change it with the `document-format` skill), using the company's Word template and
standard wording (`workspace/branding/`, falling back to the neutral
ones in `templates/`), with the company name from `workspace/company.yaml`. The access matrix, status table, data
requirement tables and screenshots all come from the spec, so they cannot contradict each other.

## 1. Make sure the spec is ready

- Every screen has a `description`; every form field that matters has `length`, `source` and `validation`.
- Requirements cover every screen and workflow step.
- `nfr` and `integrations` are filled in. Missing NFRs are a known gap (GP-12).
- `timeline` is filled in (`docs/spec-format.md`). If it is missing and the project has a scope of work in
  `docs/`, offer to draft it: one activity per SOW item (`ref` = item number), weeks worked out from the
  mandays and the team size, client activities marked `client: true`, milestones for kick-off, sign-off,
  development complete, UAT sign-off, go-live and end of warranty, each with what the client must do.
  Mandays are not weeks: ask the lead developer for the team size and state it in `assumptions`, with a
  range where the team is not fixed. Show the draft to the user before generating.
- Open questions are in `register.json` as client items; they become the **Open Issues** section.
  Resolved items drop out automatically.
- Version, dates, `status` and `history` in `project` are right for this issue.
- `signoff` lists everyone who must sign (client signatories first). Ask the user if it is missing.
- Requirement groups list the `screens` they apply to, so requirements and screens link to each other.
  Only set `priority` (Must, Should, Could) when the client has agreed it; never invent priorities.
- Cross-references use `{ref:...}` (see `docs/spec-format.md`), never literal section numbers. When a spec is
  rebuilt from an earlier requirements document, copied requirement text is full of stale "section N.N" and "Appendix X"
  references and remarks about the mock-up: fix them all.
- Each TBC inside a requirement is linked to its register item with `tbc: R-xxx`.

## 2. Generate

1. `python -I tools/mockup.py screenshots projects/<slug>` (always regenerate, so the screenshots match
   the spec).
2. `python -I tools/generate_requirements.py projects/<slug>`. This writes the `.docx` to `projects/<slug>/output/`,
   and, if Microsoft Word is installed, updates the table of contents and writes a PDF next to it. A copy
   of the spec used is saved as `spec-v<version>.yaml`.
3. Read the warnings it prints (literal cross-references, unknown `{ref:...}`, requirements that mention the
   mock-up, missing images). Do not issue a version with warnings.

## 3. Never overwrite an issued version

If the spec's version was already issued to the client, the generator stops with a message. Bump
`project.version` (and add a `history` entry), then generate again. Never unlock an issued version to
regenerate it: the client has that file.

## 4. Review before it goes out

Run the `review-requirements` skill on the generated document. Generated documents are consistent by
construction, so the review should focus on what generation cannot guarantee: missing workflow edge
cases, undefined KPIs, integration scope, NFRs and open items. Fix findings in the spec and regenerate,
rather than editing the Word file by hand. Hand edits are lost at the next generation.

If the client needs something the generator does not produce (for example a process-flow diagram), add
it as a spec file (`spec/process-flow.png`) or extend `tools/generate_requirements.py`.

## 5. Issue it

When the user says the document has gone (or is going) to the client, record it:
`python -I tools/project.py issue <slug> --to "<recipient>"`. This locks the version: its files become
read-only, and any later change needs a new version.

## 6. Report

Give the user the paths to the `.docx` and `.pdf`, the number of open issues included, and the review
verdict.
