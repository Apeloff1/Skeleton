"""User-reachable, restartable Cinder Ridge game on Windows, macOS and Linux.

The interface never executes arbitrary user code. Every action is selected
from the canonical campaign's available actions, and committed atomically
before the next prompt. Quit and EOF leave the last committed save intact.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

from .campaign import verify_export, CampaignError
from .consumer_experience import status_panel, navigation_hint, recent_events, action_label
from .consumer_store import SlotStore, StoreError, MAX_EXPORT_BYTES
from .io import read_bounded
from .render import render_map, legend
from .schema import parse_world

# Pasted or malformed commands must not crash a consumer or consume a turn.
MAX_TERMINAL_INPUT = 128
MAX_MENU_DIGITS = 8
MAX_ACTION_JSON_BYTES = 4096


def _strict_action_json(payload: str) -> dict:
    """Reject duplicate keys and non-finite values before any save mutation."""
    if not isinstance(payload, str):
        raise ValueError("action JSON must be text")
    try:
        payload_size = len(payload.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("action JSON contains invalid Unicode") from exc
    if payload_size > MAX_ACTION_JSON_BYTES:
        raise ValueError("action JSON exceeds byte budget")

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate action JSON key: " + key)
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError("non-finite action JSON number: " + value)

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("non-finite action JSON number: " + value)
        return number

    try:
        action = json.loads(payload, object_pairs_hook=unique_pairs,
                            parse_constant=reject_constant, parse_float=finite_float)
    except RecursionError as exc:
        # Deeply nested but byte-bounded input can exhaust the JSON decoder
        # before the campaign validator ever sees an action.
        raise ValueError("action JSON nesting exceeds parser budget") from exc
    if not isinstance(action, dict):
        raise ValueError("action JSON must be an object")
    return action


def _action_index(answer: str, available: int) -> int | None:
    """Decode only bounded ASCII menu choices; never parse giant integers."""
    if (not answer or len(answer) > MAX_MENU_DIGITS or
            not answer.isascii() or not answer.isdecimal()):
        return None
    selected = int(answer)
    return selected if selected < available else None


def _view(verified: dict, *, ascii_mode: bool = False) -> str:
    index = verified["index"]
    campaign = verified["campaign"]
    lines = [
        campaign["title"],
        f"Save: {verified['slot']}  Revision: {verified['revision']}",
        f"Chapter: {min(index + 1, len(campaign['episodes']))}/{len(campaign['episodes'])}  Status: {verified['status']}",
    ]
    lines.append(status_panel(verified))
    if verified["status"] == "completed":
        lines.append("Victory: both chapters earned their declared endings.")
        completed = "\n".join(lines)
        return completed.encode("ascii", errors="replace").decode("ascii") if ascii_mode else completed
    if verified["state"] is not None:
        world = parse_world(campaign["episodes"][index]["world"])
        lines.append(render_map(world, verified["state"]))
        lines.append(legend())
        lines.append("Inventory: " + json.dumps(verified["state"]["inventory"], sort_keys=True))
        lines.append("Actions:")
        for number, action in enumerate(verified["actions"]):
            lines.append(f"  {number}: {action_label(action)}")
    result = "\n".join(lines)
    if ascii_mode:
        result = result.translate(str.maketrans({"·": ".", "█": "#", "≈": "~", "▲": "^"}))
        result = result.encode("ascii", errors="replace").decode("ascii")
    return result


def play(store: SlotStore, slot: str, *, read=input, write=print, ascii_mode: bool | None = None) -> dict:
    try:
        current = store.load(slot)
    except StoreError as exc:
        if str(exc) != "save slot does not exist":
            raise
        try:
            current = store.new(slot)
        except StoreError as create_error:
            # Two consumer processes may both observe an absent slot. If the
            # other process won creation, attach to its authoritative save;
            # never replace or reset its first committed turn.
            if str(create_error) != "save slot already exists":
                raise
            current = store.load(slot)
    if ascii_mode is None:
        ascii_mode = os.name == "nt"
    while True:
        write(_view(current, ascii_mode=ascii_mode))
        if current["status"] == "completed":
            write("Campaign complete. Type a to audit, e to export, b for full backup, j for journal, or q to quit.")
        elif current["status"] != "playing":
            write("Chapter ended without its required ending. Type r to retry, a to audit, b for full backup, e to export, j for journal, q to quit.")
        else:
            write("Choose an action number, h for a hint, j for journal, a to audit, ? for help, e to export, b for full backup, s to sync the latest save, q to save and quit.")
        try:
            raw = read("> ")
        except (EOFError, KeyboardInterrupt, StopIteration, OSError, UnicodeError):
            # Closed terminal streams, disconnected consoles and decoding
            # failures are orderly exits. Never consume an action or reset
            # the authoritative save when interactive input disappears.
            raw = "q"
        # Terminal input may contain pasted Unicode or control characters. Reject
        # all controls (including pasted newlines/tabs) rather than normalizing them into a valid
        # action, especially where two players share one authoritative slot.
        if (not isinstance(raw, str) or len(raw) > MAX_TERMINAL_INPUT or
                any(ord(ch) < 32 or ord(ch) == 127 for ch in raw) or
                any(0xD800 <= ord(ch) <= 0xDFFF for ch in raw)):
            write("Unavailable command; no turn was consumed.")
            continue
        answer = raw.strip().lower()
        if answer in ("q", "quit"):
            break
        if answer in ("?", "help"):
            write("Numbers perform listed actions and save immediately. h = advisory route, j = recent events, a = replay-verify save history, e = replay-verified export, b = retry-aware full backup, s = sync from disk, q = quit without losing the last turn. No command besides a numbered action or retry consumes a turn.")
            continue
        if answer in ("s", "sync"):
            try:
                current = store.load(slot)
                write("Authoritative save refreshed; no turn was consumed.")
            except (StoreError, CampaignError, OSError) as exc:
                write("Save refresh unavailable; no turn was consumed: " + str(exc))
            continue
        if answer in ("a", "audit"):
            try:
                report = store.audit(slot)
                if report["head"] != current["head"]:
                    write("Audit verified a newer authoritative save; refreshing view.")
                    current = store.load(slot)
                write("Save audit verified: " + json.dumps(report, sort_keys=True))
            except (StoreError, CampaignError, OSError) as exc:
                write("Save audit unavailable; no turn was consumed: " + str(exc))
            continue
        if answer in ("h", "hint"):
            try:
                # Hints must never advise a route from a stale concurrent save.
                current = store.load(slot)
                write(navigation_hint(current))
            except (StoreError, CampaignError, OSError) as exc:
                write("Hint unavailable; no turn was consumed: " + str(exc))
            continue
        if answer in ("j", "journal"):
            try:
                # A second player may have committed since this menu was shown.
                # Journal is read-only, but must describe the authoritative slot.
                current = store.load(slot)
                write(recent_events(current))
            except (StoreError, CampaignError, OSError) as exc:
                write("Journal unavailable; no turn was consumed: " + str(exc))
            continue
        if answer == "e":
            try:
                # Export reads the authoritative slot, not the menu snapshot.
                # Refresh the visible state as well: another process may have
                # finished a chapter while this player was at the prompt.
                exported = store.export(slot)
                current = store.load(slot)
                write("Exported: " + str(exported))
            except (StoreError, CampaignError, OSError) as exc:
                write("Export unavailable; saved game unchanged: " + str(exc))
            continue
        if answer == "b":
            try:
                backed_up = store.backup(slot)
                current = store.load(slot)
                write("Backup created: " + str(backed_up))
            except (StoreError, CampaignError, OSError) as exc:
                write("Backup unavailable; saved game unchanged: " + str(exc))
            continue
        if answer == "r" and current["status"] not in ("playing", "completed"):
            try:
                current = store.retry(slot, expected_head=current["head"])
            except (StoreError, CampaignError) as exc:
                write("Retry not saved; refreshing authoritative slot: " + str(exc))
                current = store.load(slot)
            continue
        if current["status"] == "playing":
            selected = _action_index(answer, len(current["actions"]))
            if selected is not None:
                try:
                    current = store.step(slot, current["actions"][selected], expected_head=current["head"])
                except (StoreError, CampaignError) as exc:
                    # A second process may have advanced the slot while this
                    # player was reading the menu. Never replay stale input.
                    write("Action not saved; refreshing authoritative slot: " + str(exc))
                    current = store.load(slot)
                continue
        write("Unavailable command; no turn was consumed.")
    return store.load(slot)


def _portable_input(path: str | None) -> bytes:
    """Accept bounded stdin on all hosts; arbitrary Windows paths stay held."""
    if not path:
        raise StoreError("--file required (use '-' for bounded stdin)")
    if path == "-":
        if sys.stdin.isatty():
            raise StoreError("piped export input required; interactive stdin refused")
        payload = sys.stdin.buffer.read(MAX_EXPORT_BYTES + 1)
        if len(payload) > MAX_EXPORT_BYTES:
            raise StoreError("portable input exceeds byte budget")
        return payload
    if os.name == "nt":
        raise StoreError("arbitrary Windows export paths are unsupported; pipe with --file -")
    return read_bounded(path, MAX_EXPORT_BYTES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cinder-ridge-consumer")
    parser.add_argument("command", choices=("play", "new", "status", "journal", "step", "retry", "export", "restore", "backup", "restore-backup", "audit", "verify-export", "verify-backup", "acceptance", "bundle", "smoke", "portable-smoke"))
    parser.add_argument("--slot", default="adventure", help="lowercase save name, 1-32 safe characters")
    parser.add_argument("--ascii", action="store_true", help="ASCII-only terminal fallback")
    parser.add_argument("--action", help="canonical JSON action for a noninteractive step")
    parser.add_argument("--expected-head", help="exact revision head for a noninteractive mutation")
    parser.add_argument("--file", help="portable campaign export to verify")
    args = parser.parse_args(argv)
    try:
        if args.command == "acceptance":
            from .consumer_acceptance import run_acceptance
            result = run_acceptance()
        elif args.command == "smoke":
            from .consumer_smoke import run_smoke
            result = run_smoke()
        elif args.command == "portable-smoke":
            from .consumer_smoke import run_portable_smoke
            result = run_portable_smoke()
        elif args.command == "verify-export":
            result = verify_export(_portable_input(args.file))
            result = {"verified": True, "head": result["head"], "status": result["status"],
                      "chapters": result["index"]}
        elif args.command == "verify-backup":
            from .consumer_backup import verify_backup
            from .consumer_store import _source
            session, history = verify_backup(_portable_input(args.file), _source())
            result = {"verified": True, "head": session["head"],
                      "actions": len(history), "retries": session["retries"]}
        else:
            store = SlotStore()
            if args.command == "play":
                result = play(store, args.slot, ascii_mode=args.ascii or os.name == "nt")
            elif args.command == "bundle":
                from .consumer_bundle import build_bundle
                result = build_bundle(store)
            elif args.command == "new":
                result = store.new(args.slot)
            elif args.command == "restore":
                result = store.restore(args.slot, _portable_input(args.file))
            elif args.command == "restore-backup":
                result = store.restore_backup(args.slot, _portable_input(args.file))
            elif args.command == "backup":
                result = {"path": str(store.backup(args.slot))}
            elif args.command == "status":
                result = store.load(args.slot)
            elif args.command == "journal":
                current = store.load(args.slot)
                result = {"slot": args.slot, "head": current["head"],
                          "revision": current["revision"],
                          "journal": recent_events(current)}
            elif args.command == "step":
                if not args.action or not args.expected_head:
                    raise StoreError("--action and --expected-head required")
                result = store.step(args.slot, _strict_action_json(args.action), expected_head=args.expected_head)
            elif args.command == "retry":
                if not args.expected_head:
                    raise StoreError("--expected-head required")
                result = store.retry(args.slot, expected_head=args.expected_head)
            elif args.command == "export":
                result = {"path": str(store.export(args.slot))}
            else:
                result = store.audit(args.slot)
        if args.command != "play":
            print(json.dumps(result, sort_keys=True, separators=(",", ":"), default=str))
        return 0
    except (ValueError, TypeError, KeyError, OSError, EOFError) as exc:
        parser.exit(2, f"cinder-ridge-consumer: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
