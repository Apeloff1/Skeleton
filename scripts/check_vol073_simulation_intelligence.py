#!/usr/bin/env python3
"""Independent repository verifier for VOL-073 Game & Simulation Intelligence."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/ai_simulation_contract.json"
WORLD = ROOT / "skeleton/simulation/world.py"
AUTHORITY = ROOT / "skeleton/simulation/authority.py"
WORLD_MODEL = ROOT / "skeleton/simulation/world_model.py"
ENVIRONMENT = ROOT / "skeleton/simulation/environment.py"
TESTS = ROOT / "tests/test_vol073_simulation_intelligence.py"
WORKFLOW = ROOT / ".github/workflows/vol073-simulation-intelligence.yml"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"unable to load {path.relative_to(ROOT)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate() -> list[str]:
    errors: list[str] = []
    required = (MANIFEST, WORLD, AUTHORITY, WORLD_MODEL, ENVIRONMENT, TESTS, WORKFLOW)
    for path in required:
        if not path.is_file():
            errors.append(f"required VOL-073 surface missing: {path.relative_to(ROOT)}")
    if errors:
        return errors

    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        errors.append("simulation contract schema_version must be 1")
    if payload.get("volume") != "VOL-073":
        errors.append("simulation contract must bind VOL-073")
    if payload.get("status") != "implementation_contract":
        errors.append("simulation contract must remain implementation_contract before promotion")

    policy = payload.get("policy")
    if not isinstance(policy, dict):
        errors.append("simulation policy must be an object")
    else:
        for key in ("state_rule", "authority_rule", "resource_rule"):
            if not isinstance(policy.get(key), str) or not policy[key].strip():
                errors.append(f"simulation policy missing {key}")

    authority = payload.get("authority")
    if not isinstance(authority, dict):
        errors.append("simulation authority block must be an object")
    else:
        if authority.get("real_side_effect_authority") is not False:
            errors.append("VOL-073 must not grant real side-effect authority")
        if authority.get("world_model_dependency") != "skeleton.simulation.world.WorldState":
            errors.append("world-model state dependency drift")

    world_model_text = WORLD_MODEL.read_text(encoding="utf-8")
    if "from skeleton.simulation.world import WorldState" not in world_model_text:
        errors.append("existing world model is not bound to canonical WorldState")

    world = _load("vol073_world_verify", WORLD)
    guard_module = _load("vol073_authority_verify", AUTHORITY)
    required_world_exports = {
        "WORLD_STATE_SCHEMA",
        "SimulationAction",
        "SimulationEvidence",
        "WorldRule",
        "WorldRules",
        "WorldState",
        "WorldStateError",
        "verify_transition",
    }
    required_authority_exports = {
        "SIMULATION_AUTHORITY_SCHEMA",
        "RolloutRequest",
        "SimulationActionLike",
        "SimulationAuthorityError",
        "SimulationAuthorityGuard",
        "SimulationPermit",
        "SimulationResourceBudget",
        "SimulationStateLike",
    }
    if set(world.__all__) != required_world_exports:
        errors.append("canonical WorldState export contract drift")
    if set(guard_module.__all__) != required_authority_exports:
        errors.append("simulation authority export contract drift")

    try:
        rule = world.WorldRule("smoke-rule", "Remain inside the simulated boundary.", {})
        rules = world.WorldRules("smoke-rules", (rule,))
        state = world.WorldState(
            world_id="smoke-world",
            tick=0,
            rules_digest=rules.digest,
            values={"position": 0},
            uncertainty=0.1,
        )
        action = world.SimulationAction(
            action_id="smoke-action",
            actor_id="smoke-agent",
            intent="Advance one simulated unit.",
            parameters={"delta": 1},
            requested_capabilities=("simulate.read-state",),
        )
        default_budget = payload["default_budget"]
        budget = guard_module.SimulationResourceBudget(**default_budget)
        guard = guard_module.SimulationAuthorityGuard(
            guard_id="vol073-smoke",
            budget=budget,
            allowed_capabilities=payload["allowed_simulation_capabilities"],
        )
        request = guard_module.RolloutRequest(
            request_id="smoke-rollout",
            depth=1,
            branching_factor=1,
            planned_nodes=1,
            compute_units=1,
        )
        permit = guard.authorize(state=state, action=action, request=request)
        guard.verify(permit, state=state, action=action, request=request)
        if permit.can_execute_real_side_effect is not False:
            errors.append("simulation permit unexpectedly grants real side effects")
        if state.can_support_real_world_fact is not False:
            errors.append("simulation state unexpectedly supports real-world fact")
    except Exception as exc:
        errors.append(f"simulation smoke contract failed: {exc}")

    forbidden = payload.get("forbidden_real_capabilities")
    allowed = payload.get("allowed_simulation_capabilities")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("forbidden real capability registry must be non-empty")
    if not isinstance(allowed, list) or not allowed:
        errors.append("allowed simulation capability registry must be non-empty")
    if isinstance(forbidden, list) and isinstance(allowed, list):
        if set(forbidden).intersection(allowed):
            errors.append("real and simulation capability sets must be disjoint")

    implementation = payload.get("implementation", {})
    expected = {
        "state_contract": "skeleton/simulation/world.py",
        "authority_guard": "skeleton/simulation/authority.py",
        "tests": "tests/test_vol073_simulation_intelligence.py",
        "verifier": "scripts/check_vol073_simulation_intelligence.py",
        "workflow": ".github/workflows/vol073-simulation-intelligence.yml",
    }
    if implementation != expected:
        errors.append("simulation implementation path binding drift")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-073 ERROR: {error}")
        return 1
    print(
        "VOL-073 OK: canonical state/rules/uncertainty, simulation-only authority, "
        "bounded rollout resources, capability allowlisting, and world-model integration verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
