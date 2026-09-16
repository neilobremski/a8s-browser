"""a8s wake entry point: a tell in, a transcript and its artifacts back."""
import os
import subprocess

import commands

MAX_BODY = 4000


def allowed(sender):
    """An empty allowlist means nobody — this seat drives a logged-in browser."""
    names = {
        name.strip().lower()
        for name in os.environ.get("A8S_BROWSER_ALLOW", "").split(",")
        if name.strip()
    }
    return sender.lower() in names


def _tell(recipient, body, files):
    argv = ["tell", recipient, "-"]
    for path in files:
        argv += ["--attach", path]
    subprocess.run(argv, input=body, text=True, check=False)


def handle(seat, sender, message):
    if not allowed(sender):
        _tell(sender, f"{seat}: refusing — {sender} is not on this seat's allowlist.", [])
        return 1

    allow_eval = os.environ.get("A8S_BROWSER_ALLOW_EVAL", "").lower() in ("1", "true", "yes")
    run = commands.run_script(seat, message, allow_eval=allow_eval)

    verdict = "ok" if run.ok else f"failed: {run.error}"
    body = f"{seat}: {verdict}\n\n{run.transcript()}"
    _tell(sender, body[:MAX_BODY], run.files)
    return 0 if run.ok else 1
