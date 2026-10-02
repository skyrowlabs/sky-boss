---
name: feature
description: Write, expand, or execute a plan in docs/TODO/. Takes an existing slug (execute mode) or a plain description (expand the plan that already owns it, or write a new one, then confirm and execute). Use when the user says "implement X", "work through X", "plan and build X", or describes a feature, a change to one, or a defect worth designing around.
---

# /feature — the plan driver

**One doc per feature, for the life of the feature.** A doc records one piece of the system, not
one work session. Features change, gain capabilities, and turn out to have defects worth designing
around — all of that expands the doc that already owns the feature. It does not produce a second
doc.

Open work lives at `docs/TODO/<slug>.md`; a feature with no open work lives at
`docs/implementations/<category>/<slug>.md`. **The directory is the status** — there is no
frontmatter field that overrides it, and that is deliberate. This workflow used to run on a
`status: draft | active | complete` field, declared to be "the truth", which nothing anywhere
read: one doc sat at `status: done` — a word not in the vocabulary — for a week without a reader.
Both indexes are generated from the directory a plan is in, so the location cannot lie.

Cross-document links are `[[slug]]`, never relative paths. That is what makes moving free, and it
is the rule to defend — it was cashed in on 2026-09-07 when twenty-five docs moved into this
lifecycle and gained a category directory, and not one `[[slug]]` needed editing.

Full rules in `docs/rules/docs.md`, which owns the shelf-status taxonomy, the gates, and the
filing command. This skill owns the *authoring* discipline the rules do not cover.

No subagents. This runs in a single session.

## Step 0 — Find the doc that already owns this

**Always run this step, including when the argument looks like a brand-new feature.** Adding a
doc that should have been a section is the failure this workflow exists to prevent, and it is only
ever preventable here, before anything is written.

```bash
cat docs/todo_index.json | python3 -m json.tool | grep -i "<keyword>"
grep -rl "<keyword>" docs/TODO/ docs/implementations/
```

The two indexes exist for exactly this question — `docs/todo_index.json` answers *"is this already
built but parked?"* and `docs/implementation_index.json` answers *"did we already decide this?"*.
Read the index before the tree; it carries a one-line summary per plan and the tree does not.

Then decide:

- **A slug or path** matching an existing plan → **execute mode**, Step 2.
- **A description of a change, an addition, or a defect in something that already has a plan** →
  **expand mode**, Step 1b. This is the common case and the default when it is close.
- **A description of a genuinely new subsystem** — a new command group, a new substrate, a
  boundary nothing currently owns → **write mode**, Step 1a.

The test for a new doc is not "is this new work." It is **"would a reader looking for this think
to open a different file."** A fix to the surface is surface work however novel its cause. When
unsure, expand: a doc that grew a section splits easily later, whereas four docs that should have
been one require reading all four to discover it.

If the answer is not obvious after Step 0, say which doc you propose to expand and why, and let
the user redirect before you write.

## Step 1a — Write a new plan (write mode)

Copy `docs/TODO/_TEMPLATE.md` to `docs/TODO/<slug>.md` and fill it in.

Set `summary:` even in draft. It is the only thing a reader sees in either index, and a plan that
reaches the archive without one leaves a blank cell in the document whose entire job is telling
somebody which of twenty-five docs to open. Say **what changes**, not what area it touches.

Set `agent_value` (1–3) at the same time; the archive sorts on it and it defaults to `1`, which
means *historical only*.

Spend the effort on **Problem** and **Approach** — or **Why** and **Shape**, which this repo's
older plans use and which the template's four sections map onto — and especially on the explicit
*"Does not do"* / **Dropped, and why**. Scope boundaries are cheap to write now and expensive to
reconstruct later. Break the work into phases that are each independently commitable and leave
the repo working.

**Show the user the plan and confirm before executing.**

## Step 1b — Expand an existing plan (expand mode)

Do not restart the doc and do not rewrite its history.

