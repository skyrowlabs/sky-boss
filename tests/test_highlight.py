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
    assert role_of(LINE, "2026-08-22T14:03:11") == "sb.muted"


def test_a_timestamp_not_at_line_start_is_not_the_muted_one():
    """Round 1 left a mid-line stamp entirely alone; round 2 gives its date
    and time the *number* role, which is the asymmetry that matters: the
    leading stamp is the most repeated and least informative thing on the
    line, so it is dimmed, while a date inside the prose is a fact someone
    wrote down. Same shape, opposite jobs — so what must stay true is only
    that a mid-line stamp is never muted."""
    roles = {role for _, _, role in marks("at 2026-08-22T14:03:11 it happened")}
    assert "sb.muted" not in roles
    assert roles == {"sb.num"}


def test_space_separated_and_zoned_stamps_count():
    assert role_of("2026-08-22 14:03:11+02:00 x", "2026-08-22 14:03:11+02:00") == "sb.muted"


def test_a_tag_after_the_timestamp_wears_the_accent():
    assert role_of(LINE, "[jam-pr-report]") == "sb.accent"


def test_a_tag_at_line_start_counts_too():
    assert role_of("[cron] job started", "[cron]") == "sb.accent"


def test_a_bracket_mid_prose_is_prose():
    """The tag rule is positional — recognition, not a search for anything
    bracket-shaped anywhere."""
    assert role_of("saw an [interesting] thing", "[interesting]") is None


def test_a_url_wears_the_path_role_without_its_trailing_punctuation():
    got = marks("see https://example.com/x. next")
    assert got == [(4, len("see https://example.com/x"), "sb.path")]


def test_the_url_inside_line_prose_is_found():
    assert role_of(LINE, "https://api.github.com/repos") == "sb.path"


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
    `sb data`, whose `_cell` gives a number `sb.num`. A number that looked
    like a number in a table and like prose in a stream would be two palettes
    wearing one name."""
    assert role_of("queued 8 issues", "8") == "sb.num"


def test_an_attached_unit_or_percent_comes_with_the_number():
    for line, token in (
        ("budget 300m, timeout 90m", "300m"),
        ("checks 8% of the bucket", "8%"),
        ("10.2 of 28 days", "10.2"),
    ):
        assert role_of(line, token) == "sb.num", token


def test_a_spaced_word_after_a_number_is_prose_not_a_unit():
    """The rule that was wrong first. Allowing a space before the unit tinted
    `8 issue`, `104 archive` and `50 candidate` — the numeral plus whatever
    English word followed it. Invisible in a unit test written from the
    pattern, unmissable in a rendered log."""
    assert role_of("8 issue(s) queued", "8") == "sb.num"
    assert [text for text, role in _tinted("104 archive tag applications")] == ["104"]


def test_a_digit_inside_an_identifier_is_not_a_number():
    """`7d9d878` is a git SHA. Tinting its leading digit reads as a rendering
    fault, not a highlight — found by running the rules over a real log."""
    assert marks("new commits: 7d9d878 (first run)") == []


def test_an_issue_reference_is_a_number():
    assert role_of("#925 model-health's stage wraps", "#925") == "sb.num"


def test_a_mid_line_date_and_clock_time_are_values():
    assert role_of("the first decay wave on 2026-08-26 will", "2026-08-26") == "sb.num"
    assert role_of("AGENT-FIX 19:00 — budget", "19:00") == "sb.num"


def test_inline_code_takes_the_path_role_rather_than_a_hue_of_its_own():
    """A code span and a path are the same kind of thing — a literal, an
    identifier — and the design system has no third colour to spend. A violet
    was prototyped, looked good, and is exactly how a second palette starts."""
    assert role_of("caps at `MAX_COMMITS = 50` and breaks", "`MAX_COMMITS = 50`") == "sb.path"


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
        assert role_of(line, token) == "sb.path", token


def test_bold_is_a_weight_that_composes_with_a_colour():
    """Not a colour, so it does not compete for the slot: a mark inside an
    emphasised range keeps its role and gains `bold`."""
    line = "**the `report.py:75` cap**"
    roles = {text: role for text, role in _tinted(line)}
    assert roles["`report.py:75`"] == "bold sb.path"
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


def _tinted(line, ruleset=None):
    return [(chunk, role) for chunk, role in spans(line, ruleset) if role]


# ============================================================================
# Round 3 — the operator's own patterns
# ============================================================================


def _ruleset(*rules):
    from cli.highlight import parse_rulesets

    sets, problems = parse_rulesets({"highlight": {"jam": {"rules": list(rules)}}})
    return (sets[0] if sets else None), problems


def test_a_declared_rule_tints_a_word_sb_would_never_judge():
    """Shape is sb's; vocabulary is the operator's. `ESCALATE` means
    everything in one log and nothing in anyone else's."""
    rules, problems = _ruleset({"pattern": r"\bESCALATE\b", "role": "warn"})
    assert problems == []
    line = "the finding was ESCALATE today"
    assert [(t, r) for t, r in _tinted(line, rules)] == [("ESCALATE", "sb.warn")]


