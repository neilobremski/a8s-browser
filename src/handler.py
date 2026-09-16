"""a8s wake entry point: a tell in, a transcript and its artifacts back."""
import os
import subprocess

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
    argv = ["tell", recipient, "-"]
    for path in files:
        argv += ["--attach", path]
    subprocess.run(argv, input=body, text=True, check=False)


def handle(seat, sender, message, allow=None, allow_eval=None):
    """`allow`/`allow_eval` come from the definition's argv (a8s vars); unset,
    they fall back to the environment so a hand-run `handle` behaves the same."""
    spec = allow if allow is not None else os.environ.get("A8S_BROWSER_ALLOW", "")
    if not allowed(sender, spec):
        _tell(sender, f"{seat}: refusing — {sender} is not on this seat's allowlist.", [])
        return 1

    eval_flag = allow_eval if allow_eval is not None else os.environ.get("A8S_BROWSER_ALLOW_EVAL", "")
    run = commands.run_script(seat, message, allow_eval=_truthy(eval_flag))

    verdict = "ok" if run.ok else f"failed: {run.error}"
    body = f"{seat}: {verdict}\n\n{run.transcript()}"
    _tell(sender, body[:MAX_BODY], run.files)
    return 0 if run.ok else 1
