"""Seat-keyed browser session.

One seat, one Chrome profile, one CDP port, one playwright-cli session. Chrome
is launched directly rather than by playwright so it carries no automation
flags, and playwright-cli attaches afterwards over CDP. The profile directory
is what makes a seat persistent: cookies survive a restart because Chrome
stores them the way it does for a person.

Derived from b3t's session layer (neilobremski/bin), generalised so the seat
name selects the profile.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import time
import urllib.request

import plc

CDP_PORT_BASE = 9222
CDP_PORT_SPAN = 200
CHROME_STARTUP_WAIT = 60  # x 0.2s


def state_root():
    """Where seats live. Separate from the install dir, which updates replace."""
    override = os.environ.get("A8S_BROWSER_HOME")
    if override:
        return os.path.expanduser(override)
    return os.path.join(
        os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
        "a8s-browser",
    )


def seat_home(seat):
    return os.path.join(state_root(), seat)


def profile_dir(seat):
    return os.path.join(seat_home(seat), "chrome")


def artifacts_dir(seat):
    return os.path.join(seat_home(seat), "artifacts")


def scratch_dir(seat):
    """The seat's working directory — playwright-cli drops per-command scratch
    (page-*.yml, console-*.log) under a `.playwright-cli` dir beneath its cwd,
    so the CLI runs from here instead of the caller's directory."""
    path = os.path.join(seat_home(seat), "scratch")
    os.makedirs(path, exist_ok=True)
    return path


def prune_scratch(seat, max_age=86400):
    """Bound the scratch playwright-cli leaves behind — it writes a file per
    command, so an unpruned dir grows without limit on a busy seat."""
    directory = os.path.join(scratch_dir(seat), ".playwright-cli")
    try:
        names = os.listdir(directory)
    except OSError:
        return
    cutoff = time.time() - max_age
    for name in names:
        path = os.path.join(directory, name)
        try:
            stale = os.path.getmtime(path) < cutoff
            if os.path.isfile(path) and not os.path.islink(path) and stale:
                os.remove(path)
        except OSError:
            pass


def video_state_path(seat):
    return os.path.join(seat_home(seat), "video.json")


def video_state(seat):
    """The active recording's {path, started_at, chapters}, or None."""
    try:
        with open(video_state_path(seat)) as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def save_video_state(seat, state):
    os.makedirs(seat_home(seat), exist_ok=True)
    path = video_state_path(seat)
    with open(path + ".tmp", "w") as handle:
        json.dump(state, handle)
    os.replace(path + ".tmp", path)


def clear_video_state(seat):
    try:
        os.remove(video_state_path(seat))
    except OSError:
        pass


def cdp_port(seat):
    """A stable port per seat, so seats never collide and a restart reuses one."""
    override = os.environ.get("A8S_BROWSER_PORT")
    if override:
        return int(override)
    digest = hashlib.sha256(seat.encode()).digest()
    return CDP_PORT_BASE + (int.from_bytes(digest[:2], "big") % CDP_PORT_SPAN)


def chrome_path():
    explicit = os.environ.get("A8S_BROWSER_CHROME")
    if explicit:
        return explicit
    if platform.system() == "Darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def cdp_base(seat):
    port = cdp_port(seat)
    for host in ("127.0.0.1", "localhost", "[::1]"):
        base = f"http://{host}:{port}"
        try:
            urllib.request.urlopen(f"{base}/json/version", timeout=2)
            return base
        except OSError:
            continue
    return None


def _wait_for_cdp(seat):
    for _ in range(CHROME_STARTUP_WAIT):
        base = cdp_base(seat)
        if base:
            return base
        time.sleep(0.2)
    return None


def _profile_pids(seat):
    """Chromes holding this seat's profile, whether or not CDP answers yet."""
    if platform.system() == "Windows":
        return []
    result = subprocess.run(
        ["pgrep", "-f", profile_dir(seat)], capture_output=True, text=True
    )
    return result.stdout.split()


def _main_pids(seat):
    """Just the browser process — helpers carry --type= between binary and
    profile flag, and die on their own when the parent exits."""
    if platform.system() == "Windows":
        return []
    binary = re.escape(os.path.basename(chrome_path() or "chrome"))
    pattern = f"{binary} --user-data-dir={re.escape(profile_dir(seat))}"
    result = subprocess.run(
        ["pgrep", "-f", pattern], capture_output=True, text=True
    )
    return result.stdout.split()


def _daemon_pids(seat):
    """playwright-cli's per-seat daemon; a broken one can outlive its browser."""
    if platform.system() == "Windows":
        return []
    result = subprocess.run(
        ["pgrep", "-f", f"cliDaemon.js {re.escape(seat)}([[:space:]]|$)"],
        capture_output=True, text=True,
    )
    return result.stdout.split()


def _signal(pid, sig):
    try:
        os.kill(int(pid), sig)
    except (ProcessLookupError, PermissionError, ValueError):
        pass


def _terminate_profile(seat):
    """Nothing the seat owns gets to stay: SIGTERM the browser process, wait,
    then SIGKILL whatever is still holding the profile, and stop the seat's
    playwright daemon. A wedged Chrome is how a stray dock icon outlives its
    seat — SIGTERM alone can stall behind a busy or dialog-blocked browser."""
    for pid in _main_pids(seat):
        _signal(pid, signal.SIGTERM)
    for _ in range(20):
        if not _profile_pids(seat):
            break
        time.sleep(0.25)
    for pid in _profile_pids(seat):
        _signal(pid, signal.SIGKILL)
    for pid in _daemon_pids(seat):
        _signal(pid, signal.SIGTERM)


