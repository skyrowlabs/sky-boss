"""`check_commit_style.py` resolves every range shape `default_range()` can return.

The rule is skeletor's hook; the range walk is ours, and it borrows
`default_range()` from `check_commit_subjects.py`, which is theirs. skeletor
v0.33.0 made that function return `HEAD --not --remotes` for a branch with no
upstream — one string, three argv entries — and split it in its own caller.
Ours passed it whole, so `rev-list` saw one unknown revision and the gate
reported *"could not resolve"* on every first push. Nothing upstream could see
it: a helper's contract changing is invisible to the template, whose callers
move in the same commit.

v0.34.0 made one git argument the released contract, and
`tests/test_commit_range_is_one_argument.py` (theirs) pins it by what `git log`
lists. So the shapes below are v0.34.0's, and the split this file used to hold
in place is gone with the shape that needed it. What stays here is the half
their test cannot see: that *this* consumer, which calls `rev-list` rather than
`log`, resolves each of them.
"""

from __future__ import annotations

import pytest

from scripts.check_commit_style import commits
from scripts.check_commit_subjects import default_range

pytestmark = pytest.mark.unit


# `@{u}..HEAD` and `<boundary>..HEAD` are absent on purpose: both depend on the
# checkout's remotes, CI's differ from a developer's, and a skip here would spend
# the suite's skip budget of zero. The live call below reaches whichever one this
# checkout produces.
@pytest.mark.parametrize("commit_range", ["-1", "HEAD", "HEAD..HEAD"])
def test_every_default_range_shape_resolves(commit_range):
    assert commits(commit_range) is not None, f"`{commit_range}` did not resolve"


def test_the_range_this_checkout_produces_resolves():
    # The real producer against the real consumer, rather than a list of what it
    # returned when this was written.
    commit_range = default_range()
    assert commits(commit_range) is not None, f"`{commit_range}` did not resolve"


def test_a_limit_alone_still_means_head():
    inspected = commits("-1")
    assert inspected is not None and len(inspected) <= 1
