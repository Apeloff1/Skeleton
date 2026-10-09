"""Bounded deterministic capabilities for the offline Skeleton app.

These typed operations increase *functional* capability without requiring
new training examples, inference, GPU acceleration, network access, dynamic
Python code evaluation or tool permissions. A result is authoritative only
for its explicit, checked input contract; natural-language interpretation
and generalization remain unverified.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import re
from typing import Any, Callable, Mapping

from .gameplay_capabilities import GAMEPLAY_OPERATIONS

SCHEMA = "skeleton.offline_deterministic_capabilities.v1"
MAX_INPUT_BYTES = 8192
MAX_OUTPUT_BYTES = 32768
MAX_TEXT = 2048
MAX_NUMBER = 1_000_000
MAX_COLLECTION = 64
MAX_GRID = 32


class CapabilityTaskError(ValueError):
    """An untrusted, oversized, ambiguous or unsupported operation."""


def _keys(data: Any, required: tuple[str, ...],
          optional: tuple[str, ...] = ()) -> Mapping[str, Any]:
    if not isinstance(data, dict) or set(data) - set(required) - set(optional) or any(
        k not in data for k in required
    ):
        raise CapabilityTaskError("task arguments do not match operation schema")
    return data


def _n(value: Any, *, low: int = -MAX_NUMBER,
       high: int = MAX_NUMBER) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CapabilityTaskError("integer exceeds task domain")
    return value


def _str(value: Any, limit: int = MAX_TEXT) -> str:
    if (
        not isinstance(value, str) or len(value) > limit or "\x00" in value
        or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    ):
        raise CapabilityTaskError("text must be a bounded valid unicode string")
    return value


def _xy(value: Any) -> tuple[int, int]:
    obj = _keys(value, ("x", "y"))
    return _n(obj["x"]), _n(obj["y"])


def _rect(value: Any) -> tuple[int, int, int, int]:
    obj = _keys(value, ("x0", "y0", "x1", "y1"))
    x0, y0, x1, y1 = (_n(obj[key]) for key in ("x0", "y0", "x1", "y1"))
    if x1 <= x0 or y1 <= y0:
        raise CapabilityTaskError("rectangle must have positive dimensions")
    return x0, y0, x1, y1


def _list(value: Any, limit: int = MAX_COLLECTION) -> list[Any]:
    if not isinstance(value, list) or not len(value) <= limit:
        raise CapabilityTaskError("sequence exceeds bounded task domain")
    return value


def _add(args: dict[str, Any]) -> int:
    v = _keys(args, ("a", "b"))
    return _n(v["a"]) + _n(v["b"])


def _multiply(args: dict[str, Any]) -> int:
    v = _keys(args, ("a", "b"))
    return _n(v["a"]) * _n(v["b"])


def _sum(args: dict[str, Any]) -> int:
    v = _keys(args, ("values",))
    return sum(_n(x) for x in _list(v["values"]))


def _move(args: dict[str, Any]) -> dict[str, int]:
    v = _keys(args, ("position", "delta"))
    x, y = _xy(v["position"])
    dx, dy = _xy(v["delta"])
    return {"x": x + dx, "y": y + dy}


def _neighbors(args: dict[str, Any]) -> list[dict[str, int]]:
    v = _keys(args, ("position", "width", "height"))
    x, y = _xy(v["position"])
    w, h = _n(v["width"], low=1, high=MAX_GRID), _n(v["height"], low=1, high=MAX_GRID)
    if not 0 <= x < w or not 0 <= y < h:
        raise CapabilityTaskError("position outside grid")
    # Fixed neighbor order makes game replays and unit tests deterministic.
    return [
        {"x": xx, "y": yy}
        for xx, yy in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1))
        if 0 <= xx < w and 0 <= yy < h
    ]


def _distance(args: dict[str, Any]) -> int:
    v = _keys(args, ("start", "goal"))
    x, y = _xy(v["start"])
    gx, gy = _xy(v["goal"])
    return abs(x - gx) + abs(y - gy)


def _pathfind(args: dict[str, Any]) -> dict[str, Any]:
    v = _keys(args, ("start", "goal", "width", "height", "blocked"))
    w, h = _n(v["width"], low=1, high=MAX_GRID), _n(v["height"], low=1, high=MAX_GRID)
    start, goal = _xy(v["start"]), _xy(v["goal"])
    blocked = {_xy(p) for p in _list(v["blocked"], limit=256)}
    for point in (start, goal, *blocked):
        if not 0 <= point[0] < w or not 0 <= point[1] < h:
            raise CapabilityTaskError("pathfinding point outside map bounds")
    if start in blocked or goal in blocked:
        return {"reachable": False, "steps": None, "path": []}
    queue = deque([start])
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            break
        for next_pos in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)):
            nx, ny = next_pos
            if not 0 <= nx < w or not 0 <= ny < h or next_pos in blocked or next_pos in parent:
                continue
            parent[next_pos] = (x, y)
            queue.append(next_pos)
    if goal not in parent:
        return {"reachable": False, "steps": None, "path": []}
    route: list[tuple[int, int]] = []
    node: tuple[int, int] | None = goal
    while node is not None:
        route.append(node)
        node = parent[node]
    route.reverse()
    return {
        "reachable": True, "steps": len(route) - 1,
        "path": [{"x": x, "y": y} for x, y in route],
    }


def _motion(args: dict[str, Any]) -> int:
    v = _keys(args, ("position", "velocity", "ticks"))
    p, speed = _n(v["position"]), _n(v["velocity"])
    ticks = _n(v["ticks"], low=0, high=10_000)
    return p + speed * ticks


def _integrate(args: dict[str, Any]) -> dict[str, int]:
    v = _keys(args, ("position", "velocity", "acceleration", "ticks"))
    x, y = _xy(v["position"])
    vx, vy = _xy(v["velocity"])
    ax, ay = _xy(v["acceleration"])
    ticks = _n(v["ticks"], low=0, high=10_000)
    # Symplectic Euler, integer-timestep; closed form avoids a long CPU loop.
    n = ticks * (ticks + 1) // 2
    return {
        "position": {"x": x + vx * ticks + ax * n,
                     "y": y + vy * ticks + ay * n},
        "velocity": {"x": vx + ax * ticks, "y": vy + ay * ticks},
        "ticks": ticks,
    }


def _aabb(args: dict[str, Any]) -> bool:
    v = _keys(args, ("a", "b"))
    x0, y0, x1, y1 = _rect(v["a"])
    u0, v0, u1, v1 = _rect(v["b"])
    return x0 < u1 and u0 < x1 and y0 < v1 and v0 < y1


def _point_rect(args: dict[str, Any]) -> bool:
    v = _keys(args, ("point", "rect"))
    x, y = _xy(v["point"])
    x0, y0, x1, y1 = _rect(v["rect"])
    return x0 <= x < x1 and y0 <= y < y1


_TRANSITIONS = {
    ("idle", "start"): "running",
    ("running", "pause"): "paused",
    ("paused", "resume"): "running",
    ("running", "stop"): "idle",
    ("paused", "stop"): "idle",
}


def _state(args: dict[str, Any]) -> str:
    v = _keys(args, ("state", "event"))
    state, event = _str(v["state"], 16), _str(v["event"], 16)
    if state not in ("idle", "running", "paused") or event not in (
        "start", "pause", "resume", "stop"
    ):
        raise CapabilityTaskError("unsupported state or event")
    return _TRANSITIONS.get((state, event), state)


def _inventory(args: dict[str, Any]) -> dict[str, Any]:
    v = _keys(args, ("current", "maximum", "action", "quantity"))
    current, maximum = _n(v["current"], low=0), _n(v["maximum"], low=0)
    qty = _n(v["quantity"], low=0)
    action = _str(v["action"], 16)
    if current > maximum or action not in ("add", "remove"):
        raise CapabilityTaskError("invalid inventory state/action")
    new = current + qty if action == "add" else current - qty
    accepted = 0 <= new <= maximum
    return {"accepted": accepted, "remaining": new if accepted else current}


def _damage(args: dict[str, Any]) -> int:
    v = _keys(args, ("health", "damage"))
    return max(0, _n(v["health"], low=0) - _n(v["damage"], low=0))


def _coins(args: dict[str, Any]) -> int:
    v = _keys(args, ("coins", "points_per_coin"))
    return _n(v["coins"], low=0) * _n(v["points_per_coin"], low=0)


def _cooldown(args: dict[str, Any]) -> int:
    v = _keys(args, ("frames", "elapsed"))
    return max(0, _n(v["frames"], low=0) - _n(v["elapsed"], low=0))


def _animation(args: dict[str, Any]) -> int:
    v = _keys(args, ("tick", "frames", "ticks_per_frame"))
    tick = _n(v["tick"], low=0)
    frames = _n(v["frames"], low=1, high=256)
    step = _n(v["ticks_per_frame"], low=1, high=100_000)
    return (tick // step) % frames


def _event_order(args: dict[str, Any]) -> list[str]:
    v = _keys(args, ("events",))
    events = _list(v["events"])
    ordered: list[tuple[int, int, str]] = []
    for n, item in enumerate(events):
        event = _keys(item, ("name", "tick"))
        ordered.append((_n(event["tick"]), n, _str(event["name"], 64)))
    return [name for tick, original, name in sorted(ordered)]


def _event_elapsed(args: dict[str, Any]) -> int:
    v = _keys(args, ("start_tick", "end_tick"))
    start, end = _n(v["start_tick"]), _n(v["end_tick"])
    if end < start:
        raise CapabilityTaskError("end tick precedes start tick")
    return end - start


def _json_select(args: dict[str, Any]) -> dict[str, Any]:
    v = _keys(args, ("object", "keys"))
    obj = v["object"]
    if not isinstance(obj, dict) or len(obj) > MAX_COLLECTION:
        raise CapabilityTaskError("source JSON must be bounded object")
    requested = _list(v["keys"])
    if any(not isinstance(k, str) or len(k) > 128 for k in requested):
        raise CapabilityTaskError("selection keys must be bounded strings")
    if len(requested) != len(set(requested)):
        raise CapabilityTaskError("selection keys must be unique")
    if any(k not in obj for k in requested):
        raise CapabilityTaskError("requested source field is absent")
    return {key: obj[key] for key in requested}


def _normalize(args: dict[str, Any]) -> str:
    v = _keys(args, ("text",))
    data = _str(v["text"])
    # No Unicode transliteration promise: ASCII case-folding only.
    data = re.sub(r"[,;!/]", " ", data)
    data = "".join(chr(ord(ch) + 32) if "A" <= ch <= "Z" else ch for ch in data)
    return " ".join(data.split())


def _policy(args: dict[str, Any]) -> dict[str, Any]:
    v = _keys(args, ("action", "operator_selected"))
    action = _str(v["action"], 24)
    operator_selected = v["operator_selected"]
    if type(operator_selected) is not bool or action not in (
        "read_local_text", "fetch_url", "execute_binary", "write_workspace",
    ):
        raise CapabilityTaskError("unsupported offline authorization action")
    # No I/O is performed and caller-provided flags are NOT authorization.
    # This is a *policy recommendation* only; executor still needs grants.
    return {
        "policy_allow": action == "read_local_text" and operator_selected,
        "executor_permission_granted": False,
    }


def _fact(args: dict[str, Any]) -> dict[str, Any]:
    v = _keys(args, ("facts", "key"))
    facts = v["facts"]
    if not isinstance(facts, dict) or len(facts) > MAX_COLLECTION:
        raise CapabilityTaskError("evidence facts must be bounded mapping")
    key = _str(v["key"], 64)
    if key not in facts:
        return {"found": False, "value": None, "source_trusted": False}
    return {"found": True, "value": facts[key], "source_trusted": False}


def _hash_text(args: dict[str, Any]) -> str:
    v = _keys(args, ("text",))
    return hashlib.sha256(_str(v["text"]).encode("utf-8")).hexdigest()


OPERATIONS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "math.add": _add,
    "math.multiply": _multiply,
    "math.sum": _sum,
    "grid.move": _move,
    "grid.neighbors": _neighbors,
    "grid.manhattan": _distance,
    "grid.shortest_path": _pathfind,
    "physics.advance_1d": _motion,
    "physics.integrate_2d": _integrate,
    "collision.aabb": _aabb,
    "collision.point_rect": _point_rect,
    "state.transition": _state,
    "inventory.update": _inventory,
    "game.damage": _damage,
    "game.coins": _coins,
    "game.cooldown": _cooldown,
    "game.animation_frame": _animation,
    "events.order": _event_order,
    "events.elapsed": _event_elapsed,
    "json.select": _json_select,
    "text.normalize": _normalize,
    "policy.local_action": _policy,
    "evidence.lookup": _fact,
    "content.sha256": _hash_text,
    **GAMEPLAY_OPERATIONS,
}


def _strict_json(data: bytes) -> dict[str, Any]:
    if not isinstance(data, bytes):
        raise CapabilityTaskError("task JSON must be bytes")
    if len(data) > MAX_INPUT_BYTES:
        raise CapabilityTaskError("task payload exceeds size limit")
    try:
        parsed = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=lambda entries: _pairs(entries),
            parse_constant=lambda token: _invalid_constant(token),
        )
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise CapabilityTaskError("invalid task JSON") from exc
    if not isinstance(parsed, dict):
        raise CapabilityTaskError("task JSON must be an object")
    return parsed


def _pairs(entries: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in entries:
        if key in result:
            raise CapabilityTaskError("duplicate task JSON key")
        result[key] = value
    return result


def _invalid_constant(token: str) -> None:
    raise CapabilityTaskError("nonfinite numeric value")


def execute_capability_task(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute a single read-only, deterministic typed task, with no I/O."""
    if not isinstance(payload, dict) or set(payload) != {"operation", "args"}:
        raise CapabilityTaskError("task requires only operation and args")
    op = payload["operation"]
    args = payload["args"]
    if not isinstance(op, str) or op not in OPERATIONS or not isinstance(args, dict):
        raise CapabilityTaskError("operation unsupported or arguments invalid")
    # Also enforce size on direct Python API use, not only JSON CLI input.
    try:
        canonical = json.dumps(payload, sort_keys=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CapabilityTaskError("task is not JSON-compatible") from exc
    if len(canonical) > MAX_INPUT_BYTES:
        raise CapabilityTaskError("task exceeds bounded input size")
    result = OPERATIONS[op](args)
    receipt = {
        "schema_version": SCHEMA,
        "operation": op,
        "result": result,
        "result_sha256": hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False).encode("ascii")
        ).hexdigest(),
        "deterministic": True,
        "model_inference_used": False,
        "network_access_used": False,
        "filesystem_access_used": False,
        "authority_granted": False,
    }
    if len(json.dumps(receipt, ensure_ascii=True).encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise CapabilityTaskError("capability output exceeds bounded domain")
    return receipt


def execute_capability_json(data: bytes) -> dict[str, Any]:
    return execute_capability_task(_strict_json(data))


__all__ = [
    "SCHEMA", "MAX_INPUT_BYTES", "MAX_OUTPUT_BYTES", "OPERATIONS",
    "CapabilityTaskError", "execute_capability_task", "execute_capability_json",
]
