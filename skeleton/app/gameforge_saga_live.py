"""Interactive, append-only terminal player for recovered multi-owner sagas.

Every displayed menu is derived from an independent replay of an exact
stored revision. Selecting an action writes that action only. Conflict
handling refreshes the menu but never automatically retries a stale choice.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys
from typing import Any, BinaryIO, Sequence, TextIO

from skeleton.app.gameforge_campaign import digest
from skeleton.app.gameforge_campaign_cli import open_workspace
from skeleton.app.gameforge_campaign_store import RevisionConflict
from skeleton.app.gameforge_saga_board import board, recover
from skeleton.app.gameforge_saga_store import SagaStore
from skeleton.app.original_quest_cli import _encode, _integer, _require, read_document
from skeleton.gameforge.errors import GameForgeError

MAX_COMMANDS = 2048
MAX_COMMAND_BYTES = 256
HELP = "number = take that action; list = refresh; status = current summary; hint = read-only next step; quit = keep save"


def _line(stream: TextIO, value: str) -> None:
    stream.write(value + "\n")
    stream.flush()


def _json(stream: TextIO, name: str, value: Any) -> None:
    # Canonical ensure_ascii JSON safely escapes authored terminal control
    # sequences and line breaks; no external shell escape is performed.
    _line(stream, name + " " + _encode(value).decode("ascii"))


def _menu(stream: TextIO, stored: dict, view: dict) -> None:
    base = view["expedition_view"]["campaign_view"]
    _json(stream, "LOCATION", {"slot": stored["slot"], "revision": stored["revision"],
                               "region": base["location"], "status": view["status"],
                               "board_digest": view["board_digest"]})
    _json(stream, "OBJECTIVES", base["objectives"])
    _json(stream, "REWARDS", base["earned_totals"])
    _json(stream, "BLOCKERS", view["blockers"])
    for oid, episode in sorted(view["advanced_episodes"].items()):
        if episode["kind"] == "survey_expedition":
            _json(stream, "SURVEY", {"objective": oid, "grid": episode["grid"],
                                    "energy": episode["energy"], "weather": episode["next_weather"],
                                    "permit": episode["delivery_permit"], "trust": episode["trust"],
                                    "sites": episode["required_sites_remaining"],
                                    "ending": episode["state"]["ending"]})
        elif episode["kind"] == "convoy_league":
            _json(stream, "LEAGUE", {"objective": oid, "round": episode["next_round"],
                                    "score": episode["score"], "target": episode["target_score"],
                                    "hull": episode["hull"], "threat": episode["threat"],
                                    "standings": episode["standings"], "remaining": episode["remaining"]})
        elif episode["kind"] in {"timed_season", "delivery_chain"}:
            _json(stream, "ROUND", {"objective": oid, "kind": episode["kind"],
                                    "round": episode["next_round"], "score": episode["score"],
                                    "standings": episode["standings"], "remaining": episode["remaining"],
                                    "course_progress": episode["course_progress"]})
        else:
            _json(stream, "CONVOY", {"objective": oid, "hull": episode["hull"],
                                    "threat": episode["threat"], "waypoint": episode["waypoint"],
                                    "bounty": episode["bounty"], "tokens": episode["tokens"],
                                    "remaining": episode["required_contracts_remaining"]})
    for index, action in enumerate(view["legal_actions"]):
        _json(stream, str(index + 1), action)
    _line(stream, HELP)


def play_live(store: SagaStore, source: Any, slot: str, incoming: BinaryIO,
              outgoing: TextIO, *, command_limit: int = MAX_COMMANDS) -> int:
    """Run bounded explicit turns in a private durable journal.

    A command may not include a shell fragment, arbitrary payload, reset,
    or hidden auto-play. Oversized input aborts rather than consuming its
    suffix as another valid command. EOF leaves the last committed save.
    """
    _integer(command_limit, 1, MAX_COMMANDS)
    stored = store.read(slot, source)
    view = board(source, stored["receipt"])
    _menu(outgoing, stored, view)
    for _ in range(command_limit):
        raw = incoming.readline(MAX_COMMAND_BYTES + 1)
        if not raw:
            _json(outgoing, "CHECKPOINT", {"revision": stored["revision"],
                                          "digest": stored["receipt"]["session_digest"]})
            return 0
        if len(raw) > MAX_COMMAND_BYTES:
            _line(outgoing, "REJECTED command too long")
            return 2
        try:
            command = raw.decode("ascii").strip()
        except UnicodeError:
            _line(outgoing, "REJECTED command must be ASCII")
            continue
        if command == "quit":
            _json(outgoing, "CHECKPOINT", {"revision": stored["revision"],
                                          "digest": stored["receipt"]["session_digest"]})
            return 0
        if command in {"list", "status"}:
            stored = store.read(slot, source)
            view = board(source, stored["receipt"])
            _menu(outgoing, stored, view)
            continue
        if command == "hint":
            plan = recover(source, stored["receipt"])
            _json(outgoing, "HINT", {"status": plan["status"], "next_action": plan["next_action"],
                                    "blocker": plan["blocker"]})
            continue
        if not command.isdecimal() or len(command) > 4:
            _line(outgoing, "REJECTED unknown player command")
            continue
        index = int(command) - 1
        legal = view["legal_actions"]
        if not 0 <= index < len(legal):
            _line(outgoing, "REJECTED selection outside current menu")
            continue
        action = legal[index]
        revision = stored["revision"]
        # The operation identity binds the exact observed revision and action.
        # Identical retries converge; another writer's action remains a conflict.
        operation = "live-" + str(revision) + "-" + digest(
            {"board": view["board_digest"], "action": action})[:32]
        try:
            stored = store.append(slot, source, revision, operation, [action])
        except RevisionConflict:
            _line(outgoing, "CONFLICT save advanced; choose again from refreshed menu")
            stored = store.read(slot, source)
            view = board(source, stored["receipt"])
            _menu(outgoing, stored, view)
            continue
        except ValueError:
            _line(outgoing, "REJECTED action not committed")
            continue
        # A duplicate operation may return its original historical response.
        # Always refresh current head before presenting the next menu.
        accepted = stored
        stored = store.read(slot, source)
        view = board(source, stored["receipt"])
        _json(outgoing, "ACCEPTED", {"revision": accepted["revision"], "action": action,
                                    "head": stored["revision"]})
        _menu(outgoing, stored, view)
        if view["status"] == "completed":
            _json(outgoing, "SAGA_COMPLETE", {"revision": stored["revision"],
                                             "digest": stored["receipt"]["session_digest"]})
            return 0
    _line(outgoing, "LIMIT command budget reached; committed save retained")
    return 2


def main(argv: Sequence[str] | None = None, *, stdin: BinaryIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive persistent multi-owner saga player")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args(argv)
    incoming = stdin if stdin is not None else sys.stdin.buffer
    outgoing = stdout if stdout is not None else sys.stdout
    errors = stderr if stderr is not None else sys.stderr
    try:
        with args.source.open("rb") as stream:
            source = read_document(stream)
        with open_workspace(args.database, create=args.create, saga=True) as store:
            _require(isinstance(store, SagaStore), "wrong workspace adapter")
            if args.create:
                store.create(args.slot, source, "live-genesis")
            return play_live(store, source, args.slot, incoming, outgoing)
    except (GameForgeError, ValueError, TypeError, KeyError, OverflowError,
            RecursionError, OSError, sqlite3.Error) as exc:
        _line(errors, "saga player rejected: " + type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
