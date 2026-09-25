# Changelog

## 0.3.2

- `click`/`fill`/etc. resolve a text target after normalising quote and apostrophe confusables (curly vs straight `'`/`"`) when the literal, case-insensitive match finds nothing. A chat page renders a curly apostrophe; an agent types a straight one; the two now resolve to the same element. An exact literal match still wins first, so a page carrying both forms resolves to the one actually typed.
- When nothing visible matches at all, the error now names the closest visible candidate by a bounded edit-distance search, so a one-character miss (a quote style, a typo) is visible in the message instead of sending the operator down a "display crashed" path.
- The normalisation pool no longer loses candidates. `click` on a plain `<button>` (not `cursor: pointer`) kept it out of the normalisation/hint pool whenever the literal match fell back to the pointer-cursor scan, which replaced the whole pool instead of adding to it. `fill` kept only a control's first label (aria-label, `label[for]`, wrapping `<label>`, placeholder), so a query matching a later label found nothing once the literal pass missed. Both verbs now carry every candidate label into normalisation, and a control matched by more than one label collapses to a single candidate instead of reading as an ambiguous multi-element pick.

## 0.3.1

- A seat keeps its page when its window is behind other windows or minimised. Every command checked `document.visibilityState` and restarted Chrome when it read `hidden`, to catch a Chrome with no window. On macOS a covered or minimised window also reads `hidden`, so a seat whose window sat behind other windows lost its page on every command and landed on `about:blank`.
- Chrome is launched with `--disable-backgrounding-occluded-windows`, so a covered page stays `visible` to itself. A minimised window still reads `hidden` with that flag, so it is restored to a normal window before the command runs. That brings it back without taking focus.
- The restart test asks CDP for the window that holds the driven page (`Browser.getWindowForTarget`). Chrome is restarted only when there is no such window.
- A restart navigates back to the page it was on. A restart that cannot return fails the command and names the lost URL.
- A page that reads `hidden` in a normal window is brought to the front with `Page.bringToFront`. This is the seat's Chrome hidden with Cmd-H, which the launch flag does not cover. A hidden page never settles for Playwright, so a click there would wait until it timed out.
- `download` works on the seat's real Chrome. The seat attaches to a Chrome it launched as a person would, so Playwright managed no downloads. Chrome saved each file to the person's Downloads folder, and the verb waited for an event that never came. Every attach and every command now points Chrome's downloads at the seat's own `downloads` directory (`Browser.setDownloadBehavior`). That override lasts only while its CDP session stays attached, so one session is kept for the life of the attach. Each `download` call points Chrome at a new directory of its own under that one before it clicks. Chrome fixes a download's path when the download starts, so a download an earlier call timed out on finishes in that call's directory and is never returned for a later click. The verb waits for a finished file in its own directory (not `.crdownload`), moves it into the run's artifacts, and prints its path, as before. A timeout names the directory Chrome was saving into, and names the partial file when one is still arriving. On macOS, Chrome still creates and at once deletes an empty `.com.google.Chrome.*` temp file in the person's Downloads folder on each download. A profile's default download directory preference does not move it.
- An artifact path is never one already taken. Artifact names carry a one-second timestamp, so two downloads of one name in the same second used the same path, and the second replaced the first. A second artifact of that name in that second now gets a counter (`<stamp>-2-<name>`). A download is moved into place with a hard link, which refuses an existing path, so no artifact is replaced even under a race.
- `text`, `url` and `eval` return a string result as the string itself. playwright-cli prints a string as a JSON literal. Before this release only its outer quotes were removed, so newlines, quotes and backslashes arrived as `\n`, `\"` and `\\`. The literal is now decoded once with a JSON parser. A caller that decoded these escapes itself must stop, or it decodes twice. a8s-gemini-web 0.2.0 does this for `text`.

## 0.3.0

- File verbs, so a seat can carry files as well as text. `upload <path>` hands one file to a chooser the page has already opened, which is a driver-level modal no page JS can reach — one file, because a chooser is answered once and then closes, so `drop` is the verb for several at a time. `drop <target> <path> ...` drops them onto an element as a drag would, which opens no menu and no chooser and is the one to prefer where a page accepts it. `download <target> [secs]` clicks something that downloads and attaches what came back.
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
