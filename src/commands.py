"""The command vocabulary a tell is allowed to use.

A script is one command per line, run in order, stopping at the first failure —
and a failure attaches a snapshot of the page it died on, because the next
message is going to be a correction and the sender needs to see what the
browser sees.

The vocabulary is fixed on purpose. A seat holds live logins, so a message
naming a verb is a different thing from a message carrying code: `eval` is the
one door to arbitrary execution and it stays shut unless the seat opts in.
"""
import os
import shlex
import time

import plc
import resolve
import session

MAX_WAIT = 300.0

# Verbs that must not auto-open the browser: `close` is the whole point, and
# `video-stop` needs to report a stale recording rather than launch Chrome to
# discover one.
NO_ENSURE = {"close", "video-stop"}

# Verbs whose argument is the rest of the line verbatim, not shlex words:
# `eval console.log('x')` must keep its quotes, and `type don't` must not die
# on an unbalanced apostrophe.
RAW_ARGS = {"eval", "type", "find", "assert-text", "video-chapter", "dialog-accept"}


class Run:
    """The transcript of one script: what each step did, and what it produced."""

    def __init__(self, seat):
        self.seat = seat
        self.steps = []
        self.files = []
        self.error = None

    def note(self, line, output=""):
        self.steps.append({"command": line, "ok": True, "output": output})

    def fail(self, line, message):
        self.steps.append({"command": line, "ok": False, "error": message})
        self.error = message

    def attach(self, path):
        self.files.append(path)

    @property
    def ok(self):
        return self.error is None

    def transcript(self):
        lines = []
        for step in self.steps:
            mark = "  " if step["ok"] else "! "
            lines.append(f"{mark}{step['command']}")
            detail = step.get("output") or step.get("error") or ""
            for line in detail.splitlines():
                lines.append(f"      {line}")
        return "\n".join(lines)


def artifact(seat, suffix):
    directory = session.artifacts_dir(seat)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{time.strftime('%Y%m%dT%H%M%S')}-{suffix}")


def _write_snapshot(seat, run, label="snapshot"):
    path = artifact(seat, f"{label}.txt")
    with open(path, "w") as handle:
        handle.write(session.snapshot(seat))
    run.attach(path)
    return path


def _seconds(value):
    """Anything over 300 is milliseconds, not a long nap."""
    number = float(value)
    if number > MAX_WAIT:
        number = number / 1000.0
    return min(number, MAX_WAIT)


def _need(args, count, usage):
    if len(args) < count:
        raise plc.BrowserError(f"usage: {usage}")


def _go(seat, args):
    _need(args, 1, "go <url>")
    url = args[0]
    if not url.startswith(("http://", "https://", "file://", "about:")):
        raise plc.BrowserError(f"go: refusing {url!r} — give a full http(s) URL")
    plc.run(seat, "goto", url, timeout=60)
    return session.current_url(seat)


def _click(seat, args):
    _need(args, 1, "click <text or selector>")
    target = resolve.click_target(seat, " ".join(args))
    plc.run(seat, "click", target)
    return target


def _fill(seat, args):
    _need(args, 2, "fill <label or selector> <text>")
    target = resolve.fill_target(seat, args[0])
    plc.run(seat, "fill", target, " ".join(args[1:]))
    return target


def _text(seat, args):
    _need(args, 1, "text <selector>")
    selector = plc.js_string(args[0])
    return plc.evaluate(
        seat, f"(document.querySelector('{selector}')?.innerText || '').trim()"
    )


def _wait_for(seat, args):
    _need(args, 1, "wait-for <selector> [seconds]")
    timeout = _seconds(args[1]) if len(args) > 1 else 10.0
    selector = plc.js_string(args[0])
    plc.run_code(
        seat,
        f"await page.waitForSelector('{selector}', {{state: 'visible', timeout: {int(timeout * 1000)}}});",
        timeout=timeout + 10,
    )
    return f"visible: {args[0]}"


def _wait_for_url(seat, args):
    _need(args, 1, "wait-for-url <substring> [seconds]")
    deadline = time.monotonic() + (_seconds(args[1]) if len(args) > 1 else 10.0)
    while time.monotonic() < deadline:
        url = session.current_url(seat)
        if args[0] in url:
            return url
        time.sleep(0.5)
    raise plc.BrowserError(f"wait-for-url: still at {session.current_url(seat)}")


def _assert_text(seat, args):
    _need(args, 1, "assert-text <text>")
    wanted = args[0]
    found = plc.evaluate_json(
        seat, f"(document.body?.innerText || '').includes('{plc.js_string(wanted)}')"
    )
    if not found:
        raise plc.BrowserError(f"assert-text: {wanted!r} is not on the page")
    return "found"


def _assert_url(seat, args):
    _need(args, 1, "assert-url <substring>")
    url = session.current_url(seat)
    if args[0] not in url:
        raise plc.BrowserError(f"assert-url: at {url}")
    return url


def _console(seat, args, run):
    """Attach the page's console log; the transcript keeps a copy inline."""
    argv = ["console"] + args[:1]
    body = plc.result_or(plc.run(seat, *argv))
    path = artifact(seat, "console.log")
    with open(path, "w") as handle:
        handle.write(body + "\n")
    run.attach(path)
    return body or "(console is empty)"


def _video_start(seat, args):
    active = session.video_state(seat)
    if active:
        raise plc.BrowserError(f"video-start: already recording {active['path']}")
    slug = "-".join(args) if args else "recording"
    path = artifact(seat, f"{slug}.webm")
    plc.run(seat, "video-start", path, "--size", "1280x1024")
    session.save_video_state(
        seat, {"path": path, "started_at": time.time(), "chapters": 0}
    )
    return path