def _launch_chrome(seat):
    binary = chrome_path()
    if not binary:
        raise plc.BrowserError("no Chrome found — set A8S_BROWSER_CHROME")
    os.makedirs(profile_dir(seat), exist_ok=True)
    subprocess.Popen(
        [
            binary,
            f"--user-data-dir={profile_dir(seat)}",
            f"--remote-debugging-port={cdp_port(seat)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-backgrounding-occluded-windows",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_browser(seat):
    if plc.is_open(seat):
        return

    base = cdp_base(seat)
    if not base:
        if not _profile_pids(seat):
            _launch_chrome(seat)
        base = _wait_for_cdp(seat)
    if not base:
        # A launch that never serves CDP would otherwise leave a browser
        # nobody can drive — and an icon nobody can quit — running forever.
        _terminate_profile(seat)
        raise plc.BrowserError(f"Chrome for seat {seat!r} did not come up on port {cdp_port(seat)}")

    try:
        plc.run(seat, "attach", f"--cdp={base}", timeout=15)
    except plc.BrowserError:
        _terminate_profile(seat)
        raise


def _salvage_recording(seat):
    """Stop an active recording so the file flushes before the browser dies."""
    if not video_state(seat):
        return
    try:
        plc.run(seat, "video-stop", timeout=30)
    except plc.BrowserError:
        pass
    clear_video_state(seat)


def close_browser(seat):
    if plc.is_open(seat):
        try:
            # A modal dialog can keep a graceful quit — and even state-save —
            # from ever completing; clear one before anything else.
            plc.run(seat, "dialog-dismiss", timeout=5)
        except plc.BrowserError:
            pass
        try:
            save_state(seat)
        except plc.BrowserError:
            pass
        _salvage_recording(seat)
        try:
            # Browser.close over CDP quits exactly this Chrome instance with a
            # clean exit (profile flushes, no crash flag). browser().close()
            # only disconnects, and osascript "tell application ... to quit"
            # is unscoped — it can take down a person's own browser running
            # beside the seat's.
            plc.run_code(
                seat,
                "const s = await page.context().browser().newBrowserCDPSession();"
                " await s.send('Browser.close');",
                timeout=15,
            )
        except plc.BrowserError:
            pass
        try:
            plc.run(seat, "close")
        except plc.BrowserError:
            pass

    _terminate_profile(seat)

    for _ in range(20):
        if not cdp_base(seat):
            break
        time.sleep(0.25)


# Asks CDP which window holds the driven page. A page no window holds is the
# genuine zero-window Chrome; visibilityState cannot tell that apart from a
# window that is merely covered or minimised, which also read "hidden".
_WINDOW_PROBE = (
    "const s = await page.context().newCDPSession(page);"
    " try {"
    " let w = null;"
    " try { w = await s.send('Browser.getWindowForTarget'); }"
    " catch (e) { if (!/window not found/i.test(e.message)) throw e; }"
    " return JSON.stringify({url: page.url(),"
    " window: w && w.windowId, state: w && w.bounds.windowState});"
    " } finally { await s.detach(); }"
)

BLANK_URLS = ("", "about:blank")


def _window_of_page(seat):
    return plc.parse_json(plc.result_of(plc.run_code(seat, _WINDOW_PROBE, timeout=15)))


def _unminimise(seat, window_id):
    plc.run_code(
        seat,
        "const s = await page.context().newCDPSession(page);"
        f" try {{ await s.send('Browser.setWindowBounds', {{windowId: {int(window_id)},"
        " bounds: {windowState: 'normal'}}); } finally { await s.detach(); }",
        timeout=15,
    )


def _restart_browser(seat, url):
    """Cycle Chrome and land back on `url`, so a restart never moves the caller."""
    close_browser(seat)
    open_browser(seat)
    if url not in BLANK_URLS:
        try:
            plc.run(seat, "goto", url, timeout=60)
        except plc.BrowserError as exc:
            raise plc.BrowserError(
                f"restarted Chrome but could not return to {url}: {exc}"
            ) from exc


def ensure_running(seat):
    """Open the browser, and make sure the driven page sits in a window.

    A page no window holds takes no input in its out-of-process iframes —
    clicks silently no-op — so that Chrome is cycled, and the page it was on
    is reopened. A minimised window is only restored, and a window behind
    other windows is left alone: Chrome is launched with
    --disable-backgrounding-occluded-windows, so its pages stay visible.

    A session that is listed but refuses the probe is busy, not dead — an open
    dialog blocks the driver — so the failure falls through to the verb, which
    either handles the modal state or reports the real error.
    """
    if not plc.is_open(seat):
        open_browser(seat)
        return
    try:
        page = _window_of_page(seat)
    except plc.BrowserError:
        return
    if page.get("window") is None:
        _restart_browser(seat, page.get("url") or "")
    elif page.get("state") == "minimized":
        _unminimise(seat, page["window"])


def save_state(seat):
    path = os.path.join(seat_home(seat), "state.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plc.run(seat, "state-save", path)
    return path


def snapshot(seat):
    return plc.run(seat, "snapshot", timeout=30)


def current_url(seat):
    return plc.evaluate(seat, "window.location.href")


def status(seat):
    if not plc.is_open(seat):
        return f"{seat}: not attached (cdp {cdp_port(seat)})"
    return f"{seat}: attached at {current_url(seat)}"
