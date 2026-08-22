"""Highlight — recognition for tinting only. See [[highlight]].

The properties worth defending: the text is never altered (marks are offsets
beside it), marks are sorted and never overlap, a line matching nothing yields
no marks, and every rule is shape — no severity vocabulary anywhere.
"""

import time

from cli.highlight import marks, spans

LINE = "2026-08-22T14:03:11 [jam-pr-report] fetched https://api.github.com/repos rows=14"


def role_of(text, snippet):
    got = marks(text)
    start = text.index(snippet)
    for s, e, role in got:
        if s <= start and text.index(snippet) + len(snippet) <= e:
            return role
    return None


# ------------------------------------------------------------------- rules


def test_a_leading_iso_timestamp_is_muted():
    assert role_of(LINE, "2026-08-22T14:03:11") == "tb.muted"


def test_a_timestamp_not_at_line_start_is_left_alone():
    assert marks("at 2026-08-22T14:03:11 it happened") == []


def test_space_separated_and_zoned_stamps_count():
    assert role_of("2026-08-22 14:03:11+02:00 x", "2026-08-22 14:03:11+02:00") == "tb.muted"


def test_a_tag_after_the_timestamp_wears_the_accent():
    assert role_of(LINE, "[jam-pr-report]") == "tb.accent"


def test_a_tag_at_line_start_counts_too():
    assert role_of("[cron] job started", "[cron]") == "tb.accent"


def test_a_bracket_mid_prose_is_prose():
    """The tag rule is positional — recognition, not a search for anything
    bracket-shaped anywhere."""
    assert role_of("saw an [interesting] thing", "[interesting]") is None


def test_a_url_wears_the_path_role_without_its_trailing_punctuation():
    got = marks("see https://example.com/x. next")
    assert got == [(4, len("see https://example.com/x"), "tb.path")]


def test_the_url_inside_line_prose_is_found():
    assert role_of(LINE, "https://api.github.com/repos") == "tb.path"


def test_a_line_matching_nothing_yields_no_marks():
    assert marks("ordinary prose with numbers 42 and words") == []


# -------------------------------------------------------------- properties


def test_marks_are_sorted_and_never_overlap():
    got = marks(LINE)
    assert got == sorted(got)
    for (s1, e1, _), (s2, e2, _) in zip(got, got[1:]):
        assert e1 <= s2
    for s, e, _ in got:
        assert 0 <= s < e <= len(LINE)


def test_spans_join_back_to_exactly_the_text():
    """The one property that makes tinting safe to apply anywhere: the spans
    are the text, byte for byte, whatever matched."""
    for text in (LINE, "", "no matches here", "[t] https://a.b 2026-01-01T00:00:00"):
        assert "".join(chunk for chunk, _ in spans(text)) == text


def test_a_pathological_line_returns_in_bounded_time():
    text = "x" * 200_000
    started = time.monotonic()
    assert marks(text) == []
    assert time.monotonic() - started < 1.0


def test_no_severity_vocabulary_anywhere():
    """A word list is a judgment wearing a regex's clothes. ERROR in prose is
    prose — the Rule branch owns judgments, later, with the operator holding
    the pen."""
    assert marks("ERROR everything is on fire") == []
    assert marks("WARN disk almost full") == []
