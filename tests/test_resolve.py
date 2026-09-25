import pytest

import plc
import resolve


def _page(monkeypatch, verdict):
    monkeypatch.setattr(resolve, "evaluate_json", lambda seat, expression: verdict)


def _verdict(**overrides):
    base = {
        "selectorValid": False,
        "selectorCount": 0,
        "selectorVisibleCount": 0,
        "selectorTarget": "",
        "exact": [],
        "substring": [],
        "candidates": [],
    }
    base.update(overrides)
    return base


def test_a_css_selector_that_matches_is_used_as_given(monkeypatch):
    _page(monkeypatch, _verdict(
        selectorValid=True, selectorCount=1, selectorVisibleCount=1, selectorTarget="#login",
    ))
    assert resolve.click_target("seat", "#login") == "#login"


def test_a_selector_matching_only_hidden_elements_is_an_error(monkeypatch):
    _page(monkeypatch, _verdict(selectorValid=True, selectorCount=2, selectorVisibleCount=0))
    with pytest.raises(plc.BrowserError, match="nothing visible"):
        resolve.click_target("seat", ".hidden")


def test_visible_text_resolves_to_a_selector(monkeypatch):
    _page(monkeypatch, _verdict(
        exact=[{"tag": "button", "text": "Sign in", "selector": "#signin"}],
    ))
    assert resolve.click_target("seat", "Sign in") == "#signin"


def test_substring_is_the_fallback_when_nothing_matches_exactly(monkeypatch):
    _page(monkeypatch, _verdict(
        substring=[{"tag": "button", "text": "Sign in now", "selector": "#signin"}],
    ))
    assert resolve.click_target("seat", "Sign in") == "#signin"


def test_no_match_asks_for_a_snapshot_rather_than_guessing(monkeypatch):
    _page(monkeypatch, _verdict())
    with pytest.raises(plc.BrowserError, match="snap"):
        resolve.click_target("seat", "Sign in")


def test_several_matches_come_back_as_selectors_to_choose_from(monkeypatch):
    _page(monkeypatch, _verdict(exact=[
        {"tag": "button", "text": "Next", "selector": "#a"},
        {"tag": "a", "text": "Next", "selector": "#b"},
    ]))
    with pytest.raises(plc.BrowserError) as raised:
        resolve.click_target("seat", "Next")
    message = str(raised.value)
    assert "2 elements match" in message
    assert "#a" in message and "#b" in message


def test_fill_resolves_by_label(monkeypatch):
    _page(monkeypatch, _verdict(
        exact=[{"tag": "input", "text": "Password", "selector": "#pw"}],
    ))
    assert resolve.fill_target("seat", "Password") == "#pw"


def test_straight_apostrophe_typed_matches_a_curly_one_rendered(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "a", "text": "Mrs. Example\u2019s class", "selector": "#c1"},
        ],
    ))
    assert resolve.click_target("seat", "Mrs. Example's class") == "#c1"


def test_curly_apostrophe_typed_matches_a_straight_one_rendered(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "a", "text": "Mrs. Example's class", "selector": "#c1"},
        ],
    ))
    assert resolve.click_target("seat", "Mrs. Example\u2019s class") == "#c1"


def test_curly_double_quote_typed_matches_a_straight_one_rendered(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "span", "text": 'the "big" one', "selector": "#c2"},
        ],
    ))
    assert resolve.click_target("seat", "the \u201cbig\u201d one") == "#c2"


def test_straight_double_quote_typed_matches_a_curly_one_rendered(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "span", "text": "the \u201cbig\u201d one", "selector": "#c2"},
        ],
    ))
    assert resolve.click_target("seat", 'the "big" one') == "#c2"


