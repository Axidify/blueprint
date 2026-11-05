---
name: generate-srs
description: Generate the SRS Word document (and PDF) for a project from its spec and mock-up screenshots, in the company's standard layout, then review it before it goes to the client. Use when the user asks to create, produce, update or issue the SRS or requirements document for a project that has a spec and mock-up.
---

# Generate the SRS

The SRS is built from `projects/<slug>/spec/app.yaml` plus the mock-up screenshots, in the SRS format
(`docs/srs-format.md`; change it with the `srs-format` skill), using the company's Word template and
standard wording (`workspace/branding/`, falling back to the neutral
ones in `templates/`), with the company name from `workspace/company.yaml`. The access matrix, status table, data
requirement tables and screenshots all come from the spec, so they cannot contradict each other.

## 1. Make sure the spec is ready

- Every screen has a `description`; every form field that matters has `length`, `source` and `validation`.
- Requirements cover every screen and workflow step.
- `nfr` and `integrations` are filled in. Missing NFRs are a known gap (GP-12).
- Open questions are in `register.json` as client items; they become the **Open Issues** section.
  Resolved items drop out automatically.
- Version, dates, `status` and `history` in `project` are right for this issue.
- `signoff` lists everyone who must sign (client signatories first). Ask the user if it is missing.
- Requirement groups list the `screens` they apply to, so requirements and screens link to each other.
  Only set `priority` (Must, Should, Could) when the client has agreed it; never invent priorities.
- Cross-references use `{ref:...}` (see `docs/spec-format.md`), never literal section numbers. When a spec is
  rebuilt from an earlier SRS, copied requirement text is full of stale "section N.N" and "Appendix X"
  references and remarks about the mock-up: fix them all.
- Each TBC inside a requirement is linked to its register item with `tbc: R-xxx`.

## 2. Generate

1. `python -I tools/mockup.py screenshots projects/<slug>` (always regenerate, so the screenshots match
   the spec).
2. `python -I tools/generate_srs.py projects/<slug>`. This writes the `.docx` to `projects/<slug>/output/`,
   and, if Microsoft Word is installed, updates the table of contents and writes a PDF next to it. A copy
   of the spec used is saved as `spec-v<version>.yaml`.
3. Read the warnings it prints (literal cross-references, unknown `{ref:...}`, requirements that mention the
   mock-up, missing images). Do not issue a version with warnings.

## 3. Review before it goes out

Run the `review-srs` skill on the generated document. Generated documents are consistent by
construction, so the review should focus on what generation cannot guarantee: missing workflow edge
cases, undefined KPIs, integration scope, NFRs and open items. Fix findings in the spec and regenerate,
rather than editing the Word file by hand. Hand edits are lost at the next generation.

If the client needs something the generator does not produce (for example a process-flow diagram), add
it as a spec file (`spec/process-flow.png`) or extend `tools/generate_srs.py`.

## 4. Report

Give the user the paths to the `.docx` and `.pdf`, the number of open issues included, and the review
verdict.
