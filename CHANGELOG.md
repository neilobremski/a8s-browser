# Changelog

## 0.2.0

- `run-code`: Playwright statements with `page` in scope, for pages the DOM cannot drive — a menu that ignores a synthetic click, a file chooser, a driver-level wait. It is gated on the same `A8S_BROWSER_ALLOW_EVAL` opt-in as `eval`, because it is the same class of capability and strictly more of it.
- Heredoc blocks in the script language: a command line ending in `<<MARKER` takes the following lines as its argument, verbatim, up to a line reading just `MARKER`. Nothing inside is interpreted — `#` lines, blank lines, indentation and words that look like other verbs are all body text. A block nobody closed fails the script naming the marker, and runs none of it. The form works for any verb that takes the rest of its line verbatim.

## 0.1.2

- Ruff lint gate: `ruff.toml` (select E, F, W, I, B, UP, RUF; line-length 100), `tools/lint` as the local runner, and a `lint` job in both the PR workflow and the release gate. `src/resolve.py` is exempt from E501 because it carries large embedded JavaScript that a Python line-length rule would only mangle. `ruff format` is not adopted — reformatting all 15 files would bury this change.

## 0.1.1

- README documents the development workflow: branch + PR, every merge bumps VERSION, PII gates on diff and tree.

## 0.1.0

First working release.

- Persistent Chrome profile per named seat; `playwright-cli` attaches over CDP on a stable per-seat port.
- A8S `handle` entry point: each tell is a line-oriented command script, and the reply carries the transcript plus snapshot, screenshot, console log, requests log, or video attachments.
- Command vocabulary: `open`, `close`, `save`, `url`, `go`, `back`, `forward`, `reload`, `snap`, `shot`, `find`, `click`, `fill`, `type`, `press`, `select`, `check`, `uncheck`, `hover`, `scroll`, `wait`, `wait-for`, `wait-for-url`, `assert-text`, `assert-url`, `text`, `console`, `requests`, `dialog-accept`, `dialog-dismiss`, `video-start`, `video-chapter`, `video-stop`, and gated `eval`.
- Sender allowlist and `eval` opt-in are per-seat a8s vars; an unset allowlist refuses everyone.
- `close` always reaps the seat: browser-level CDP shutdown for a clean profile (`exit_type: Normal`), then SIGTERM to SIGKILL escalation and the session daemon — even with a modal dialog open or a dead session. Your own Chrome is never targeted.
