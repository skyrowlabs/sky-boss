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


def test_a_timestamp_not_at_line_start_is_not_the_muted_one():
    """Round 1 left a mid-line stamp entirely alone; round 2 gives its date
    and time the *number* role, which is the asymmetry that matters: the
    leading stamp is the most repeated and least informative thing on the
    line, so it is dimmed, while a date inside the prose is a fact someone
    wrote down. Same shape, opposite jobs — so what must stay true is only
    that a mid-line stamp is never muted."""
    roles = {role for _, _, role in marks("at 2026-08-22T14:03:11 it happened")}
    assert "tb.muted" not in roles
    assert roles == {"tb.num"}


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
    """Round 1 wrote this with `42` in it, back when a number was nothing to
    tint. Round 2 tints numbers, so the example moved rather than the
    property: a line of plain prose still carries no marks at all, and a
    quiet frame stays byte-identical to one from before any of this."""
    assert marks("ordinary prose with only words in it") == []


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


# ============================================================================
# Round 2 — the shapes an agent's log actually contains
# ============================================================================


def test_a_number_wears_the_role_a_table_cell_gives_it():
    """The governing rule of the round: the value vocabulary is shared with
    `tb data`, whose `_cell` gives a number `tb.num`. A number that looked
    like a number in a table and like prose in a stream would be two palettes
    wearing one name."""
    assert role_of("queued 8 issues", "8") == "tb.num"


def test_an_attached_unit_or_percent_comes_with_the_number():
    for line, token in (
        ("budget 300m, timeout 90m", "300m"),
        ("checks 8% of the bucket", "8%"),
        ("10.2 of 28 days", "10.2"),
    ):
        assert role_of(line, token) == "tb.num", token


def test_a_spaced_word_after_a_number_is_prose_not_a_unit():
    """The rule that was wrong first. Allowing a space before the unit tinted
    `8 issue`, `104 archive` and `50 candidate` — the numeral plus whatever
    English word followed it. Invisible in a unit test written from the
    pattern, unmissable in a rendered log."""
    assert role_of("8 issue(s) queued", "8") == "tb.num"
    assert [text for text, role in _tinted("104 archive tag applications")] == ["104"]


def test_a_digit_inside_an_identifier_is_not_a_number():
    """`7d9d878` is a git SHA. Tinting its leading digit reads as a rendering
    fault, not a highlight — found by running the rules over a real log."""
    assert marks("new commits: 7d9d878 (first run)") == []


def test_an_issue_reference_is_a_number():
    assert role_of("#925 model-health's stage wraps", "#925") == "tb.num"


def test_a_mid_line_date_and_clock_time_are_values():
    assert role_of("the first decay wave on 2026-08-26 will", "2026-08-26") == "tb.num"
    assert role_of("AGENT-FIX 19:00 — budget", "19:00") == "tb.num"


def test_inline_code_takes_the_path_role_rather_than_a_hue_of_its_own():
    """A code span and a path are the same kind of thing — a literal, an
    identifier — and the design system has no third colour to spend. A violet
    was prototyped, looked good, and is exactly how a second palette starts."""
    assert role_of("caps at `MAX_COMMITS = 50` and breaks", "`MAX_COMMITS = 50`") == "tb.path"


def test_a_number_inside_a_code_span_is_claimed_once_by_the_outer_shape():
    assert [text for text, _ in _tinted("caps at `MAX_COMMITS = 50` today")] == [
        "`MAX_COMMITS = 50`"
    ]


def test_paths_keep_their_leading_dot_and_their_line_number():
    for line, token in (
        ("ran .github/scripts/validate-docs.sh and", ".github/scripts/validate-docs.sh"),
        ("bash ./scripts/lint-css-tokens.sh", "./scripts/lint-css-tokens.sh"),
        ("see docs/AGENTIC_AUTOMATION.md:3251 now", "docs/AGENTIC_AUTOMATION.md:3251"),
        ("wrote /home/x/y/z.json today", "/home/x/y/z.json"),
    ):
        assert role_of(line, token) == "tb.path", token


def test_bold_is_a_weight_that_composes_with_a_colour():
    """Not a colour, so it does not compete for the slot: a mark inside an
    emphasised range keeps its role and gains `bold`."""
    line = "**the `report.py:75` cap**"
    roles = {text: role for text, role in _tinted(line)}
    assert roles["`report.py:75`"] == "bold tb.path"
    assert all(role.startswith("bold") for role in roles.values())


def test_the_emphasis_markers_stay_on_screen():
    """Marks tint characters and never alter them. A renderer that hid the
    asterisks would be editing the log, and the canvas's guarantee — the
    payload it appends is the payload the file carried — dies with it."""
    line = "**Zero scope violations** today"
    assert "".join(chunk for chunk, _ in spans(line)) == line
    assert "**" in "".join(text for text, role in _tinted(line) if "bold" in role)


def test_a_heading_is_emphasised_whole():
    assert all("bold" in role for _, role in _tinted("## What the automation did"))


def test_marks_are_capped_so_one_line_cannot_flood_a_frame():
    """Every mark rides to the canvas inside the frame, and round 2 turned
    three rules into ten. The tail is dropped, never the line."""
    from cli.highlight import MAX_MARKS

    line = " ".join(str(n) for n in range(500))
    found = marks(line)
    assert len(found) == MAX_MARKS
    assert "".join(chunk for chunk, _ in spans(line)) == line


def _tinted(line):
    return [(chunk, role) for chunk, role in spans(line) if role]
