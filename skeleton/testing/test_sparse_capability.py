"""Adversarial limits for wide capability coverage using tiny training subsets."""
from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from skeleton.ai.training.sparse_capability import (
    CAPABILITIES, DEFAULT_BUDGET, HARDWARE_BUDGETS,
    SyntheticCurriculumError, assess_heldout_capabilities,
    build_sparse_capability_plan, register_sparse_capability_plan,
    sparse_plan_receipt,
)
from skeleton.ai.runtime.training.data import DatasetRegistry


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "skeleton/ai/training/datasets/offline_foundations_v1"
)


def test_minimal_sparse_training_covers_all_36_modes_without_new_examples() -> None:
    plan = build_sparse_capability_plan(SOURCE)
    assert DEFAULT_BUDGET == 36
    assert sum(len(names) for names in CAPABILITIES.values()) == 36
    assert plan["active_training_rows"] == 36
    assert plan["source_training_pool"] == 504
    assert plan["heldout_source_rows"] == 216
    assert plan["heldout_rows_selected"] == 0
    assert plan["capability_modes_covered"] == plan["capability_modes_available"] == 36
    assert len(set(plan["capability_ids"])) == 36
    assert len(set(plan["selected_sample_ids"])) == 36
    assert len(set(plan["selected_scenario_groups"])) == 36
    assert plan["trained_weights_promoted"] is False
    assert plan["capability_proficiency_verified"] is False
    assert plan["hardware_acceleration_verified"] is False
    assert plan["selected_sample_ids"][:3] == [
        "ofv1-integer_arithmetic-00-0",
        "ofv1-integer_arithmetic-05-1",
        "ofv1-integer_arithmetic-10-2",
    ]
    assert all(item["source_split"] == "train" for item in plan["active_rows"])
    assert plan["training_text"].count(b"<user>\n") == 36
    assert plan["training_text"].count(b"<assistant>\n") == 36
    assert plan["training_text"].count(b"<end>\n") == 36
    report = sparse_plan_receipt(plan)
    assert "active_rows" not in report
    assert "training_text" not in report
    assert "active_jsonl" not in report


@pytest.mark.parametrize("budget", [36, 37, 48, 60, 72])
def test_budget_expansion_preserves_coverage_without_leaking_heldout(budget: int) -> None:
    plan = build_sparse_capability_plan(SOURCE, budget=budget)
    assert plan["active_training_rows"] == budget
    assert len(plan["active_rows"]) == budget
    assert plan["capability_modes_covered"] == 36
    assert len(set(plan["selected_scenario_groups"])) == budget
    assert set(plan["selected_sample_ids"]).isdisjoint({
        row["id"] for split in ("validation", "test")
        for row in (
            json.loads(line)
            for line in (SOURCE / (split + ".jsonl")).read_text("utf-8").splitlines()
        )
    })
    baseline = build_sparse_capability_plan(SOURCE, budget=36)
    assert plan["selected_sample_ids"][:36] == baseline["selected_sample_ids"]
    assert plan["heldout_rows_selected"] == 0
    assert all(
        sum(1 for row in plan["active_rows"] if row["capability_id"] == capability) <= 2
        for capability in plan["capability_ids"]
    )


@pytest.mark.parametrize("budget", [-1, 0, 12, 35, 73, 504, 720, True, "36"])
def test_unsafe_budget_cannot_force_more_training_material(budget) -> None:
    with pytest.raises(SyntheticCurriculumError, match="budget"):
        build_sparse_capability_plan(SOURCE, budget=budget)


def test_sparse_plan_is_byte_deterministic_across_repeated_requests() -> None:
    x = build_sparse_capability_plan(SOURCE, budget=48)
    y = build_sparse_capability_plan(SOURCE, budget=48)
    assert x == y
    assert x["training_text_sha256"] == y["training_text_sha256"]
    assert x["active_jsonl_sha256"] == y["active_jsonl_sha256"]


def test_sparse_registration_has_train_split_only_and_rights_no_promotion() -> None:
    plan = build_sparse_capability_plan(SOURCE)
    with DatasetRegistry(":memory:") as registry:
        identity = register_sparse_capability_plan(SOURCE, plan, registry)
        assert register_sparse_capability_plan(SOURCE, plan, registry) == identity
        ready = registry.require_training_ready(identity)
        assert ready.dataset_id == "skeleton-offline-foundations-sparse"
        assert len(ready.splits) == 1
        assert ready.splits[0].name == "train"
        assert ready.splits[0].record_count == 36
        assert ready.permitted_uses == ("training",)
        assert ready.synthetic_receipt is not None
        assert ready.synthetic_receipt.generated_record_count == 36
        assert ready.contamination_labels == ()
        assert registry.latest_quality(identity).passed is True


def test_forged_sparse_answer_cannot_register_even_with_new_self_hash() -> None:
    import hashlib

    plan = build_sparse_capability_plan(SOURCE)
    bad = dict(plan)
    altered = plan["training_text"].replace(b"<assistant>\n14\n", b"<assistant>\n999\n", 1)
    assert altered != plan["training_text"]
    bad["training_text"] = altered
    bad["training_text_sha256"] = hashlib.sha256(altered).hexdigest()
    with DatasetRegistry(":memory:") as registry:
        with pytest.raises(SyntheticCurriculumError, match="differs"):
            register_sparse_capability_plan(SOURCE, bad, registry)
        assert not registry._db.execute("SELECT 1 FROM dataset_manifest").fetchone()


