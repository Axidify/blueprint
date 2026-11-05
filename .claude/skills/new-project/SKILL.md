---
name: new-project
description: Set up a new client project in Blueprint, ask the few questions needed to start, and file any documents the user already has. Use when the user wants to start, create or add a project, or has a brief or document for a client and system that has no project folder yet.
---

# New project

## 1. Ask (one AskUserQuestion call where possible)

- **System name**, e.g. "Courier Booking System".
- **Client name** and short name, e.g. "Acme Logistics Sdn. Bhd." / "Acme".
- **Platform**: one of the platforms in `workspace/company.yaml`, or another.
- **Mock-up look**: `joget` (looks like what Joget delivers) or `modern` (custom builds or a branded UI).

Make the folder name (slug) from the system name: lowercase, hyphenated, short (`courier-booking`).
Check it is not already in `projects/`.

## 2. Create it

`python -I tools/new_project.py <slug> "<System name>" "<Client name>" --platform "<Platform>"`

## 3. File what they already have

If the user mentioned or attached documents (brief, SOW, notes, an SRS draft, a Figma export), or there
are files in `inbox/` for this client, file them with
`python -I tools/project.py file <slug> "<file>" --kind "<what it is>"` (dated, descriptive names). Never
edit the originals.

## 4. Suggest the next step

Based on what exists:
- Only a brief or SOW: build a first mock-up (`build-mockup`) to take into workshop 1, and list the gap
  patterns from `knowledge/gap-patterns.md` worth asking about.
- An SRS or URS draft: review it (`review-srs`).
- Nothing yet: ask them to drop the brief into `inbox/` or paste it.

Offer to do the next step now.
