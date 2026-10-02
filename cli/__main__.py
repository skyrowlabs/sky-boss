#!/usr/bin/env python3
"""Thin entry point for ``python -m cli``. The ``./dev`` wrapper is the only caller."""

from . import cli
from .helpers import absolutize_path_env

if __name__ == "__main__":
    # Before any command spawns anything — see helpers.absolutize_path_env for
    # why a relative PATH entry silently breaks children that chdir.
    absolutize_path_env()
    cli(prog_name="dev")
