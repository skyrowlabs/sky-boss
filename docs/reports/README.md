# Reports

Reports are **release-anchored**: each describes a commit range bounded by
release tags, never "everything since this last ran". A window that straddles a
release boundary cannot answer the only question that matters about a finding —
*is this in production right now?*

| Folder                                | Holds                          | Window               | Refresh                |
| ------------------------------------- | ------------------------------ | -------------------- | ---------------------- |
| [`regular/`](regular/README.md)       | In-flight periodic editions    | `<latest tag>..HEAD` | overwritten every run  |
| [`releases/`](releases/README.md)     | Frozen per-release editions    | `<prev tag>..<tag>`  | **never edited**       |
| [`occasional/`](occasional/README.md) | One-time deep dives and sweeps | a point in time      | not a window           |

The window is resolved from one place — `scripts/docs/release_window.py`:

```bash
./dev docs release-window          # the in-flight window as JSON
./dev check reports                # validate every anchor (blocks CI)
./dev docs freeze-release --tag v1.4.0
```

**Never edit anything under `releases/`.** A correction to a shipped release's
report goes in an `## Errata` block on the current in-flight edition, naming the
release it corrects. The full rules are in [`../rules/docs.md`](../rules/docs.md).

**Read `occasional/` before starting a sweep.** Re-running one cold is the most
expensive way to learn what an `ls` would have told you.

---

This file is the folder's **single routing row**: `docs/reports/` is registered in
the index tables by *this* README, and it owns everything below it. Adding a report
means adding it to the right subfolder — not a row in two tables.

That is the shape the routing check wants everywhere. It replaced one row per
edition folder, which was a registry: correct on the day it was written, and one
row short the first time a fourth kind of report exists.
