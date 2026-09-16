"""Scan git diffs for PII patterns from PII_PATTERNS env or a local patterns file."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_PATTERNS_FILE = Path(__file__).resolve().parent / "pii-patterns.local.txt"
EXAMPLE_PATTERNS_FILE = Path(__file__).resolve().parent / "pii-patterns.example.txt"


def parse_patterns(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


class NoPatterns(RuntimeError):
    """Nothing was loaded to scan for.

    A checker holding zero patterns matches nothing and prints success, which
    is the one result worse than not running it: a green check that proves
    nothing. Being unconfigured and being configured with a comment are the
    same outcome, so they raise the same thing.
    """


HOW_TO_CONFIGURE = (
    f"  Local: copy {EXAMPLE_PATTERNS_FILE.name} to {LOCAL_PATTERNS_FILE.name}\n"
    "  CI: set GitHub Actions secret PII_PATTERNS"
)


def _require_patterns(patterns: list[str], source: str) -> list[str]:
    if not patterns:
        raise NoPatterns(
            f"PII patterns came from {source} and parsed to none.\n"
            f"{HOW_TO_CONFIGURE}"
        )
    return patterns


def load_patterns() -> list[str]:
    env = os.environ.get("PII_PATTERNS", "").strip()
    if env:
        return _require_patterns(
            parse_patterns(env), "the PII_PATTERNS environment variable"
        )
    if LOCAL_PATTERNS_FILE.is_file():
        return _require_patterns(
            parse_patterns(LOCAL_PATTERNS_FILE.read_text(encoding="utf-8")),
            str(LOCAL_PATTERNS_FILE),
        )
    raise NoPatterns(f"PII patterns not configured.\n{HOW_TO_CONFIGURE}")


def _resolve_main_ref(repo_root: Path) -> str | None:
    for ref in ("origin/main", "main"):
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return ref
    return None


class GitUnavailable(RuntimeError):
    """The diff could not be produced, which is not the same as an empty one.

    A gate that turns "git could not answer" into "nothing to report" passes
    every branch it cannot read. An unknown ref, a detached checkout with no
    main, a repo the runner cannot open — each one used to exit 0 here.
    """


def diff_range(range_spec: str, repo_root: Path | None = None) -> str:
    root = repo_root or REPO_ROOT
    proc = subprocess.run(
        ["git", "diff", range_spec, "--", "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitUnavailable(
            f"git diff {range_spec} failed in {root} "
            f"({proc.stderr.strip() or f'exit {proc.returncode}'})"
        )
    return proc.stdout


def diff_vs_main(repo_root: Path | None = None) -> str:
    root = repo_root or REPO_ROOT
    base = _resolve_main_ref(root)
    if base is None:
        raise GitUnavailable(
            f"no main ref to diff against in {root} "
            "(tried origin/main and main)"
        )
    return diff_range(f"{base}...HEAD", root)


def added_lines(diff: str) -> list[str]:
    return [
        ln[1:]
        for ln in diff.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    ]


def added_lines_with_paths(diff: str) -> list[tuple[str, str]]:
    """Added lines paired with the file they land in, so a failure can name a
    place without quoting what is there."""
    out: list[tuple[str, str]] = []
    path = "?"
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            target = ln[4:].strip()
            path = target[2:] if target.startswith("b/") else target
        elif ln.startswith("+"):
            out.append((path, ln[1:]))
    return out


def find_violations(diff: str, patterns: list[str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for line in added_lines(diff):
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                hits.append((pattern, line))
                break
    return hits


def locate_violations(diff: str, patterns: list[str]) -> list[tuple[str, int]]:
    """The same scan, reported as (file, 1-based pattern number). Nothing in
    the return value is PII, so it is safe to print."""
    hits: list[tuple[str, int]] = []
    for path, line in added_lines_with_paths(diff):
        for index, pattern in enumerate(patterns, 1):
            if re.search(pattern, line, re.IGNORECASE):
                hits.append((path, index))
                break
    return hits


def check_diff(diff: str, patterns: list[str] | None = None) -> list[tuple[str, str]]:
    pats = patterns if patterns is not None else load_patterns()
    return find_violations(diff, pats)


def check_branch(repo_root: Path | None = None, range_spec: str | None = None) -> list[tuple[str, str]]:
    root = repo_root or REPO_ROOT
    diff = diff_range(range_spec, root) if range_spec else diff_vs_main(root)
    return check_diff(diff)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a git diff for PII patterns.")
    parser.add_argument(
        "--range",
        metavar="REV",
        help='git diff range to scan (default: origin/main...HEAD or main...HEAD)',
    )
    args = parser.parse_args(argv)
    try:
        patterns = load_patterns()
    except NoPatterns as e:
        print(str(e), file=sys.stderr)
        print(
            "pii-check: refusing to report clean with no patterns loaded.",
            file=sys.stderr,
        )
        return 1
    root = REPO_ROOT
    try:
        diff = diff_range(args.range, root) if args.range else diff_vs_main(root)
    except GitUnavailable as e:
        print(f"pii-check: {e}", file=sys.stderr)
        print(
            "pii-check: refusing to report clean on a diff it could not read.",
            file=sys.stderr,
        )
        return 1
    violations = locate_violations(diff, patterns)
    if not violations:
        print("No PII patterns found in diff.")
        return 0
    # Neither the matched line nor the pattern is printed. Both are the PII,
    # and this output lands in CI logs — a pattern is a bare name or hostname,
    # and GitHub masks a secret's whole value, not the individual lines inside
    # it. The file and the pattern's position in the loaded list are enough to
    # find it locally and mean nothing to anyone reading the log.
    for path, index in violations[:20]:
        print(f"{path}: matches PII pattern #{index}", file=sys.stderr)
    if len(violations) > 20:
        print(f"... and {len(violations) - 20} more", file=sys.stderr)
    print(
        f"\nRemove PII before merging. {len(patterns)} pattern(s) loaded.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
