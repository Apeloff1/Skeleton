"""Replay-derived original ASCII scene view with bounded fog-of-war."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    DIRECTIONS, HarborError, _keys, canonical, digest, initial_state, step,
)
from .harbor_crafting_salvage import (
    MAX_REPORT_BYTES, SPECIAL, normalize_salvage_action, verify_salvage,
)
from .harbor_crafting_salvage_assets import validate_salvage_assets

SCHEMA = "skeleton.game.harbor.salvage-map.v1"
MAX_BYTES = MAX_REPORT_BYTES * 2
FIELDS = {"schema", "report", "assets", "reveal", "frame", "legend",
          "status", "map_digest"}


def _visibility(report: dict[str, Any]) -> set[tuple[int, int]]:
    source = report["source"]
    state = initial_state(source)
    visited: set[tuple[int, int]] = set()
    def mark(pos):
        x, y = pos
        for dx, dy in ((0, 0), *DIRECTIONS.values()):
            nx, ny = x + dx, y + dy
            if 0 <= ny < len(source["map"]) and 0 <= nx < len(source["map"][0]):
                visited.add((nx, ny))
    mark(state["pos"])
    for raw in report["actions"]:
        action = normalize_salvage_action(raw)
        core = ({"op": "choose", "choice": "signal"} if action["op"] == "rescue"
                else {"op": "wait"} if action["op"] in SPECIAL else action)
        state = step(source, state, core)
        mark(state["pos"])
    if state != report["bundle"]["state"]:
        raise HarborError("salvage scene replay state mismatch")
    return visited


def render_salvage_map(report: Any, assets: Any, *, reveal: bool = False) -> dict[str, Any]:
    status = verify_salvage(report)
    authored = validate_salvage_assets(assets, report["source"], report["board"])
    if type(reveal) is not bool:
        raise HarborError("invalid salvage map reveal flag")
    if reveal and not status["complete"]:
        raise HarborError("full salvage map requires earned rescue")
    glyph = authored["glyphs"]
    world = report["source"]
    visible = _visibility(report)
    remaining = {tuple(s["at"]) for s in report["board"]["sites"]
                 if s["id"] not in status["cargo"] and s["id"] not in status["secured"]}
    player = tuple(status["position"])
    npc = tuple(report["bundle"]["state"]["npc_pos"])
    dock = tuple(world["dock"])
    frame: list[str] = []
    for y, row in enumerate(world["map"]):
        output: list[str] = []
        for x, tile in enumerate(row):
            pos = (x, y)
            if not reveal and pos not in visible:
                char = glyph["fog"]
            elif pos == player:
                char = glyph["player"]
            elif pos == npc:
                char = glyph["npc"]
            elif pos == dock:
                char = glyph["dock"]
            elif pos in remaining:
                char = glyph["site"]
            elif tile == "#":
                char = glyph["wall"]
            else:
                char = glyph["floor"]
            output.append(char)
        frame.append("".join(output))
    result = {"schema": SCHEMA, "report": deepcopy(report), "assets": authored,
              "reveal": reveal, "frame": frame,
              "legend": deepcopy(glyph), "status": status}
    result["map_digest"] = digest(result)
    if len(canonical(result)) > MAX_BYTES:
        raise HarborError("salvage map export exceeds byte budget")
    return result


def verify_salvage_map(view: Any) -> list[str]:
    _keys(view, FIELDS, "salvage map export")
    if view["schema"] != SCHEMA or len(canonical(view)) > MAX_BYTES:
        raise HarborError("unsupported or oversized salvage map")
    if view["map_digest"] != digest({k: v for k, v in view.items()
                                     if k != "map_digest"}):
        raise HarborError("salvage map digest mismatch")
    rebuilt = render_salvage_map(view["report"], view["assets"], reveal=view["reveal"])
    if rebuilt != view:
        raise HarborError("salvage map replay or visibility mismatch")
    return list(view["frame"])
