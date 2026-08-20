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

Each phase is independently commitable and leaves the repo working. Phases are grouped into
**rounds** — a round is one campaign of work on this feature. A feature that ships, and is later
changed or fixed, gains Round 2 here rather than a second doc. Shipped rounds keep their checked
boxes forever.

### Round 1 — <what this round is> (<YYYY-MM-DD>)

#### Phase 1 — <name>

- [ ] task
- [ ] task

#### Phase 2 — <name>

- [ ] task

## Notes

Filled in during implementation, one dated entry per round. Surprises, reversals, and why the
shipped thing differs from the plan. **Accretes, never rewrites** — reasoning that a later round
overturned stays on the page with the reversal recorded beside it, because a superseded argument
left visible is what stops someone making it again. This is the section a future session actually
needs.
