---
title: "<Human Title>"
slug: <kebab-slug>
shelf_status: planned
priority: medium
updated: <YYYY-MM-DD>
tags: []
summary: "<One sentence. This is what shows in the index — make it say what changes, not what area it touches.>"
---

# <Human Title>

> **Status**: 🔴 Planned
> **Shelf-Status**: planned
> **Priority**: Medium — <why this priority, in a clause>
> **Updated**: <YYYY-MM-DD>

<!--
  Header lines above always beat the frontmatter. Add these when they apply:

    > **Queue-Order**: 40        # only on a `ready` plan; lower runs earlier, gaps of 10
    > **Blocked-On**: owner-ops  # required on blocked/shelved/deferred; never inferred
    > **Review-PR**: #123        # set when the plan goes to in-review
    > **Depends on**: `other-plan.md` — why it blocks this one (link it once it exists)
-->

## Problem

What is wrong today, and what it costs. Be concrete: the failure, not the
category of failure. A reader six months from now needs to be able to tell
whether the problem still exists.

## Approach

How this fixes it, in a paragraph. Then the phases.

## Phase 1 — <name>

- [ ] Task
- [ ] Task

## Phase 2 — <name>

- [ ] Task
- [ ] Task (~operator) — a step only a human can take; exempt from the filing check
- [ ] Task (~deferred) — a deliberate non-goal for this plan

## Acceptance

What must be true, and the command that proves it. "Tests pass" is not
acceptance; name the assertion.

- [ ] `./dev test unit` green
- [ ]

## Dropped, and why

Options considered and rejected. **This section is the reason to read an old
plan.** The expensive half of a design is what it ruled out, and without this it
gets re-litigated by whoever touches the system next.
