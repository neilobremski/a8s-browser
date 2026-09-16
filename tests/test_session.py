import session


def test_each_seat_gets_its_own_profile_and_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    assert session.profile_dir("garmin") != session.profile_dir("work")
    assert session.profile_dir("garmin").startswith(str(tmp_path))
    assert session.artifacts_dir("garmin").startswith(session.seat_home("garmin"))


def test_state_root_is_outside_the_install(monkeypatch):
    monkeypatch.delenv("A8S_BROWSER_HOME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/data")
    assert session.state_root() == "/data/a8s-browser"


def test_cdp_port_is_stable_per_seat_and_differs_between_seats(monkeypatch):
    monkeypatch.delenv("A8S_BROWSER_PORT", raising=False)
    assert session.cdp_port("garmin") == session.cdp_port("garmin")
    assert session.cdp_port("garmin") != session.cdp_port("work")
    assert 9222 <= session.cdp_port("garmin") < 9422


def test_cdp_port_override_wins(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_PORT", "9500")
    assert session.cdp_port("garmin") == 9500
