"""Operator-reviewed NPC knowledge provenance, replay and HTML5 compilation."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys

from .cast import CastStore
from .knowledge import (
    KnowledgeStore, approve_knowledge, edit_knowledge,
    propose_knowledge, prove_knowledge,
)
from .session import SessionStore
from .world_canon import CanonError, WorldStore, digest, strict_json


def _operation(path: str):
    if not hasattr(os, "O_NOFOLLOW"):
        raise CanonError("platform_not_supported")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 524288:
            raise CanonError("unsafe_operation_file")
        with os.fdopen(os.dup(fd), "rb") as stream:
            return strict_json(stream.read(524289))
    finally:
        os.close(fd)


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-knowledge")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("--world-id", required=True)
    proposal.add_argument("--prompt", required=True)
    proposal.add_argument("--fact-id", required=True)
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--detail", required=True)
    proposal.add_argument("--choice", required=True)
    proposal.add_argument("--speaker", required=True)
    proposal.add_argument("--recipient", default="player")
    for action in ("inspect", "edit", "approve", "proof", "compile",
                   "verify", "player"):
        command = sub.add_parser(action)
        command.add_argument("--world-id", required=True)
        if action in {"edit", "approve", "compile"}:
            command.add_argument("--expected-digest", required=True)
        if action == "edit":
            command.add_argument("--operation-file", required=True)
        if action == "approve":
            command.add_argument("--note", required=True)
        if action == "player":
            command.add_argument("--slot", required=True)
    args = parser.parse_args(argv)
    try:
        store = KnowledgeStore(args.store)
        world = WorldStore(args.store).read(args.world_id)
        cast = CastStore(args.store).read(args.world_id)
        if args.action == "propose":
            data = propose_knowledge(
                world, cast, prompt=args.prompt, fact_id=args.fact_id,
                title=args.title, detail=args.detail, choice=args.choice,
                speaker=args.speaker, recipient=args.recipient,
            )
            lease = store.publish(args.world_id, data, create=True)
            result = {"ok": True, "knowledge_digest": lease,
                      "review_required": True, "knowledge": data}
        elif args.action == "inspect":
            data = store.read(args.world_id)
            result = {"ok": True, "knowledge_digest": digest(data),
                      "knowledge": data, "review_required": not data["approved"]}
        elif args.action == "edit":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_knowledge")
            updated = edit_knowledge(data, world, cast,
                                     _operation(args.operation_file))
            lease = store.publish(args.world_id, updated,
                                  expected_digest=args.expected_digest)
            result = {"ok": True, "knowledge_digest": lease,
                      "review_required": True}
        elif args.action == "approve":
            data = store.read(args.world_id)
            if digest(data) != args.expected_digest:
                raise CanonError("stale_knowledge")
            updated = approve_knowledge(data, world, cast, args.note)
            lease = store.publish(args.world_id, updated,
                                  expected_digest=args.expected_digest)
            result = {"ok": True, "knowledge_digest": lease,
                      "review_required": False}
        elif args.action == "proof":
            result = {"ok": True, "proof": prove_knowledge(
                store.read(args.world_id), world, cast)}
        elif args.action == "compile":
            result = {"ok": True, "receipt": store.compile(
                args.world_id, args.expected_digest)}
        elif args.action == "verify":
            result = {"ok": True, "receipt": store.verify(args.world_id)}
        else:
            session = SessionStore(args.store).read(args.world_id, args.slot)
            result = {"ok": True, "player": store.player(
                args.world_id, session["choices"])}
    except (CanonError, OSError, UnicodeError, ValueError) as exc:
        code = exc.code if isinstance(exc, CanonError) else "io_error"
        print(json.dumps({"ok": False, "error": code}, sort_keys=True))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
