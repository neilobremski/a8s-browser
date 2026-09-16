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
