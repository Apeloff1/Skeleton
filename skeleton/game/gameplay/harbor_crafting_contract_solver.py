"""Bounded source-bound solver for the next real delivery contract."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import (
    HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, verify_bundle,
)
from .harbor_crafting_contracts import (
    MAX_SAVE_BYTES, append_save, next_order, verify_save,
)
from .harbor_crafting_planner import solve, verify_plan

PLAN_SCHEMA = "skeleton.game.harbor.contract-plan.v1"
MAX_PLAN_BYTES = MAX_BUNDLE_BYTES + MAX_SAVE_BYTES + 65536
FIELDS = {"schema", "before", "before_digest", "order_id", "plan",
          "after", "after_digest", "plan_digest"}


def solve_contract(save: Any) -> dict[str, Any]:
    """Offer a plan only if canonical gameplay actually satisfies this order."""
    status = verify_save(save)
    pending = next_order(save)
    if pending["status"] != "ready":
        raise HarborError("no pending contract to solve")
    order = pending["order"]
    plan = solve(save["source"], choice=order["ending"])
    verify_plan(plan)
    advanced = append_save(save, plan["bundle"], expected_digest=status["save_digest"])
    record = {
        "schema": PLAN_SCHEMA, "before": deepcopy(save),
        "before_digest": status["save_digest"],
        "order_id": order["id"], "plan": plan,
        "after": advanced, "after_digest": advanced["save_digest"],
    }
    record["plan_digest"] = digest(record)
    if len(canonical(record)) > MAX_PLAN_BYTES:
        raise HarborError("contract plan byte limit")
    return record


def verify_contract_plan(value: Any) -> dict[str, Any]:
    """Recompute deterministic route, earned ending, and CAS continuation."""
    _keys(value, FIELDS, "contract plan")
    if value["schema"] != PLAN_SCHEMA or len(canonical(value)) > MAX_PLAN_BYTES:
        raise HarborError("unsupported or oversized contract plan")
    if value["plan_digest"] != digest({k: v for k, v in value.items() if k != "plan_digest"}):
        raise HarborError("contract plan digest mismatch")
    before = verify_save(value["before"])
    after = verify_save(value["after"])
    if before["save_digest"] != value["before_digest"] or after["save_digest"] != value["after_digest"]:
        raise HarborError("contract plan custody mismatch")
    verify_plan(value["plan"])
    if value["plan"]["bundle"]["source_digest"] != value["before"]["source_digest"]:
        raise HarborError("contract plan source mismatch")
    rebuilt = solve_contract(value["before"])
    if rebuilt != value:
        raise HarborError("contract plan replay mismatch")
    return {
        "order_id": rebuilt["order_id"],
        "next_order": after["next_order"],
        "complete": after["complete"],
        "save_digest": after["save_digest"],
    }
