"""Command-line playable Lantern Quay campaign and replay verifier."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, canonical, decode, demo_actions,
    export_bundle, load_source, verify_bundle,
)

DEFAULT_WORLD = Path(__file__).resolve().parent / "fixtures" / "harbor_lantern_quay.json"


def _read(path: str, maximum: int = MAX_BUNDLE_BYTES) -> bytes:
    try:
        if path == "-":
            return sys.stdin.buffer.read(maximum + 1)
        with Path(path).open("rb") as stream:
            return stream.read(maximum + 1)
    except OSError as exc:
        raise HarborError("cannot read requested input") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play, export, and replay-verify Lantern Quay")
    parser.add_argument("command", choices=("demo", "play", "verify"))
    parser.add_argument("--source", default=str(DEFAULT_WORLD))
    parser.add_argument("--actions", help="JSON array file or '-' for stdin, required for play")
    parser.add_argument("--bundle", help="JSON bundle file or '-' for stdin, required for verify")
    parser.add_argument("--require-win", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            if not args.bundle:
                raise HarborError("--bundle is required for verify")
            state = verify_bundle(decode(_read(args.bundle)), require_win=args.require_win)
            output = {"verified": True, "state": state}
        else:
            source = load_source(Path(args.source))
            if args.command == "demo":
                actions = demo_actions()
            else:
                if not args.actions:
                    raise HarborError("--actions is required for play")
                actions = decode(_read(args.actions))
            output = export_bundle(source, actions, require_win=args.require_win)
        sys.stdout.buffer.write(canonical(output) + b"\n")
        return 0
    except HarborError as exc:
        print("harbor: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