def test_a_declared_rule_cannot_repaint_a_timestamp_or_a_tag():
    """Operator rules run last and claim only unclaimed text. Letting a
    declaration win would make every built-in conditional on a file sb does
    not ship, and the first surprising log would be unexplainable."""
    rules, _ = _ruleset({"pattern": r"2026", "role": "fail"}, {"pattern": r"agent", "role": "ok"})
    line = "2026-08-22T05:00:02+00:00 [agent-fix] ok"
    roles = {text: role for text, role in _tinted(line, rules)}
    assert roles["2026-08-22T05:00:02+00:00"] == "sb.muted"
    assert roles["[agent-fix]"] == "sb.accent"
    assert "sb.fail" not in roles.values() and "sb.ok" not in roles.values()


def test_a_role_the_palette_does_not_define_is_refused_by_name():
    """Nothing operator-authored gets near a colour — the rule the whole
    theme rests on does not get an exception for a config file."""
    rules, problems = _ruleset({"pattern": "x", "role": "#ff0000"})
    assert rules is None
    assert "role must be one of" in problems[0] and "accent" in problems[0]


def test_a_pattern_that_does_not_compile_is_skipped_and_named():
    rules, problems = _ruleset(
        {"pattern": "[unterminated", "role": "warn"},
        {"pattern": "fine", "role": "ok"},
    )
    assert "does not compile" in problems[0]
    assert len(rules.rules) == 1  # one bad rule does not cost the others


def test_an_overlong_pattern_is_not_a_pattern():
    _, problems = _ruleset({"pattern": "a" * 500, "role": "warn"})
    assert "longer than" in problems[0]


def test_a_zero_width_pattern_marks_nothing():
    """`\\b` matches everywhere and covers nothing; a mark of no width would
    be a span the renderers have to special-case."""
    rules, _ = _ruleset({"pattern": r"\b", "role": "warn"})
    assert marks("some words here", rules) == []


def test_resolve_names_what_is_declared_when_the_name_is_wrong(tmp_path):
    from cli.highlight import resolve

    (tmp_path / "formats.toml").write_text(
        '[highlight.jam]\nrules = [{ pattern = "x", role = "ok" }]\n'
    )
    found, problem = resolve("jam", home=tmp_path)
    assert found is not None and problem is None

    found, problem = resolve("nope", home=tmp_path)
    assert found is None and "declared: jam" in problem


def test_declared_rules_still_respect_the_cap():
    rules, _ = _ruleset({"pattern": r"a", "role": "warn"})
    from cli.highlight import MAX_MARKS

    assert len(marks("a " * 400, rules)) <= MAX_MARKS


# ============================================================================
# Round 4 — glyphs that mean one thing, and words that are their own colour
# ============================================================================


def test_a_check_is_green_and_a_cross_is_red():
    """Not sb judging a line: `sb data` already renders a true boolean as a
    green ✓ and a false one as a red ✗. One value vocabulary, two surfaces."""
    for glyph in ("✓", "✔", "✅"):
        assert role_of(f"{glyph} ok · 0s", glyph) == "sb.ok", glyph
    for glyph in ("✗", "✖", "❌"):
        assert role_of(f"{glyph} failed", glyph) == "sb.fail", glyph


def test_a_warning_sign_is_warn_even_with_its_variation_selector():
    """`⚠️` is two codepoints — the sign plus U+FE0F. Matching only the first
    would tint half a glyph and leave the selector bare."""
    assert role_of("⚠️  19 diff(s) truncated", "⚠️") == "sb.warn"


def test_a_coloured_circle_shows_its_own_colour():
    assert role_of("status 🔴 down", "🔴") == "sb.fail"
    assert role_of("status 🟢 up", "🟢") == "sb.ok"


def test_a_word_that_names_a_colour_is_shown_in_it():
    """The strongest form of shape-not-judgment: the word denotes the colour.
    There is no inference between "the text says red" and "show it red" — which
    is exactly what separates this from "the text says ERROR, so it is bad"."""
    line = "the light was red, then green, then yellow"
    assert [(t, r) for t, r in _tinted(line)] == [
        ("red", "sb.fail"),
        ("green", "sb.ok"),
        ("yellow", "sb.warn"),
    ]


def test_a_colour_word_inside_another_word_is_not_one():
    assert marks("reported greenery in Greenland") == []


def test_a_glyph_inside_a_code_span_stays_code():
    assert [t for t, _ in _tinted("run `check ✔ thing` now")] == ["`check ✔ thing`"]
