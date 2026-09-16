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


def test_close_escalates_to_sigkill_for_a_wedged_browser(monkeypatch, tmp_path):
    """A browser that shrugs off SIGTERM (the stuck-dock-icon case) still dies."""
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    monkeypatch.setattr(session.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(session.plc, "is_open", lambda seat: False)
    monkeypatch.setattr(session, "_main_pids", lambda seat: ["11"])
    monkeypatch.setattr(session, "_profile_pids", lambda seat: ["11", "12"])
    monkeypatch.setattr(session, "_daemon_pids", lambda seat: ["99"])
    monkeypatch.setattr(session, "cdp_base", lambda seat: None)
    monkeypatch.setattr(session.time, "sleep", lambda s: None)
    killed = []
    monkeypatch.setattr(session, "_signal", lambda pid, sig: killed.append((pid, sig)))
    session.close_browser("seat")
    import signal
    assert ( "11", signal.SIGTERM) in killed
    assert ("11", signal.SIGKILL) in killed
    assert ("12", signal.SIGKILL) in killed
    assert ("99", signal.SIGTERM) in killed


def test_open_cleans_up_chrome_when_attach_fails(monkeypatch, tmp_path):
    """A failed attach must not leave a browser nobody can drive running."""
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    monkeypatch.setattr(session.plc, "is_open", lambda seat: False)
    monkeypatch.setattr(session, "cdp_base", lambda seat: "http://127.0.0.1:9222")
    def failing_run(*a, **k):
        raise session.plc.BrowserError("attach refused")
    monkeypatch.setattr(session.plc, "run", failing_run)
    reaped = []
    monkeypatch.setattr(session, "_terminate_profile", lambda seat: reaped.append(seat))
    try:
        session.open_browser("seat")
    except session.plc.BrowserError:
        pass
    assert reaped == ["seat"]
