# a8s-browser

A logged-in browser you can address by name.

Each seat is one Chrome profile that stays signed in, and each tell to that
seat is a short command script run in it. The reply carries the transcript and
whatever the run produced — an accessibility snapshot, a screenshot, a file.

```
tell garmin - <<'EOF'
go https://connect.garmin.com/modern/
snap
EOF
```

The point is the loop. A scraper that breaks when a page changes fails silently
at 3am; a browser seat answers with a fresh snapshot of what it is actually
looking at, and the agent on the other end sends the next step. Corrections
happen in the conversation instead of in a redeploy.

Run it on the machine whose network and profile you want to browse from. The
seat name is the handle, so `garmin`, `work` and `bank` are three profiles,
three cookie jars, three identities — on one machine or on several.

## Quickstart

Needs git, python3, Chrome, and node/npm (for playwright-cli). On the machine
the browser should live on:

```bash
curl -fsSL https://raw.githubusercontent.com/neilobremski/a8s-browser/main/get.sh | sh
source ~/.zshrc                 # or open a new shell — puts a8s-browser on PATH
a8s-browser doctor              # reports anything still missing
```

Drive a seat by hand first — `garmin` is the seat name; pick your own:

```bash
a8s-browser -s garmin open      # a real Chrome window opens on a fresh profile
# log in to whatever the seat is for, by hand, in that window — once

a8s-browser -s garmin do - <<'EOF'
go https://connect.garmin.com/modern/
snap
shot
EOF
```

