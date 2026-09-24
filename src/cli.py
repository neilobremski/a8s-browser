"""CLI for a8s-browser: drive a seat's browser by hand, or serve a8s wakes."""
import argparse
import json
import os
import sys

import commands
import doctor
import handler
import plc
import session


def _seat(args):
    return args.seat or os.environ.get("A8S_BROWSER_SEAT") or "browser"


def _allow_eval():
    return os.environ.get("A8S_BROWSER_ALLOW_EVAL", "").lower() in ("1", "true", "yes")


def _do(seat, args):
    if args.script == "-":
        body = sys.stdin.read()
    else:
        with open(args.script) as handle:
            body = handle.read()

    run = commands.run_script(seat, body, allow_eval=_allow_eval())
    if args.json:
        print(json.dumps({"ok": run.ok, "steps": run.steps, "files": run.files}))
    else:
        print(run.transcript())
        for path in run.files:
            print(f"artifact: {path}")
    return 0 if run.ok else 1


def main():
    parser = argparse.ArgumentParser(
        prog="a8s-browser",
        description="A persistent browser session addressable as an a8s seat.",
    )
    parser.add_argument("-s", "--seat", help="seat name (default: $A8S_BROWSER_SEAT or 'browser')")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("open", help="launch Chrome on this seat's profile and attach")
    sub.add_parser("close", help="save state and quit Chrome")
    sub.add_parser("status", help="report whether the session is attached, and where it is")
    sub.add_parser("snap", help="print the page accessibility snapshot")
    sub.add_parser("console", help="print the page console log")
    sub.add_parser("doctor", help="check that this box has what a seat needs")

    parser_go = sub.add_parser("go", help="navigate to a URL")
    parser_go.add_argument("url")

    parser_do = sub.add_parser("do", help="run a command script (file, or '-' for stdin)")
    parser_do.add_argument("script")
    parser_do.add_argument("--json", action="store_true", help="emit the run as JSON")

    parser_handle = sub.add_parser("handle", help="a8s wake entry point")
    parser_handle.add_argument("--from", dest="sender", required=True)
    parser_handle.add_argument("--message", required=True)
    parser_handle.add_argument(
        "--allow",
        help="comma-separated senders this seat answers; overrides A8S_BROWSER_ALLOW",
    )
    parser_handle.add_argument(
        "--allow-eval",
        nargs="?",
        const="1",
        help="permit `eval` and `run-code` on this seat; overrides A8S_BROWSER_ALLOW_EVAL",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "doctor":
        return doctor.report()

    seat = _seat(args)
    # A relative script path must resolve before the seat's scratch dir becomes
    # the cwd; everything playwright-cli drops then lands under the seat.
    if args.command == "do" and args.script != "-":
        args.script = os.path.abspath(args.script)
    os.chdir(session.scratch_dir(seat))
    if args.command == "handle":
        return handler.handle(
            seat, args.sender, args.message,
            allow=args.allow, allow_eval=args.allow_eval,
        )
    if args.command == "do":
        return _do(seat, args)

    try:
        if args.command == "open":
            session.open_browser(seat)
            print(session.status(seat))
        elif args.command == "close":
            session.close_browser(seat)
            print(f"{seat}: closed")
        elif args.command == "status":
            print(session.status(seat))
        elif args.command == "snap":
            session.ensure_running(seat)
            print(session.snapshot(seat))
        elif args.command == "console":
            session.ensure_running(seat)
            print(plc.result_or(plc.run(seat, "console")))
        elif args.command == "go":
            session.ensure_running(seat)
            plc.run(seat, "goto", args.url, timeout=60)
            print(session.current_url(seat))
    except plc.BrowserError as exc:
        print(f"{seat}: {exc}", file=sys.stderr)
        return 1
    return 0
