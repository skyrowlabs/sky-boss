# CLI Reference

`./dev` is the single entry point for everything you do in this repo. It is a
thin shell wrapper around the `cli/` package.

**The rule that keeps it useful**: adding or changing a script means updating
`cli/` in the same commit. A script nobody can discover is a script nobody runs,
and the second person to need it writes it again.

## Command Groups

| Group          | Purpose                                              |
| -------------- | ---------------------------------------------------- |
| `dev check`  | Every validation gate CI blocks on, runnable locally |
| `dev test`   | Marker-driven suite selection                        |
| `dev docs`   | Index regeneration, plan filing, report windows      |
| `dev bug`    | Capture an out-of-scope defect without widening scope |
| `dev task`   | Capture small work that is not a defect              |

Run `./dev <group> --help` for the current commands — the help is generated
from the code, so it cannot go stale the way this table can.

## Why the Wrapper Is Not Just `python -m cli`

Three environment problems, each documented at the point it is handled in the
wrapper script:

1. **Relative `PATH` entries.** A `PATH=.venv/bin:$PATH` prefix is re-resolved
   against each child process's own cwd, so an interpreter found through it
   breaks every child that chdirs. The wrapper absolutizes `PATH` before
   anything is looked up through it.
2. **`python -m` resolves from `sys.path`, not the script's location.** The
   wrapper exports `PYTHONPATH`, resolving symlinks first, so the CLI works from
   any directory and when symlinked onto `PATH`.
3. **A linked worktree has no venv.** `git worktree add` creates a checkout with
   no `.venv` and nothing creates one; the wrapper borrows the main worktree's.
   Same repository, same requirements — only the installed packages are shared,
   never the code.

## Reproducing CI Exactly

```bash
SB_PYTHON=.venv-ci/bin/python ./dev check pre-push
```

A broken override fails loudly rather than falling back. Silently running the
diverged default interpreter is the exact false negative the override removes.
