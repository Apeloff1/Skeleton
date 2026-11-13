"""CAS-bound source editor for the original Lantern Quay playable campaign.

Edits are pure data, allowlisted, bounded and replay-verifiable. A revision
includes both the original authored world and the resulting validated source.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _items, _keys,
    canonical, digest, validate_source,
)

REVISION_SCHEMA = "skeleton.game.harbor.revision.v1"
MAX_EDITS = 32
SHAPES = {
    "stock": {"op", "id", "quantity"},
    "merchant_price": {"op", "price"},
    "max_ticks": {"op", "value"},
    "move_resource": {"op", "id", "at"},
    "tile": {"op", "at", "tile"},
    "recipe": {"op", "id", "inputs", "output"},
    "delivery": {"op", "item", "quantity"},
}


def _location(value: Any, source: dict[str, Any]) -> list[int]:
    if not isinstance(value, list) or len(value) != 2:
        raise HarborError("invalid editor coordinate")
    return [
        _integer(value[0], 0, len(source["map"][0]) - 1, "editor x"),
        _integer(value[1], 0, len(source["map"]) - 1, "editor y"),
    ]


def _reachable(source: dict[str, Any]) -> None:
    """Reject edits that disconnect a finite resource or every dock approach."""
    tiles = source["map"]
    start = tuple(source["start"])
    queue = [start]
    seen = {start}
    for x, y in queue:
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= ny < len(tiles) and 0 <= nx < len(tiles[0])):
                continue
            point = (nx, ny)
            if tiles[ny][nx] == "." and point not in seen:
                seen.add(point)
                queue.append(point)
    for resource in source["resources"]:
        if tuple(resource["at"]) not in seen:
            raise HarborError("resource unreachable after edit")
    dock = tuple(source["dock"])
    if not any(abs(x - dock[0]) + abs(y - dock[1]) == 1 for x, y in seen):
        raise HarborError("dock unreachable after edit")


def _edit_key(operation: dict[str, Any]) -> tuple[Any, ...]:
    kind = operation["op"]
    if kind in {"stock", "move_resource", "recipe"}:
        return (kind, operation["id"])
    if kind == "delivery":
        return (kind, operation["item"])
    if kind == "tile":
        return (kind, *operation["at"])
    return (kind,)


def _apply_one(source: dict[str, Any], operation: Any) -> None:
    if not isinstance(operation, dict):
        raise HarborError("editor operation must be an object")
    kind = operation.get("op")
    if not isinstance(kind, str) or kind not in SHAPES:
        raise HarborError("unknown editor operation")
    _keys(operation, SHAPES[kind], "editor operation")
    if kind in {"stock", "move_resource", "recipe"}:
        item_id = _identifier(operation["id"], "editor id")
    if kind == "stock":
        quantity = _integer(operation["quantity"], 1, 64, "resource stock")
        resource = next((r for r in source["resources"] if r["id"] == item_id), None)
        if resource is None:
            raise HarborError("unknown resource id")
        resource["quantity"] = quantity
    elif kind == "merchant_price":
        source["npc"]["price"] = _integer(operation["price"], 1, 64, "merchant price")
    elif kind == "max_ticks":
        source["max_ticks"] = _integer(operation["value"], 1, 1024, "max_ticks")
    elif kind == "move_resource":
        resource = next((r for r in source["resources"] if r["id"] == item_id), None)
        if resource is None:
            raise HarborError("unknown resource id")
        resource["at"] = _location(operation["at"], source)
    elif kind == "tile":
        x, y = _location(operation["at"], source)
        if operation["tile"] not in ("#", ".") or type(operation["tile"]) is not str:
            raise HarborError("invalid editor tile")
        row = source["map"][y]
        source["map"][y] = row[:x] + operation["tile"] + row[x + 1:]
    elif kind == "recipe":
        recipe = next((r for r in source["recipes"] if r["id"] == item_id), None)
        if recipe is None:
            raise HarborError("unknown recipe id")
        recipe["inputs"] = deepcopy(_items(operation["inputs"], "editor recipe inputs"))
        recipe["output"] = deepcopy(_items(operation["output"], "editor recipe output"))
    elif kind == "delivery":
        item = _identifier(operation["item"], "delivery item")
        if item not in source["delivery"]:
            raise HarborError("unknown delivery item")
        source["delivery"][item] = _integer(operation["quantity"], 1, 64, "delivery quantity")


def author_revision(
    source: Any,
    operations: Any,
    *,
    expected_source_digest: str,
) -> dict[str, Any]:
    original = validate_source(source)
    parent_digest = digest(original)
    if not isinstance(expected_source_digest, str) or expected_source_digest != parent_digest:
        raise HarborError("stale source digest")
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_EDITS:
        raise HarborError("invalid edit count")
    result = deepcopy(original)
    seen: set[tuple[Any, ...]] = set()
    for operation in operations:
        _apply_one(result, operation)
        target = _edit_key(operation)
        if target in seen:
            raise HarborError("duplicate edit target")
        seen.add(target)
    validated = validate_source(result)
    _reachable(validated)
    if digest(validated) == parent_digest:
        raise HarborError("no-op revision")
    revision = {
        "schema": REVISION_SCHEMA,
        "parent": original,
        "parent_digest": parent_digest,
        "operations": deepcopy(operations),
        "source": validated,
        "source_digest": digest(validated),
    }
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_BUNDLE_BYTES:
        raise HarborError("revision exceeds byte limit")
    return revision


def verify_revision(revision: Any) -> dict[str, Any]:
    _keys(revision, {
        "schema", "parent", "parent_digest", "operations",
        "source", "source_digest", "revision_digest",
    }, "revision")
    if revision["schema"] != REVISION_SCHEMA or len(canonical(revision)) > MAX_BUNDLE_BYTES:
        raise HarborError("unsupported or oversized revision")
    if revision["revision_digest"] != digest({
        key: value for key, value in revision.items() if key != "revision_digest"
    }):
        raise HarborError("revision digest mismatch")
    replayed = author_revision(
        revision["parent"], revision["operations"],
        expected_source_digest=revision["parent_digest"],
    )
    if replayed != revision:
        raise HarborError("source revision replay mismatch")
    return deepcopy(replayed["source"])
