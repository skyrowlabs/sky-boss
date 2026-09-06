# Implementation Workflow

The standard phases for any feature or change. Skip a phase only when it is genuinely empty
— not because the change feels small.

**Numbering restarts in every phase, and these steps are cited as "Phase 4, step 1" if at
all.** They used to run 1–19 straight through the file, which made a step here look like an
`AGENTS.md` **Critical Rule** — those are stable identifiers, cited by number from source
comments and test docstrings across the tree. Two things numbered 11, in two files an agent
reads, produced exactly one wrong cross-reference before anybody noticed. A number here is
positional and renumbers the moment a phase gains a step; a Critical Rule number does not.

## Phase 1 — Planning & Context

1. Read the requirement carefully; restate what "done" means.
2. Identify which layers are affected (API, UI, data, infra, CLI).
3. Load only the docs you need — via `.github/DOCS_INDEX.md`, never all at once.
4. Identify **now** which docs will need updating afterwards. Deciding this at the end is how
   docs rot.

## Phase 2 — Implementation

1. Make focused changes that follow the Critical Rules in `AGENTS.md`.
2. If you added a command: update the `cli/` package in the same commit.
3. If you added a config value: add it to `.env.example` in the same commit.

## Phase 3 — Quality Checks

1. Run the blocking lint set (see `docs/rules/python.md`).
2. Run the type checker whole-project.
3. For a deeper pass, run `/code-review` from the main session.

## Phase 4 — Documentation

1. Update every doc identified in Phase 1.
2. A new `docs/*.md` gets registered in `AGENTS.md` **and** `.github/DOCS_INDEX.md`.

## Phase 5 — Testing

1. `dev test <suite>` — all tests must pass before committing.
2. New behaviour gets new tests, with the right suite marker.
3. Zero failures for core functionality. A known-flaky test is a bug, not a fact of life.

## Phase 6 — Commit

1. Bundle all related files into ONE conventional commit.
2. Commit autonomously. When the whole task is complete and checks pass, push autonomously.

## Phase 7 — Release (when a tag is cut)

1. Release Please opens the release PR from the conventional commits. A human merges it.
2. Cutting a release **closes the report window** — see `docs/rules/docs.md`.
