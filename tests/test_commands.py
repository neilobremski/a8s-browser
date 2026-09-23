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
    body = "# a comment\n\nurl\nATTACHED FILE: notes.zip\ngo https://example.com\n"
    assert commands.script_commands(body) == [
        ("url", None),
        ("go https://example.com", None),
    ]


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


def test_run_code_is_refused_unless_the_seat_opted_in(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        plc, "run_code",
        lambda *a, **k: pytest_fail("run-code reached playwright without the opt-in"),
    )
    run = commands.run_script("seat", "run-code <<END\nreturn 1;\nEND\n")
    assert not run.ok
    assert "A8S_BROWSER_ALLOW_EVAL" in run.error


def test_run_code_reaches_playwright_once_the_seat_opts_in(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch, "### Result\nclicked\n")
    run = commands.run_script("seat", "run-code <<END\nreturn 'clicked';\nEND\n", allow_eval=True)
    assert run.ok
    assert bodies == ["return 'clicked';"]
    assert run.steps[0]["output"] == "clicked"


def test_run_code_without_a_block_takes_the_rest_of_the_line(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch)
    run = commands.run_script("seat", "run-code return page.url(); // it's here\n", allow_eval=True)
    assert run.ok
    assert bodies == ["return page.url(); // it's here"]


def test_a_block_is_taken_verbatim(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch)
    script = (
        "run-code <<END\n"
        "# this is code, not a comment\n"
        "\n"
        "  const menu = page.locator('button').first();\n"
        "go https://example.com/not-a-command\n"
        "  await menu.click();\n"
        "END\n"
        "url\n"
    )
    run = commands.run_script("seat", script, allow_eval=True)
    assert run.ok
    assert bodies == [
        "# this is code, not a comment\n"
        "\n"
        "  const menu = page.locator('button').first();\n"
        "go https://example.com/not-a-command\n"
        "  await menu.click();"
    ]
    assert [step["command"] for step in run.steps] == ["run-code", "url"]


def test_only_a_whole_line_marker_closes_a_block(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch)
    script = (
        "run-code <<END\n"
        "ENDING;\n"
        "// the setup ends here: END\n"
        "  END\n"
        "url\n"
    )
    run = commands.run_script("seat", script, allow_eval=True)
    assert run.ok
    assert bodies == ["ENDING;\n// the setup ends here: END"]
    assert [step["command"] for step in run.steps] == ["run-code", "url"]


def test_a_marker_inside_a_longer_line_does_not_close_a_block(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch)
    script = (
        "run-code <<END\n"
        "await page.getByText('END').click();\n"
        "return 'after the word END';\n"
        "END\n"
    )
    run = commands.run_script("seat", script, allow_eval=True)
    assert run.ok
    assert bodies == ["await page.getByText('END').click();\nreturn 'after the word END';"]


def test_two_blocks_in_one_script_keep_their_own_markers(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    bodies = _capture_code(monkeypatch)
    script = (
        "run-code <<ONE\n"
        "return 'first';\n"
        "ONE\n"
        "run-code <<TWO\n"
        "ONE\n"
        "return 'second';\n"
        "TWO\n"
    )
    run = commands.run_script("seat", script, allow_eval=True)
    assert run.ok
    assert bodies == ["return 'first';", "ONE\nreturn 'second';"]


def test_an_unterminated_block_names_the_marker_and_runs_nothing(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        plc, "run_code", lambda *a, **k: pytest_fail("a truncated body reached playwright")
    )
    run = commands.run_script("seat", "url\nrun-code <<END\nreturn 1;\n", allow_eval=True)
    assert not run.ok
    assert "unterminated <<END" in run.error
    assert [step["command"] for step in run.steps] == ["run-code <<END"]


def test_a_block_feeds_any_verb_that_takes_the_rest_of_the_line(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(plc, "run", lambda *a, **k: calls.append(a) or "### Result\nok\n")
    run = commands.run_script("seat", "type <<TEXT\nline one\n  line two\nTEXT\n")
    assert run.ok
    assert calls[0] == ("seat", "type", "line one\n  line two")


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


def test_console_attaches_the_log_and_echoes_it(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        plc, "run",
        lambda *a, **k: "### Result\nTotal messages: 1\n\n[ERROR] boom @ :0\n",
    )
    run = commands.run_script("seat", "console")
    assert run.ok
    assert run.files and run.files[0].endswith("-console.log")
    assert "[ERROR] boom" in open(run.files[0]).read()
    assert "[ERROR] boom" in run.steps[0]["output"]


def test_console_passes_a_minimum_level_through(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(plc, "run", lambda *a, **k: calls.append(a) or "### Result\nok\n")
    run = commands.run_script("seat", "console warning")
    assert run.ok
    assert calls[0] == ("seat", "console", "warning")


def test_video_records_a_round_trip(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    calls = []

    def fake_run(seat, *args, **kwargs):
        calls.append(args)
        if args[0] == "video-stop":
            with open(commands.session.video_state("seat")["path"], "w") as handle:
                handle.write("webm")
        return "### Result\nok\n"

    monkeypatch.setattr(plc, "run", fake_run)
    run = commands.run_script("seat", "video-start trip\nvideo-chapter leg one\nvideo-stop\n")
    assert run.ok
    assert calls[0][0] == "video-start" and calls[0][1].endswith("-trip.webm")
    assert calls[1] == ("video-chapter", "leg one")
    assert calls[2] == ("video-stop",)
    assert run.files and run.files[0].endswith("-trip.webm")
    assert commands.session.video_state("seat") is None


def test_video_start_refuses_a_second_recording(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    commands.session.save_video_state(
        "seat", {"path": "/tmp/active.webm", "started_at": 0, "chapters": 0}
    )
    run = commands.run_script("seat", "video-start")
    assert not run.ok
    assert "already recording" in run.error


def test_video_stop_without_a_recording_is_an_error(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "video-stop")
    assert not run.ok
    assert "no recording in progress" in run.error


def test_video_stop_rejects_an_empty_recording(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    empty = str(tmp_path / "empty.webm")
    _touch(empty)
    commands.session.save_video_state(
        "seat", {"path": empty, "started_at": 0, "chapters": 0}
    )
    monkeypatch.setattr(plc, "run", lambda *a, **k: "### Result\nok\n")
    run = commands.run_script("seat", "video-stop")
    assert not run.ok
    assert "is empty" in run.error
    assert commands.session.video_state("seat") is None


def test_video_stop_does_not_open_the_browser(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        commands.session, "ensure_running",
        lambda seat: pytest_fail("video-stop opened the browser"),
    )
    run = commands.run_script("seat", "video-stop")
    assert not run.ok
    assert "no recording in progress" in run.error


def pytest_fail(message):
    raise AssertionError(message)


def _capture_code(monkeypatch, output="### Result\nok\n"):
    """Record every body handed to plc.run_code, and answer with `output`."""
    bodies = []

    def fake_run_code(seat, body, timeout=60):
        bodies.append(body)
        return output

    monkeypatch.setattr(plc, "run_code", fake_run_code)
    return bodies


def _touch(path):
    open(path, "w").close()
    return path
