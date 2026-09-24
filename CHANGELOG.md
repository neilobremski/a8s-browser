# Changelog

## 0.3.0

- File verbs, so a seat can carry files as well as text. `upload <path> ...` hands files to a chooser the page has already opened, which is a driver-level modal no page JS can reach. `drop <target> <path> ...` drops them onto an element as a drag would, which opens no menu and no chooser and is the one to prefer where a page accepts it. `download <target> [secs]` clicks something that downloads and attaches what came back.
- All three name files by their absolute path on the machine holding the browser. A relative path is refused rather than resolved: the seat's working directory is its own scratch dir, so a relative path means a file on the sender's machine and resolving it here would find something else or nothing.
- `download` waits on playwright-cli's own download event rather than watching for a file, because playwright-cli saves the bytes itself and names them in an event that may land after the click returns. The file is then copied into the run's artifacts, since the scratch directory it lands in is pruned of anything a day old on every run.
- None of the three needs `A8S_BROWSER_ALLOW_EVAL`. That gate is on caller-supplied code, not on the capability — this repo already runs fixed page JS ungated in `wait-for` and on every `click` and `fill`.

## 0.2.0

- `run-code`: Playwright statements with `page` in scope, for pages the DOM cannot drive — a menu that ignores a synthetic click, a file chooser, a driver-level wait. It is gated on the same `A8S_BROWSER_ALLOW_EVAL` opt-in as `eval`, because it is the same class of capability and strictly more of it.
- Heredoc blocks in the script language: a command line ending in `<<MARKER` takes the following lines as its argument, verbatim, up to a line reading just `MARKER`. Nothing inside is interpreted — `#` lines, blank lines, indentation and words that look like other verbs are all body text. The opening line carries nothing but the verb, and a line that opens a block while also carrying an inline argument is refused rather than half-run. A block nobody closed fails the script naming the marker. Both are caught while the script is parsed, so neither runs any of it. The form works for any verb that takes the rest of its line verbatim.

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
