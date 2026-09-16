#!/bin/sh
# a8s-browser one-line installer:
#
#   curl -fsSL https://raw.githubusercontent.com/neilobremski/a8s-browser/main/get.sh | sh
#
# Installs into $A8S_BROWSER_INSTALL (default ~/.a8s-browser) and adds one
# source line to your shell rc. Re-running updates in place. Overrides:
#   A8S_BROWSER_INSTALL=/somewhere   install location
#   A8S_BROWSER_REPO=<url>           source repo
#
# Python-side there is nothing to install: the CLI is stdlib-only, so this is
# a clone and a PATH line. Chrome and playwright-cli are the browser's own
# prerequisites and are handled on first use, not here; `a8s-browser doctor`
# reports whatever is still missing at the end.
#
# Wrapped in main() so a truncated pipe cannot run a partial script.
set -eu

main() {
  DIR="${A8S_BROWSER_INSTALL:-$HOME/.a8s-browser}"
  REPO="${A8S_BROWSER_REPO:-https://github.com/neilobremski/a8s-browser.git}"

  command -v git >/dev/null 2>&1 || {
    echo "a8s-browser: git is required" >&2
    exit 1
  }
  command -v python3 >/dev/null 2>&1 || {
    echo "a8s-browser: python3 is required" >&2
    exit 1
  }

  if [ -d "$DIR/.git" ]; then
    echo "Updating a8s-browser in $DIR"
    git -C "$DIR" pull --ff-only
  else
    if [ -e "$DIR" ]; then
      echo "a8s-browser: $DIR exists and is not a checkout; move it or set A8S_BROWSER_INSTALL" >&2
      exit 1
    fi
    echo "Installing a8s-browser into $DIR"
    git clone --depth 1 "$REPO" "$DIR"
  fi

  _add_to_rc "$DIR"

  echo
  "$DIR/a8s-browser" doctor || true
  echo
  echo "Register a seat (one per browser profile):"
  echo "  a8s add <seat> <seat-dir> $DIR/definitions/browser.json"
  echo "then set A8S_BROWSER_ALLOW in that seat's definition.env to the"
  echo "senders allowed to drive it — an empty allowlist accepts nobody."
}

_add_to_rc() {
  dir="$1"
  set -- "$HOME/.profile"
  case "${SHELL:-/bin/sh}" in
    */zsh) set -- "$HOME/.zshrc" ;;
    */bash)
      if   [ -f "$HOME/.bash_profile" ]; then login="$HOME/.bash_profile"
      elif [ -f "$HOME/.bash_login" ];   then login="$HOME/.bash_login"
      else                                    login="$HOME/.profile"
      fi
      set -- "$HOME/.bashrc" "$login"
      ;;
    *)
      [ -f "$HOME/.bashrc" ] && set -- "$@" "$HOME/.bashrc"
      [ -f "$HOME/.zshrc" ]  && set -- "$@" "$HOME/.zshrc"
      ;;
  esac

  line=". \"$dir/install.sh\""
  for rc in "$@"; do
    if grep -qsF "$dir/install.sh" "$rc"; then
      echo "Shell rc already sources install.sh ($rc)"
    else
      printf '\n# a8s-browser (https://github.com/neilobremski/a8s-browser)\n%s\n' "$line" >> "$rc"
      echo "Added to $rc: $line"
    fi
  done
}

main "$@"
