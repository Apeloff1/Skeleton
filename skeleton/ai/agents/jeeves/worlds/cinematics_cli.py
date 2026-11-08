"""CLI for author-reviewed source-bound original cinematic storyboards."""
from __future__ import annotations

import argparse
import json
import sys

from .cinematics import CinematicsStore, edit_cinematics
from .world_canon import CanonError, canonical, digest, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-cinematics")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "publish", "edit", "approve",
                   "compile", "verify", "editor", "player"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--id", required=True)
        if action in {"propose", "publish", "edit"}:
            cmd.add_argument("--file", required=True)
        if action in {"publish", "edit", "approve", "compile", "editor"}:
            cmd.add_argument("--expected-digest")
        if action == "publish":
            cmd.add_argument("--create", action="store_true")
        if action == "approve":
            cmd.add_argument("--note", required=True)
        if action == "player":
            cmd.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = CinematicsStore(args.store)
        if args.action in {"propose", "publish", "edit"}:
            with open(args.file, "rb") as stream:
                data = strict_json(stream.read(524289))
        if args.action == "propose":
            if type(data) is not dict or set(data) != {"prompt", "sequences"}:
                raise CanonError("cinematics_invalid_proposal")
            result = {"proposal": store.propose(args.id, **data),
                      "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.id)
        elif args.action == "publish":
            if not args.create and not args.expected_digest:
                raise CanonError("cinematics_expected_digest_required")
            result = {"cinematics_digest": store.publish(
                args.id, data, expected_digest=args.expected_digest,
                create=args.create), "review_required": True}
        elif args.action == "edit":
            if not args.expected_digest:
                raise CanonError("cinematics_expected_digest_required")
            snapshot = store.inspect(args.id)
            if digest(snapshot["cinematics"]) != args.expected_digest:
                raise CanonError("cinematics_stale_edit")
            from .world_canon import WorldStore
            world = WorldStore(args.store).read(args.id)
            updated = edit_cinematics(snapshot["cinematics"], world, data)
            result = {"cinematics_digest": store.publish(
                args.id, updated, expected_digest=args.expected_digest),
                "review_required": True}
        elif args.action == "approve":
            result = {"cinematics_digest": store.approve(
                args.id, args.expected_digest or "", args.note)}
        elif args.action == "compile":
            result = store.compile(args.id, args.expected_digest or "")
        elif args.action == "verify":
            result = store.verify(args.id)
        elif args.action == "editor":
            result = store.editor(args.id, args.expected_digest or "")
        else:
            result = store.player(args.id, args.slot)
    except (CanonError, OSError, TypeError, ValueError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "invalid_cinematics_input"
        print(json.dumps({"ok": False, "error": code}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
