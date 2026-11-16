"""Installed offline expedition gameplay, evidence, recovery and durable journal CLI."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import BinaryIO, Sequence, TextIO

from skeleton.app.gameforge_campaign_cli import open_workspace
from skeleton.app.gameforge_expedition import (
    build_expedition, play_expedition, resume_expedition, verify_expedition,
)
from skeleton.app.gameforge_expedition_author import author_expedition, verify_authoring
from skeleton.app.gameforge_expedition_board import (
    episode_evidence, expedition_board, turn, verify_board, verify_evidence,
)
from skeleton.app.gameforge_expedition_recovery import (
    compare_expeditions, plan_expedition, verify_comparison, verify_plan,
)
from skeleton.app.original_quest_cli import _encode, _integer, _object, _require, read_document
from skeleton.gameforge.errors import GameForgeError

PERSISTENT = frozenset({
    "create-slot", "append-slot", "read-slot", "history", "fork-slot",
    "snapshot-slot", "restore-slot", "board-slot", "turn-slot", "assist-slot",
    "apply-recovery-slot", "compare-slots",
})


def _budgets(data: dict) -> dict:
    return {"dialogue_budget": data.get("dialogue_budget", 1024),
            "local_budget": data.get("local_budget", 1024)}


def _persistent(cmd: str, path: Path, value: object) -> dict:
    fields = {"request", "slot"}
    optional: set[str] = set()
    required = {
        "create-slot": {"operation"},
        "append-slot": {"operation", "expected_revision", "additional"},
        "fork-slot": {"parent_revision", "expected_digest", "child_slot"},
        "restore-slot": {"archive"},
        "turn-slot": {"operation", "expected_revision", "board_digest", "index"},
        "apply-recovery-slot": {"operation", "expected_revision", "recovery"},
        "compare-slots": {"other_slot"},
    }
    if cmd in {"read-slot", "board-slot", "assist-slot", "compare-slots"}:
        optional.add("revision")
    if cmd in {"assist-slot", "compare-slots"}:
        optional.update({"dialogue_budget", "local_budget"})
    if cmd == "compare-slots":
        optional.add("other_revision")
    data = _object(value, fields | required.get(cmd, set()), optional)
    source, slot = data["request"], data["slot"]
    with open_workspace(path, create=cmd in {"create-slot", "restore-slot"}, expedition=True) as store:
        if cmd == "create-slot":
            return store.create(slot, source, data["operation"])
        if cmd == "append-slot":
            return store.append(slot, source, data["expected_revision"], data["operation"], data["additional"])
        if cmd == "history":
            return store.history(slot, source)
        if cmd == "fork-slot":
            return store.fork(slot, source, data["parent_revision"], data["expected_digest"], data["child_slot"])
        if cmd == "snapshot-slot":
            return store.snapshot(slot, source)
        if cmd == "restore-slot":
            return store.restore(slot, source, data["archive"])

        if cmd in {"turn-slot", "apply-recovery-slot"}:
            revision = _integer(data["expected_revision"], 0, 255)
            # Read the exact historical revision, allowing a lost-response
            # retry to re-derive the same action before the store's CAS check.
            previous = store.read(slot, source, revision)["receipt"]
            if cmd == "turn-slot":
                current = expedition_board(source, previous)
                _require(data["board_digest"] == current["board_digest"], "expedition board changed")
                legal = current["legal_actions"]
                _require(bool(legal), "no legal actions remain")
                index = _integer(data["index"], 0, len(legal) - 1)
                additional = [legal[index]]
            else:
                recovery = data["recovery"]
                _require(verify_plan(source, previous, recovery), "recovery plan does not replay")
                _require(recovery["status"] == "completion_witness" and bool(recovery["additional"]),
                         "no verified completion suffix to apply")
                additional = recovery["additional"]
            return store.append(slot, source, revision, data["operation"], additional)

        if cmd == "compare-slots":
            # Each record identifies its own actual observed revision.
            left = store.read(slot, source, data.get("revision"))
            right = store.read(data["other_slot"], source, data.get("other_revision"))
            result = {"left_revision": left["revision"], "right_revision": right["revision"],
                      "left_slot": slot, "right_slot": data["other_slot"],
                      "comparison": compare_expeditions(source, left["receipt"], right["receipt"], **_budgets(data))}
            _encode(result)
            return result

        stored = store.read(slot, source, data.get("revision"))
        if cmd == "read-slot":
            return stored
        if cmd == "board-slot":
            result = {"slot": slot, "revision": stored["revision"],
                      "board": expedition_board(source, stored["receipt"])}
        else:
            result = {"slot": slot, "revision": stored["revision"],
                      "recovery": plan_expedition(source, stored["receipt"], **_budgets(data))}
        _encode(result)
        return result


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay source-bound campaign and local crafting gameplay")
    parser.add_argument("command", choices=("build", "play", "resume", "verify", "verify-play",
        "board", "turn", "verify-board", "evidence", "verify-evidence", "assist", "verify-assist",
        "compare", "verify-compare", "author", "verify-author", *sorted(PERSISTENT)))
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    if (args.command in PERSISTENT) != (args.database is not None):
        parser.error("--database is required only for durable slot commands")
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        cmd = args.command
        if cmd in PERSISTENT:
            assert args.database is not None
            result = _persistent(cmd, args.database, value)
        elif cmd == "author":
            result = author_expedition(value)
        elif cmd == "verify-author":
            data = _object(value, {"request", "composition"})
            _require(verify_authoring(data["request"], data["composition"]), "package composition replay mismatch")
            result = {"verified": True, "native_qualified": False, "release_qualified": False}
        elif cmd == "build":
            result = build_expedition(value)
        elif cmd == "play":
            data = _object(value, {"request", "actions"})
            result = play_expedition(data["request"], data["actions"])
        elif cmd in {"compare", "verify-compare"}:
            extra = {"comparison"} if cmd == "verify-compare" else set()
            optional = {"dialogue_budget", "local_budget"} if cmd == "compare" else set()
            data = _object(value, {"request", "left", "right"} | extra, optional)
            if cmd == "compare":
                result = compare_expeditions(data["request"], data["left"], data["right"], **_budgets(data))
            else:
                _require(verify_comparison(data["request"], data["left"], data["right"], data["comparison"]),
                         "expedition comparison replay mismatch")
                result = {"verified": True, "native_qualified": False, "release_qualified": False}
        else:
            fields = {"request", "receipt"}
            extras = {"resume": {"additional"}, "turn": {"board_digest", "index"},
                      "evidence": {"objective"}, "verify-evidence": {"evidence"},
                      "verify-board": {"board"}, "verify-assist": {"recovery"}}
            optional = {"dialogue_budget", "local_budget"} if cmd == "assist" else set()
            data = _object(value, fields | extras.get(cmd, set()), optional)
            source, receipt = data["request"], data["receipt"]
            if cmd == "resume":
                result = resume_expedition(source, receipt, data["additional"])
            elif cmd == "board":
                result = expedition_board(source, receipt)
            elif cmd == "turn":
                result = turn(source, receipt, data["board_digest"], data["index"])
            elif cmd == "evidence":
                result = episode_evidence(source, receipt, data["objective"])
            elif cmd == "assist":
                result = plan_expedition(source, receipt, **_budgets(data))
            else:
                if cmd == "verify-evidence":
                    ok = verify_evidence(source, receipt, data["evidence"])
                elif cmd == "verify-board":
                    ok = verify_board(source, receipt, data["board"])
                elif cmd == "verify-assist":
                    ok = verify_plan(source, receipt, data["recovery"])
                else:
                    ok = verify_expedition(source, receipt, session=cmd == "verify-play")
                _require(ok, "independent expedition replay mismatch")
                result = {"verified": True, "native_qualified": False, "release_qualified": False}
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError, sqlite3.Error) as exc:
        errors.write("expedition rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
