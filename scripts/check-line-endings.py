#!/usr/bin/env python3
"""Validate Git-tracked files against .gitattributes EOL rules."""

import argparse
import subprocess
import sys


class Arguments(argparse.Namespace):
    staged: bool = False
    worktree: bool = False


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        check=True,
    ).stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    _ = group.add_argument("--staged", action="store_true")
    _ = group.add_argument("--worktree", action="store_true")
    args = parser.parse_args(namespace=Arguments())

    entries = git("ls-files", "--eol", "-z").split(b"\0")
    failures: list[tuple[str, str, str]] = []

    for entry in entries:
        if not entry:
            continue

        metadata, path_bytes = entry.split(b"\t", 1)
        fields = metadata.decode("ascii").split()

        if len(fields) != 3:
            continue

        index_eol, worktree_eol, attr = fields

        if "eol=crlf" in attr:
            expected = "crlf"
        elif "eol=lf" in attr:
            expected = "lf"
        else:
            continue

        path = path_bytes.decode("utf-8", errors="surrogateescape")

        if args.staged:
            # Git's index should contain normalized LF.
            actual = index_eol.removeprefix("i/")
            required = "lf"
        else:
            actual = worktree_eol.removeprefix("w/")
            required = expected

        if actual != required:
            failures.append((path, actual, required))

    if failures:
        print("Line-ending violations detected:\n")
        for path, actual, required in failures:
            print(f"  {path}: {actual} (expected {required})")

        print(f"\nFailed: {len(failures)} file(s)")
        return 1

    mode = "staged index" if args.staged else "working tree"
    print(f"Line endings OK ({mode}).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        print(f"Git command failed: {exc}", file=sys.stderr)
        sys.exit(2)
