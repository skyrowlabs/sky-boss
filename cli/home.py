"""Creating the operator's home.

`TB_HOME` holds what *you* wrote — job definitions — as opposed to this repo,
which holds what the project wrote. A fresh clone has neither the directory nor
anything in it, so something has to make one.

It lives behind `tb run` because it writes. That is not ceremony: a scaffold
that fired automatically from a read command would be a write path with no
ledger entry, which is the single property the whole command taxonomy exists
to protect.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from cli.helpers import PROJECT_ROOT, TB_HOME

TEMPLATES = PROJECT_ROOT / "templates"

# Directory in the home, and the template that seeds it. The template keeps its
# `_template.yaml` name inside the home so the loaders skip it — they already
# ignore a leading underscore, which is what makes a scaffolded home load
# cleanly with no definitions in it yet.
LAYOUT: tuple[tuple[str, str], ...] = (
    ("jobs", "job.yaml"),
)


def init_home(home: Path | None = None) -> dict:
    """Create the home and seed it with templates.

    Refuses an existing home rather than merging into it. Overwriting is the
    one thing that could destroy a job definition, and "it was already there"
    is not enough information to decide what the caller wanted.
    """
    home = home or TB_HOME

    if home.exists() and any(home.iterdir()):
        raise FileExistsError(
            f"{home} already exists and is not empty — refusing to write into it. "
            "Remove it, or point TB_HOME somewhere else."
        )

    created = []
    for directory, template in LAYOUT:
        target = home / directory
        target.mkdir(parents=True, exist_ok=True)
        source = TEMPLATES / template
        if source.exists():
            shutil.copy2(source, target / "_template.yaml")
            created.append(f"{directory}/_template.yaml")
        else:
            created.append(f"{directory}/")

    (home / ".gitignore").write_text(
        "# Your content is worth versioning — `git init` here.\n"
        "# Run state is not: it lives in ~/.local/state/tb/ and appends on every run.\n"
    )
    created.append(".gitignore")
    return {"home": str(home), "created": created}
