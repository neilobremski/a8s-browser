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
import os
import platform
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
        raise plc.BrowserError(f"Chrome for seat {seat!r} did not come up on port {cdp_port(seat)}")

    plc.run(seat, "attach", f"--cdp={base}", timeout=15)


def close_browser(seat):
    if plc.is_open(seat):
        save_state(seat)
        plc.run(seat, "close")

    if platform.system() == "Darwin":
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to quit'],
            capture_output=True, timeout=10,
        )
    else:
        for pid in _profile_pids(seat):
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, ValueError):
                pass

    for _ in range(20):
        if not cdp_base(seat):
            break
        time.sleep(0.25)


def ensure_running(seat):
    """Open the browser, cycling it when Chrome has no visible window.

    A zero-window Chrome reports visibilityState "hidden": pages still load,
    but out-of-process iframes take no input and clicks silently no-op.
    """
    if not plc.is_open(seat):
        open_browser(seat)
        return
    if plc.evaluate(seat, "document.visibilityState") == "hidden":
        close_browser(seat)
        open_browser(seat)


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
