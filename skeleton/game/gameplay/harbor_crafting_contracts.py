"""Portable source-bound delivery contracts over the actual Lantern Quay game."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _identifier, _integer, _keys,
    canonical, digest, export_bundle, validate_source, verify_bundle,
)

BOARD_SCHEMA = "skeleton.game.harbor.contracts.v1"
SAVE_SCHEMA = "skeleton.game.harbor.contract-save.v1"
EDIT_SCHEMA = "skeleton.game.harbor.contract-edit.v1"
MAX_BOARD_BYTES = 32768
MAX_SAVE_BYTES = MAX_BUNDLE_BYTES * 8 + 65536
MAX_EDITS_BYTES = 131072
MAX_ORDERS = 8
RULES = {"min_gathers", "min_crafts", "min_trades", "max_waits", "min_coins", "min_reputation"}


def validate_board(board: Any, source: Any) -> dict[str, Any]:
    world = validate_source(source)
    _keys(board, {"schema", "source_id", "orders"}, "contract board")
    if board["schema"] != BOARD_SCHEMA or board["source_id"] != world["id"]:
        raise HarborError("contract source mismatch")
    if len(canonical(board)) > MAX_BOARD_BYTES:
        raise HarborError("contract board exceeds byte limit")
    orders = board["orders"]
    if not isinstance(orders, list) or not 1 <= len(orders) <= MAX_ORDERS:
        raise HarborError("invalid contract count")
    seen: set[str] = set()
    for order in orders:
        _keys(order, {"id", "ending", "deadline", "rules"}, "contract order")
        name = _identifier(order["id"], "contract id")
        if name in seen:
            raise HarborError("duplicate contract id")
        seen.add(name)
        if type(order["ending"]) is not str or order["ending"] not in ("signal", "shelter"):
            raise HarborError("invalid contract ending")
        deadline = _integer(order["deadline"], 1, world["max_ticks"], "contract deadline")
        rules = _keys(order["rules"], RULES, "contract rules")
        for field in ("min_gathers", "min_crafts", "min_trades", "max_waits"):
            _integer(rules[field], 0, deadline, field)
        _integer(rules["min_coins"], 0, 64, "min_coins")
        _integer(rules["min_reputation"], 0, 1024, "min_reputation")
        if sum(rules[k] for k in ("min_gathers", "min_crafts", "min_trades")) + 2 > deadline:
            raise HarborError("contract requirements exceed deadline")
    return deepcopy(board)


def _earn(bundle: Any, order: dict[str, Any], source_digest: str) -> dict[str, Any]:
    state = verify_bundle(bundle, require_win=True)
    if bundle["source_digest"] != source_digest:
        raise HarborError("contract replay source mismatch")
    ending = "beacon" if order["ending"] == "signal" else "safe_harbor"
    if state["ending"] != ending or state["tick"] > order["deadline"]:
        raise HarborError("contract consequence or deadline not earned")
    counts = {op: sum(event["action"]["op"] == op for event in bundle["events"])
              for op in ("gather", "craft", "trade", "wait")}
    rules = order["rules"]
    if any(counts[op] < rules[field] for field, op in (
        ("min_gathers", "gather"), ("min_crafts", "craft"), ("min_trades", "trade")
    )) or counts["wait"] > rules["max_waits"]:
        raise HarborError("contract activity not earned")
    if state["coins"] < rules["min_coins"] or state["reputation"] < rules["min_reputation"]:
        raise HarborError("contract economy not earned")
    return {"id": order["id"], "bundle": deepcopy(bundle), "counts": counts,
            "ending": state["ending"], "tick": state["tick"],
            "coins": state["coins"], "reputation": state["reputation"]}


def build_save(source: Any, board: Any, bundles: Any) -> dict[str, Any]:
    world = validate_source(source)
    authored = validate_board(board, world)
    if not isinstance(bundles, list) or len(bundles) > len(authored["orders"]):
        raise HarborError("invalid contract replay count")
    if len(canonical(bundles)) > MAX_SAVE_BYTES:
        raise HarborError("contract replay byte limit")
    results = []
    seen: set[str] = set()
    for index, bundle in enumerate(bundles):
        # Verify canonical custody before consulting any untrusted digest field.
        verify_bundle(bundle, require_win=True)
        if bundle["bundle_digest"] in seen:
            raise HarborError("duplicate contract replay")
        earned = _earn(bundle, authored["orders"][index], digest(world))
        seen.add(bundle["bundle_digest"])
        results.append(earned)
    save = {"schema": SAVE_SCHEMA, "source": world, "source_digest": digest(world),
            "board": authored, "board_digest": digest(authored),
            "results": results, "next_order": len(results),
            "complete": len(results) == len(authored["orders"])}
    save["save_digest"] = digest(save)
    if len(canonical(save)) > MAX_SAVE_BYTES:
        raise HarborError("contract save byte limit")
    return save


def verify_save(save: Any) -> dict[str, Any]:
    _keys(save, {"schema", "source", "source_digest", "board", "board_digest",
                 "results", "next_order", "complete", "save_digest"}, "contract save")
    if save["schema"] != SAVE_SCHEMA or len(canonical(save)) > MAX_SAVE_BYTES:
        raise HarborError("unsupported or oversized contract save")
    if save["save_digest"] != digest({k: v for k, v in save.items() if k != "save_digest"}):
        raise HarborError("contract save digest mismatch")
    if not isinstance(save["results"], list) or len(save["results"]) > MAX_ORDERS:
        raise HarborError("invalid contract results")
    bundles = []
    for result in save["results"]:
        _keys(result, {"id", "bundle", "counts", "ending", "tick", "coins", "reputation"}, "contract result")
        bundles.append(result["bundle"])
    rebuilt = build_save(save["source"], save["board"], bundles)
    if rebuilt != save:
        raise HarborError("contract replay verification mismatch")
    return {"complete": rebuilt["complete"], "next_order": rebuilt["next_order"],
            "save_digest": rebuilt["save_digest"]}


def append_save(save: Any, bundle: Any, *, expected_digest: str) -> dict[str, Any]:
    status = verify_save(save)
    if type(expected_digest) is not str or expected_digest != status["save_digest"]:
        raise HarborError("stale contract checkpoint")
    if status["complete"]:
        raise HarborError("contract board already complete")
    return build_save(save["source"], save["board"],
                      [r["bundle"] for r in save["results"]] + [bundle])


def play_save(save: Any, actions: Any, *, expected_digest: str) -> dict[str, Any]:
    status = verify_save(save)
    if expected_digest != status["save_digest"]:
        raise HarborError("stale contract checkpoint")
    if status["complete"]:
        raise HarborError("contract board already complete")
    bundle = export_bundle(save["source"], actions, require_win=True)
    return append_save(save, bundle, expected_digest=expected_digest)


def next_order(save: Any) -> dict[str, Any]:
    status = verify_save(save)
    if status["complete"]:
        return {"status": "complete", "order": None, "source": None,
                "save_digest": status["save_digest"]}
    return {"status": "ready", "order": deepcopy(save["board"]["orders"][status["next_order"]]),
            "source": deepcopy(save["source"]), "save_digest": status["save_digest"]}


def edit_board(source: Any, board: Any, edits: Any, *,
               expected_source_digest: str, expected_board_digest: str) -> dict[str, Any]:
    world = validate_source(source)
    before = validate_board(board, world)
    if expected_source_digest != digest(world) or expected_board_digest != digest(before):
        raise HarborError("stale contract authoring lease")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 16 or len(canonical(edits)) > MAX_BOARD_BYTES:
        raise HarborError("invalid contract edits")
    after = deepcopy(before)
    for edit in edits:
        _keys(edit, {"id", "field", "value"}, "contract edit")
        name = _identifier(edit["id"], "contract edit id")
        order = next((o for o in after["orders"] if o["id"] == name), None)
        if order is None:
            raise HarborError("unknown contract edit target")
        field = edit["field"]
        if type(field) is not str:
            raise HarborError("invalid contract edit field")
        if field in RULES:
            order["rules"][field] = edit["value"]
        elif field in ("deadline", "ending"):
            order[field] = edit["value"]
        else:
            raise HarborError("unsupported contract edit field")
    after = validate_board(after, world)
    revision = {"schema": EDIT_SCHEMA, "source": world, "before": before,
                "before_digest": digest(before), "edits": deepcopy(edits),
                "after": after, "after_digest": digest(after)}
    revision["revision_digest"] = digest(revision)
    if len(canonical(revision)) > MAX_EDITS_BYTES:
        raise HarborError("contract revision byte limit")
    return revision


def verify_edit(revision: Any) -> dict[str, Any]:
    _keys(revision, {"schema", "source", "before", "before_digest", "edits",
                     "after", "after_digest", "revision_digest"}, "contract revision")
    if revision["schema"] != EDIT_SCHEMA or len(canonical(revision)) > MAX_EDITS_BYTES:
        raise HarborError("unsupported or oversized contract revision")
    if revision["revision_digest"] != digest({k: v for k, v in revision.items()
                                               if k != "revision_digest"}):
        raise HarborError("contract revision digest mismatch")
    rebuilt = edit_board(revision["source"], revision["before"], revision["edits"],
                         expected_source_digest=digest(revision["source"]),
                         expected_board_digest=revision["before_digest"])
    if rebuilt != revision:
        raise HarborError("contract authoring replay mismatch")
    return {"after_digest": rebuilt["after_digest"], "orders": len(rebuilt["after"]["orders"])}
