# Changelog

## 0.1.1

- README documents the development workflow: branch + PR, every merge bumps VERSION, PII gates on diff and tree.

## 0.1.0

First working release.

- Persistent Chrome profile per named seat; `playwright-cli` attaches over CDP on a stable per-seat port.
- A8S `handle` entry point: each tell is a line-oriented command script, and the reply carries the transcript plus snapshot, screenshot, console log, requests log, or video attachments.
- Command vocabulary: `open`, `close`, `save`, `url`, `go`, `back`, `forward`, `reload`, `snap`, `shot`, `find`, `click`, `fill`, `type`, `press`, `select`, `check`, `uncheck`, `hover`, `scroll`, `wait`, `wait-for`, `wait-for-url`, `assert-text`, `assert-url`, `text`, `console`, `requests`, `dialog-accept`, `dialog-dismiss`, `video-start`, `video-chapter`, `video-stop`, and gated `eval`.
- Sender allowlist and `eval` opt-in are per-seat a8s vars; an unset allowlist refuses everyone.
- `close` always reaps the seat: browser-level CDP shutdown for a clean profile (`exit_type: Normal`), then SIGTERM to SIGKILL escalation and the session daemon — even with a modal dialog open or a dead session. Your own Chrome is never targeted.
