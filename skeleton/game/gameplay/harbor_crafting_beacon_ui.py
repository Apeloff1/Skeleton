"""Interactive original beacon rescue with bounded input and safe retry."""
from __future__ import annotations

import sys
from typing import Any, TextIO

from .harbor_crafting import HarborError, validate_source
from .harbor_crafting_beacon_guidance import legal_beacon_actions
from .harbor_crafting_beacons import (
    beacon_status, build_beacon_rescue, normalize_beacon_action,
    resume_beacon_rescue, validate_beacon_board, verify_beacon_rescue,
)


def _parse(line: str) -> dict[str, str]:
    words = line.strip().split()
    if not words:
        raise HarborError("empty beacon command")
    op = words[0].lower()
    if op in {"move", "craft", "trade", "repair", "signal"}:
        if len(words) != 2:
            raise HarborError("beacon command requires exactly one argument")
        field = {
            "move": "direction", "craft": "recipe", "trade": "item",
            "repair": "beacon", "signal": "beacon",
        }[op]
        return normalize_beacon_action({"op": op, field: words[1]})
    if op in {"gather", "deliver", "wait", "rescue"} and len(words) == 1:
        return normalize_beacon_action({"op": op})
    raise HarborError("unsupported beacon terminal command")


def play_beacon_live(source: Any, board: Any, *,
                     instream: TextIO | None = None,
                     outstream: TextIO | None = None,
                     initial_report: Any = None) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_beacon_board(board, world)
    reader = sys.stdin if instream is None else instream
    writer = sys.stderr if outstream is None else outstream
    if initial_report is None:
        report = build_beacon_rescue(world, authored, [])
    else:
        verify_beacon_rescue(initial_report)
        if initial_report["source"] != world or initial_report["board"] != authored:
            raise HarborError("beacon live checkpoint source mismatch")
        report = initial_report
    # Rejected commands never advance the canonical clock or mutate custody.
    attempts = 0
    while not report["state"]["rescued"] and attempts < authored["max_turns"] * 4 + 16:
        status = beacon_status(report)
        writer.write(
            f"tick={status['tick']} pos={status['position']} "
            f"signals={','.join(status['signaled']) or '-'} "
            f"delivered={status['delivered']}\n"
        )
        writer.write("beacon> ")
        writer.flush()
        raw = reader.readline(256)
        if not raw:
            break
        attempts += 1
        if raw.strip().lower() in {"quit", "exit"}:
            break
        if raw.strip().lower() == "hint":
            guidance = legal_beacon_actions(report)
            writer.write("Legal: " + ", ".join(
                " ".join(item["action"].values())
                for item in guidance["candidates"]
            ) + "\n")
            continue
        try:
            action = _parse(raw)
            report = resume_beacon_rescue(
                report, [action], expected_digest=report["report_digest"],
            )
        except HarborError as exc:
            writer.write("Rejected: " + str(exc) + "\n")
    verify_beacon_rescue(report)
    return report
