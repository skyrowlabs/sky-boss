# JavaScript / TypeScript Rules

Applies to all `**/*.{js,mjs,cjs,ts,tsx}` outside `node_modules/`.

## The Blocking Set

```bash
npm run lint:check      # ESLint, whole-tree, with the warning ratchet
npm run format:check    # Prettier
npm run typecheck       # tsc --noEmit (TypeScript projects)
```

## The ESLint Ratchet

ESLint runs with `--max-warnings=<baseline>` rather than `0`. A greenfield project starts at
`0` and stays there; a project adopting lint mid-life starts at its current count and may
only go **down**. The baseline lives in `package.json`'s `lint:check` script and is the
number a commit must not exceed.

Because `--max-warnings` counts every linted file, the gate is **whole-tree** and cannot be
apportioned per file. The pre-commit hook therefore uses `pass_filenames: false`, and its
`files:` pattern decides only *whether* to run — so a docs-only or backend-only commit
matches nothing and pays nothing.

Never raise the baseline to make a commit pass. Fix the warning, or `// eslint-disable-next-line`
it with a written reason on the line above — a suppression a reader can evaluate is worth
more than a number nobody can interpret.

## Formatting Is Not Negotiable, and Not Manual

Prettier owns formatting; ESLint owns correctness. Never hand-format to satisfy a linter, and
never add a stylistic ESLint rule that Prettier already decides — the two will disagree and
the loser is whoever runs them in the wrong order.

## Module Rules

- No default exports from shared modules — a renamed default import is invisible in review.
- No side effects at import time in a module that anything else imports. Export a function.
- `console.log` is for debugging, never for shipped code paths. Use the project logger.
