#!/usr/bin/env python3
"""Validate the 500-level dual-rival AI game-builder authority."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_game_builder_500_levels.json")
DUEL = Path("machine/ai_game_builder_dual_rival_forge.json")
OVERENGINEERING = Path("machine/ai_game_builder_overengineering.json")
MASTER = Path("docs/plan/MASTER_PLAN.md")
HUMAN = Path("docs/architecture/AI_GAME_BUILDER_500_LEVELS.md")
OVERENGINEERING_HUMAN = Path("docs/architecture/AI_GAME_BUILDER_OVERENGINEERING.md")
RUNTIME_CONTRACTS = Path("skeleton/ai/game_builder/contracts.py")
RUNTIME_FORGE = Path("skeleton/ai/game_builder/dual_rival_forge.py")
RUNTIME_TESTS = Path("tests/test_ai_game_builder_runtime.py")
GOVERNANCE_CANON = Path("skeleton/ai/game_builder/canon.py")
GOVERNANCE_RIGHTS = Path("skeleton/ai/game_builder/rights.py")
GOVERNANCE_ATOMS = Path("skeleton/ai/game_builder/atomizer.py")
GOVERNANCE_TESTS = Path("tests/test_ai_game_builder_governance.py")
EVALUATION_RUNTIME = Path("skeleton/ai/game_builder/evaluation.py")
RESOURCE_RUNTIME = Path("skeleton/ai/game_builder/resource_governor.py")
QUALITY_DEBT_RUNTIME = Path("skeleton/ai/game_builder/quality_debt.py")
CONTROL_PLANE_RUNTIME = Path("skeleton/ai/game_builder/control_plane.py")
RESILIENCE_RUNTIME = Path("skeleton/ai/game_builder/resilience.py")
GOLD_MASTER_RUNTIME = Path("skeleton/ai/game_builder/release.py")
FRONTIER_ASSURANCE_RUNTIME = Path("skeleton/ai/game_builder/frontier_assurance.py")
DEEP_ASSURANCE_RUNTIME = Path("skeleton/ai/game_builder/deep_assurance.py")
OVERENGINEERING_RUNTIME_TESTS = Path("tests/test_ai_game_builder_overengineering_runtime.py")
FRONTIER_RUNTIME_TESTS = Path("tests/test_ai_game_builder_frontier_runtime.py")
DEEP_ASSURANCE_TESTS = Path("tests/test_ai_game_builder_deep_assurance.py")


class GameBuilderAuthorityError(RuntimeError):
    pass


def _reject_constant(token: str) -> None:
    raise GameBuilderAuthorityError(f"non-finite JSON token rejected: {token}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GameBuilderAuthorityError(f"duplicate JSON object key: {key}")
        out[key] = value
    return out


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise GameBuilderAuthorityError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GameBuilderAuthorityError(f"{path} must contain an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GameBuilderAuthorityError(f"{label} must be non-empty text")
    return value.strip()


def _list(value: Any, label: str, minimum: int = 1) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum:
        raise GameBuilderAuthorityError(f"{label} requires at least {minimum} entries")
    return value


def _alias(row: dict[str, Any], long_key: str, short_key: str, label: str, minimum: int) -> list[Any]:
    value = row.get(long_key, row.get(short_key))
    return _list(value, label, minimum)


def _effort_rounds(row: dict[str, Any]) -> list[int]:
    value = row.get("effort_rounds")
    if isinstance(value, list):
        return value
    value = row.get("effort_modes")
    if isinstance(value, dict):
        return [value.get("forge_100"), value.get("forge_1000"), value.get("forge_10000")]
    if isinstance(value, list):
        mapping = {"forge_100": 100, "forge_1000": 1000, "forge_10000": 10000}
        return [mapping.get(item) for item in value]
    return []


def validate(root: Path = ROOT) -> dict[str, Any]:
    manifest = _load(root / MANIFEST)
    duel = _load(root / DUEL)
    overengineering = _load(root / OVERENGINEERING)

    if manifest.get("schema_version") != "skeleton.ai_game_builder_500_levels.v1":
        raise GameBuilderAuthorityError("unsupported game-builder manifest schema")
    if manifest.get("status") != "active_design_authority":
        raise GameBuilderAuthorityError("game-builder authority must be active_design_authority")
    topology = manifest.get("topology")
    if not isinstance(topology, dict):
        raise GameBuilderAuthorityError("topology must be an object")
    expected = {"family_count": 50, "levels_per_family": 10, "total_levels": 500}
    for key, value in expected.items():
        if topology.get(key) != value:
            raise GameBuilderAuthorityError(f"topology.{key} must be {value}")
    if "overlay-only" not in _text(topology.get("scope"), "topology.scope"):
        raise GameBuilderAuthorityError("topology must preserve the masterplan breadth freeze")

    stages = _list(manifest.get("stages"), "stages", 10)
    if len(stages) != 10 or [row.get("stage") for row in stages] != list(range(1, 11)):
        raise GameBuilderAuthorityError("stages must be exactly contiguous 1..10")
    families = _list(manifest.get("families"), "families", 50)
    if len(families) != 50:
        raise GameBuilderAuthorityError("exactly 50 capability families are required")
    family_ids = [_text(row.get("id"), "family.id") for row in families]
    if family_ids != [f"GB{i:02d}" for i in range(1, 51)]:
        raise GameBuilderAuthorityError("family ids must be GB01..GB50 in order")

    if manifest.get("overengineering_authority") != str(OVERENGINEERING):
        raise GameBuilderAuthorityError("game-builder overengineering authority binding drifted")
    if manifest.get("overengineering_human_spec") != str(OVERENGINEERING_HUMAN):
        raise GameBuilderAuthorityError("game-builder overengineering human-spec binding drifted")
    runtime = manifest.get("runtime_contracts")
    expected_runtime = {
        "package": "skeleton/ai/game_builder",
        "contracts": str(RUNTIME_CONTRACTS),
        "dual_rival_state_machine": str(RUNTIME_FORGE),
        "evaluation_panel": str(EVALUATION_RUNTIME),
        "resource_governor": str(RESOURCE_RUNTIME),
        "quality_debt": str(QUALITY_DEBT_RUNTIME),
        "integrated_control_plane": str(CONTROL_PLANE_RUNTIME),
        "resilience": str(RESILIENCE_RUNTIME),
        "gold_master": str(GOLD_MASTER_RUNTIME),
        "frontier_assurance": str(FRONTIER_ASSURANCE_RUNTIME),
        "deep_assurance": str(DEEP_ASSURANCE_RUNTIME),
        "tests": [str(RUNTIME_TESTS), str(OVERENGINEERING_RUNTIME_TESTS), str(FRONTIER_RUNTIME_TESTS), str(DEEP_ASSURANCE_TESTS)],
    }
    if runtime != expected_runtime:
        raise GameBuilderAuthorityError("game-builder runtime contract binding drifted")
    for path in (
        RUNTIME_CONTRACTS,
        RUNTIME_FORGE,
        RUNTIME_TESTS,
        EVALUATION_RUNTIME,
        RESOURCE_RUNTIME,
        QUALITY_DEBT_RUNTIME,
        CONTROL_PLANE_RUNTIME,
        RESILIENCE_RUNTIME,
        GOLD_MASTER_RUNTIME,
        FRONTIER_ASSURANCE_RUNTIME,
        DEEP_ASSURANCE_RUNTIME,
        OVERENGINEERING_RUNTIME_TESTS,
        FRONTIER_RUNTIME_TESTS,
        DEEP_ASSURANCE_TESTS,
    ):
        if not (root / path).is_file():
            raise GameBuilderAuthorityError(f"missing game-builder runtime file: {path}")
    expected_governance = {
        "canon": str(GOVERNANCE_CANON),
        "rights": str(GOVERNANCE_RIGHTS),
        "atom_lineage": str(GOVERNANCE_ATOMS),
        "tests": str(GOVERNANCE_TESTS),
    }
    if manifest.get("governance_runtime") != expected_governance:
        raise GameBuilderAuthorityError("game-builder governance runtime binding drifted")
    for path in (GOVERNANCE_CANON, GOVERNANCE_RIGHTS, GOVERNANCE_ATOMS, GOVERNANCE_TESTS):
        if not (root / path).is_file():
            raise GameBuilderAuthorityError(f"missing game-builder governance runtime file: {path}")

    if overengineering.get("schema_version") != "skeleton.ai_game_builder_overengineering.v4":
        raise GameBuilderAuthorityError("unsupported game-builder overengineering schema")
    if overengineering.get("status") != "active_design_authority":
        raise GameBuilderAuthorityError("overengineering constitution must be active_design_authority")
    over_topology = overengineering.get("topology")
    if not isinstance(over_topology, dict):
        raise GameBuilderAuthorityError("overengineering topology must be an object")
    if over_topology.get("plane_count") != 80:
        raise GameBuilderAuthorityError("overengineering plane_count must equal 80")
    if over_topology.get("family_count") != 50:
        raise GameBuilderAuthorityError("overengineering family_count must equal 50")
    minimum_planes = over_topology.get("minimum_planes_per_family")
    if isinstance(minimum_planes, bool) or not isinstance(minimum_planes, int) or minimum_planes < 38:
        raise GameBuilderAuthorityError("minimum_planes_per_family must be at least 38")

    critical = _list(overengineering.get("critical_planes"), "critical_planes", 20)
    expected_critical = [
        "OP01", "OP02", "OP04", "OP05", "OP06", "OP11",
        "OP14", "OP15", "OP16", "OP22", "OP24",
        "OP25", "OP26", "OP27", "OP28", "OP29", "OP30",
        "OP43", "OP47", "OP48",
        "OP49", "OP50", "OP51", "OP54", "OP55", "OP60", "OP63", "OP64",
        "OP65", "OP66", "OP67", "OP69", "OP70", "OP75", "OP76", "OP78", "OP79", "OP80",
    ]
    if critical != expected_critical:
        raise GameBuilderAuthorityError("critical overengineering planes drifted")
    if over_topology.get("critical_plane_count") != len(critical):
        raise GameBuilderAuthorityError("critical_plane_count mismatch")

    foundations = overengineering.get("implemented_foundations")
    if not isinstance(foundations, dict):
        raise GameBuilderAuthorityError("overengineering implemented_foundations must be an object")
    for required_path in (
        str(RUNTIME_CONTRACTS),
        str(RUNTIME_FORGE),
        str(GOVERNANCE_CANON),
        str(GOVERNANCE_RIGHTS),
        str(GOVERNANCE_ATOMS),
        str(EVALUATION_RUNTIME),
        str(RESOURCE_RUNTIME),
        str(QUALITY_DEBT_RUNTIME),
        str(CONTROL_PLANE_RUNTIME),
        str(RESILIENCE_RUNTIME),
        str(GOLD_MASTER_RUNTIME),
        str(FRONTIER_ASSURANCE_RUNTIME),
        str(DEEP_ASSURANCE_RUNTIME),
        str(OVERENGINEERING_RUNTIME_TESTS),
        str(FRONTIER_RUNTIME_TESTS),
        str(DEEP_ASSURANCE_TESTS),
    ):
        if required_path not in json.dumps(foundations, sort_keys=True):
            raise GameBuilderAuthorityError(
                f"overengineering implemented foundation missing: {required_path}"
            )

    planes = _list(overengineering.get("planes"), "overengineering.planes", 80)
    if len(planes) != 80:
        raise GameBuilderAuthorityError("exactly 80 overengineering planes are required")
    plane_ids = [_text(row.get("id"), "plane.id") for row in planes]
    if plane_ids != [f"OP{i:02d}" for i in range(1, 81)]:
        raise GameBuilderAuthorityError("overengineering plane ids must be OP01..OP80")
    for plane in planes:
        plane_id = plane["id"]
        _text(plane.get("title"), f"{plane_id}.title")
        _text(plane.get("objective"), f"{plane_id}.objective")
        _list(plane.get("mandatory_controls"), f"{plane_id}.mandatory_controls", 4)
        _list(plane.get("evidence_required"), f"{plane_id}.evidence_required", 3)
        if plane.get("status") != "planned" or plane.get("signed") is not False:
            raise GameBuilderAuthorityError(f"{plane_id} may not self-claim completion")

    bindings = overengineering.get("family_bindings")
    if not isinstance(bindings, dict) or list(bindings) != family_ids:
        raise GameBuilderAuthorityError("overengineering family binding registry must be GB01..GB50")
    valid_plane_ids = set(plane_ids)
    critical_set = set(critical)
    for family_id in family_ids:
        bound = _list(bindings.get(family_id), f"{family_id}.overengineering_planes", minimum_planes)
        if len(bound) != len(set(bound)):
            raise GameBuilderAuthorityError(f"{family_id} overengineering planes must be unique")
        if not set(bound).issubset(valid_plane_ids):
            raise GameBuilderAuthorityError(f"{family_id} contains unknown overengineering plane")
        if not critical_set.issubset(set(bound)):
            raise GameBuilderAuthorityError(f"{family_id} is missing a critical overengineering plane")

    laws = "\n".join(str(x).lower() for x in _list(overengineering.get("laws"), "overengineering.laws", 10))
    for fragment in (
        "failed non-compensable gate",
        "private scratch state",
        "final authority",
        "long-form consistency",
        "unknown incorporated rights",
        "no-wall-clock-deadline",
        "last known-good champion",
        "causal obligations",
        "critical evidence becomes stale transitively",
        "correlated failure root",
        "stagnation or convergence never proves completion",
        "complexity is a cost",
        "external game knowledge",
        "critical cross-system interactions",
        "terminal completion requires a tamper-evident evidence root",
    ):
        if fragment not in laws:
            raise GameBuilderAuthorityError(f"overengineering law missing fragment: {fragment}")

    shards = _list(manifest.get("shards"), "shards", 1)
    if topology.get("shard_count") != len(shards):
        raise GameBuilderAuthorityError("topology.shard_count must equal manifest shard count")
    if len(shards) != len(set(shards)):
        raise GameBuilderAuthorityError("shard paths must be unique")

    levels: list[dict[str, Any]] = []
    for shard_path in shards:
        shard = _load(root / _text(shard_path, "shard path"))
        rows = _list(shard.get("levels"), f"{shard_path}.levels", 1)
        if shard.get("count") != len(rows):
            raise GameBuilderAuthorityError(f"{shard_path} count mismatch")
        if shard.get("start") != rows[0].get("ordinal") or shard.get("end") != rows[-1].get("ordinal"):
            raise GameBuilderAuthorityError(f"{shard_path} range mismatch")
        levels.extend(rows)

    if len(levels) != 500:
        raise GameBuilderAuthorityError(f"expected 500 levels, found {len(levels)}")

    seen: set[str] = set()
    for ordinal, row in enumerate(levels, 1):
        level_id = _text(row.get("id"), "level.id")
        if level_id != f"GBL-{ordinal:03d}" or row.get("ordinal") != ordinal:
            raise GameBuilderAuthorityError(f"level identity drift at ordinal {ordinal}")
        if level_id in seen:
            raise GameBuilderAuthorityError(f"duplicate level id: {level_id}")
        seen.add(level_id)

        expected_family = f"GB{((ordinal - 1) // 10) + 1:02d}"
        expected_stage = ((ordinal - 1) % 10) + 1
        if row.get("family_id") != expected_family or row.get("stage") != expected_stage:
            raise GameBuilderAuthorityError(f"{level_id} family/stage topology mismatch")

        _text(row.get("task_goal"), f"{level_id}.task_goal")
        _text(row.get("owner_binding", row.get("owner")), f"{level_id}.owner")
        _list(row.get("batches", row.get("game_creation_batches")), f"{level_id}.batches", 1)
        _list(row.get("metrics", row.get("required_metrics")), f"{level_id}.metrics", 4)
        _alias(row, "implementation_requirements", "requirements", f"{level_id}.requirements", 3)
        adversarial = _list(row.get("adversarial_focus", row.get("adversarial")), f"{level_id}.adversarial", 4)
        gates = _alias(row, "hard_gates", "gates", f"{level_id}.gates", 6)
        evidence = _alias(row, "evidence_required", "evidence", f"{level_id}.evidence", 7)
        if not all(isinstance(item, str) and item.strip() for item in adversarial + gates + evidence):
            raise GameBuilderAuthorityError(f"{level_id} contains empty evidence/gate/adversarial text")
        if _effort_rounds(row) != [100, 1000, 10000]:
            raise GameBuilderAuthorityError(f"{level_id} effort modes must be 100/1000/10000")
        cycle = row.get("cycle", row.get("three_stage_cycle"))
        if cycle != ["construct", "attack_and_improve", "reconcile_and_promote"]:
            raise GameBuilderAuthorityError(f"{level_id} must use exact three-stage rival cycle")
        gate_text = " ".join(str(x).lower() for x in gates)
        if "rights" not in gate_text and "provenance" not in gate_text:
            raise GameBuilderAuthorityError(f"{level_id} is missing a rights/provenance gate")
        if "bounded" not in gate_text and "unbounded" not in gate_text:
            raise GameBuilderAuthorityError(f"{level_id} is missing a bounded-resource gate")
        if row.get("status") != "planned" or row.get("signed") is not False:
            raise GameBuilderAuthorityError(f"{level_id} may not self-claim completion")
        if row.get("completion_evidence", []) != []:
            raise GameBuilderAuthorityError(f"{level_id} design authority must begin without completion evidence")

    if duel.get("schema_version") != "skeleton.ai_game_builder_dual_rival_forge.v1":
        raise GameBuilderAuthorityError("unsupported dual-rival authority schema")
    modes = duel.get("effort_modes")
    if not isinstance(modes, dict):
        raise GameBuilderAuthorityError("dual-rival effort_modes must be an object")
    for key, rounds in (("forge_100", 100), ("forge_1000", 1000), ("forge_10000", 10000)):
        mode = modes.get(key)
        if not isinstance(mode, dict) or mode.get("rounds") != rounds:
            raise GameBuilderAuthorityError(f"{key} must use exactly {rounds} rounds")
        if mode.get("stages_per_round") != 3 or mode.get("total_stage_executions") != rounds * 3:
            raise GameBuilderAuthorityError(f"{key} stage-count contract mismatch")
        if mode.get("wall_clock_deadline") is not None:
            raise GameBuilderAuthorityError(f"{key} must not have a wall-clock deadline")

    cycle = duel.get("three_stage_cycle")
    if not isinstance(cycle, list) or [row.get("key") for row in cycle] != [
        "construct", "attack_and_improve", "reconcile_and_promote"
    ]:
        raise GameBuilderAuthorityError("dual-rival authority must define the exact three-stage cycle")
    rights = duel.get("rights_and_originality")
    if not isinstance(rights, dict) or rights.get("default_for_unknown") != "unknown_quarantine":
        raise GameBuilderAuthorityError("unknown source rights must fail closed to quarantine")
    rights_text = json.dumps(rights, sort_keys=True).lower()
    for token in ("similarity", "human/legal", "legal determination", "project_owned"):
        if token not in rights_text:
            raise GameBuilderAuthorityError(f"rights authority missing requirement: {token}")
    if duel.get("governance_runtime") != expected_governance:
        raise GameBuilderAuthorityError("dual-rival governance runtime binding drifted")
    quality_vector = duel.get("quality_vector")
    if not isinstance(quality_vector, list):
        raise GameBuilderAuthorityError("dual-rival quality vector must be a list")
    for protected_axis in ("security/privacy", "state integrity", "reproducibility"):
        if protected_axis not in quality_vector:
            raise GameBuilderAuthorityError(
                f"dual-rival quality vector missing protected axis: {protected_axis}"
            )

    runtime_binding = duel.get("runtime_contracts")
    if runtime_binding != {
        "contracts": str(RUNTIME_CONTRACTS),
        "state_machine": str(RUNTIME_FORGE),
        "evaluation_panel": str(EVALUATION_RUNTIME),
        "resource_governor": str(RESOURCE_RUNTIME),
        "quality_debt": str(QUALITY_DEBT_RUNTIME),
        "integrated_control_plane": str(CONTROL_PLANE_RUNTIME),
        "resilience": str(RESILIENCE_RUNTIME),
        "gold_master": str(GOLD_MASTER_RUNTIME),
        "tests": [str(RUNTIME_TESTS), str(OVERENGINEERING_RUNTIME_TESTS)],
    }:
        raise GameBuilderAuthorityError("dual-rival runtime binding drifted")
    if duel.get("overengineering_authority") != str(OVERENGINEERING):
        raise GameBuilderAuthorityError("dual-rival overengineering binding drifted")

    consistency = duel.get("longform_consistency")
    if not isinstance(consistency, dict):
        raise GameBuilderAuthorityError("long-form consistency authority is missing")
    prime = _text(consistency.get("prime_directive"), "longform prime directive").lower()
    if "local improvement" not in prime or "long-form" not in prime:
        raise GameBuilderAuthorityError("long-form consistency prime directive is missing")

    over_human = (root / OVERENGINEERING_HUMAN).read_text(encoding="utf-8")
    for marker in ("48 mandatory cross-cutting planes", "Bounded-Resource Infinite-Time Discipline", "Pixel-to-Project Traceability", "Second-generation runtime controls"):
        if marker not in over_human:
            raise GameBuilderAuthorityError(f"overengineering human authority missing marker: {marker}")

    human = (root / HUMAN).read_text(encoding="utf-8")
    for marker in ("GBL-001..GBL-500", "Forge-10000", "long-form consistency", "Unknown is quarantined"):
        if marker not in human:
            raise GameBuilderAuthorityError(f"human authority missing marker: {marker}")
    master = (root / MASTER).read_text(encoding="utf-8")
    for marker in ("AI_GAME_BUILDER_500_LEVELS.md", "ai_game_builder_500_levels.json", "500-level"):
        if marker not in master:
            raise GameBuilderAuthorityError(f"master plan missing game-builder binding: {marker}")

    return {
        "status": "valid",
        "family_count": 50,
        "stage_count": 10,
        "level_count": 500,
        "shard_count": len(shards),
        "first_level": levels[0]["id"],
        "last_level": levels[-1]["id"],
        "signed_levels": sum(1 for row in levels if row.get("signed")),
        "effort_rounds": [100, 1000, 10000],
        "overengineering_plane_count": len(planes),
        "minimum_planes_per_family": minimum_planes,
        "runtime_kernel_bound": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT)
    except GameBuilderAuthorityError as exc:
        if args.json:
            print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}")
        return 1
    print(json.dumps(result, sort_keys=True) if args.json else f"valid: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