1. If it is in `docs/implementations/`, `git mv` it back to `docs/TODO/` and set
   `> **Shelf-Status**: in-progress`. The archive is for what is finished, not for what was
   finished once. Then run `dev docs index` so both indexes stop disagreeing with the tree.
2. Leave every shipped phase and its checked boxes exactly as they are.
3. Append a new round below them, headed with what it is and when:

   ```markdown
   ### Round 2 — stop the surface freezing (2026-08-20)

   - [ ] task
   ```

4. Extend the opening sections in place where the new work changes what they claim. If a decision
   is being reversed, **edit the decision and record the reversal in Notes with its original
   reasoning intact.** A superseded argument left visible is the most useful thing in one of these
   files; deleting it is how a doc loses the ability to stop someone repeating the mistake.
5. Add to *"Does not do"* / **Dropped, and why** if the round draws a new boundary.
6. Bump `updated:`. Never touch `created:`.

Then show the user the new round and confirm before executing.

## Step 2 — Execute

1. Read the whole doc — every round, not just the new one. The earlier rounds are why the code
   looks the way it does.
2. Build a task list mirroring the open phases so progress is visible.
3. Set `> **Shelf-Status**: in-progress` and update `updated:`.
4. Work one phase at a time. After each phase:
   - Check off its `- [ ]` boxes **in the doc**.
   - Commit that phase.
   - Append anything surprising to **Notes** while it is still fresh.

Check the boxes as you go, not at the end. A session that dies mid-feature must be resumable by
reading the doc alone — that is the entire point of the format. The boxes are also load-bearing
at filing time: `dev docs file` refuses a plan with unchecked tasks, so a box left ticked-in-fact
and unticked-in-doc blocks the close-out until somebody works out which it was.

If a phase is blocked with no path forward, stop, set `> **Shelf-Status**: blocked` with a
`> **Blocked-On**:` gate and a Notes entry explaining it, and surface it. Do not mark a feature
complete around a hole.

## Step 3 — Close out

- Every box in this round checked, or marked `(~operator)` / `(~deferred)` with a Notes entry
  saying what was dropped and why.
- A dated **Notes** entry for the round. Not optional.
- `updated:` set to today; `summary:` re-read and corrected if the round changed what the plan does.
- `agent_value:` re-judged for the doc as it now stands. It generally rises across rounds — a doc
  covering three rounds of a system is more load-bearing than one covering its first.
- `key_files:` extended with what this round actually changed.
- Update `CLAUDE.md` if the round changed a convention, a scope boundary, or a rejected idea.
- **File it**: `dev docs file <slug> --category <category>`. Never a plain `git mv` — the filing
  does the move, the frontmatter and both regenerations in one step, and refuses on open tasks.
  Existing categories are `commands`, `rendering`, `surfaces`, `projects`, `tooling`; a new one is
  a directory that did not exist, so make it deliberately rather than by typo.
- Then `dev check docs`, which is what catches a *path* reference this move broke. `[[slug]]`
  links need no change; that is the point of them.

Then report: what shipped, what deferred, which files changed.

## Rules

1. **The doc is the state.** If it disagrees with reality, the doc is wrong — fix it.
2. **Expand before you add.** A new doc is for a subsystem nothing currently owns, not for a new
   piece of work. Step 0 is not skippable.
3. **Notes accretes, never rewrites.** One dated entry per round. A feature that ships a round
   with no Notes entry either had no surprises (rare) or lost them (common).
4. **The directory tracks the lifecycle both ways.** Into `docs/implementations/` at close-out,
   back out to `docs/TODO/` on reopening. Links are `[[slug]]`, so the move breaks nothing inside a
   doc; fix path references in code comments in the same commit, and prefer writing new ones as
   slugs so they never break again.
5. **Never hand-edit a generated index.** `docs/TODO/README.md`, `docs/implementations/README.md`
   and both JSON files come from frontmatter. Edit the plan and run `dev docs index`.
   *(This rule replaced "no index machinery yet", which said `ls` was enough for a directory with
   one file in it and that if volume ever demanded an index it should be built as a generated
   block checked by a test. Volume arrived; so did the machinery, already built that way.)*
