# Conventional Commit Rules

> Applies to every commit in this repository.

## Format

```
<type>(<scope>): <summary in imperative mood, max 72 chars>

- <change 1>
- <change 2>
```

The `conventional-commit-check` hook (commit-msg stage) **rejects any message with more than
one subject line**. That is deliberate: a message with three `feat:` lines in it is three
commits wearing one hat, and the changelog generator will take only the first.

## Rules

1. **ONE subject line** for the entire commit — never repeat the type prefix per file.
2. **Bundle all related files** into that one commit. One logical idea, all of its files.
3. **Imperative mood**: "add", "fix" — not "adds", "fixed", "adding".
4. **No capital** on the first letter of the summary. No trailing period.
5. **Commit without asking; push when the work is complete.** Make the commit as soon as a
   logical unit is done and its checks pass — do not pause to request permission. When the
   whole task is complete and checks pass, push autonomously. Never push half-finished work.
6. **These subjects are the changelog.** Nothing generates one here, so
   `git log <old-tag>..<new-tag> --format='%s'` is what a reader gets.
7. **`docs:` for changes under `docs/**` only** — never `feat:`, which would trigger a
   version bump for a prose edit.

## Types

| Type       | Meaning                     | Version bump |
| ---------- | --------------------------- | ------------ |
| `feat`     | New feature                 | minor        |
| `fix`      | Bug fix                     | patch        |
| `perf`     | Performance improvement     | patch        |
| `refactor` | Restructure, no behaviour   | none         |
| `docs`     | Documentation only          | none         |
| `test`     | Tests only                  | none         |
| `chore`    | Maintenance                 | none         |
| `ci`       | CI/CD config                | none         |
| `build`    | Build system / dependencies | none         |

A breaking change adds `!` after the type/scope **and** a `BREAKING CHANGE:` paragraph in the
body: `feat(api)!: redesign the training endpoints`.

## When to Commit

Commit after each **independent logical idea**, not after finishing everything:

- ✅ New endpoint complete + tested + docs updated
- ✅ Migration applied + models updated + verified
- ❌ Half-finished feature
- ❌ Several unrelated ideas bundled together
- ❌ Before the tests pass

## Branching

- **Base branch: `develop`.** New branches are cut from it and every PR targets it.
- **Never commit directly to `main`** — that is the release branch. It
  moves by merge from `develop`, and releases are tagged on it.
- **Force-push is permitted on your own unreviewed branch** — amending or squashing your own
  in-flight work is how four CI runs become one — but **never** on `develop` or
  `main`, and never from an unattended agent.
