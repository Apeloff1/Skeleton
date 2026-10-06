#!/usr/bin/env python3
"""Validate the 200-level competitive AI engineering ladder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path("machine/competitive_ai_engineering_ladder.json")
MASTER = Path("docs/plan/MASTER_PLAN.md")
HUMAN = Path("docs/architecture/COMPETITIVE_AI_ENGINEERING_LADDER.md")

class CompetitiveEngineeringError(RuntimeError):
    pass

def _reject_constant(token: str) -> None:
    raise CompetitiveEngineeringError(f"non-finite JSON token rejected: {token}")

def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CompetitiveEngineeringError(f"duplicate JSON object key: {key}")
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
        raise CompetitiveEngineeringError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompetitiveEngineeringError(f"{path} must contain an object")
    return value

def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise CompetitiveEngineeringError(f"{label} must be canonical non-empty text")
    return value

def _texts(value: Any, label: str, minimum: int) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise CompetitiveEngineeringError(f"{label} requires at least {minimum} entries")
    rows = [_text(x, f"{label}[]") for x in value]
    if len(rows) != len(set(rows)):
        raise CompetitiveEngineeringError(f"{label} must be unique")
    return rows

def validate(root: Path = ROOT) -> dict[str, Any]:
    policy = _load(root / POLICY)
    if policy.get("schema_version") != "skeleton.competitive_ai_engineering_ladder.v1":
        raise CompetitiveEngineeringError("unsupported engineering-ladder schema")
    if policy.get("status") != "active_design_authority":
        raise CompetitiveEngineeringError("engineering ladder must be active_design_authority")

    topology = policy.get("topology")
    if not isinstance(topology, dict):
        raise CompetitiveEngineeringError("topology must be an object")
    expected = {"family_count": 20, "levels_per_family": 10, "total_levels": 200}
    for key, value in expected.items():
        if topology.get(key) != value:
            raise CompetitiveEngineeringError(f"topology.{key} must be {value}")
    if "does not create top-level volumes beyond VOL-420" not in _text(
        topology.get("scope_rule"), "topology.scope_rule"
    ):
        raise CompetitiveEngineeringError("scope freeze binding is missing")
    _text(topology.get("completion_rule"), "topology.completion_rule")
    _text(topology.get("superiority_rule"), "topology.superiority_rule")

    laws = "\n".join(_texts(policy.get("non_negotiable_laws"), "non_negotiable_laws", 8)).lower()
    for fragment in (
        "marketing language is never implementation evidence",
        "non-compensable",
        "tested reference or rollback path",
        "tail saturation recovery and adversarial behavior",
        "superiority claims expire",
    ):
        if fragment not in laws:
            raise CompetitiveEngineeringError(f"missing law fragment: {fragment}")

    stages = policy.get("stages")
    families = policy.get("families")
    levels = policy.get("levels")
    if not isinstance(stages, list) or len(stages) != 10:
        raise CompetitiveEngineeringError("exactly 10 stages are required")
    if [row.get("n") for row in stages] != list(range(1, 11)):
        raise CompetitiveEngineeringError("stage numbers must be contiguous 1..10")
    if not isinstance(families, list) or len(families) != 20:
        raise CompetitiveEngineeringError("exactly 20 families are required")
    if not isinstance(levels, list) or len(levels) != 200:
        raise CompetitiveEngineeringError("exactly 200 levels are required")

    family_ids = [_text(row.get("id"), "family.id") for row in families]
    if family_ids != [f"F{i:02d}" for i in range(1, 21)]:
        raise CompetitiveEngineeringError("family ids must be F01..F20 in order")
    for family in families:
        _text(family.get("competitor_claim"), f"{family['id']}.competitor_claim")
        _text(family.get("objective"), f"{family['id']}.objective")
        _text(family.get("baseline"), f"{family['id']}.baseline")
        _texts(family.get("required_metrics"), f"{family['id']}.required_metrics", 4)
        _texts(family.get("implementation_paths"), f"{family['id']}.implementation_paths", 3)
        _texts(family.get("adversarial_campaign"), f"{family['id']}.adversarial_campaign", 4)
        refs = _texts(family.get("masterplan_volume_refs"), f"{family['id']}.masterplan_volume_refs", 2)
        if not all(ref.startswith("VOL-") and len(ref) == 7 for ref in refs):
            raise CompetitiveEngineeringError(f"{family['id']} has invalid masterplan volume refs")

    ids: list[str] = []
    by_family: dict[str, list[int]] = {fid: [] for fid in family_ids}
    for index, row in enumerate(levels, 1):
        level_id = _text(row.get("id"), "level.id")
        if level_id != f"ENG-{index:03d}":
            raise CompetitiveEngineeringError(f"level identity drift at ordinal {index}")
        if row.get("ordinal") != index:
            raise CompetitiveEngineeringError(f"{level_id} ordinal mismatch")
        family_id = _text(row.get("family_id"), f"{level_id}.family_id")
        if family_id not in by_family:
            raise CompetitiveEngineeringError(f"{level_id} unknown family {family_id}")
        stage = row.get("stage")
        if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= 10:
            raise CompetitiveEngineeringError(f"{level_id} invalid stage")
        expected_family = f"F{((index - 1) // 10) + 1:02d}"
        expected_stage = ((index - 1) % 10) + 1
        if family_id != expected_family or stage != expected_stage:
            raise CompetitiveEngineeringError(f"{level_id} family/stage topology mismatch")
        by_family[family_id].append(stage)

        _text(row.get("competitor_claim"), f"{level_id}.competitor_claim")
        _text(row.get("engineering_outcome"), f"{level_id}.engineering_outcome")
        _text(row.get("baseline"), f"{level_id}.baseline")
        _texts(row.get("masterplan_volume_refs"), f"{level_id}.masterplan_volume_refs", 2)
        _texts(row.get("implementation_paths"), f"{level_id}.implementation_paths", 3)
        _texts(row.get("required_metrics"), f"{level_id}.required_metrics", 4)
        _texts(row.get("implementation_requirements"), f"{level_id}.implementation_requirements", 4)
        gates = "\n".join(_texts(row.get("hard_gates"), f"{level_id}.hard_gates", 6)).lower()
        for fragment in ("security/privacy/tenant", "authority", "state loss", "unbounded"):
            if fragment not in gates:
                raise CompetitiveEngineeringError(f"{level_id} missing hard gate: {fragment}")
        _texts(row.get("adversarial_campaign"), f"{level_id}.adversarial_campaign", 4)
        _texts(row.get("evidence_required"), f"{level_id}.evidence_required", 7)
        exits = "\n".join(_texts(row.get("exit_criteria"), f"{level_id}.exit_criteria", 4)).lower()
        if "prose-only" not in exits and stage != 10:
            raise CompetitiveEngineeringError(f"{level_id} must reject prose-only completion")
        if stage == 10 and "independent superiority authority" not in exits:
            raise CompetitiveEngineeringError(f"{level_id} final stage needs independent promotion")
        if row.get("status") != "planned" or row.get("signed") is not False:
            raise CompetitiveEngineeringError(f"{level_id} may not self-claim completion")
        if row.get("completion_evidence") != []:
            raise CompetitiveEngineeringError(f"{level_id} design authority must start without completion evidence")
        ids.append(level_id)

    if len(ids) != len(set(ids)):
        raise CompetitiveEngineeringError("level ids must be unique")
    if any(stages_seen != list(range(1, 11)) for stages_seen in by_family.values()):
        raise CompetitiveEngineeringError("every family must contain stages 1..10 exactly once")

    master = (root / MASTER).read_text(encoding="utf-8")
    human = (root / HUMAN).read_text(encoding="utf-8")
    for required in (
        "competitive_ai_engineering_ladder.json",
        "COMPETITIVE_AI_ENGINEERING_LADDER.md",
        "200-level",
    ):
        if required not in master:
            raise CompetitiveEngineeringError(f"master plan missing ladder binding: {required}")
    for required in ("ENG-001", "ENG-200", "20 competitive claim families"):
        if required not in human:
            raise CompetitiveEngineeringError(f"human ladder missing marker: {required}")

    return {
        "status": "valid",
        "family_count": len(families),
        "stage_count": len(stages),
        "level_count": len(levels),
        "first_level": levels[0]["id"],
        "last_level": levels[-1]["id"],
        "signed_levels": sum(1 for row in levels if row["signed"]),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(ROOT)
    except CompetitiveEngineeringError as exc:
        if args.json:
            print(json.dumps({"status": "invalid", "error": str(exc)}, sort_keys=True))
        else:
            print(f"invalid: {exc}")
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"valid: {result}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
