"""Translate captured original game input events through a versioned profile.

python -m scripts.game.route_inputs --profile profile.json --events events.json
python -m scripts.game.route_inputs --profile profile.json --rebind BINDING --control NEW --revision N
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from skeleton.game.presentation.flgb_presentation_runtime import PresentationContractError
from skeleton.game.presentation.input_router import InputEvent, InputProfile, InputSession

MAX_READ = 262144


def _read(path: Path) -> object:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_READ:
            raise PresentationContractError("input must be a bounded regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_READ + 1)
        if len(data) > MAX_READ:
            raise PresentationContractError("input byte budget exceeded")
        return json.loads(data)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--rebind")
    parser.add_argument("--control")
    parser.add_argument("--revision", type=int)
    args = parser.parse_args(argv)
    try:
        profile = InputProfile.load(_read(args.profile))
        if args.rebind is not None:
            if args.events is not None or args.control is None or args.revision is None:
                raise PresentationContractError("rebind requires --control and --revision only")
            revised = profile.rebind(args.rebind, args.control, args.revision)
            print(json.dumps({"profile": revised.manifest(), "digest": revised.digest}, sort_keys=True))
            return 0
        if args.events is None or args.control is not None or args.revision is not None:
            raise PresentationContractError("routing requires --events")
        raw = _read(args.events)
        if not isinstance(raw, list) or len(raw) > 4096:
            raise PresentationContractError("invalid input event batch")
        session = InputSession(profile)
        for event in raw:
            session = session.step(InputEvent.load(event))
        print(json.dumps(session.snapshot(), sort_keys=True))
        return 0
    except (PresentationContractError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"input-router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
