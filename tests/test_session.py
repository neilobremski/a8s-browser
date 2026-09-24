import json

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


class FakeSeat:
    """A seat's Chrome as the plc layer sees it: one driven page, maybe in a window."""

    def __init__(self, monkeypatch, url, window_state="normal", visibility="visible"):
        self.url = url
        self.window_state = window_state
        self.visibility = visibility
        self.calls = []
        monkeypatch.setattr(session.plc, "is_open", lambda seat: True)
        monkeypatch.setattr(session.plc, "evaluate", self.evaluate)
        monkeypatch.setattr(session.plc, "run_code", self.run_code)
        monkeypatch.setattr(session.plc, "run", self.run)
        monkeypatch.setattr(session, "close_browser", lambda seat: self.restart("close"))
        monkeypatch.setattr(session, "open_browser", lambda seat: self.restart("open"))

    def restart(self, step):
        self.calls.append(step)
        if step == "open":
            self.url, self.window_state, self.visibility = "about:blank", "normal", "visible"

    def evaluate(self, seat, expression, timeout=30):
        return self.visibility if "visibilityState" in expression else self.url

    def run_code(self, seat, body, timeout=60):
        if "setWindowBounds" in body:
            self.calls.append("unminimise")
            self.window_state, self.visibility = "normal", "visible"
            return "### Result\nundefined"
        if "bringToFront" in body:
            self.calls.append("front")
            self.visibility = "visible"
            return "### Result\nundefined"
        window = "null" if self.window_state is None else "7"
        state = "null" if self.window_state is None else f'\\"{self.window_state}\\"'
        return (
            f'### Result\n"{{\\"url\\":\\"{self.url}\\",\\"visible\\":\\"{self.visibility}\\",'
            f'\\"window\\":{window},\\"state\\":{state}}}"'
        )

    def run(self, seat, *args, timeout=30):
        self.calls.append(" ".join(args))
        if args[0] == "goto":
            self.url = args[1]
        return ""


def test_a_window_behind_other_windows_keeps_its_chrome_and_its_page(monkeypatch):
    """A covered window reads visible under the launch flag, and is left alone."""
    seat = FakeSeat(monkeypatch, "https://example.com/")
    session.ensure_running("seat")
    assert seat.calls == []
    assert seat.url == "https://example.com/"


def test_a_hidden_page_in_a_normal_window_is_brought_forward_not_restarted(monkeypatch):
    """A hidden app's page reads hidden in a normal window; it is not a dead browser."""
    seat = FakeSeat(monkeypatch, "https://example.com/", visibility="hidden")
    session.ensure_running("seat")
    assert seat.calls == ["front"]
    assert seat.url == "https://example.com/"


def test_a_minimised_window_is_restored_not_restarted(monkeypatch):
    seat = FakeSeat(
        monkeypatch, "https://example.com/", window_state="minimized", visibility="hidden"
    )
    session.ensure_running("seat")
    assert seat.calls == ["unminimise"]
    assert seat.url == "https://example.com/"


def test_a_page_no_window_holds_is_restarted_back_onto_its_url(monkeypatch):
    seat = FakeSeat(monkeypatch, "https://example.com/", window_state=None, visibility="hidden")
    session.ensure_running("seat")
    assert seat.calls == ["close", "open", "goto https://example.com/"]
    assert seat.url == "https://example.com/"


def test_a_restart_from_a_blank_page_navigates_nowhere(monkeypatch):
    seat = FakeSeat(monkeypatch, "about:blank", window_state=None, visibility="hidden")
    session.ensure_running("seat")
    assert seat.calls == ["close", "open"]


def test_a_restart_that_cannot_return_names_the_page_it_lost(monkeypatch):
    seat = FakeSeat(monkeypatch, "https://example.com/", window_state=None, visibility="hidden")
    def refuse(seat_name, *args, timeout=30):
        raise session.plc.BrowserError("net::ERR_NAME_NOT_RESOLVED")
    monkeypatch.setattr(session.plc, "run", refuse)
    try:
        session.ensure_running("seat")
    except session.plc.BrowserError as exc:
        assert "https://example.com/" in str(exc)
    else:
        raise AssertionError("a lost page must not pass silently")
    assert seat.calls == ["close", "open"]


def test_a_probe_the_driver_refuses_leaves_the_browser_alone(monkeypatch):
    """An open dialog blocks the driver; that seat is busy, not dead."""
    seat = FakeSeat(monkeypatch, "https://example.com/", visibility="hidden")
    def busy(*a, **k):
        raise session.plc.BrowserError("does not handle the modal state")
    monkeypatch.setattr(session.plc, "run_code", busy)
    monkeypatch.setattr(session.plc, "evaluate", busy)
    session.ensure_running("seat")
    assert seat.calls == []


def test_chrome_launches_with_occluded_windows_kept_visible(monkeypatch, tmp_path):
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    monkeypatch.setenv("A8S_BROWSER_CHROME", "/bin/chrome")
    launched = []
    monkeypatch.setattr(session.subprocess, "Popen", lambda cmd, **k: launched.append(cmd))
    session._launch_chrome("seat")
    assert "--disable-backgrounding-occluded-windows" in launched[0]


def test_every_probe_routes_downloads_into_the_seat(monkeypatch, tmp_path):
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    bodies = []
    monkeypatch.setattr(session.plc, "is_open", lambda seat: True)
    page = {"url": "about:blank", "visible": "visible", "window": 7, "state": "normal"}
    def probe(seat, body, timeout=60):
        bodies.append(body)
        return "### Result\n" + json.dumps(json.dumps(page))
    monkeypatch.setattr(session.plc, "run_code", probe)
    session.ensure_running("seat")
    assert "Browser.setDownloadBehavior" in bodies[0]
    assert f"downloadPath: '{session.downloads_dir('seat')}'" in bodies[0]
    assert session.downloads_dir("seat").startswith(str(tmp_path))


def test_open_routes_downloads_right_after_attaching(monkeypatch, tmp_path):
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    monkeypatch.setattr(session.plc, "is_open", lambda seat: False)
    monkeypatch.setattr(session, "cdp_base", lambda seat: "http://127.0.0.1:9222")
    steps = []
    monkeypatch.setattr(session.plc, "run", lambda seat, *a, **k: steps.append(a[0]))
    monkeypatch.setattr(
        session.plc, "run_code",
        lambda seat, body, timeout=60: steps.append(
            "route" if "setDownloadBehavior" in body else "code"
        ),
    )
    session.open_browser("seat")
    assert steps == ["attach", "route"]
