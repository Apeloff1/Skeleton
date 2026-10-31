"""Installed offline crafting CLI: python -m skeleton.game.gameplay.crafting_cli."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

from .crafting_runtime import (
    CraftAction, CraftEngine, CraftPlan, GameplayContractError,
)

MAX_INPUT_BYTES = 1_048_576


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise GameplayContractError("duplicate JSON key")
        result[key] = value
    return result


def _read(path: Path) -> object:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
            raise GameplayContractError("input must be a bounded regular file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise GameplayContractError("input byte budget exceeded")
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(GameplayContractError("non-finite JSON")),
        )
    finally:
        os.close(fd)


def _write_new(path: Path, value: object) -> None:
    data = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
    if len(data) > MAX_INPUT_BYTES:
        raise GameplayContractError("save byte budget exceeded")
    fd, tmp = tempfile.mkstemp(prefix=".craft-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline source-bound crafting transactions")
    parser.add_argument("command", choices=("inspect", "run", "verify", "play"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--actions", type=Path)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = CraftPlan.parse(_read(args.plan))
        engine = CraftEngine(plan)
        if args.command == "inspect":
            if any((args.actions, args.save, args.resume)):
                raise GameplayContractError("inspect accepts only a plan")
            result = {"world_id": plan.world_id, "plan_digest": plan.digest,
                      "recipes": [recipe.recipe_id for recipe in plan.recipes]}
        elif args.command == "verify":
            if args.save is None or args.actions is not None or args.resume is not None:
                raise GameplayContractError("verify requires --save")
            state = engine.restore(_read(args.save))
            result = {"state": state.state_record(), "state_digest": state.digest}
        elif args.command == "run":
            if args.actions is None or args.save is None or args.resume is not None:
                raise GameplayContractError("run requires --actions and --save")
            raw = _read(args.actions)
            if not isinstance(raw, list):
                raise GameplayContractError("actions must be a list")
            actions = []
            for action in raw:
                if not isinstance(action, dict) or set(action) != {"sequence", "recipe_id", "batches"}:
                    raise GameplayContractError("invalid craft action")
                actions.append(CraftAction(**action))
            state = engine.replay(actions)
            _write_new(args.save, state.save_record())
            result = {"state": state.state_record(), "state_digest": state.digest}
        else:
            if args.save is None or args.actions is not None:
                raise GameplayContractError("play requires --save and forbids --actions")
            state = engine.restore(_read(args.resume)) if args.resume is not None else engine.start()
            while len(state.actions) < 10000:
                print("Owned: " + json.dumps(state.state_record(), sort_keys=True), flush=True)
                print("Recipes: " + ", ".join(recipe.recipe_id for recipe in plan.recipes), flush=True)
                try:
                    choice = input("Craft recipe ID, or quit: ").strip()
                except EOFError:
                    choice = "quit"
                if choice == "quit":
                    break
                if choice not in plan.by_id:
                    print("Unknown recipe; no state change.", flush=True)
                    continue
                try:
                    state = engine.apply(state, CraftAction(len(state.actions), choice))
                except GameplayContractError as exc:
                    print("Craft rejected: " + str(exc), flush=True)
            _write_new(args.save, state.save_record())
            result = {"state": state.state_record(), "state_digest": state.digest}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GameplayContractError, ValueError, TypeError, KeyError, UnicodeError, OSError) as exc:
        print("crafting rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
