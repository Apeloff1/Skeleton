"""Private source-leased NPC conversation transcript operator CLI."""
from __future__ import annotations

import argparse
import json
import sys

from .dialogue_transcript import DialogueTranscriptStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-dialogue-transcript")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("begin", "inspect", "append", "commit", "cancel", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--slot", required=True)
        if action == "begin":
            cmd.add_argument("--conversation", required=True)
            cmd.add_argument("--expected-session-digest", required=True)
            cmd.add_argument("--expected-dialogue-digest", required=True)
        if action in ("append", "commit", "cancel"):
            cmd.add_argument("--expected-digest", required=True)
        if action == "append":
            cmd.add_argument("--response-id", required=True)
    args = parser.parse_args(argv)
    try:
        store = DialogueTranscriptStore(args.store)
        if args.action == "begin":
            result = store.begin(
                args.world_id, args.slot, args.conversation,
                expected_session_digest=args.expected_session_digest,
                expected_dialogue_digest=args.expected_dialogue_digest)
        elif args.action == "inspect":
            result = store.inspect(args.world_id, args.slot)
        elif args.action == "append":
            result = store.append(
                args.world_id, args.slot, args.response_id,
                args.expected_digest)
        elif args.action == "commit":
            result = {"receipt": store.commit(
                args.world_id, args.slot, args.expected_digest)}
        elif args.action == "cancel":
            store.cancel(args.world_id, args.slot, args.expected_digest)
            result = {"cancelled": True}
        else:
            result = {"receipt": store.verify_receipt(args.world_id, args.slot)}
    except (CanonError, OSError, UnicodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "error":
                          exc.code if isinstance(exc, CanonError) else "invalid_input"},
                         sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
