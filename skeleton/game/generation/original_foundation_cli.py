"""Browse and play 10,240 authored causal world-law compositions offline.

Every preview identifies provenance: two authored laws and a domain-specific
authored coupling, combined by machine. Gameplay is an *abstract causal
adapter* rather than a bespoke graphical build of every written premise.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
from typing import Sequence

from .original_foundation_compiler import (
    FoundationError, foundation_at, foundation_from_seed,
    iter_foundations, provenance_report,
)
from .original_foundation_runtime import (
    ACTIONS, CausalAction, CausalState, create_causal,
    available_exits, restore_causal, save_causal, step_causal,
)
MAX_COMMAND_BYTES = 65536


def _parse_script(source: str) -> tuple[CausalAction, ...]:
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_COMMAND_BYTES:
        raise FoundationError("script size exceeds the supported limit")
    try:
        commands = json.loads(source)
    except (ValueError, TypeError) as exc:
        raise FoundationError("invalid script JSON") from exc
    if not isinstance(commands, list) or len(commands) > 1000:
        raise FoundationError("script must be a bounded command array")
    output = []
    for command in commands:
        if not isinstance(command, dict) or set(command) - {
            "verb", "amount", "target", "option",
        }:
            raise FoundationError("unknown scripted action fields")
        try:
            action = CausalAction(**command)
        except (TypeError, ValueError) as exc:
            raise FoundationError("missing or invalid scripted action") from exc
        if action.verb not in ACTIONS:
            raise FoundationError("unsupported command")
        output.append(action)
    return tuple(output)


def _parse_command(text: str) -> CausalAction:
    try:
        words = shlex.split(text)
    except ValueError as exc:
        raise FoundationError("invalid terminal command quoting") from exc
    if not words or words[0] not in ACTIONS or len(words) > 3:
        raise FoundationError("unknown game action")
    verb = words[0]
    if verb == "move":
        if len(words) != 2:
            raise FoundationError("move requires an adjacent room number")
        try:
            return CausalAction(verb, target=int(words[1]))
        except ValueError as exc:
            raise FoundationError("room number invalid") from exc
    if verb == "choose":
        if len(words) != 2:
            raise FoundationError("choose requires care or power")
        return CausalAction(verb, option=words[1])
    if len(words) not in (1, 2):
        raise FoundationError("action takes one optional amount")
    try:
        return CausalAction(verb, amount=int(words[1]) if len(words) == 2 else 1)
    except ValueError as exc:
        raise FoundationError("amount invalid") from exc


def _render(state: CausalState) -> str:
    from .original_foundation_compiler import foundation_by_id
    law = foundation_by_id(state.foundation_id)
    strength = state.primary
    return "\n".join([
        f"{law.title}",
        f"Original root: {law.root.invariant}",
        f"Overlay: {law.regime.invariant}",
        f"Coupling: {law.coupling}",
        f"World meter ({law.root.meter}) {strength} | Threat ({law.root.hazard}) {state.hazard}",
        f"Turn {state.tick}, AP {state.action_points}, Location {state.position}, "
        f"Passages {available_exits(state)}",
        f"Supplies {state.supplies}, reserves {state.reserve}, stamina {state.energy}, "
        f"trust {state.trust}, evidence {state.evidence}",
        f"Remote benefit {state.remote}, unpaid duties {state.duty}, "
        f"pending echoes {state.echo_due}",
        f"Surveyed {len(state.investigated)}/12 sectors, "
        f"built {state.outposts} outposts, "
        f"branch {state.branch or 'none'}",
        f"Chapter: {'completed' if state.chapter_complete else 'ongoing'} | "
        f"Main ending policy: {law.ending_policy} | "
        f"Regime ending policy: {law.secondary_ending_policy}",
        "This is an abstract executable cross-law proof, not a fully realized native game.",
    ])


def _interactive(state: CausalState) -> CausalState:
    print("Original Foundation Studio — playable causal law preview.")
    print("Type 'help', 'status', 'quit'; intervene / negotiate / move N / end_turn.")
    print(_render(state))
    while True:
        try:
            line = input("foundation> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLocal simulation closed.")
            break
        if not line:
            continue
        if line in ("quit", "exit"):
            break
        if line in ("status", "map"):
            print(_render(state))
            continue
        if line == "help":
            print("Actions:", ", ".join(sorted(ACTIONS)))
            print("Use 'intervene 2', 'study', 'negotiate', 'choose care', 'end_turn'.")
            continue
        try:
            state, receipt = step_causal(state, _parse_command(line))
            print(" | ".join(receipt.changes))
            print(_render(state))
        except FoundationError as exc:
            print("Action rejected:", exc)
    return state


def _save_file(path: Path, state: CausalState) -> None:
    if not path.parent.is_dir() or path.is_dir():
        raise FoundationError("save destination is not writable file path")
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(save_causal(state), encoding="utf-8")
    temp.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explore 10,240 authorship-tracked original-law world foundations."
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--index", type=int)
    selection.add_argument("--seed")
    selection.add_argument("--load", type=Path)
    parser.add_argument("--report", action="store_true",
                        help="Report provenance counts and authorship distinctions")
    parser.add_argument("--page", type=int,
                        help="Stream starting index for a bounded foundation page")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--actions-json", default="[]")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--show-map", action="store_true")
    parser.add_argument("--save", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.report:
            print(json.dumps(provenance_report(), sort_keys=True, indent=2))
            return 0
        if args.page is not None:
            items = list(iter_foundations(start=args.page, limit=args.limit))
            print(json.dumps({
                "source": "authored causal compositions",
                "start": args.page,
                "count": len(items),
                "worlds": [{
                    "id": item.foundation_id,
                    "index": str(item.foundation_index),
                    "title": item.title,
                    "root_law": item.root.invariant,
                    "regime_law": item.regime.invariant,
                    "causal_coupling": item.coupling,
                    "provenance": item.provenance,
                } for item in items],
            }, sort_keys=True, ensure_ascii=False, indent=2))
            return 0
        if args.load:
            if not args.load.is_file() or args.load.stat().st_size > 65536:
                raise FoundationError("invalid or oversized save file")
            state = restore_causal(args.load.read_text(encoding="utf-8"))
        else:
            law = (foundation_at(args.index)
                   if args.index is not None
                   else foundation_from_seed(args.seed or "atlas-default"))
            state = create_causal(law.foundation_id)
        for action in _parse_script(args.actions_json):
            state, receipt = step_causal(state, action)
        if args.interactive:
            state = _interactive(state)
        if args.save:
            _save_file(args.save, state)
        if not args.interactive:
            if args.show_map:
                print(_render(state))
            else:
                from .original_foundation_compiler import foundation_by_id
                law = foundation_by_id(state.foundation_id)
                print(json.dumps({
                    "foundation": law.as_dict(),
                    "game_state": json.loads(save_causal(state))["payload"]["state"],
                    "provenance": law.provenance,
                    "simulation_status": "bounded-generic-causal-prototype",
                }, sort_keys=True, ensure_ascii=False, indent=2))
    except (FoundationError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
