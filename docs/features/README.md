# Feature docs

One doc per feature, for the life of that feature. Each one carries a piece of tackle-box from
its first sentence to whatever state it is in now — why it exists, what was decided, what was
deliberately refused, and every round of work since.

*(This file is orientation, not a feature. It has no frontmatter and the `/feature` skill ignores
it, along with `_template.md`.)*

## Where a doc lives

```
docs/features/          open work — draft or active
docs/features/done/     features with nothing open
```

`status:` in the frontmatter is the truth; the directory follows it. **Both ways** — reopening a
completed feature moves its doc back out of `done/`, which is a normal event rather than a rare
one.

So `ls docs/features/` answers "what is in flight", and that is the question this directory gets
asked most. The table below answers the rest.

## The docs

**Generated from frontmatter — do not edit the table by hand.** `tests/test_features_index.py`
rebuilds it and fails when this file disagrees, so it cannot quietly go stale. To update it after
adding, moving, or closing a doc:

```bash
TB_WRITE_DOC_INDEX=1 .venv/bin/python -m pytest -k features_index
```

Only the block between the markers is generated. Everything else on this page is prose.

<!-- index:start -->

### Open — 2

| Doc | Status | Value | What it covers |
|---|---|---|---|
| [operator-home](operator-home.md) | active | 3 | The product and the operator's content, separated |
| [locations](locations.md) | draft | 3 | Key locations — a registry and a two-way channel |

### Done — 8

| Doc | Status | Value | What it covers |
|---|---|---|---|
| [command-taxonomy](done/command-taxonomy.md) | complete | 3 | Command taxonomy — grouping by mood |
| [jobs](done/jobs.md) | complete | 3 | Job management — tb auto |
| [output-contract](done/output-contract.md) | complete | 3 | Uniform output contract |
| [surface-concepts](done/surface-concepts.md) | complete | 3 | The idle state as a place, and the envelope without a second trip |
| [surface-panes](done/surface-panes.md) | complete | 3 | Panes, progressive disclosure and watched conditions |
| [tui](done/tui.md) | complete | 3 | tb tui — a persistent surface over the envelope |
| [rich-output](done/rich-output.md) | complete | 2 | Rich human rendering |
| [surface-design](done/surface-design.md) | complete | 2 | Skyrow palette and the REPL region |

<!-- index:end -->

*Value* is `agent_value` — **3** read it before changing this area, **2** read it when something
surprises you, **1** historical.

The links above are the only relative doc paths in the repo, and they are safe precisely because
nothing maintains them by hand: a doc moving into `done/` fails the test rather than leaving a
dead link. Inside the docs themselves, links stay `[[slug]]`.

## The rule that matters most

**Expand the existing doc. Do not add a new one.**

A doc records one piece of the system, not one work session. A change, a new capability, a defect
worth designing around — all of that is a new *round* inside the doc that already owns the
feature.

The failure this prevents is not long docs. It is a directory where four files describe one thing
and none of them is the one to read. That is where the surface was heading — `tui.md`,
`surface-panes.md`, `surface-concepts.md`, `surface-design.md` — before a single line about it had
been revised.

The test for a new doc is not *is this new work.* It is **would a reader looking for this think to
open a different file.** A fix to the surface is surface work however novel its cause. A new doc
is for a subsystem nothing currently owns: a new command group, a new substrate, a boundary with
no home. **When unsure, expand** — a doc that grew a section splits easily later, whereas four
docs that should have been one require reading all four to discover it.

## Rounds

Shipped phases keep their checked boxes forever. New work is appended below them under a dated
heading:

```markdown
### Round 1 — build the surface (2026-08-19)

#### Phase 1 — capture and dispatch, headless

- [x] task

### Round 2 — stop the surface freezing (2026-08-20)

- [ ] task
```

Reading a doc top to bottom therefore reads chronologically, and the earlier rounds are why the
code looks the way it does.

## Frontmatter

```yaml
slug: tui                 # matches the filename; what [[links]] resolve to
title: ...                # short human title
status: draft             # draft → active → complete; the directory follows it
created: 2026-08-19       # never changes
updated: 2026-08-20       # bumped every round
agent_value: 3            # 1–3, re-judged at each close-out
key_files: []             # what actually changed, with inline why-comments
```

**`agent_value` is the field to read first.** It says whether a future session needs this doc
before touching the system:

| | meaning |
|---|---|
| **3** | Load-bearing. Read it before changing this area — it will otherwise be got wrong. |
| **2** | Useful debugging context. Read it when something here surprises you. |
| **1** | Historical. It happened; nothing depends on knowing why. |

It generally rises across rounds. A doc covering three rounds of a system is more load-bearing
than one covering its first.

## Links

Cross-document links are `[[slug]]`, **never a relative path.**

This is the constraint everything else rests on. The sibling project (jam.sense) files completed
specs into a second directory and its `git mv` broke 141 links — 128 of them generated by that
exact step. That breakage was a property of relative-path links, not of moving: a slug is
position-independent, so the same reorganisation here touched no link inside any doc.

The same applies outside this directory. **Reference a feature doc by slug in code comments too**
— `see the output-contract feature doc`, not a path. A path breaks the moment that feature
reopens.

## Sections

`_template.md` is the skeleton: **Why** · **Shape** (including an explicit *"Does not do"*) ·
**Phases** · **Notes**.

Two of those carry most of the weight.

***"Does not do"*** is the scope boundary, written before any code exists. It is cheap now and
expensive to reconstruct once an implementation has blurred it. It is also where a deliberately
rejected idea goes, so nobody re-proposes it.

**Notes accretes and is never rewritten** — one dated entry per round, filled in *as the work
happens*, not at the end. Reasoning that a later round overturned stays on the page with the
reversal recorded beside it. A superseded argument left visible is the single most useful thing in
one of these files; deleting it is how a doc loses the ability to stop someone making the same
mistake again. A dead session must be resumable from the doc alone.

## Finding something

The index answers most of it. For the rest:

```bash
grep -rl "lane" docs/features/            # which doc owns a concept
grep -rn "^agent_value: 3" docs/features/ # what to read before changing anything
```

**Do not add a second index** — no categories, no JSON, no per-status pages. This one exists
because sixteen docs across two directories stopped being answerable with `ls`, and it is one
generated table checked by one test. The sibling project got here by a different route and now
carries a 1,100-line docs module, three JSON indexes and a CI validator.

The workflow itself is in `CLAUDE.md` § Feature workflow, and `.claude/skills/feature/SKILL.md`
drives it.
