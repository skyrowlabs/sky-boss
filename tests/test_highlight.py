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
    the pen.

    **Round 5 made this assertion narrower and, in doing so, stronger.** It
    used to demand that `ERROR` produce nothing at all, which the shout rule
    now breaks: a capitalised word of five characters or more is emphasised.
    That is not the boundary this test exists to hold, and reading it as one
    would have blocked a rule that never judges anything — the shout knows
    only that someone capitalised a word, and bolds `VACUUM` and `PREFLIGHT`
    with exactly the same enthusiasm.

    The property that actually matters, and the one asserted here: **no word
    earns a verdict colour.** `sb.fail` and `sb.warn` are the two roles a
    severity vocabulary would reach for, and no built-in rule hands either to
    a word. Weight carries no verdict — that is the whole argument for
    spending it in round 5 rather than a hue.
    """
    for line in ("ERROR everything is on fire", "WARN disk almost full",
                 "FAILED to reach the host", "CRITICAL outage"):
        roles = {role for _, _, role in marks(line)}
        assert roles <= {"bold"}, line


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
    fault, not a highlight — found by running the rules over a real log.

    Asserts the property rather than an empty list: round 6 dims the brackets
    in `(first run)`, and an `== []` here would have read as a boundary about
    SHAs while actually being a claim about the whole line. The third time this
    file has made that mistake, and the tell is the same each time — an empty
    list passes for reasons the test's name never mentions.
    """
    line = "new commits: 7d9d878 (first run)"
    assert not [m for m in marks(line) if line[m[0] : m[1]].strip("()")]


def test_an_issue_reference_wears_a_ground_of_its_own():
    """Round 6. It was `sb.num` — correct, and indistinguishable from every
    other number on the line, which is what the operator asked it not to be.
    There was no ninth hue to give it: the design system holds four and
    sky.boss spends all four. `sb.ref` is the number's own hue on a wash of
    itself — the same colour, a different object."""
    assert role_of("#925 model-health's stage wraps", "#925") == "sb.ref"


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
    """Shape is sky.boss's; vocabulary is the operator's. `ESCALATE` means
    everything in one log and nothing in anyone else's."""
    rules, problems = _ruleset({"pattern": r"\bESCALATE\b", "role": "warn"})
    assert problems == []
    line = "the finding was ESCALATE today"
    assert [(t, r) for t, r in _tinted(line, rules)] == [("ESCALATE", "bold sb.warn")]
    # The colour is theirs and the weight is the shout's — round 5's central
    # claim, that emphasis composes where a ninth colour would have had to
    # displace one. A colour rule claiming ESCALATE would have locked this
    # declaration out of its own word.


