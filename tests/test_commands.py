import commands
import plc


def _stub_browser(monkeypatch, tmp_path, **overrides):
    monkeypatch.setenv("A8S_BROWSER_HOME", str(tmp_path))
    monkeypatch.setattr(commands.session, "ensure_running", lambda seat: None)
    monkeypatch.setattr(commands.session, "current_url", lambda seat: "https://example.com/")
    monkeypatch.setattr(commands.session, "snapshot", lambda seat: "- button 'Sign in'")
    monkeypatch.setattr(plc, "run", lambda *a, **k: "### Result\nok\n")
    for name, value in overrides.items():
        monkeypatch.setattr(commands.session, name, value)


def test_comments_blanks_and_attachment_lines_are_not_commands():
    body = "# a comment\n\nurl\nATTACHED FILE: p0o.zip\ngo https://example.com\n"
    assert commands.script_lines(body) == ["url", "go https://example.com"]


def test_a_run_stops_at_the_first_failure(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "url\nbogus thing\nurl\n")
    assert not run.ok
    assert [step["command"] for step in run.steps] == ["url", "bogus thing"]
    assert "unknown command: bogus" in run.error


def test_a_failure_attaches_the_page_it_died_on(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "bogus\n")
    assert len(run.files) == 1
    assert open(run.files[0]).read() == "- button 'Sign in'"


def test_eval_is_refused_unless_the_seat_opted_in(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "eval 1 + 1")
    assert not run.ok
    assert "A8S_BROWSER_ALLOW_EVAL" in run.error


def test_eval_runs_once_the_seat_opts_in(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(plc, "evaluate", lambda seat, expression, timeout=30: "2")
    run = commands.run_script("seat", "eval 1 + 1", allow_eval=True)
    assert run.ok
    assert run.steps[0]["output"] == "2"


def test_go_refuses_anything_that_is_not_a_url(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "go example.com")
    assert not run.ok
    assert "full http(s) URL" in run.error


def test_missing_arguments_report_usage(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "fill username")
    assert "usage: fill" in run.error


def test_an_unbalanced_quote_is_a_parse_error_not_a_crash(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "fill 'username")
    assert "unparseable" in run.error


def test_shot_attaches_the_screenshot(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(plc, "screenshot", lambda seat, path, timeout=60: _touch(path))
    run = commands.run_script("seat", "shot")
    assert run.ok
    assert run.files and run.files[0].endswith("-screen.png")


def test_long_waits_are_capped(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    slept = []
    monkeypatch.setattr(commands.time, "sleep", slept.append)
    commands.run_script("seat", "wait 9000")
    assert slept == [9.0]


def _touch(path):
    open(path, "w").close()
    return path
