"""Reviewed interactive dialogue CLI: proposal, edit, proof, play and commit."""
from __future__ import annotations

import argparse
import json
import sys

from .dialogue_graph import DialogueStore
from .world_canon import CanonError, strict_json


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-dialogue")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("propose", "inspect", "save", "edit", "approve", "editor",
                   "compile", "verify", "player", "choose"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        if action == "propose":
            for key in ("prompt", "conversation-id", "actor", "scene", "text",
                        "response-id", "label", "world-choice"):
                cmd.add_argument("--" + key, required=True)
        if action in ("save", "edit", "approve", "editor", "compile"):
            cmd.add_argument("--expected-digest")
        if action == "save":
            cmd.add_argument("--source-json", required=True)
            cmd.add_argument("--create", action="store_true")
        if action == "edit":
            cmd.add_argument("--operation-json", required=True)
        if action == "approve":
            cmd.add_argument("--review-note", required=True)
        if action in ("player", "choose"):
            cmd.add_argument("--slot", required=True)
            cmd.add_argument("--conversation", required=True)
            cmd.add_argument("--responses-json", required=True)
        if action == "choose":
            cmd.add_argument("--expected-session-digest", required=True)
            cmd.add_argument("--expected-dialogue-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = DialogueStore(args.store)
        if args.action == "propose":
            result = {"proposal": store.propose(
                args.world_id, prompt=args.prompt,
                conversation_id=args.conversation_id, actor=args.actor,
                scene=args.scene, text=args.text,
                response_id=args.response_id, label=args.label,
                world_choice=args.world_choice), "review_required": True}
        elif args.action == "inspect":
            result = store.inspect(args.world_id)
        elif args.action == "save":
            result = {"dialogue_digest": store.publish(
                args.world_id, strict_json(args.source_json.encode("utf-8")),
                expected_digest=args.expected_digest, create=args.create)}
        elif args.action == "edit":
            result = {"dialogue_digest": store.edit(
                args.world_id, args.expected_digest,
                strict_json(args.operation_json.encode("utf-8")))}
        elif args.action == "approve":
            result = {"dialogue_digest": store.approve(
                args.world_id, args.expected_digest, args.review_note)}
        elif args.action == "editor":
            result = store.editor(args.world_id, args.expected_digest)
        elif args.action == "compile":
            result = {"receipt": store.compile(args.world_id, args.expected_digest)}
        elif args.action == "player":
            result = store.player(
                args.world_id, args.slot, args.conversation,
                strict_json(args.responses_json.encode("utf-8")))
        elif args.action == "choose":
            result = store.choose(
                args.world_id, args.slot, args.conversation,
                strict_json(args.responses_json.encode("utf-8")),
                expected_session_digest=args.expected_session_digest,
                expected_dialogue_digest=args.expected_dialogue_digest)
        else:
            result = {"receipt": store.verify(args.world_id)}
    except (CanonError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "invalid_input"},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
