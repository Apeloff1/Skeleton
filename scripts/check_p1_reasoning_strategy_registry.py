#!/usr/bin/env python3
"""Validate the canonical P1 reasoning/search/stopping strategy registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from skeleton.intelligence.strategy_registry import (
    REASONING_STRATEGY_ACCOUNTABILITY_ID,
    REASONING_STRATEGY_TASK_ID,
    ReasoningStrategyError,
    registry_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = Path("machine/p1_reasoning_strategy_registry.json")
MASTER_PLAN_PATH = Path("machine/ai_master_plan.json")
EXPECTED_REGISTRY_ID = "skeleton.p1.reasoning_strategy_registry"
EXPECTED_STRATEGY_IDS = {
    "direct_verified",
    "retrieve_then_reason",
    "bounded_search",
    "plan_then_verify",
    "ensemble_then_abstain",
}
EXPECTED_SELECTION_POLICY = {
    "order": "lowest_priority_then_id",
    "required_capabilities_must_be_subset": True,
    "request_budget_is_hard_ceiling": True,
    "registry_limits_are_hard_ceiling": True,
    "no_eligible_strategy": "abstain",
    "model_self_confidence_is_not_authority": True,
}
EXPECTED_STOP_POLICY = {
    "over_budget": "policy_violation",
    "verified_completion": "stop_success",
    "unverified_completion": "abstain_unverified",
    "hard_limit_reached": "stop_budget",
    "low_evidence_gain_and_low_value_of_information":
        "stop_diminishing_returns",
    "high_uncertainty_without_evidence_gain": "abstain_uncertain",
    "otherwise": "continue",
}


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReasoningStrategyError(f"cannot load {path}") from exc


def validate_repository(root: Path = ROOT) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    payload = _load(root / REGISTRY_PATH)
    master = _load(root / MASTER_PLAN_PATH)

    if not isinstance(payload, dict):
        return ["reasoning registry must be an object"], {"valid": False}
    if not isinstance(master, dict):
        errors.append("master plan must be an object")
        master = {}

    authority = master.get("authority")
    if not isinstance(authority, dict):
        errors.append("master plan authority must be an object")
    elif authority.get("p1_reasoning_strategy_registry") != str(REGISTRY_PATH):
        errors.append("master plan reasoning strategy registry pointer drift")

    if payload.get("schema_version") != 1:
        errors.append("registry schema_version must equal 1")
    if payload.get("registry_id") != EXPECTED_REGISTRY_ID:
        errors.append("registry_id drift")
    if payload.get("task_id") != REASONING_STRATEGY_TASK_ID:
        errors.append("registry task_id drift")
    if payload.get("accountability_ref") != REASONING_STRATEGY_ACCOUNTABILITY_ID:
        errors.append("registry accountability_ref drift")
    if payload.get("selection_policy") != EXPECTED_SELECTION_POLICY:
        errors.append("selection_policy drift")
    if payload.get("stop_policy") != EXPECTED_STOP_POLICY:
        errors.append("stop_policy drift")

    try:
        registry = registry_from_payload(payload)
    except (ReasoningStrategyError, TypeError, ValueError) as exc:
        errors.append(f"registry contract invalid: {exc}")
        registry = None

    if registry is not None:
        ids = {item.strategy_id for item in registry.strategies}
        if ids != EXPECTED_STRATEGY_IDS:
            errors.append(
                "strategy inventory drift: "
                f"expected={sorted(EXPECTED_STRATEGY_IDS)} "
                f"actual={sorted(ids)}"
            )
        priorities = [item.priority for item in registry.strategies]
        if len(priorities) != len(set(priorities)):
            errors.append("strategy priorities must be unique")
        for item in registry.strategies:
            if "verification" not in item.capabilities:
                errors.append(
                    f"{item.strategy_id}: verification capability is required"
                )

    summary = {
        "schema_version": 1,
        "registry_id": payload.get("registry_id"),
        "registry_version": payload.get("registry_version"),
        "strategy_count": (
            0 if registry is None else len(registry.strategies)
        ),
        "registry_digest": (
            None if registry is None else registry.digest
        ),
        "valid": not errors,
        "errors": errors,
    }
    return errors, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    try:
        errors, summary = validate_repository(ROOT)
    except ReasoningStrategyError as exc:
        print(f"P1 reasoning registry: rejected: {exc}", file=sys.stderr)
        return 2
    if args.print_summary:
        print(json.dumps(summary, indent=2, sort_keys=True))
    for error in errors:
        print(f"P1 reasoning registry: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
