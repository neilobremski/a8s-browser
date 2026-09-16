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
| `snap` | attach the accessibility snapshot (text, with the refs `click`/`fill` take) |
| `shot` | attach a screenshot |
| `click <ref>` / `fill <ref> <text>` / `press <key>` | interact |
| `wait <seconds>` | let something settle |
| `url` | report where the browser is |
| `open` / `close` / `save` | session lifecycle |
| `eval <js>` | arbitrary JavaScript — refused unless the seat opts in |

Prefer `snap` over `shot`: the snapshot is text, it is cheap for an agent to
read, and its refs are what you click by. Ask for pixels when you need to see
pixels.

## Trust

A browser seat holds live logins, and a message is an instruction to use them.
Two deliberate limits:

**Nobody is allowed by default.** `A8S_BROWSER_ALLOW` is a comma-separated list
of senders whose tells this seat will act on. Empty means it refuses
everything. The router force-stamps `from` for local nodes, but a node reached
over a remote asserts its own name — so the allowlist is a filter, not proof of
identity, and the broker's own access control is what keeps strangers off the
topic.

**`eval` is off.** It is arbitrary code on the machine holding the profile.
Turn it on per seat with `A8S_BROWSER_ALLOW_EVAL=1` when you want it.

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

## Setup

```bash
mkdir -p ~/browsers/garmin
a8s add garmin ~/browsers/garmin ~/.a8s-browser/definitions/browser.json \
  --A8S_BROWSER=$HOME/.a8s-browser/a8s-browser

a8s-browser -s garmin open     # log in by hand, once
a8s start garmin
```

Edit `env` in your copy of the definition to name the senders the seat accepts,
and `PATH` if the handler is started somewhere without your login shell's
`PATH` — a wake inherits the environment of whatever started it.

Drive a seat locally without a8s while you work out a flow:

```bash
a8s-browser -s garmin status
a8s-browser -s garmin do - <<'EOF'
go https://connect.garmin.com/modern/
snap
EOF
```

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
