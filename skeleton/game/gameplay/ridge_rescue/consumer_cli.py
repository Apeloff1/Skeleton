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

from .campaign import verify_export
from .consumer_experience import status_panel, navigation_hint, recent_events, action_label
from .consumer_store import SlotStore, StoreError, MAX_EXPORT_BYTES
from .io import read_bounded
from .render import render_map, legend
from .schema import parse_world


def _view(verified: dict, *, ascii_mode: bool = False) -> str:
    index = verified["index"]
    campaign = verified["campaign"]
    lines = [
        campaign["title"],
        f"Save: {verified['slot']}  Revision: {verified['revision']}",
        f"Chapter: {index + 1}/{len(campaign['episodes'])}  Status: {verified['status']}",
    ]
    lines.append(status_panel(verified))
    if verified["status"] == "completed":
        lines.append("Victory: both chapters earned their declared endings.")
        return "\n".join(lines)
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
            write("Campaign complete. Type e to export, j for the journal, or q to quit.")
        elif current["status"] != "playing":
            write("Chapter ended without its required ending. Type r to retry, e to export, j for journal, q to quit.")
        else:
            write("Choose an action number, h for a hint, j for journal, ? for help, e to export, q to save and quit.")
        try:
            answer = read("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "q"
        if answer in ("q", "quit"):
            break
        if answer in ("?", "help"):
            write("Numbers perform listed actions and save immediately. h = advisory route, j = recent events, e = replay-verified export, q = quit without losing the last turn. No command besides a numbered action or retry consumes a turn.")
            continue
        if answer in ("h", "hint"):
            write(navigation_hint(current))
            continue
        if answer in ("j", "journal"):
            write(recent_events(current))
            continue
        if answer == "e":
            write("Exported: " + str(store.export(slot)))
            continue
        if answer == "r" and current["status"] not in ("playing", "completed"):
            current = store.retry(slot, expected_head=current["head"])
            continue
        if current["status"] == "playing" and answer.isascii() and answer.isdecimal():
            selected = int(answer)
            if 0 <= selected < len(current["actions"]):
                current = store.step(slot, current["actions"][selected], expected_head=current["head"])
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
    parser.add_argument("command", choices=("play", "new", "status", "step", "retry", "export", "restore", "audit", "verify-export", "acceptance", "bundle", "smoke", "portable-smoke"))
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
