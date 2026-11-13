"""Operator-only authoring and compilation of narrative continuity promises."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .promises import (
    PromiseStore, approve_promises, edit_promises, propose_promises, prove_promises,
)
from .world_canon import CanonError, WorldStore, digest, strict_json


def _operation_bytes(args: argparse.Namespace) -> bytes:
    if args.operation_json is not None:
        return args.operation_json.encode("utf-8")
    fd = os.open(args.operation_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
            raise CanonError("unsafe_operation_file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            raw = stream.read(524289)
        if len(raw) > 524288:
            raise CanonError("operation_too_large")
        return raw
    finally:
        os.close(fd)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-promises")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    for name in ("world-id", "prompt", "promise-id", "title", "setup",
                 "payoff", "trigger-choice", "resolve-choice"):
        proposal.add_argument("--" + name, required=True)
    proposal.add_argument("--optional", action="store_true")
    for action in ("inspect", "edit", "approve", "proof", "compile", "verify", "player", "editor", "verify-editor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action in ("edit", "approve", "compile", "editor"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "edit":
            group = cmd.add_mutually_exclusive_group(required=True)
            group.add_argument("--operation-json")
            group.add_argument("--operation-file")
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = PromiseStore(args.store)
        if args.action == "editor":
            from .review_editor import ReviewEditorStore
            result = {"ok": True, "editor": ReviewEditorStore(args.store).render(
                args.world_id, "promises", args.expected_digest)}
        elif args.action == "verify-editor":
            from .review_editor import ReviewEditorStore
            result = {"ok": True, "editor": ReviewEditorStore(args.store).verify(
                args.world_id, "promises")}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        elif args.action == "player":
            result = {"ok": True, "player": store.player(args.world_id, args.slot)}
        else:
            world = WorldStore(args.store).read(args.world_id)
            if args.action == "propose":
                data = propose_promises(
                    world, prompt=args.prompt, promise_id=args.promise_id,
                    title=args.title, setup=args.setup, payoff=args.payoff,
                    trigger_choice=args.trigger_choice,
                    resolve_choice=args.resolve_choice, required=not args.optional)
                result = {"ok": True, "promises_digest": store.publish(
                    args.world_id, data, create=True), "review_required": True}
            else:
                data = store.read(args.world_id)
                if args.action == "inspect":
                    result = {"ok": True, "promises": data, "promises_digest": digest(data)}
                elif args.action == "proof":
                    result = {"ok": True, "proof": prove_promises(data, world)}
                else:
                    if digest(data) != args.expected_digest:
                        raise CanonError("stale_promises")
                    updated = (edit_promises(
                        data, world, strict_json(_operation_bytes(args)))
                        if args.action == "edit" else
                        approve_promises(data, world, args.note))
                    result = {"ok": True, "promises_digest": store.publish(
                        args.world_id, updated, expected_digest=args.expected_digest),
                        "review_required": not updated["approved"]}
    except (CanonError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "io_error"},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
