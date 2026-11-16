"""Installed multi-owner saga authoring, player turns, evidence and durable recovery."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import Any, BinaryIO, Sequence, TextIO

from skeleton.app.gameforge_campaign_cli import open_workspace
from skeleton.app.gameforge_saga import build_saga, play_saga, resume_saga, verify_saga
from skeleton.app.gameforge_saga_author import author_saga, verify_authoring
from skeleton.app.gameforge_saga_board import (
    board, compare, episode_evidence, recover, selected_action, turn, verify_derived,
)
from skeleton.app.original_quest_cli import _encode, _integer, _object, _require, read_document
from skeleton.gameforge.errors import GameForgeError

PERSISTENT = frozenset({
    "create-slot", "append-slot", "read-slot", "history", "fork-slot",
    "snapshot-slot", "restore-slot", "board-slot", "turn-slot", "assist-slot",
    "apply-recovery-slot", "compare-slots", "evidence-slot",
})
ORDINARY = (
    "author", "verify-author", "build", "verify", "play", "verify-play", "resume",
    "board", "turn", "verify-board", "evidence", "verify-evidence",
    "assist", "verify-assist", "compare", "verify-compare",
)


def _budgets(data: dict) -> dict:
    return {"dialogue_budget": data.get("dialogue_budget", 1024),
            "local_budget": data.get("local_budget", 1024)}


def _persistent(command: str, path: Path, value: Any) -> dict:
    fields = {"request", "slot"}
    extra = {
        "create-slot": {"operation"},
        "append-slot": {"operation", "expected_revision", "additional"},
        "fork-slot": {"parent_revision", "expected_digest", "child_slot"},
        "restore-slot": {"archive"},
        "turn-slot": {"operation", "expected_revision", "board_digest", "index"},
        "apply-recovery-slot": {"operation", "expected_revision", "recovery"},
        "compare-slots": {"other_slot"},
        "evidence-slot": {"objective"},
    }
    optional = {"revision"} if command in {
        "read-slot", "board-slot", "assist-slot", "compare-slots", "evidence-slot"
    } else set()
    if command == "assist-slot":
        optional.update({"dialogue_budget", "local_budget"})
    if command == "compare-slots":
        optional.add("other_revision")
    data = _object(value, fields | extra.get(command, set()), optional)
    source, slot = data["request"], data["slot"]
    with open_workspace(path, create=command in {"create-slot", "restore-slot"}, saga=True) as store:
        if command == "create-slot":
            return store.create(slot, source, data["operation"])
        if command == "append-slot":
            return store.append(slot, source, data["expected_revision"], data["operation"], data["additional"])
        if command == "history":
            return store.history(slot, source)
        if command == "fork-slot":
            return store.fork(slot, source, data["parent_revision"], data["expected_digest"], data["child_slot"])
        if command == "snapshot-slot":
            return store.snapshot(slot, source)
        if command == "restore-slot":
            return store.restore(slot, source, data["archive"])
        if command in {"turn-slot", "apply-recovery-slot"}:
            revision = _integer(data["expected_revision"], 0, 255)
            previous = store.read(slot, source, revision)["receipt"]
            if command == "turn-slot":
                actions = [selected_action(source, previous, data["board_digest"], data["index"])]
            else:
                plan = data["recovery"]
                _require(verify_derived(source, previous, plan, kind="recovery"),
                         "saga recovery does not independently replay")
                _require(plan["status"] == "completion_witness" and bool(plan["additional"]),
                         "no verified saga completion to apply")
                actions = plan["additional"]
            return store.append(slot, source, revision, data["operation"], actions)
        left = store.read(slot, source, data.get("revision"))
        receipt = left["receipt"]
        if command == "read-slot":
            return left
        result = {"slot": slot, "revision": left["revision"],
                  "native_qualified": False, "release_qualified": False}
        if command == "compare-slots":
            right = store.read(data["other_slot"], source, data.get("other_revision"))
            result.update({"other_slot": data["other_slot"], "other_revision": right["revision"],
                           "comparison": compare(source, receipt, right["receipt"])})
        elif command == "board-slot":
            result["board"] = board(source, receipt)
        elif command == "assist-slot":
            result["recovery"] = recover(source, receipt, **_budgets(data))
        elif command == "evidence-slot":
            result["evidence"] = episode_evidence(source, receipt, data["objective"])
        else:
            raise ValueError("unimplemented saga journal command")
        _encode(result)
        return result


def _verified(ok: bool) -> dict:
    _require(ok, "saga independent replay mismatch")
    return {"verified": True, "native_qualified": False, "release_qualified": False}


def _ordinary(command: str, value: Any) -> dict:
    if command == "author":
        return author_saga(value)
    if command == "verify-author":
        data = _object(value, {"request", "composition"})
        return _verified(verify_authoring(data["request"], data["composition"]))
    if command == "build":
        return build_saga(value)
    if command == "play":
        data = _object(value, {"request", "actions"})
        return play_saga(data["request"], data["actions"])
    if command in {"compare", "verify-compare"}:
        extra = {"comparison"} if command == "verify-compare" else set()
        data = _object(value, {"request", "left", "right"} | extra)
        if command == "compare":
            return compare(data["request"], data["left"], data["right"])
        return _verified(verify_derived(data["request"], data["left"], data["comparison"],
                                        kind="comparison", other=data["right"]))
    extras = {"resume": {"additional"}, "turn": {"board_digest", "index"},
              "evidence": {"objective"}, "verify-evidence": {"evidence"},
              "verify-board": {"board"}, "verify-assist": {"recovery"}}
    optional = {"dialogue_budget", "local_budget"} if command == "assist" else set()
    data = _object(value, {"request", "receipt"} | extras.get(command, set()), optional)
    source, receipt = data["request"], data["receipt"]
    if command == "resume":
        return resume_saga(source, receipt, data["additional"])
    if command == "board":
        return board(source, receipt)
    if command == "turn":
        return turn(source, receipt, data["board_digest"], data["index"])
    if command == "evidence":
        return episode_evidence(source, receipt, data["objective"])
    if command == "assist":
        return recover(source, receipt, **_budgets(data))
    if command == "verify-board":
        return _verified(verify_derived(source, receipt, data["board"], kind="board"))
    if command == "verify-evidence":
        return _verified(verify_derived(source, receipt, data["evidence"], kind="evidence"))
    if command == "verify-assist":
        return _verified(verify_derived(source, receipt, data["recovery"], kind="recovery"))
    return _verified(verify_saga(source, receipt, session=command == "verify-play"))


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Source-bound multi-owner adventure and tactical saga")
    parser.add_argument("command", choices=(*ORDINARY, *sorted(PERSISTENT)))
    parser.add_argument("--database", type=Path)
    args = parser.parse_args(argv)
    if (args.command in PERSISTENT) != (args.database is not None):
        parser.error("--database is required only for journal operations")
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        value = read_document(incoming)
        result = (_ordinary(args.command, value) if args.command not in PERSISTENT else
                  _persistent(args.command, args.database, value))
        outgoing.write(_encode(result).decode("ascii") + "\n")
        return 0
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError, sqlite3.Error) as exc:
        errors.write("saga rejected: " + type(exc).__name__ + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
