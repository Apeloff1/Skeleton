"""Source-bound cohort delta exercises real game exports and replay."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from skeleton.ai.game_builder.dual_runtime_export import (
    export_dual_runtime_package, render_dual_runtime_package,
)
from skeleton.ai.game_builder.offline_export_batch import (
    OfflineBatchVerificationError, SCHEMA,
)
from skeleton.ai.game_builder.offline_export_batch_delta import compare_export_batches
from skeleton.ai.game_builder.original_game_studio_cli import main as studio_cli
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent


def _export(root: Path, project_id: str, directory: str, seed: int):
    intent = GameBuildIntent(
        project_id=project_id, title="Original Delta Harbor",
        subtitle="Original replay-verifiable route", seed=seed,
        levels=1, width=9, height=9, collectibles_per_level=1,
        hazards_per_level=0, starting_health=3,
    )
    project = compile_original_game(intent, authorized=True)
    package = render_dual_runtime_package(project, authorized=True)
    exported = export_dual_runtime_package(
        package, root / directory, authorized=True,
    )
    return {
        "project_id": project_id,
        "package_dir": directory,
        "release_sha256": sha256((exported / "release.json").read_bytes()).hexdigest(),
    }


def _index(root: Path, entries: list[dict[str, str]]) -> str:
    data = (json.dumps({"schema": SCHEMA, "packages": entries},
                       sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "batch.json").write_bytes(data)
    return sha256(data).hexdigest()


@pytest.fixture
def cohorts(tmp_path):
    left = tmp_path / "old"
    right = tmp_path / "new"
    left.mkdir()
    right.mkdir()
    old_a = _export(left, "delta-a", "a", 100)
    old_b = _export(left, "delta-b", "b", 101)
    shutil.copytree(left / "a", right / "a-renamed")
    new_a = {**old_a, "package_dir": "a-renamed"}
    new_b = _export(right, "delta-b", "b", 202)
    left_pin = _index(left, [old_a, old_b])
    right_pin = _index(right, [new_a, new_b])
    return left, left_pin, right, right_pin


def test_real_verified_source_change_and_relocation(cohorts):
    left, left_pin, right, right_pin = cohorts
    result = compare_export_batches(
        left, right, left_index_sha256=left_pin,
        right_index_sha256=right_pin, authorized=True,
    )
    assert result["classification_counts"]["relocated"] == 1
    assert result["classification_counts"]["source_changed"] == 1
    assert result["both_cohorts_replayed"] is True
    assert result["migration_applied"] is False
    assert result["release_certified"] is False
    assert len(result["receipt_digest"]) == 64
    assert compare_export_batches(
        left, right, left_index_sha256=left_pin,
        right_index_sha256=right_pin, authorized=True,
    ) == result


def test_cli_routes_to_verified_delta(cohorts, capsys):
    left, left_pin, right, right_pin = cohorts
    assert studio_cli([
        "diff-batch", "--left-root", str(left),
        "--left-index-sha256", left_pin,
        "--right-root", str(right),
        "--right-index-sha256", right_pin,
        "--trusted-local-operator",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["classification_counts"]["source_changed"] == 1


@pytest.mark.parametrize("attack", ["left-pin", "right-pin", "left-source", "right-source"])
def test_either_untrusted_cohort_rejects_entire_delta(cohorts, attack):
    left, left_pin, right, right_pin = cohorts
    if attack == "left-pin":
        left_pin = "0" * 64
    elif attack == "right-pin":
        right_pin = "0" * 64
    elif attack == "left-source":
        (left / "a" / "index.html").write_text("tampered")
    else:
        (right / "b" / "index.html").write_text("tampered")
    with pytest.raises(OfflineBatchVerificationError):
        compare_export_batches(
            left, right, left_index_sha256=left_pin,
            right_index_sha256=right_pin, authorized=True,
        )


def test_delta_requires_operator_authorization(cohorts):
    left, left_pin, right, right_pin = cohorts
    with pytest.raises(PermissionError):
        compare_export_batches(
            left, right, left_index_sha256=left_pin,
            right_index_sha256=right_pin, authorized=False,
        )


def test_added_and_removed_projects_are_source_bound(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    old = _export(left, "removed-project", "old", 50)
    new = _export(right, "added-project", "new", 60)
    left_pin = _index(left, [old])
    right_pin = _index(right, [new])
    result = compare_export_batches(
        left, right, left_index_sha256=left_pin,
        right_index_sha256=right_pin, authorized=True,
    )
    assert result["classification_counts"]["added"] == 1
    assert result["classification_counts"]["removed"] == 1
