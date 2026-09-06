# Contributing

## The short version

```bash
git switch -c fix/<slug> develop
# ...work...
./dev check pre-push
git commit                       # conventional; the hook enforces it
gh pr create --draft --base develop
# ...iterate in draft; a draft runs the cheap gate job alone...
gh pr ready <n>                  # once, when you believe it is green
```

## Branches

| Branch                | Role                                                  |
| --------------------- | ----------------------------------------------------- |
| `develop`     | Integration. Cut branches from it; PRs target it.     |
| `main`  | Release. Release Please owns it. Never commit direct. |

Force-push is fine on your own unreviewed branch — squashing your own in-flight
work is how four CI runs become one. Never on either branch above.

## Commits

One logical idea per commit, all of its files bundled in. One subject line.
See [`docs/rules/commits.md`](../docs/rules/commits.md); the commit-msg
hook enforces the format.

## Why drafts

A `synchronize` event on a **ready** PR re-runs everything that PR earns. Open
as a draft, push freely, flip to ready once. Nothing is un-gated by this —
GitHub blocks merging a draft, and `ready_for_review` runs the full set before
it can merge.

## Docs are part of the change

Decide in planning which docs a change invalidates, and update them in the same
PR. A finished plan **moves** from `docs/TODO/` to `docs/implementations/` —
`dev docs file <slug> --category <category>` does the move and every
regeneration. Then `dev check doc-refs` and `dev check doc-links`:
**repoint, never delete.**
