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
import tempfile

from skeleton.game.presentation.flgb_presentation_runtime import PresentationContractError
from skeleton.game.presentation.input_router import InputEvent, InputProfile, InputSession

MAX_READ = 2_000_000


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PresentationContractError("duplicate input JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise PresentationContractError("non-finite input JSON constant: " + value)


def _read(path: Path) -> object:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_READ:
            raise PresentationContractError("input must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            data = stream.read(MAX_READ + 1)
        if len(data) > MAX_READ:
            raise PresentationContractError("input byte budget exceeded")
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    finally:
        os.close(fd)


def _write_new(path: Path, value: object) -> None:
    data = (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ) + "\n").encode("utf-8")
    if len(data) > MAX_READ:
        raise PresentationContractError("input receipt exceeds file budget")
    fd, temporary = tempfile.mkstemp(prefix=".input-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--rebind")
    parser.add_argument("--control")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--out-profile", type=Path, help="Write a new revisioned profile")
    parser.add_argument("--resume", type=Path, help="Verified prior input session")
    parser.add_argument("--out-session", type=Path, help="Write a new replayable session")
    parser.add_argument("--game-source", type=Path, help="Route inputs into original playable grid game")
    parser.add_argument("--goal-ending", help="Select an authored ending for confirm")
    parser.add_argument("--out-game", type=Path, help="Write new replay-bound input/game report")
    args = parser.parse_args(argv)
    try:
        profile = InputProfile.load(_read(args.profile))
        if args.rebind is not None:
            if (args.events is not None or args.control is None or args.revision is None
                    or args.resume is not None or args.out_session is not None
                    or args.game_source is not None or args.goal_ending is not None
                    or args.out_game is not None):
                raise PresentationContractError("rebind requires --control and --revision only")
            revised = profile.rebind(args.rebind, args.control, args.revision)
            if args.out_profile is not None:
                _write_new(args.out_profile, revised.manifest())
            print(json.dumps({"profile": revised.manifest(), "digest": revised.digest}, sort_keys=True))
            return 0
        if (args.events is None or args.control is not None or args.revision is not None
                or args.out_profile is not None):
            raise PresentationContractError("routing requires --events")
        raw = _read(args.events)
        if not isinstance(raw, list) or len(raw) > 4096:
            raise PresentationContractError("invalid input event batch")
        if args.game_source is not None:
            if args.resume is not None or args.out_session is not None:
                raise PresentationContractError("gameplay routing forbids input resume/output")
            from skeleton.game.gameplay.offline_grid_campaign import Campaign
            from skeleton.game.presentation.input_gameplay_bridge import play_inputs
            campaign = Campaign.load(_read(args.game_source))
            result = play_inputs(
                campaign, profile, raw, selected_ending=args.goal_ending,
            )
            if args.out_game is not None:
                _write_new(args.out_game, result)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.goal_ending is not None or args.out_game is not None:
            raise PresentationContractError("game options require --game-source")
        session = (InputSession.restore(profile, _read(args.resume))
                   if args.resume is not None else InputSession(profile))
        for event in raw:
            session = session.step(InputEvent.load(event))
        if args.out_session is not None:
            _write_new(args.out_session, session.snapshot())
        print(json.dumps(session.snapshot(), sort_keys=True))
        return 0
    except (PresentationContractError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"input-router: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
