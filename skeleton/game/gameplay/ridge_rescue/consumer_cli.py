"""User-reachable, restartable Cinder Ridge game on Windows, macOS and Linux.

The interface never executes arbitrary user code. Every action is selected
from the canonical campaign's available actions, and committed atomically
before the next prompt. Quit and EOF leave the last committed save intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .campaign import verify_export
from .consumer_store import SlotStore, StoreError, MAX_EXPORT_BYTES
from .io import read_bounded
from .render import render_map, legend
from .schema import parse_world


def _view(verified: dict) -> str:
    index = verified["index"]
    campaign = verified["campaign"]
    lines = [
        campaign["title"],
        f"Save: {verified['slot']}  Revision: {verified['revision']}",
        f"Chapter: {index + 1}/{len(campaign['episodes'])}  Status: {verified['status']}",
    ]
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
            lines.append(f"  {number}: {json.dumps(action, sort_keys=True)}")
    return "\n".join(lines)


def play(store: SlotStore, slot: str, *, read=input, write=print) -> dict:
    try:
        current = store.load(slot)
    except StoreError as exc:
        if str(exc) != "save slot does not exist":
            raise
        current = store.new(slot)
    while True:
        write(_view(current))
        if current["status"] == "completed":
            write("Campaign complete. Type e to export, or q to quit.")
        elif current["status"] != "playing":
            write("Chapter ended without its required ending. Type r to retry, e to export, q to quit.")
        else:
            write("Choose an action number, e to export, or q to save and quit.")
        try:
            answer = read("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "q"
        if answer in ("q", "quit"):
            break
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cinder-ridge-consumer")
    parser.add_argument("command", choices=("play", "new", "status", "step", "retry", "export", "audit", "verify-export", "acceptance", "bundle"))
    parser.add_argument("--slot", default="adventure", help="lowercase save name, 1-32 safe characters")
    parser.add_argument("--action", help="canonical JSON action for a noninteractive step")
    parser.add_argument("--expected-head", help="exact revision head for a noninteractive mutation")
    parser.add_argument("--file", help="portable campaign export to verify")
    args = parser.parse_args(argv)
    try:
        if args.command == "acceptance":
            from .consumer_acceptance import run_acceptance
            result = run_acceptance()
        elif args.command == "verify-export":
            if not args.file:
                raise StoreError("--file required")
            if os.name == "nt":
                raise StoreError("external file verification requires descriptor-anchored IO; Windows held")
            result = verify_export(read_bounded(args.file, MAX_EXPORT_BYTES))
            result = {"verified": True, "head": result["head"], "status": result["status"],
                      "chapters": result["index"]}
        else:
            store = SlotStore()
            if args.command == "play":
                result = play(store, args.slot)
            elif args.command == "bundle":
                from .consumer_bundle import build_bundle
                result = build_bundle(store)
            elif args.command == "new":
                result = store.new(args.slot)
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
