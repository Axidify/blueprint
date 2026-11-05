# Workflow

Blueprint follows a typical delivery process. Gaps missed during requirements come back as change
requests (CRs) during development, usually underpriced. Each stage below has a Blueprint step that
catches gaps earlier.

| Stage | What happens | What to ask Blueprint | You get |
|---|---|---|---|
| 1. Brief → SOW | The lead dev scopes the work and estimates mandays | "Start a new project", then share the brief | A project folder; the gap patterns worth raising in workshop 1 |
| 2. Workshop 1 | The BA gathers requirements | "Build a mock-up from the brief / these notes" | A clickable mock-up and open questions in the register |
| 3. Mock-up review (workshop 2) | The client walks through the mock-up | Present with `present.cmd`, then "apply the feedback" | A new mock-up version; decisions, questions and possible CRs in the register |
| 4. SRS for sign-off | The SRS goes to the client | "Generate the SRS" | Word and PDF in the company's layout, with screenshots, an access matrix built from the screens, and an Open Issues section from the register |
| 4a. Any requirements document | Drafts from anyone, including the client | "Review this SRS" | A review report and the Excel register for the BA |
| 5. Delivery | Development, UAT, CRs, go-live | "Close the project" with actual effort and the CR list | Estimate vs actual, CRs mapped to gap patterns, a stronger knowledge base |

## How the pieces connect

- **One spec per project** (`projects/<name>/spec/app.yaml`) drives both the mock-up and the SRS, so the
  screenshots, field tables, statuses and access matrix cannot contradict each other. Change things in
  the spec, never in the generated Word file. See [Spec format](spec-format.md).
- **One register per project** collects every question, gap, assumption and decision from every stage, with
  its status. The BA takes the Excel version to the client; resolved items drop out of the SRS Open Issues
  section automatically. See [The register](register.md).
- **The knowledge base** grows with every project: each CR becomes evidence for a gap pattern, and each
  gap pattern becomes a standard workshop question and review check. See [Knowledge base](knowledge.md).

## A typical cycle

```
brief ──► new project ──► mock-up v0.1 ──► workshop ──► apply feedback ──► mock-up v0.2 ──► ...
                                                                                 │
              review (any draft) ◄── generate SRS v1.0 ◄─────────────────────────┘
                     │
                     └──► fix in spec ──► regenerate ──► client sign-off ──► delivery ──► close project
```
