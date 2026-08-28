#!/usr/bin/env python3
"""Thin entry point for ``python -m cli``.

Implementation lives in the sibling modules of this package. The ``sb`` wrapper
is the only caller; it puts the repo root on PYTHONPATH so ``-m cli`` resolves
no matter which directory sky.boss was invoked from.
"""

from cli import cli

if __name__ == "__main__":
    cli(prog_name="sb")