Then put it on the wire. This machine needs [ar3](https://github.com/witw-llc/ar3)
running already:

```bash
mkdir -p ~/browsers/garmin
a8s add garmin ~/browsers/garmin ~/.a8s-browser/definitions/browser.json \
  --A8S_BROWSER=$HOME/.a8s-browser/a8s-browser \
  --A8S_BROWSER_ALLOW=dresden
a8s start garmin
```

`A8S_BROWSER_ALLOW` is the comma-separated allowlist of senders — unset, the
seat refuses everyone. Add another later with
`a8s vars garmin set A8S_BROWSER_ALLOW dresden,gropple`. Now
`tell garmin - <<'EOF' … EOF` from an allowed seat runs the script in the
logged-in browser and sends back the transcript and artifacts.

## How a seat works

```
tell → a8s wake → a8s-browser handle → playwright-cli -s=<seat>
                                              ↓ CDP
                                       Chrome --user-data-dir=<state>/<seat>/chrome
```

Chrome is launched directly and playwright attaches over CDP afterwards, so the
browser carries none of the automation flags a launcher would set. The profile
directory is the session: cookies survive restarts because Chrome persists them
the way it does for a person.

Everything a seat owns is keyed by its name — profile directory, CDP port
(derived from the name, so two seats never collide), artifacts, saved state.
They live under `${XDG_DATA_HOME:-~/.local/share}/a8s-browser`, away from the
install directory an update overwrites; `A8S_BROWSER_HOME` moves them.

## Command vocabulary

One command per line. A run stops at the first failure and attaches a snapshot
of the page it died on.

| | |
|---|---|
| `go <url>` | navigate |
| `back` / `forward` / `reload` | history and refresh |
| `snap` | attach the accessibility snapshot (text, with the refs `click`/`fill` take) |
| `find <text>` | search the snapshot for text, returning matching nodes with refs |
| `shot` | attach a screenshot |
| `click <target>` / `fill <target> <text>` / `press <key>` / `type <text>` | interact |
| `select <target> <value>` / `check <target>` / `uncheck <target>` / `hover <target>` | more interaction |
| `scroll <dy>` | wheel-scroll the page |
| `dialog-accept [prompt]` / `dialog-dismiss` | answer a modal dialog |
| `wait <seconds>` / `wait-for <selector> [secs]` / `wait-for-url <substr> [secs]` | let something settle |
| `assert-text <text>` / `assert-url <substr>` | fail the run unless the page matches |
| `url` / `text <selector>` | report where the browser is / what an element says |
| `console [level]` | attach the page console log (optionally `debug`/`info`/`warning`/`error` and up) |
| `requests` | list the page's network requests |
| `video-start [name]` / `video-chapter <title>` / `video-stop` | record a .webm of the run; `stop` attaches it |
| `open` / `close` / `save` | session lifecycle |
| `eval <js>` | arbitrary JavaScript — refused unless the seat opts in |

`click`, `fill`, `select`, `check`, `uncheck` and `hover` take a CSS selector
or the element's visible text/label — quote a multi-word label
(`fill "Full name" Neil`). `eval`, `type`, `find`, `assert-text`,
`dialog-accept` and `video-chapter` take the rest of the line verbatim, so
`eval console.log('x')` and `video-chapter it's done` need no quoting.

`video-start` begins a recording that survives across tells until
`video-stop` flushes and attaches the file — record a long flow over several
messages, not just one script. `close` stops and salvages a recording still in
progress.

Prefer `snap` over `shot`: the snapshot is text, it is cheap for an agent to
read, and its refs are what you click by. Ask for pixels when you need to see
pixels.

## Trust

A browser seat holds live logins, and a message is an instruction to use them.
Two deliberate limits:

**Nobody is allowed by default.** `A8S_BROWSER_ALLOW` is a comma-separated
list of senders whose tells this seat will act on, set as a per-node a8s var
(`a8s vars garmin set A8S_BROWSER_ALLOW dresden,gropple`) so each seat gets
its own list from the shared definition. Unset means it refuses everything.
The router force-stamps `from` for local nodes, but a node reached over a
remote asserts its own name — so the allowlist is a filter, not proof of
identity, and the broker's own access control is what keeps strangers off the
topic.

**`eval` is off.** It is arbitrary code on the machine holding the profile.
Turn it on per seat with `a8s vars garmin set A8S_BROWSER_ALLOW_EVAL 1`.

Credentials live on the seat's machine and never travel in a tell. Log the
profile in once by hand; it stays logged in.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/neilobremski/a8s-browser/main/get.sh | sh
```

Clones to `~/.a8s-browser` and sources `install.sh` from your shell rc, which
puts `a8s-browser` on `PATH`. Re-run it to update. There is nothing to build
and nothing to pip install — the CLI is Python standard library only.

Two things it does not install: **Chrome**, and **`playwright-cli`**, which is
a Node package. The first command that needs playwright-cli offers to `npm
install -g` it for you; a seat woken by a8s has no terminal to ask on, so it
fails with the command instead. `a8s-browser doctor` reports what is missing.

## Setup notes

The `a8s add` in the quickstart stores the definition *path*, so every seat
registered against `~/.a8s-browser/definitions/browser.json` shares the one
file — per-seat settings go through a8s vars, not edits to that file:

```bash
a8s vars garmin set A8S_BROWSER_ALLOW dresden,gropple   # who may drive it
a8s vars garmin set A8S_BROWSER_ALLOW_EVAL 1            # permit `eval`
a8s vars garmin                                          # show what's set
```

A wake inherits the environment of whatever ran `a8s start`, so if the handler
can't find `playwright-cli` or `tell` there, record a PATH for wakes with
`a8s config set wake_path "$PATH"` or add `"PATH": "..."` to the definition's
`env`.

The same knobs work when running `handle` by hand — as flags
(`--allow=…`, `--allow-eval`) or as the `A8S_BROWSER_ALLOW` /
`A8S_BROWSER_ALLOW_EVAL` environment variables.

Other environment overrides: `A8S_BROWSER_HOME` (where seat state lives),
`A8S_BROWSER_CHROME` (browser binary), `A8S_BROWSER_PORT` (CDP port instead of
the seat-derived one), `A8S_BROWSER_INSTALL_PLAYWRIGHT=1` (answer the
playwright-cli install prompt without asking).

## Tests

```bash
tests/run
```

Builds a venv at `tests/.venv` and runs pytest in it; arguments pass through.
The suite stubs playwright-cli, so it needs no browser.

## Origin

The session layer began as `b3t` in [neilobremski/bin](https://github.com/neilobremski/bin),
where it drives one browser for one newsletter pipeline. Here it is generalised
so the seat name selects the profile.
