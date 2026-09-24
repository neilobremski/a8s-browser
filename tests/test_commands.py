import os

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


def test_an_opener_that_also_carries_an_argument_is_refused(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        plc, "run", lambda *a, **k: pytest_fail("a truncated argument reached playwright")
    )
    run = commands.run_script("seat", "type Dear team <<TEXT\nand the rest\nTEXT\n")
    assert not run.ok
    assert run.error == (
        "a line that opens a block cannot also carry an inline argument: "
        "type Dear team <<TEXT"
    )
    assert [step["command"] for step in run.steps] == ["type Dear team <<TEXT"]


def test_run_code_keeps_no_exception_to_the_opener_rule(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    monkeypatch.setattr(
        plc, "run_code", lambda *a, **k: pytest_fail("a truncated body reached playwright")
    )
    run = commands.run_script(
        "seat", "run-code some.js() <<END\nreturn 1;\nEND\n", allow_eval=True
    )
    assert not run.ok
    assert "cannot also carry an inline argument" in run.error
    assert [step["command"] for step in run.steps] == ["run-code some.js() <<END"]


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


def _stub_targets(monkeypatch):
    monkeypatch.setattr(commands.resolve, "click_target", lambda seat, arg: arg)


def _stub_real_argv(monkeypatch, answer=None):
    """A playwright-cli stub that enforces its REAL argv contract.

    A stub that accepts anything only proves this repo builds the argv it meant
    to build. The installed CLI takes exactly one positional for `upload` — its
    help says "one or multiple files" and names the argument "the absolute
    paths", and the parser still rejects two before it opens a browser. Believing
    the help shipped a broken verb, so the contract lives here now.
    """
    seen = []

    def run(seat, *args, **kwargs):
        seen.append(args)
        verb, rest = args[0], list(args[1:])
        if verb == "upload":
            positional = [arg for arg in rest if not arg.startswith("-")]
            if len(positional) != 1:
                raise plc.BrowserError(
                    f"too many arguments: expected 1, received {len(positional)}"
                )
        if verb == "drop":
            if not rest or rest[0].startswith("-"):
                raise plc.BrowserError("drop needs a target")
            flags = rest[1:]
            if any(flags[index] != "--path" for index in range(0, len(flags), 2)):
                raise plc.BrowserError("drop takes files as repeated --path")
        return answer(args) if answer else ""

    monkeypatch.setattr(plc, "run", run)
    return seen


def test_upload_refuses_a_relative_path(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", "upload notes.txt\n")
    assert not run.ok
    assert "not an absolute path" in run.error


def test_upload_refuses_a_file_that_is_not_there(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    run = commands.run_script("seat", f"upload {tmp_path / 'gone.txt'}\n")
    assert not run.ok
    assert "no such file" in run.error


def test_upload_hands_its_one_path_to_playwright(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    seen = _stub_real_argv(monkeypatch)
    one = tmp_path / "a.txt"
    one.write_text("a")
    run = commands.run_script("seat", f"upload {one}\n")
    assert run.ok, run.error
    assert seen == [("upload", str(one))]
    assert run.steps[0]["output"] == "a.txt"


def test_upload_refuses_several_files_and_names_drop(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_real_argv(monkeypatch)
    one, two = tmp_path / "a.txt", tmp_path / "b.txt"
    one.write_text("a")
    two.write_text("b")
    run = commands.run_script("seat", f"upload {one} {two}\n")
    # The chooser is answered once and closes, so a second upload goes nowhere.
    # The refusal has to point at the verb that does take several.
    assert not run.ok
    assert "takes one file" in run.error
    assert "drop" in run.error


def test_upload_never_sends_an_argv_the_real_cli_refuses(monkeypatch, tmp_path):
    """The stub enforces playwright-cli's own argv rules, not this repo's."""
    _stub_browser(monkeypatch, tmp_path)
    _stub_real_argv(monkeypatch)
    one = tmp_path / "a.txt"
    one.write_text("a")
    run = commands.run_script("seat", f"upload {one}\n")
    assert run.ok, run.error
    assert "expected 1" not in (run.error or "")


def test_drop_sends_one_path_flag_per_file(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    seen = _stub_real_argv(monkeypatch)
    one, two = tmp_path / "a.txt", tmp_path / "b.txt"
    one.write_text("a")
    two.write_text("b")
    run = commands.run_script("seat", f"drop div.box {one} {two}\n")
    assert run.ok, run.error
    assert seen == [("drop", "div.box", "--path", str(one), "--path", str(two))]


def test_drop_needs_a_target_and_a_file(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    run = commands.run_script("seat", "drop div.box\n")
    assert not run.ok
    assert "drop <target> <path>" in run.error


def _chrome_saves(seat, name, data, partial=False):
    """What the seat's Chrome does on a download: bytes land in the seat's dir."""
    directory = commands.session.downloads_dir(seat)
    suffix = commands.PARTIAL_DOWNLOAD if partial else ""
    with open(os.path.join(directory, name + suffix), "wb") as handle:
        handle.write(data)


def test_download_attaches_the_file_the_click_saved_into_the_seat(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    def click(seat, *a, **k):
        _chrome_saves(seat, "chart.png", b"\x89PNG bytes")
        return ""
    monkeypatch.setattr(plc, "run", click)

    run = commands.run_script("seat", "download button.save\n")
    assert run.ok, run.error
    assert len(run.files) == 1
    assert run.files[0].startswith(commands.session.artifacts_dir("seat"))
    assert run.files[0].endswith("chart.png")
    assert open(run.files[0], "rb").read() == b"\x89PNG bytes"
    # Moved, not copied: the seat's downloads dir keeps only what nobody asked for.
    assert os.listdir(commands.session.downloads_dir("seat")) == []


def test_download_waits_for_a_partial_file_to_finish(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    directory = commands.session.downloads_dir("seat")
    monkeypatch.setattr(
        plc, "run", lambda seat, *a, **k: _chrome_saves(seat, "late.pdf", b"p", True)
    )
    sleeps = []

    def finish_later(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            partial = os.path.join(directory, "late.pdf" + commands.PARTIAL_DOWNLOAD)
            os.replace(partial, os.path.join(directory, "late.pdf"))

    monkeypatch.setattr(commands.time, "sleep", finish_later)
    run = commands.run_script("seat", "download button.save 5\n")
    assert run.ok, run.error
    assert len(sleeps) == 3
    assert run.files[0].endswith("late.pdf")


def test_download_ignores_files_that_were_already_there(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    _chrome_saves("seat", "old.txt", b"earlier")
    def click(seat, *a, **k):
        _chrome_saves(seat, "new.txt", b"now")
        return ""
    monkeypatch.setattr(plc, "run", click)
    run = commands.run_script("seat", "download button.save\n")
    assert run.ok, run.error
    assert run.files[0].endswith("new.txt")


def test_download_fails_when_nothing_downloads(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    monkeypatch.setattr(plc, "run", lambda seat, *a, **k: "")
    run = commands.run_script("seat", "download button.save 1\n")
    assert not run.ok
    assert "saved no finished file" in run.error
    assert commands.session.downloads_dir("seat") in run.error


def test_download_that_never_finishes_names_the_partial_file(monkeypatch, tmp_path):
    _stub_browser(monkeypatch, tmp_path)
    _stub_targets(monkeypatch)
    monkeypatch.setattr(
        plc, "run", lambda seat, *a, **k: _chrome_saves(seat, "big.iso", b"x", True)
    )
    run = commands.run_script("seat", "download button.save 1\n")
    assert not run.ok
    assert "big.iso.crdownload is still arriving" in run.error


def test_text_arrives_as_the_page_wrote_it(monkeypatch, tmp_path):
    """playwright-cli prints a string result as a JSON literal; the verb decodes it once."""
    import json
    page_text = 'line one\nsaid "hi" \\ back\\slash, a literal \\n, caf\u00e9 \u2014 \U0001F600'
    for ensure_ascii in (False, True):
        _stub_browser(monkeypatch, tmp_path)
        printed = json.dumps(page_text, ensure_ascii=ensure_ascii)
        monkeypatch.setattr(plc, "run", lambda *a, printed=printed, **k: f"### Result\n{printed}\n")
        run = commands.run_script("seat", "text #reply\n")
        assert run.ok, run.error
        assert run.steps[0]["output"] == page_text
