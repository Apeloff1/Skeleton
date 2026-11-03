"""User-reachable, restartable Cinder Ridge game on Windows, macOS and Linux.

The interface never executes arbitrary user code. Every action is selected
from the canonical campaign's available actions, and committed atomically
before the next prompt. Quit and EOF leave the last committed save intact.
"""
from __future__ import annotations

import argparse
import json
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
        current = store.new(slot)
    if ascii_mode is None:
        ascii_mode = os.name == "nt"
    while True:
        write(_view(current, ascii_mode=ascii_mode))
        if current["status"] == "completed":
            write("Campaign complete. Type e to export, b for full backup, j for journal, or q to quit.")
        elif current["status"] != "playing":
            write("Chapter ended without its required ending. Type r to retry, b for full backup, e to export, j for journal, q to quit.")
        else:
            write("Choose an action number, h for a hint, j for journal, ? for help, e to export, b for full backup, q to save and quit.")
        try:
            raw = read("> ")
        except (EOFError, KeyboardInterrupt):
            raw = "q"
        if not isinstance(raw, str) or len(raw) > MAX_TERMINAL_INPUT:
            write("Unavailable command; no turn was consumed.")
            continue
        answer = raw.strip().lower()
        if answer in ("q", "quit"):
            break
        if answer in ("?", "help"):
            write("Numbers perform listed actions and save immediately. h = advisory route, j = recent events, e = replay-verified export, b = retry-aware full backup, q = quit without losing the last turn. No command besides a numbered action or retry consumes a turn.")
            continue
        if answer in ("h", "hint"):
            write(navigation_hint(current))
            continue
        if answer in ("j", "journal"):
            write(recent_events(current))
            continue
        if answer == "e":
            try:
                write("Exported: " + str(store.export(slot)))
            except (StoreError, CampaignError, OSError) as exc:
                write("Export unavailable; saved game unchanged: " + str(exc))
            continue
        if answer == "b":
            try:
                write("Backup created: " + str(store.backup(slot)))
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
    parser.add_argument("command", choices=("play", "new", "status", "step", "retry", "export", "restore", "backup", "restore-backup", "audit", "verify-export", "verify-backup", "acceptance", "bundle", "smoke", "portable-smoke"))
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
            elif args.command == "step":
                if not args.action or not args.expected_head:
                    raise StoreError("--action and --expected-head required")
                result = store.step(args.slot, json.loads(args.action), expected_head=args.expected_head)
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