def test_no_match_names_the_closest_visible_candidate(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "a", "text": "Mrs. Example's class", "selector": "#c1"},
        ],
    ))
    with pytest.raises(plc.BrowserError) as raised:
        resolve.click_target("seat", "Mrs. Ecksample's class")
    message = str(raised.value)
    assert "nothing visible matching" in message
    assert "closest:" in message
    assert "Mrs. Example's class" in message


def test_exact_match_wins_over_a_normalised_one_when_both_are_visible(monkeypatch):
    _page(monkeypatch, _verdict(
        exact=[{"tag": "a", "text": "Mrs. Example's class", "selector": "#straight"}],
        candidates=[
            {"tag": "a", "text": "Mrs. Example's class", "selector": "#straight"},
            {"tag": "a", "text": "Mrs. Example\u2019s class", "selector": "#curly"},
        ],
    ))
    assert resolve.click_target("seat", "Mrs. Example's class") == "#straight"


# R1 (PR #9 review): a <button> lives in the semantic pool (SEL), not the
# cursor:pointer pool. On a literal miss the old code replaced the whole
# candidate set with the pointer-only pool, so a plain button dropped out of
# normalisation and the near-miss hint entirely, even though it was visible
# the whole time. `candidates` must carry the semantic pool through a pointer
# fallback.


def test_button_in_the_semantic_pool_survives_a_pointer_fallback_straight_typed(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "button", "text": "Owner\u2019s page", "selector": "#target"},
        ],
    ))
    assert resolve.click_target("seat", "Owner's page") == "#target"


def test_button_in_the_semantic_pool_survives_a_pointer_fallback_curly_typed(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "button", "text": "Owner's page", "selector": "#target"},
        ],
    ))
    assert resolve.click_target("seat", "Owner\u2019s page") == "#target"


# R2 (PR #9 review): a fillable control can carry several labels (aria-label,
# label[for], a wrapping <label>, a placeholder). The old code kept only the
# first one in `candidates`, so a query that only matched a later label found
# nothing once literal matching failed. All labels must reach normalisation,
# and matching by more than one of a control's labels must still count as one
# control, not an ambiguous pick.


def test_fill_matches_by_a_later_label_once_normalised_straight_typed(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "input", "text": "Account holder", "selector": "#target"},
            {"tag": "input", "text": "Owner\u2019s name", "selector": "#target"},
        ],
    ))
    assert resolve.fill_target("seat", "Owner's name") == "#target"


def test_fill_matches_by_a_later_label_once_normalised_curly_typed(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "input", "text": "Account holder", "selector": "#target"},
            {"tag": "input", "text": "Owner's name", "selector": "#target"},
        ],
    ))
    assert resolve.fill_target("seat", "Owner\u2019s name") == "#target"


def test_two_labels_matching_the_same_control_is_one_match_not_two(monkeypatch):
    # Both "Owner's name" and "Owner's account" contain "owner", so a
    # substring query against either normalised label resolves the same
    # control \u2014 that must collapse to a single candidate, not read as
    # "2 elements match" for what is in fact one input.
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "input", "text": "Owner's name", "selector": "#target"},
            {"tag": "input", "text": "Owner's account", "selector": "#target"},
        ],
    ))
    assert resolve.fill_target("seat", "owner") == "#target"


def test_normalised_exact_beats_normalised_substring(monkeypatch):
    _page(monkeypatch, _verdict(
        candidates=[
            {"tag": "a", "text": "Owner\u2019s page", "selector": "#exact"},
            {"tag": "a", "text": "Owner\u2019s page and more", "selector": "#sub"},
        ],
    ))
    assert resolve.click_target("seat", "Owner's page") == "#exact"


def test_css_selector_resolution_is_untouched_by_normalisation(monkeypatch):
    _page(monkeypatch, _verdict(
        selectorValid=True, selectorCount=1, selectorVisibleCount=1, selectorTarget="#login",
        candidates=[{"tag": "button", "text": "Owner\u2019s page", "selector": "#other"}],
    ))
    assert resolve.click_target("seat", "#login") == "#login"
