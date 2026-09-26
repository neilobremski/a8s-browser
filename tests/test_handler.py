import subprocess

import commands
import handler


def test_an_empty_allowlist_accepts_nobody(monkeypatch):
    monkeypatch.delenv("A8S_BROWSER_ALLOW", raising=False)
    assert not handler.allowed("iris", "")


def test_the_allowlist_is_case_insensitive(monkeypatch):
    assert handler.allowed("iris", "Iris, codex")
    assert handler.allowed("CODEX", "Iris, codex")
    assert not handler.allowed("stranger", "Iris, codex")


def test_the_argv_allowlist_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "codex")
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))
    run = commands.Run("garmin")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)
    # The reply always goes out, so the exit code no longer tells allowed from
    # refused apart (#11) — the message does.
    assert handler.handle("garmin", "iris", "url", allow="iris") == 0
    assert handler.handle("garmin", "codex", "url", allow="iris") == 0
    assert "allowlist" in sent[1][1]


def test_a_refused_sender_gets_one_reply_and_the_wake_still_exits_zero(monkeypatch):
    """#11: a refused sender is not the wake failing — the reply saying so is
    the wake succeeding. a8s must not retry this, or the refusal repeats."""
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "iris")
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))
    monkeypatch.setattr(
        commands, "run_script",
        lambda *a, **k: pytest_fail("the browser ran for an unlisted sender"),
    )
    assert handler.handle("garmin", "stranger", "go https://example.com") == 0
    assert len(sent) == 1
    assert "allowlist" in sent[0][1]


def test_a_reply_carries_the_transcript_and_the_artifacts(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "iris")
    run = commands.Run("garmin")
    run.note("url", "https://example.com/")
    run.attach("/tmp/shot.png")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))

    assert handler.handle("garmin", "iris", "url") == 0
    recipient, body, files = sent[0]
    assert recipient == "iris"
    assert body.startswith("garmin: ok")
    assert "https://example.com/" in body
    assert files == ["/tmp/shot.png"]


def test_a_failing_verb_still_gets_one_reply_and_exits_zero(monkeypatch):
    """#11: the old contract retried the wake on a failing verb, which
    re-sent the same failure reply up to four times and blocked the queue
    behind it. Once the reply is sent, the wake is complete."""
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "iris")
    run = commands.Run("garmin")
    run.fail("click Submit", "nothing visible matching 'Submit'")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))
    assert handler.handle("garmin", "iris", "click Submit") == 0
    assert len(sent) == 1
    assert "failed" in sent[0][1]


def test_a_tell_that_cannot_deliver_is_the_one_thing_that_exits_nonzero(monkeypatch, capsys):
    """#11: a8s's retry exists for a wake that could not answer at all — so a
    reply that never went out must be the one thing that exits nonzero."""
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "iris")
    run = commands.Run("garmin")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)

    def _raise(*args):
        raise RuntimeError("tell exploded")

    monkeypatch.setattr(handler, "_tell", _raise)
    assert handler.handle("garmin", "iris", "url") == 1
    assert "tell exploded" in capsys.readouterr().err


def test_tell_raises_when_the_underlying_tell_command_fails(monkeypatch):
    """`_tell` uses `check=True` so a nonzero exit from `tell` is not a
    `CompletedProcess` nobody looked at (the bug's root cause) — it raises."""
    monkeypatch.setattr(
        handler.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, a[0] if a else [])),
    )
    try:
        handler._tell("iris", "body", [])
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("_tell did not raise on a failed send")


def test_allow_eval_arg_overrides_the_environment(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "iris")
    monkeypatch.delenv("A8S_BROWSER_ALLOW_EVAL", raising=False)
    seen = []
    monkeypatch.setattr(
        commands, "run_script",
        lambda seat, body, allow_eval=False: seen.append(allow_eval) or commands.Run(seat),
    )
    monkeypatch.setattr(handler, "_tell", lambda *args: None)
    handler.handle("garmin", "iris", "url", allow_eval="1")
    handler.handle("garmin", "iris", "url", allow_eval="0")
    assert seen == [True, False]


def pytest_fail(message):
    raise AssertionError(message)
