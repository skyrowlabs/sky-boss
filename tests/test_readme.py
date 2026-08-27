"""The README's examples are executed, not illustrated.

A README that shows a command which no longer works is worse than one with no
examples, because it has already told you the command exists — the same
argument [[canvas]] makes about a palette that cannot drift. Every ```console
block whose lines start with `$ sb ` is run here.

Blocks fenced as ```bash are *illustration*: resident views, `sb ui`, anything
needing a network or a real terminal. They are deliberately not run, and the
fence is the marker rather than a list of exceptions in this file.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"

# `$ sb …` inside a ```console fence. The prompt is what makes a line a command
# rather than the output beneath it.
_CONSOLE = re.compile(r"```console\n(.*?)```", re.S)


def examples() -> list[str]:
    found = []
    for block in _CONSOLE.findall(README.read_text()):
        for line in block.splitlines():
            if line.startswith("$ "):
                found.append(line[2:])
    return found


def test_the_readme_has_examples():
    """If this ever reads zero the extraction broke, and every test below would
    pass by vacuum."""
    assert len(examples()) >= 8


@pytest.mark.parametrize("command", examples(), ids=lambda c: c[:48])
def test_a_readme_example_runs(command, tmp_path):
    """Run it the way a reader would, from a clone, through the wrapper.

    `SB_HOME` is redirected like everywhere else in this suite: an example must
    not depend on what the operator happens to have saved, and must not run
    their commands. The one example that names its own `SB_HOME` keeps it.
    """
    root = README.parent
    # Through a shell, always. The examples contain pipes, shell quoting and an
    # inline `SB_HOME=` prefix, and reconstructing those into an argv would mean
    # testing something adjacent to what the README shows. `sb` resolves off
    # PATH the way a reader's would, pointed at this clone.
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=root,
        timeout=30,
        env={
            "PATH": f"{root}:/usr/bin:/bin",
            "HOME": str(tmp_path),
            "SB_HOME": str(tmp_path / "home"),
            "COLUMNS": "76",
        },
    )

    # `data` on a deliberately failing tool exits 1, and that example says so.
    assert proc.returncode in (0, 1), f"{command}\n{proc.stdout}\n{proc.stderr}"
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "No such command" not in proc.stderr, proc.stderr
    assert "no such option" not in proc.stderr.lower(), proc.stderr
