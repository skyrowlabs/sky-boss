---
slug: <kebab-case-slug>
title: <Short human title>
status: draft          # draft → active → complete
created: <YYYY-MM-DD>
updated: <YYYY-MM-DD>
agent_value: 2         # 1–3, set at completion. 3 = read before touching this system;
                       # 2 = useful debugging context; 1 = historical only
key_files: []          # fill in as you go
---

# <Title>

## Why

The problem, in plain terms. What is annoying, manual, or invisible today. If this
exists to prevent a specific failure, name the failure.

## Shape

The design decision. How it works, and which substrate or existing tool it drives
rather than reimplements.

**Does not do:** the explicit scope boundary. Write this before any code exists —
it is much harder to reconstruct once implementation has blurred it.

## Phases

Each phase is independently commitable and leaves the repo working.

### Phase 1 — <name>

- [ ] task
- [ ] task

### Phase 2 — <name>

- [ ] task

## Notes

Filled in during implementation. Surprises, reversals, and why the shipped thing
differs from the plan. This is the section a future session actually needs.
