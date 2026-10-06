from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_ai_game_builder_500_levels",
    ROOT / "scripts" / "check_ai_game_builder_500_levels.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    manifest = json.loads((ROOT / "machine/ai_game_builder_500_levels.json").read_text(encoding="utf-8"))
    paths = [
        "machine/ai_game_builder_500_levels.json",
        "machine/ai_game_builder_dual_rival_forge.json",
        "docs/architecture/AI_GAME_BUILDER_500_LEVELS.md",
        "docs/plan/MASTER_PLAN.md",
        *manifest["shards"],
    ]
    for relative in paths:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _json(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write(root: Path, relative: str, payload: dict) -> None:
    (root / relative).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_current_500_level_authority_is_valid() -> None:
    assert MODULE.validate(ROOT) == {
        "status": "valid",
        "family_count": 50,
        "stage_count": 10,
        "level_count": 500,
        "shard_count": 19,
        "first_level": "GBL-001",
        "last_level": "GBL-500",
        "signed_levels": 0,
        "effort_rounds": [100, 1000, 10000],
    }


def test_exact_topology_is_fifty_by_ten() -> None:
    manifest = _json(ROOT, "machine/ai_game_builder_500_levels.json")
    rows = []
    for shard in manifest["shards"]:
        rows.extend(_json(ROOT, shard)["levels"])
    assert [row["id"] for row in rows] == [f"GBL-{i:03d}" for i in range(1, 501)]
    for family_index in range(50):
        group = rows[family_index * 10:(family_index + 1) * 10]
        assert {row["family_id"] for row in group} == {f"GB{family_index + 1:02d}"}
        assert [row["stage"] for row in group] == list(range(1, 11))


def test_every_level_is_unsigned_and_uses_all_effort_modes() -> None:
    manifest = _json(ROOT, "machine/ai_game_builder_500_levels.json")
    rows = []
    for shard in manifest["shards"]:
        rows.extend(_json(ROOT, shard)["levels"])
    for row in rows:
        assert row["status"] == "planned"
        assert row["signed"] is False
        assert MODULE._effort_rounds(row) == [100, 1000, 10000]
        assert row.get("cycle", row.get("three_stage_cycle")) == [
            "construct", "attack_and_improve", "reconcile_and_promote"
        ]


def test_dual_rival_modes_have_no_wall_clock_deadline() -> None:
    duel = _json(ROOT, "machine/ai_game_builder_dual_rival_forge.json")
    for key, rounds in (("forge_100", 100), ("forge_1000", 1000), ("forge_10000", 10000)):
        mode = duel["effort_modes"][key]
        assert mode["rounds"] == rounds
        assert mode["stages_per_round"] == 3
        assert mode["total_stage_executions"] == rounds * 3
        assert mode["wall_clock_deadline"] is None


def test_unknown_rights_fail_closed_to_quarantine() -> None:
    duel = _json(ROOT, "machine/ai_game_builder_dual_rival_forge.json")
    assert duel["rights_and_originality"]["default_for_unknown"] == "unknown_quarantine"
    assert "forbidden" in duel["rights_and_originality"]["rights_states"]


def test_rejects_missing_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    manifest = _json(root, "machine/ai_game_builder_500_levels.json")
    last = manifest["shards"][-1]
    shard = _json(root, last)
    shard["levels"].pop()
    shard["count"] -= 1
    shard["end"] -= 1
    _write(root, last, shard)
    with pytest.raises(MODULE.GameBuilderAuthorityError, match="expected 500 levels"):
        MODULE.validate(root)


def test_rejects_self_signed_level(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    manifest = _json(root, "machine/ai_game_builder_500_levels.json")
    first = manifest["shards"][0]
    shard = _json(root, first)
    shard["levels"][0]["status"] = "complete"
    shard["levels"][0]["signed"] = True
    _write(root, first, shard)
    with pytest.raises(MODULE.GameBuilderAuthorityError, match="may not self-claim completion"):
        MODULE.validate(root)


def test_rejects_effort_mode_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    duel = _json(root, "machine/ai_game_builder_dual_rival_forge.json")
    duel["effort_modes"]["forge_10000"]["rounds"] = 9999
    _write(root, "machine/ai_game_builder_dual_rival_forge.json", duel)
    with pytest.raises(MODULE.GameBuilderAuthorityError, match="exactly 10000 rounds"):
        MODULE.validate(root)


def test_rejects_wall_clock_deadline(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    duel = _json(root, "machine/ai_game_builder_dual_rival_forge.json")
    duel["effort_modes"]["forge_1000"]["wall_clock_deadline"] = "24h"
    _write(root, "machine/ai_game_builder_dual_rival_forge.json", duel)
    with pytest.raises(MODULE.GameBuilderAuthorityError, match="must not have a wall-clock deadline"):
        MODULE.validate(root)


def test_rejects_unknown_rights_becoming_permissive(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    duel = _json(root, "machine/ai_game_builder_dual_rival_forge.json")
    duel["rights_and_originality"]["default_for_unknown"] = "facts_and_ideas_reference_only"
    _write(root, "machine/ai_game_builder_dual_rival_forge.json", duel)
    with pytest.raises(MODULE.GameBuilderAuthorityError, match="fail closed to quarantine"):
        MODULE.validate(root)
