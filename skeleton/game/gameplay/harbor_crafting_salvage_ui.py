"""Bounded interactive offline salvage session with safe invalid-action fallback."""
from __future__ import annotations

from typing import Any, Callable

from .harbor_crafting import HarborError
from .harbor_crafting_salvage import build_salvage, verify_salvage


def _parse(line: str) -> dict[str, str] | None:
    parts = line.strip().split()
    if not parts or parts[0] in {"quit", "exit"}:
        return None
    if len(parts) == 2 and parts[0] == "move":
        return {"op": "move", "direction": parts[1]}
    if len(parts) == 2 and parts[0] in {"gather", "craft", "trade", "salvage"}:
        if parts[0] == "gather":
            raise HarborError("gather takes no argument")
        return {"op": parts[0], {"craft": "recipe", "trade": "item", "salvage": "site"}[parts[0]]: parts[1]}
    if len(parts) == 1 and parts[0] in {"gather", "deliver", "wait", "offload", "patch", "rescue"}:
        return {"op": parts[0]}
    raise HarborError("unsupported salvage terminal command")


def play_salvage_live(source: Any, board: Any, *,
                      input_fn: Callable[[str], str] = input,
                      output_fn: Callable[[str], Any] = print,
                      max_commands: int = 128) -> dict[str, Any]:
    if type(max_commands) is not int or not 1 <= max_commands <= 128:
        raise HarborError("invalid interactive command budget")
    report = build_salvage(source, board, [])
    output_fn("Salvage: move <direction>, gather, craft <recipe>, trade <item>, "
              "salvage <site>, offload, patch, deliver, rescue, quit")
    for _ in range(max_commands):
        status = verify_salvage(report)
        output_fn("tick={tick} pos={position} hull={hull} cargo={cargo} secured={secured} reward={reward}".format(**status))
        if status["complete"] or status["failed"]:
            break
        try:
            line = input_fn("salvage> ")
        except (EOFError, KeyboardInterrupt):
            break
        try:
            action = _parse(line)
            if action is None:
                break
            next_report = build_salvage(source, board, report["actions"] + [action])
        except HarborError as exc:
            output_fn("rejected: " + str(exc))
            continue
        report = next_report
    return report
