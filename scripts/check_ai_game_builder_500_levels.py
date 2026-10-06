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
MASTER = Path("docs/plan/MASTER_PLAN.md")
HUMAN = Path("docs/architecture/AI_GAME_BUILDER_500_LEVELS.md")


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
    consistency = duel.get("longform_consistency")
    if not isinstance(consistency, dict) or "prime" not in _text(consistency.get("prime_directive"), "longform prime directive").lower():
        raise GameBuilderAuthorityError("long-form consistency prime directive is missing")

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
