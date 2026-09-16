import commands
import handler


def test_an_empty_allowlist_accepts_nobody(monkeypatch):
    monkeypatch.delenv("A8S_BROWSER_ALLOW", raising=False)
    assert not handler.allowed("dresden")


def test_the_allowlist_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "Dresden, gropple")
    assert handler.allowed("dresden")
    assert handler.allowed("GROPPLE")
    assert not handler.allowed("stranger")


def test_a_stranger_is_told_no_and_the_browser_is_never_touched(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "dresden")
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))
    monkeypatch.setattr(
        commands, "run_script",
        lambda *a, **k: pytest_fail("the browser ran for an unlisted sender"),
    )
    assert handler.handle("garmin", "stranger", "go https://example.com") == 1
    assert "allowlist" in sent[0][1]


def test_a_reply_carries_the_transcript_and_the_artifacts(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "dresden")
    run = commands.Run("garmin")
    run.note("url", "https://example.com/")
    run.attach("/tmp/shot.png")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)
    sent = []
    monkeypatch.setattr(handler, "_tell", lambda *args: sent.append(args))

    assert handler.handle("garmin", "dresden", "url") == 0
    recipient, body, files = sent[0]
    assert recipient == "dresden"
    assert body.startswith("garmin: ok")
    assert "https://example.com/" in body
    assert files == ["/tmp/shot.png"]


def test_a_failed_run_exits_nonzero_so_a8s_sees_it(monkeypatch):
    monkeypatch.setenv("A8S_BROWSER_ALLOW", "dresden")
    run = commands.Run("garmin")
    run.fail("click Submit", "nothing visible matching 'Submit'")
    monkeypatch.setattr(commands, "run_script", lambda *a, **k: run)
    monkeypatch.setattr(handler, "_tell", lambda *args: None)
    assert handler.handle("garmin", "dresden", "click Submit") == 1


def pytest_fail(message):
    raise AssertionError(message)
