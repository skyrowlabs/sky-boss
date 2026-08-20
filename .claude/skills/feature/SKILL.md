---
name: feature
description: Write, expand, or execute a feature doc in docs/features/. Takes an existing slug (execute mode) or a plain description (expand the doc that already owns it, or write a new spec, then confirm and execute). Use when the user says "implement docs/features/X.md", "work through X", "plan and build X", or describes a feature, a change to one, or a defect worth designing around.
---

# /feature — feature doc driver

**One doc per feature, for the life of the feature.** A doc records one piece of the system, not
one work session. Features change, gain capabilities, and turn out to have defects worth designing
around — all of that expands the doc that already owns the feature. It does not produce a second
doc.

Open work lives at `docs/features/<slug>.md`; a feature with no open work lives at
`docs/features/done/<slug>.md`. `status:` in frontmatter is the truth and **the directory follows
it in both directions** — reopening a completed feature moves its doc back out of `done/`.

Cross-document links are `[[slug]]`, never relative paths. That is what makes moving free, and it
is the rule to defend — jam.sense's 141 dead links came from relative paths, not from moving.

No subagents. This runs in a single session — tackle-box has no database and no test suite
to delegate to, so a multi-agent pipeline would be ceremony.

## Step 0 — Find the doc that already owns this

**Always run this step, including when the argument looks like a brand-new feature.** Adding a
doc that should have been a section is the failure this workflow exists to prevent, and it is only
ever preventable here, before anything is written.

```bash
ls docs/features/ docs/features/done/
grep -rl "<keyword>" docs/features/
```

Then decide:

- **A slug or path** matching an existing doc → **execute mode**, Step 2.
- **A description of a change, an addition, or a defect in something that already has a doc** →
  **expand mode**, Step 1b. This is the common case and the default when it is close.
- **A description of a genuinely new subsystem** — a new command group, a new substrate, a
  boundary nothing currently owns → **write mode**, Step 1a.

The test for a new doc is not "is this new work." It is **"would a reader looking for this think
to open a different file."** A fix to the surface is surface work however novel its cause. When
unsure, expand: a doc that grew a section splits easily later, whereas four docs that should have
been one require reading all four to discover it.

If the answer is not obvious after Step 0, say which doc you propose to expand and why, and let
the user redirect before you write.

## Step 1a — Write a new spec (write mode)

Copy `docs/features/_template.md` to `docs/features/<slug>.md` and fill it in.

Spend the effort on **Why** and **Shape**, especially the *"Does not do"* line — scope boundaries
are cheap to write now and expensive to reconstruct later. Break the work into phases that are
each independently commitable and leave the repo working.

Set `status: draft`. **Show the user the spec and confirm before executing.**

## Step 1b — Expand an existing doc (expand mode)

Do not restart the doc and do not rewrite its history.

1. If it is in `done/`, `git mv` it back to `docs/features/` and set `status: active`.
2. Leave every shipped phase and its checked boxes exactly as they are.
3. Append a new round below them, headed with what it is and when:

   ```markdown
   ### Round 2 — stop the surface freezing (2026-08-20)

   - [ ] task
   ```

4. Extend **Why** and **Shape** in place where the new work changes what they claim. If a decision
   is being reversed, **edit the decision and record the reversal in Notes with its original
   reasoning intact.** A superseded argument left visible is the most useful thing in one of these
   files; deleting it is how a doc loses the ability to stop someone repeating the mistake.
5. Add to the *"Does not do"* list if the round draws a new boundary.
6. Bump `updated:`. Never touch `created:`.

Then show the user the new round and confirm before executing.

## Step 2 — Execute

1. Read the whole doc — every round, not just the new one. The earlier rounds are why the code
   looks the way it does.
2. Build a task list mirroring the open phases so progress is visible.
3. Set `status: active` and update `updated:`.
4. Work one phase at a time. After each phase:
   - Check off its `- [ ]` boxes **in the doc**.
   - Commit that phase.
   - Append anything surprising to **Notes** while it is still fresh.

Check the boxes as you go, not at the end. A session that dies mid-feature must be resumable by
reading the doc alone — that is the entire point of the format.

If a phase is blocked with no path forward, stop, set `status: draft` with a Notes entry
explaining the block, and surface it. Do not mark a feature complete around a hole.

## Step 3 — Close out

- Every box in this round checked, or an explicit Notes entry saying what was dropped and why.
- A dated **Notes** entry for the round. Not optional.
- `status: complete`, `updated:` set to today.
- `agent_value:` re-judged for the doc as it now stands. It generally rises across rounds — a doc
  covering three rounds of a system is more load-bearing than one covering its first.
- `key_files:` extended with what this round actually changed.
- Update `CLAUDE.md` if the round changed a convention, a scope boundary, or a rejected idea.
- `git mv docs/features/<slug>.md docs/features/done/<slug>.md`, now that nothing is open. Then
  `grep -rn "<slug>"` and fix any *path* reference in prose or a code comment. `[[slug]]` links
  need no change; that is the point of them.

Then report: what shipped, what deferred, which files changed.

## Rules

1. **The doc is the state.** If it disagrees with reality, the doc is wrong — fix it.
2. **Expand before you add.** A new doc is for a subsystem nothing currently owns, not for a new
   piece of work. Step 0 is not skippable.
3. **Notes accretes, never rewrites.** One dated entry per round. A feature that ships a round
   with no Notes entry either had no surprises (rare) or lost them (common).
4. **The directory tracks `status:` both ways.** Into `done/` at close-out, back out on reopening.
   Links are `[[slug]]`, so the move breaks nothing inside a doc; fix path references in code
   comments in the same commit, and prefer writing new ones as slugs so they never break again.
5. **Do not build the index machinery** — categories, generated READMEs, link checkers. The
   frontmatter is already machine-readable; add tooling when volume demands it, not before.
