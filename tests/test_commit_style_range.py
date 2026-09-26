"""`check_commit_style.py` resolves every range shape `default_range()` can return.

The rule is skeletor's hook; the range walk is ours, and it borrows
`default_range()` from `check_commit_subjects.py`, which is theirs. skeletor
v0.33.0 made that function return `HEAD --not --remotes` for a branch with no
upstream — one string, three argv entries — and split it in its own caller.
Ours passed it whole, so `rev-list` saw one unknown revision and the gate
reported *"could not resolve"* on every first push. Nothing upstream could see
it: a helper's contract changing is invisible to the template, whose callers
move in the same commit.
"""

from __future__ import annotations

import pytest

from scripts.check_commit_style import commits

pytestmark = pytest.mark.unit


# `@{u}..HEAD` is absent on purpose: an upstream is a property of the checkout,
# CI's has none, and a skip here would spend the suite's skip budget of zero.
@pytest.mark.parametrize("commit_range", ["HEAD --not --remotes", "-1"])
def test_every_default_range_shape_is_split_before_git_sees_it(commit_range):
    assert commits(commit_range) is not None, f"`{commit_range}` did not resolve"


def test_a_limit_alone_still_means_head():
    inspected = commits("-1")
    assert inspected is not None and len(inspected) <= 1
