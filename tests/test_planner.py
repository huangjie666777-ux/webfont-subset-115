from app.planner import collect_codepoints, merge_ranges, plan_fallback, PlanningError, unicode_range_css


def test_dedup_and_ignored_controls():
    cps = collect_codepoints(["ab\ta", "b\n\rc"])  # TAB CR LF ignored
    assert cps == [ord("a"), ord("b"), ord("c")]


def test_no_normalization():
    # U+00EA (single codepoint) vs e + combining circumflex (two) stay distinct
    cps = collect_codepoints(["\u00ea", "e\u0302"])
    assert cps == [0x00EA, ord("e"), 0x0302]


def test_first_font_wins_and_missing_rejected():
    cov = {"A": frozenset({ord("x"), ord("z")}), "B": frozenset({ord("y"), ord("z")})}
    plan = plan_fallback([ord("x"), ord("y"), ord("z")], ["A", "B"], cov)
    assert plan.assignment["A"] == [ord("x"), ord("z")]
    assert plan.assignment["B"] == [ord("y")]
    assert plan.used_font_ids == ["A", "B"]

    try:
        plan_fallback([ord("x"), 0x1234], ["A"], cov)
        assert False
    except PlanningError as exc:
        assert exc.args[0] == [0x1234]


def test_range_merge_and_css():
    assert merge_ranges([1, 2, 3, 5, 7, 8]) == [(1, 3), (5, 5), (7, 8)]
    assert unicode_range_css([0x41, 0x42, 0x44]) == "U+0041-0042, U+0044"