def _video_stop(seat, args, run):
    state = session.video_state(seat)
    if not state:
        raise plc.BrowserError("video-stop: no recording in progress")
    try:
        output = plc.run(seat, "video-stop", timeout=60)
    finally:
        # Stopped or not, the recording is gone once the call returns —
        # a lost session must not leave the seat looking busy forever.
        session.clear_video_state(seat)
    if "no videos were recorded" in output.lower():
        raise plc.BrowserError(f"video-stop: playwright-cli recorded nothing: {output.strip()}")
    path = state["path"]
    if not os.path.exists(path):
        raise plc.BrowserError(f"video-stop: no file written at {path}")
    if os.path.getsize(path) == 0:
        raise plc.BrowserError(f"video-stop: {path} is empty")
    run.attach(path)
    return f"{path} ({state.get('chapters') or 0} chapters)"


def _video_chapter(seat, args):
    _need(args, 1, "video-chapter <title>")
    state = session.video_state(seat)
    if not state:
        raise plc.BrowserError("video-chapter: no recording in progress")
    title = args[0]
    plc.run(seat, "video-chapter", title)
    state["chapters"] = int(state.get("chapters") or 0) + 1
    session.save_video_state(seat, state)
    return f"chapter {state['chapters']}: {title}"


def _step(seat, verb, args, run, allow_eval):
    if verb == "open":
        session.ensure_running(seat)
        return session.current_url(seat)
    if verb == "close":
        session.close_browser(seat)
        return "closed"
    if verb == "save":
        return session.save_state(seat)
    if verb == "url":
        return session.current_url(seat)
    if verb == "go":
        return _go(seat, args)
    if verb == "click":
        return _click(seat, args)
    if verb == "fill":
        return _fill(seat, args)
    if verb == "press":
        _need(args, 1, "press <key>")
        plc.run(seat, "press", args[0])
        return args[0]
    if verb == "type":
        _need(args, 1, "type <text>")
        plc.run(seat, "type", args[0])
        return "typed"
    if verb == "text":
        return _text(seat, args)
    if verb == "wait":
        _need(args, 1, "wait <seconds>")
        time.sleep(_seconds(args[0]))
        return f"{_seconds(args[0])}s"
    if verb == "wait-for":
        return _wait_for(seat, args)
    if verb == "wait-for-url":
        return _wait_for_url(seat, args)
    if verb == "assert-text":
        return _assert_text(seat, args)
    if verb == "assert-url":
        return _assert_url(seat, args)
    if verb == "back":
        plc.run(seat, "go-back", timeout=60)
        return session.current_url(seat)
    if verb == "forward":
        plc.run(seat, "go-forward", timeout=60)
        return session.current_url(seat)
    if verb == "reload":
        plc.run(seat, "reload", timeout=60)
        return session.current_url(seat)
    if verb == "scroll":
        _need(args, 1, "scroll <dy>")
        plc.run(seat, "mousewheel", "0", args[0])
        return args[0]
    if verb == "find":
        _need(args, 1, "find <text>")
        return plc.result_or(plc.run(seat, "find", args[0]))
    if verb == "select":
        _need(args, 2, "select <label or selector> <value>")
        target = resolve.fill_target(seat, args[0])
        plc.run(seat, "select", target, " ".join(args[1:]))
        return target
    if verb in ("check", "uncheck", "hover"):
        _need(args, 1, f"{verb} <text or selector>")
        target = resolve.click_target(seat, " ".join(args))
        plc.run(seat, verb, target)
        return target
    if verb == "dialog-accept":
        plc.run(seat, "dialog-accept", *args[:1])
        return "accepted"
    if verb == "dialog-dismiss":
        plc.run(seat, "dialog-dismiss")
        return "dismissed"
    if verb == "requests":
        return plc.result_or(plc.run(seat, "requests", timeout=60))
    if verb == "console":
        return _console(seat, args, run)
    if verb == "video-start":
        return _video_start(seat, args)
    if verb == "video-stop":
        return _video_stop(seat, args, run)
    if verb == "video-chapter":
        return _video_chapter(seat, args)
    if verb == "snap":
        return _write_snapshot(seat, run)
    if verb == "shot":
        path = plc.screenshot(seat, artifact(seat, "screen.png"))
        run.attach(path)
        return path
    if verb == "eval":
        if not allow_eval:
            raise plc.BrowserError("eval refused: this seat has not opted in (A8S_BROWSER_ALLOW_EVAL)")
        _need(args, 1, "eval <expression>")
        return plc.evaluate(seat, args[0], timeout=60)
    raise plc.BrowserError(f"unknown command: {verb}")


def script_lines(body):
    """Command lines of a message: comments, blanks and a8s attachment lines out."""
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("ATTACHED FILE:", "ATTACHMENT UNAVAILABLE:")):
            continue
        lines.append(line)
    return lines


def run_script(seat, body, allow_eval=False):
    run = Run(seat)
    session.prune_scratch(seat)
    for line in script_lines(body):
        verb = line.split(None, 1)[0]
        if verb in RAW_ARGS:
            args = line.split(None, 1)[1:]
        else:
            try:
                words = shlex.split(line)
            except ValueError as exc:
                run.fail(line, f"unparseable: {exc}")
                break
            if not words:
                continue
            verb, args = words[0], words[1:]
        try:
            if verb not in NO_ENSURE:
                session.ensure_running(seat)
            output = _step(seat, verb, args, run, allow_eval)
            run.note(line, str(output or ""))
        except plc.BrowserError as exc:
            run.fail(line, str(exc))
            break

    if not run.ok:
        try:
            _write_snapshot(seat, run, "failure")
        except plc.BrowserError:
            pass
    return run
