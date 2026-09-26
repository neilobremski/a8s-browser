"""a8s wake entry point: a tell in, a transcript and its artifacts back."""
import os
import subprocess
import sys
import traceback

import commands

MAX_BODY = 4000


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes")


def allowed(sender, spec):
    """An empty allowlist means nobody — this seat drives a logged-in browser."""
    names = {
        name.strip().lower()
        for name in (spec or "").split(",")
        if name.strip()
    }
    return sender.lower() in names


def _tell(recipient, body, files):
    """Send the reply. Raises if `tell` itself could not deliver it.

    `check=True` is the whole fix for making that failure observable: a
    nonzero exit from `tell` becomes a `CalledProcessError` instead of a
    `CompletedProcess` nobody looked at.
    """
    argv = ["tell", recipient, "-"]
    for path in files:
        argv += ["--attach", path]
    subprocess.run(argv, input=body, text=True, check=True)


def _reply(sender, body, files):
    """Send the reply and report whether the wake completed.

    a8s retries a wake on nonzero exit (30/120/600s, four attempts), and a
    retried wake runs `handle` again — so the only failure worth an a8s retry
    is a reply that never went out. A failing verb already told the sender so
    in the reply itself; sending that reply is what completes the wake.
    """
    try:
        _tell(sender, body, files)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


def handle(seat, sender, message, allow=None, allow_eval=None):
    """`allow`/`allow_eval` come from the definition's argv (a8s vars); unset,
    they fall back to the environment so a hand-run `handle` behaves the same."""
    spec = allow if allow is not None else os.environ.get("A8S_BROWSER_ALLOW", "")
    if not allowed(sender, spec):
        return _reply(sender, f"{seat}: refusing — {sender} is not on this seat's allowlist.", [])

    eval_flag = (
        allow_eval
        if allow_eval is not None
        else os.environ.get("A8S_BROWSER_ALLOW_EVAL", "")
    )
    run = commands.run_script(seat, message, allow_eval=_truthy(eval_flag))

    verdict = "ok" if run.ok else f"failed: {run.error}"
    body = f"{seat}: {verdict}\n\n{run.transcript()}"
    return _reply(sender, body[:MAX_BODY], run.files)
