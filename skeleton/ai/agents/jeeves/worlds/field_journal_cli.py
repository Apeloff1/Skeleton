"""Player field journal CLI with replay and optimistic source leases."""
from __future__ import annotations

import argparse
import json
import sys

from .field_journal import FieldJournalStore
from .world_canon import CanonError


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton world-field-journal")
    parser.add_argument("--store", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("create", "inspect", "preview", "append", "edit",
                   "compile", "verify", "editor"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--world-id", required=True)
        cmd.add_argument("--slot", required=True)
        if action in {"preview", "append", "edit"}:
            cmd.add_argument("--note-id", required=True)
            cmd.add_argument("--text", required=True)
        if action in {"append", "edit", "compile", "editor"}:
            cmd.add_argument("--expected-journal-digest", required=True)
        if action in {"append", "compile"}:
            cmd.add_argument("--expected-session-digest", required=True)
    args = parser.parse_args(argv)
    try:
        store = FieldJournalStore(args.store)
        if args.action == "create":
            result = store.create(args.world_id, args.slot)
        elif args.action == "inspect":
            result = store.inspect(args.world_id, args.slot)
        elif args.action == "preview":
            result = store.preview(args.world_id, args.slot,
                                   note_id=args.note_id, text=args.text)
        elif args.action == "append":
            result = store.append(
                args.world_id, args.slot, note_id=args.note_id,
                text=args.text,
                expected_journal_digest=args.expected_journal_digest,
                expected_session_digest=args.expected_session_digest)
        elif args.action == "edit":
            result = store.edit(
                args.world_id, args.slot, note_id=args.note_id,
                text=args.text,
                expected_journal_digest=args.expected_journal_digest)
        elif args.action == "compile":
            result = store.compile(
                args.world_id, args.slot,
                expected_journal_digest=args.expected_journal_digest,
                expected_session_digest=args.expected_session_digest)
        elif args.action == "verify":
            result = store.verify(args.world_id, args.slot)
        else:
            result = store.editor(args.world_id, args.slot,
                                  args.expected_journal_digest)
    except (CanonError, OSError, TypeError, ValueError) as exc:
        error = exc.code if isinstance(exc, CanonError) else "field_journal_invalid_input"
        print(json.dumps({"ok": False, "error": error}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, "result": result},
                     ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
