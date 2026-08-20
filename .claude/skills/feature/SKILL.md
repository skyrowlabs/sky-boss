---
name: feature
description: Write or execute a single feature doc in docs/features/. Takes either an existing slug (execute mode) or a plain description (write the spec first, confirm, then execute). Use when the user says "implement docs/features/X.md", "work through X", "plan and build X", or describes a feature to add to tackle-box.
---

# /feature — feature doc driver

One doc per feature at `docs/features/<slug>.md`, cradle to grave. **The doc never moves.**
`status:` transitions in frontmatter instead. This is deliberate — the sibling project
(jam.sense) files completed specs into a second directory, and that `git mv` broke 141
cross-document links before anyone noticed. One folder cannot have that bug.

No subagents. This runs in a single session — tackle-box has no database and no test suite
to delegate to, so a multi-agent pipeline would be ceremony.

## Modes

Look at the argument:

- **A slug or path** matching an existing `docs/features/*.md` → **execute mode**, start at Step 2.
- **A description** with no matching doc → **write mode**, start at Step 1.

If ambiguous, `ls docs/features/` and look for a near match before asking.

## Step 1 — Write the spec (write mode only)

Copy `docs/features/_template.md` to `docs/features/<slug>.md` and fill it in.

Spend the effort on **Why** and **Shape**, especially the *"Does not do"* line — scope
boundaries are cheap to write now and expensive to reconstruct later. Break the work into
phases that are each independently commitable and leave the repo working.

Set `status: draft`. **Show the user the spec and confirm before executing.** Planning is
cheap to redo; a wrong spec is expensive to implement.

## Step 2 — Execute

1. Read the whole doc. Build a task list mirroring the phases so progress is visible.
2. Set `status: active` and update `updated:`.
3. Work one phase at a time. After each phase:
   - Check off its `- [ ]` boxes **in the doc**.
   - Commit that phase (once the repo is under git).
   - Append anything surprising to **Notes** while it is still fresh.

Check the boxes as you go, not at the end. A session that dies mid-feature must be resumable
by reading the doc alone — that is the entire point of the format.

If a phase is blocked with no path forward, stop, set `status: draft` with a Notes entry
explaining the block, and surface it. Do not mark a feature complete around a hole.

## Step 3 — Close out

- Every box checked, or an explicit Notes entry saying what was dropped and why.
- `status: complete`, `updated:` set to today.
- `agent_value:` set honestly — `3` only if a future session would get this wrong without
  reading the doc.
- `key_files:` filled in with what actually changed.
- Update `CLAUDE.md` if the feature changed a convention, a scope boundary, or a rejected idea.

Then report: what shipped, what deferred, which files changed.

## Rules

1. **The doc is the state.** If it disagrees with reality, the doc is wrong — fix it.
2. **Never move the doc.** Status lives in frontmatter.
3. **Notes is not optional.** A feature that ships with an empty Notes section either had no
   surprises (rare) or lost them (common).
4. **Do not build the index machinery** — categories, generated READMEs, link checkers. The
   frontmatter is already machine-readable; add tooling when volume demands it, not before.