def test_a_declared_rule_cannot_repaint_a_timestamp_or_a_tag():
    """Operator rules run last and claim only unclaimed text. Letting a
    declaration win would make every built-in conditional on a file sky.boss does
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
    """Not sky.boss judging a line: `sb data` already renders a true boolean as a
    green ✓ and a false one as a red ✗. One value vocabulary, two surfaces."""
    for glyph in ("✓", "✔", "✅"):
        assert role_of(f"{glyph} ok · 0s", glyph) == "bold sb.ok", glyph
    for glyph in ("✗", "✖", "❌"):
        assert role_of(f"{glyph} failed", glyph) == "bold sb.fail", glyph


def test_a_warning_sign_is_warn_even_with_its_variation_selector():
    """`⚠️` is two codepoints — the sign plus U+FE0F. Matching only the first
    would tint half a glyph and leave the selector bare."""
    assert role_of("⚠️  19 diff(s) truncated", "⚠️") == "bold sb.warn"


def test_a_coloured_circle_shows_its_own_colour():
    assert role_of("status 🔴 down", "🔴") == "bold sb.fail"
    assert role_of("status 🟢 up", "🟢") == "bold sb.ok"


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


# ============================================================================
# Round 5 — weight instead of hue
# ============================================================================


def test_a_thumb_carries_the_verdict_its_direction_names():
    """The operator's own example, and the rule round 5 sharpened for it:
    a glyph qualifies when carrying the verdict is its *whole job*. Strip the
    verdict from 👍 and there is no glyph left."""
    assert role_of("👍 approved by the reviewer", "👍") == "bold sb.ok"
    assert role_of("👎 rejected on sight", "👎") == "bold sb.fail"
    assert role_of("🚨 the grid is down", "🚨") == "bold sb.warn"


def test_a_conventional_glyph_stays_untinted():
    """The other half of the same rule, and the half that keeps this module
    honest. Every one of these appears in the live log it was measured
    against — 🤝 fifteen times, 🌙 ten — and every one means something to
    *that* grid and nothing anywhere else. They denote a handshake, night, a
    party, a rocket; the verdict is a convention laid over them, and reading a
    convention is the judgment this module has refused since round 1.

    The operator is not left without them: a declared pattern may be a glyph.
    """
    for glyph in ("🤝", "🌙", "🎉", "🚀", "🔥", "🙋"):
        assert marks(f"{glyph} handing off") == [], glyph


def test_a_glyph_is_emphasised_as_well_as_coloured():
    """A glyph is one character wide, and hue at one character is the weakest
    signal this palette has. Weight is the strongest and costs no role."""
    for _, _, role in marks("✓ done"):
        assert role.startswith("bold ")


def test_a_screaming_snake_name_is_a_literal_not_a_shout():
    """The corpus split one rule into two: of the all-caps runs in the log this
    was measured against, the majority are configuration identifiers. An
    underscore decides it, and an identifier takes the role round 2 already
    gave a literal — the same one a code span and a filename take."""
    assert role_of("set JAM_KUMA_FORCE_PING to 1", "JAM_KUMA_FORCE_PING") == "sb.path"
    assert role_of("MAX_PER_RUN reached", "MAX_PER_RUN") == "sb.path"


def test_a_shout_carries_weight_and_no_colour():
    """Which is what makes it not a severity vocabulary. The rule knows only
    that someone capitalised a word, and treats VACUUM exactly like ERROR."""
    for word in ("ERROR", "PREFLIGHT", "VACUUM", "DEVELOPMENT"):
        assert marks(f"{word} in the log") == [(0, len(word), "bold")], word


def test_an_acronym_in_prose_is_not_a_shout():
    """Five characters, measured rather than chosen: below it the corpus is
    acronyms in ordinary prose — `PR` 122 times, `CI` 52, plus a bare `I` and
    `A`. Four would buy TODO at the price of HEAD and HTTP."""
    for line in ("the PR is green and CI agrees, I think",
                 "SHA and LFS and API and HEAD"):
        # No *shout* — `green` is still a colour word, which is round 4's and
        # not this rule's. Asserting an empty list here would have tested the
        # wrong thing and passed for the wrong reason.
        assert not any("bold" in role for _, _, role in marks(line)), line


def test_a_declared_colour_composes_with_a_shout():
    """**The round's central claim, in the one case that proves it.** A colour
    rule claiming ERROR would block the operator's own `error → fail` from
    ever reaching it, because a declared rule takes only unclaimed text. As an
    emphasis range it does the opposite: their colour lands first and the
    shout adds weight to it. That is why emphasis was spent here and not hue.
    """
    rules, problems = _ruleset({"pattern": r"\bESCALATE\b", "role": "warn"})
    assert problems == []
    assert marks("ESCALATE now", rules) == [(0, 8, "bold sb.warn")]


def test_overlapping_emphasis_ranges_merge_into_one():
    """Round 4 had one source of range and could skip merging. Round 5 has
    four, and they overlap in the most ordinary line there is. Unmerged, the
    filler emitted two marks for one stretch — which the frontend applies
    dumbly and by construction cannot notice."""
    for line in ("**ERROR**", "# PREFLIGHT ✓ done", "**✓ SHIPPED**", "**a ✗ b** ERROR"):
        got = marks(line)
        assert got == sorted(got), line
        for (_, e1, _), (s2, _, _) in zip(got, got[1:]):
            assert e1 <= s2, line
        assert "".join(text for text, _ in spans(line)) == line, line


def test_marks_for_the_wire_are_in_the_units_a_browser_slices_by():
    """**Python counts code points; JavaScript counts UTF-16 code units.**
    Every mark shipped to the canvas crosses that boundary, and an astral
    character — 🔴, 🟢, 👍 — is one Python character and two JS ones. Without
    conversion `text.slice(start, end)` cut a surrogate pair in half and
    shifted every offset after it on the line.

    Shipped in round 4 and invisible for a week: both sides were internally
    consistent, the suite compared marks to marks and never sliced, and the
    live log's most common glyph (`✅`, U+2705) is inside the BMP and behaves.
    Only drawing it in a real browser showed it. Asserted here the way the
    page does it — by slicing UTF-16 — because comparing offsets is exactly
    the check that missed it.
    """
    from cli.highlight import utf16

    text = "🟢 up  🔴 down 👍"
    wire = utf16(text, marks(text))
    units = text.encode("utf-16-le")
    got = [units[2 * s : 2 * e].decode("utf-16-le") for s, e, _ in wire]
    assert got == ["🟢", "🔴", "👍"]


def test_a_line_with_no_astral_character_is_returned_unchanged():
    """The conversion is identity for almost every line there is, so it costs
    nothing on the common path and cannot introduce a difference there."""
    from cli.highlight import utf16

    text = "2026-08-29 04:15:02 [agent-fix] ✓ 8 done"
    found = marks(text)
    assert utf16(text, found) is found


# ============================================================================
# Round 6 — ground, not hue
# ============================================================================


def test_a_delimiter_dims_and_what_it_wraps_does_not():
    """**The inverse of what was asked, and it is the timestamp's argument
    applied to punctuation.** The ask was for bracketed text in a colour of its
    own; there is no colour of its own to give. `--text-3` is defined by the
    design system as *structure, not reading text*, which is what a delimiter
    is — so dimming the two characters makes what they wrap stand out by taking
    noise away instead of adding it."""
    line = "retry (attempt 3 of 5) after {timeout: 90m}"
    dimmed = [line[s:e] for s, e, role in marks(line) if role == "sb.muted"]
    assert dimmed == ["(", ")", "{", "}"]
    # The contents keep whatever they already were, and nothing else moved.
    assert ("3", "sb.num") in _tinted(line)


def test_a_leading_tag_keeps_its_brackets():
    """The delimiter pass runs last, so a bracket another rule already claimed
    is never re-tagged. A `[job]` tinted whole and then half-dimmed would be
    two rules disagreeing in public."""
    line = "2026-08-29 04:15:02 [agent-fix] starting"
    assert ("[agent-fix]", "sb.accent") in _tinted(line)
    assert "sb.muted" not in {r for _, r in _tinted(line) if _ in ("[", "]")}


def test_a_bracket_inside_a_code_span_is_code():
    """Same ordering, one level in. First match wins and the code span is the
    outer shape."""
    assert _tinted("`(not this)` stays code") == [("`(not this)`", "sb.path")]


def test_an_unbalanced_bracket_is_prose():
    """Three alternatives rather than one character class, so `(foo]` is not a
    pair and a lone bracket in prose is left alone."""
    assert marks("smile :) or (not closed") == []
    assert marks("mismatched (foo] here") == []


# ============================================================================
# Round 6 — the hanging indent a wrapped line uses. See [[wrap]].
# ============================================================================


def test_the_hang_is_the_first_character_after_the_stamp():
    """Not the stamp's end — the first *text* after it. A continuation that
    began in the gap would sit under whitespace rather than under the words."""
    from cli.highlight import hang

    assert hang("2026-08-29 04:15:02 [agent-fix] a finding") == 20
    assert hang("2026-08-29T04:15:02.123Z  double spaced") == 26


def test_a_line_with_no_stamp_hangs_flush():
    """Zero, and a flush wrap is what zero means — the same rule with nothing
    to skip rather than a special case."""
    from cli.highlight import hang

    assert hang("no stamp here at all") == 0
    assert hang("") == 0


def test_an_indent_without_a_stamp_is_not_a_hang():
    """The leading-space skip runs only *behind* a stamp. A line indented for
    its own reasons must not be silently given a hanging indent it never asked
    for — that would be inferring structure from whitespace, which is the one
    thing this surface refuses."""
    from cli.highlight import hang

    assert hang("    indented but no stamp") == 0


def test_the_hang_comes_from_the_matcher_that_dims_the_stamp():
    """The property, not the number. Measuring the stamp a second time — here
    or in the frontend — is the second timestamp matcher the one-rule-set
    design exists to prevent, and it would drift the week it was written."""
    from cli.highlight import hang

    line = "2026-08-29 04:15:02 [agent-fix] starting"
    stamp = next((e for s, e, role in marks(line) if s == 0 and role == "sb.muted"), None)
    assert stamp is not None
    assert hang(line) >= stamp
    assert line[hang(line)] != " "
