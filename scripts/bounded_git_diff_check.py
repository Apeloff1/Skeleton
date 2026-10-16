#!/usr/bin/env python3
"""Run Git's whitespace gate without exhausting GitHub Actions log limits.

The exit code is Git's real exit code. Only diagnostics are abbreviated, not
the inspected diff, so a failing patch cannot be made to pass by log clipping.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

MAX_CAPTURE_BYTES = 16 * 1024
MAX_DISPLAY_LINES = 40
MAX_DISPLAY_LINE_CHARS = 320
CHUNK_BYTES = 64 * 1024


def inspect(base: str, head: str) -> int:
    command = [
        "git", "diff", "--check", base, head, "--", ".",
        ":!skeleton/ai/research/legacy/**",
    ]
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
    except OSError as exc:
        print(f"git diff --check: cannot launch git: {exc!r}", file=sys.stderr)
        return 2

    prefix = bytearray()
    output_bytes = 0
    assert process.stdout is not None
    with process.stdout:
        while True:
            chunk = process.stdout.read(CHUNK_BYTES)
            if not chunk:
                break
            output_bytes += len(chunk)
            if len(prefix) < MAX_CAPTURE_BYTES:
                prefix.extend(chunk[: MAX_CAPTURE_BYTES - len(prefix)])
    exit_code = process.wait()
    if exit_code == 0:
        print("git diff --check: OK")
        return 0

    print(f"git diff --check: FAIL (exit={exit_code}; diagnostic bytes={output_bytes})")
    lines = prefix.decode("utf-8", errors="replace").splitlines()
    for line in lines[:MAX_DISPLAY_LINES]:
        # repr() prevents untrusted filenames from injecting Actions log commands.
        print(f"  {line[:MAX_DISPLAY_LINE_CHARS]!r}")
    shown = sum(len(line.encode("utf-8", errors="replace")) for line in lines[:MAX_DISPLAY_LINES])
    if output_bytes > shown or len(lines) > MAX_DISPLAY_LINES:
        print(
            f"  [diagnostics bounded to {MAX_CAPTURE_BYTES} bytes / "
            f"{MAX_DISPLAY_LINES} lines; Git's failure status is preserved]"
        )
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    return inspect(args.base, args.head)


if __name__ == "__main__":
    raise SystemExit(main())