def test_swapped_heldout_training_identity_cannot_register() -> None:
    plan = build_sparse_capability_plan(SOURCE)
    bad = dict(plan)
    bad["selected_sample_ids"] = ["ofv1-integer_arithmetic-14-0"] + (
        plan["selected_sample_ids"][1:]
    )
    with DatasetRegistry(":memory:") as registry:
        with pytest.raises(SyntheticCurriculumError, match="differs"):
            register_sparse_capability_plan(SOURCE, bad, registry)


def test_plan_fails_if_original_dataset_changes(tmp_path: Path) -> None:
    copied = tmp_path / "source"
    shutil.copytree(SOURCE, copied)
    (copied / "train.jsonl").write_text("modified", encoding="utf-8")
    with pytest.raises(SyntheticCurriculumError):
        build_sparse_capability_plan(copied)


def _write_predictions(path: Path, split: str, *, inject_error: bool = False) -> None:
    rows = [
        json.loads(line)
        for line in (SOURCE / (split + ".jsonl")).read_text("utf-8").splitlines()
    ]
    if inject_error:
        rows[0]["response"] = "WRONG"
    path.write_text(
        "".join(json.dumps({"id": item["id"], "prediction": item["response"]}) + "\n"
                for item in rows),
        encoding="utf-8",
    )


def test_all_36_modes_have_independent_heldout_scorecard(tmp_path: Path) -> None:
    predictions = tmp_path / "pred.jsonl"
    _write_predictions(predictions, "validation")
    result = assess_heldout_capabilities(SOURCE, predictions)
    assert result["available_modes"] == 36
    assert result["evaluated_modes"] == 36
    assert result["modes_perfect_on_heldout"] == 36
    assert result["modes_with_observed_errors"] == []
    assert result["heldout_correct"] == result["heldout_total"] == 108
    assert all(x == {"correct": 3, "total": 3}
               for x in result["per_mode"].values())
    assert result["promotion_authorized"] is False
    assert result["real_world_generalization_proven"] is False
    _write_predictions(predictions, "validation", inject_error=True)
    result = assess_heldout_capabilities(SOURCE, predictions)
    assert result["heldout_correct"] == 107
    assert result["modes_perfect_on_heldout"] == 35
    assert len(result["modes_with_observed_errors"]) == 1
    assert result["heldout_total"] == 108


def test_scorecard_rejects_training_split_and_missing_predictions(tmp_path: Path) -> None:
    predictions = tmp_path / "pred.jsonl"
    _write_predictions(predictions, "validation")
    with pytest.raises(SyntheticCurriculumError, match="held-out"):
        assess_heldout_capabilities(SOURCE, predictions, split="train")
    predictions.write_text("{}", encoding="utf-8")
    with pytest.raises(SyntheticCurriculumError):
        assess_heldout_capabilities(SOURCE, predictions)


def test_consumer_cli_enforces_profile_and_no_clobber(tmp_path: Path, capsys) -> None:
    from scripts.training.sparse_capability import main

    assert HARDWARE_BUDGETS == {
        "low-memory": 36, "consumer": 48, "workstation": 72,
    }
    assert main(["--dataset", str(SOURCE)]) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["active_training_rows"] == 36
    assert baseline["hardware_profile"] == "low-memory"
    assert baseline["hardware_benchmark_run"] is False
    assert "training_text" not in baseline
    assert main([
        "--dataset", str(SOURCE), "--profile", "consumer", "--budget", "72",
    ]) == 2
    capsys.readouterr()
    file = tmp_path / "sparse.txt"
    assert main([
        "--dataset", str(SOURCE), "--export", str(file),
    ]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["training_text_sha256"] == baseline["training_text_sha256"]
    assert file.read_bytes() == build_sparse_capability_plan(SOURCE)["training_text"]
    assert main([
        "--dataset", str(SOURCE), "--export", str(file),
    ]) == 1
    assert file.read_bytes() == build_sparse_capability_plan(SOURCE)["training_text"]
    capsys.readouterr()
    assert main([
        "--dataset", str(SOURCE), "--register-db", str(tmp_path / "sparse.sqlite"),
    ]) == 0
    governed = json.loads(capsys.readouterr().out)
    assert governed["governed_training_ready"] is True
    assert len(governed["registered_sparse_dataset_digest"]) == 64


def test_cli_refuses_writing_into_verified_dataset(tmp_path: Path, capsys) -> None:
    from scripts.training.sparse_capability import main

    local = tmp_path / "copied"
    shutil.copytree(SOURCE, local)
    assert main([
        "--dataset", str(local), "--export", str(local / "bad.txt"),
    ]) == 1
    assert not (local / "bad.txt").exists()
    assert main([
        "--dataset", str(local), "--register-db", str(local / "bad.sqlite"),
    ]) == 1
    assert not (local / "bad.sqlite").exists()
