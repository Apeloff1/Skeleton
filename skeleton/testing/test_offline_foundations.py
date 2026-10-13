"""Executable adversarial tests for the original synthetic offline training set."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from skeleton.ai.training.offline_foundations import (
    DATASET_ID,
    FAMILIES,
    SyntheticCurriculumError,
    evaluate_predictions,
    register_with_training_registry,
    validate_curriculum,
)


SOURCE = Path(__file__).resolve().parents[2] / (
    "skeleton/ai/training/datasets/offline_foundations_v1"
)


def _copy(tmp_path: Path) -> Path:
    location = tmp_path / "curriculum"
    shutil.copytree(SOURCE, location)
    return location


def _rows(directory: Path, split: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (directory / (split + ".jsonl")).read_text("utf-8").splitlines()
    ]


def _change_rows(directory: Path, split: str, rows: list[dict]) -> None:
    raw = ("".join(json.dumps(x, separators=(",", ":"), ensure_ascii=False) + "\n"
                   for x in rows)).encode("utf-8")
    (directory / (split + ".jsonl")).write_bytes(raw)
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    manifest["files"][split]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["files"][split]["byte_count"] = len(raw)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _change_corpus(directory: Path, rows: list[dict]) -> None:
    raw = "".join(
        "<user>\n" + x["instruction"] + "\n<assistant>\n"
        + x["response"] + "\n<end>\n" for x in rows
    ).encode("utf-8")
    (directory / "train_corpus.txt").write_bytes(raw)
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    manifest["files"]["train_corpus"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["files"]["train_corpus"]["byte_count"] = len(raw)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def test_full_dataset_admission_verifies_720_independent_oracles() -> None:
    report = validate_curriculum(SOURCE)
    assert report["dataset_id"] == DATASET_ID
    assert report["split_counts"] == {
        "train": 504, "validation": 108, "test": 108,
    }
    assert report["oracle_verified_rows"] == 720
    assert report["groups"] == 240
    assert report["scenario_leakage"] == 0
    assert report["exact_duplicate_prompts"] == 0
    assert report["synthetic_only"] is True
    assert report["rights_independently_verified"] is False
    assert report["template_generalization_established"] is False
    assert report["weights_promoted"] is False
    assert len(FAMILIES) == 12


def test_train_text_contains_exact_train_records_and_no_heldout_prompts() -> None:
    training = (SOURCE / "train_corpus.txt").read_text("utf-8")
    train = _rows(SOURCE, "train")
    assert training.count("<user>\n") == 504
    assert training.count("<assistant>\n") == 504
    assert training.count("<end>\n") == 504
    for item in train:
        assert item["instruction"] in training
        assert item["response"] in training
    for split in ("validation", "test"):
        for item in _rows(SOURCE, split):
            assert item["instruction"] not in training


def test_game_and_normalization_oracles_cover_boundary_cases() -> None:
    rows = _rows(SOURCE, "train")
    by_family = {f: [x for x in rows if x["family"] == f] for f in FAMILIES}
    assert all(len(items) == 42 for items in by_family.values())
    assert any(x["response"] == "no-overlap"
               for x in by_family["aabb_collision"])
    assert any(x["response"] == "DENY"
               for x in by_family["offline_authority"])
    for case in by_family["text_normalization"]:
        assert "preserve underscores" in case["instruction"]
        assert "_" in case["response"]


def test_forged_answer_is_rejected_even_when_file_and_corpus_hashes_are_updated(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    data = _rows(root, "train")
    assert data[0]["response"] == "14"
    data[0]["response"] = "15"  # Incorrect but all SHA-256 manifests updated.
    _change_rows(root, "train", data)
    _change_corpus(root, data)
    with pytest.raises(SyntheticCurriculumError, match="independent oracle"):
        validate_curriculum(root)


def test_validation_scenario_leak_rejected_after_resigning_file_hash(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    rows = _rows(root, "validation")
    rows[0]["group_id"] = "integer_arithmetic-scenario-00"
    _change_rows(root, "validation", rows)
    with pytest.raises(SyntheticCurriculumError, match="shape|split|scenario"):
        validate_curriculum(root)


def test_evaluation_answers_can_never_be_submitted_as_training_split() -> None:
    for split, permitted in (("train", 14), ("validation", 3), ("test", 3)):
        rows = _rows(SOURCE, split)
        assert len(rows) == len(FAMILIES) * permitted * 3
        assert all(x["split"] == split for x in rows)


def test_corrupt_file_rejected_before_oracle_parsing(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    with (root / "validation.jsonl").open("ab") as stream:
        stream.write(b"extra-unlisted-record")
    with pytest.raises(SyntheticCurriculumError, match="checksum"):
        validate_curriculum(root)


def test_unlisted_and_symlinked_dataset_file_rejected(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    (root / "unsourced-private.bin").write_bytes(b"PRIVATE")
    with pytest.raises(SyntheticCurriculumError, match="unexpected"):
        validate_curriculum(root)
    (root / "unsourced-private.bin").unlink()
    victim = tmp_path / "external.jsonl"
    victim.write_bytes((root / "test.jsonl").read_bytes())
    (root / "test.jsonl").unlink()
    try:
        (root / "test.jsonl").symlink_to(victim)
    except OSError:
        pytest.skip("host does not permit symlinks")
    with pytest.raises(SyntheticCurriculumError, match="regular"):
        validate_curriculum(root)


def test_registry_admission_is_idempotent_and_never_promotes_weights() -> None:
    from skeleton.ai.runtime.training.data import DatasetRegistry
    from skeleton.ai.runtime.training.trainer import corpus_digest

    registry = DatasetRegistry(":memory:")
    try:
        identity = register_with_training_registry(SOURCE, registry)
        assert register_with_training_registry(SOURCE, registry) == identity
        ready = registry.require_training_ready(identity)
        assert ready.dataset_id == DATASET_ID
        assert ready.synthetic_receipt is not None
        assert ready.synthetic_receipt.generated_record_count == 720
        assert ready.permitted_uses == ("training", "evaluation")
        train = next(split for split in ready.splits if split.name == "train")
        text = (SOURCE / "train_corpus.txt").read_text("utf-8")
        assert train.digest == corpus_digest((text,))
        assert ready.contamination_labels == ()
        report = registry.latest_quality(identity)
        assert report is not None and report.passed is True
        assert report.critical_failures == ()
    finally:
        registry.close()


def test_heldout_evaluation_counts_oracle_accuracy_without_printing_answers(
    tmp_path: Path,
) -> None:
    predictions = tmp_path / "heldout-predictions.jsonl"
    rows = _rows(SOURCE, "validation")
    predictions.write_text(
        "".join(json.dumps({"id": x["id"], "prediction": x["response"]})
                + "\n" for x in rows), encoding="utf-8",
    )
    report = evaluate_predictions(SOURCE, predictions, split="validation")
    assert report["correct"] == 108
    assert report["total"] == 108
    assert len(report["by_family"]) == 12
    assert all(v["correct"] == v["total"] == 9
               for v in report["by_family"].values())
    assert report["trained_weights_promoted"] is False
    rows[0]["response"] = "intentionally-wrong"
    predictions.write_text(
        "".join(json.dumps({"id": x["id"], "prediction": x["response"]})
                + "\n" for x in rows), encoding="utf-8",
    )
    lower = evaluate_predictions(SOURCE, predictions, split="validation")
    assert lower["correct"] == 107
    assert lower["total"] == 108
    with pytest.raises(SyntheticCurriculumError, match="held-out"):
        evaluate_predictions(SOURCE, predictions, split="train")


def test_heldout_evaluator_rejects_unknown_and_duplicate_prediction_ids(
    tmp_path: Path,
) -> None:
    rows = _rows(SOURCE, "test")
    answers = [{"id": x["id"], "prediction": x["response"]} for x in rows]
    file = tmp_path / "predictions.jsonl"
    answers[0]["id"] = "ofv1-unknown-train-00-0"
    file.write_text("".join(json.dumps(x) + "\n" for x in answers), "utf-8")
    with pytest.raises(SyntheticCurriculumError, match="identity"):
        evaluate_predictions(SOURCE, file, split="test")
    answers[0]["id"] = answers[1]["id"]
    file.write_text("".join(json.dumps(x) + "\n" for x in answers), "utf-8")
    with pytest.raises(SyntheticCurriculumError, match="identity"):
        evaluate_predictions(SOURCE, file, split="test")


def test_cross_group_alias_mutation_cannot_pretend_to_be_same_scenario(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    rows = _rows(root, "test")
    rows[0]["id"] = "ofv1-integer_arithmetic-14-0"
    _change_rows(root, "test", rows)
    with pytest.raises(SyntheticCurriculumError, match="missing|duplicated"):
        validate_curriculum(root)


def test_independent_generator_rebuilds_every_committed_byte() -> None:
    from scripts.training.generate_offline_foundations import (
        expected_files, verify_regeneration,
    )
    report = verify_regeneration(SOURCE)
    assert report["regeneration_verified"] is True
    files = expected_files()
    assert set(files) == {
        "train.jsonl", "validation.jsonl", "test.jsonl", "train_corpus.txt",
    }
    for name, content in files.items():
        assert content == (SOURCE / name).read_bytes()


def test_generator_can_materialize_a_new_pinned_dataset(tmp_path: Path) -> None:
    from scripts.training.generate_offline_foundations import main

    destination = tmp_path / "regenerated"
    assert main(["--dataset", str(SOURCE), "--output", str(destination)]) == 0
    assert validate_curriculum(destination)["oracle_verified_rows"] == 720
    assert (destination / "train_corpus.txt").read_bytes() == (
        SOURCE / "train_corpus.txt"
    ).read_bytes()
    # Exclusive output path requirement; no replacement.
    assert main(["--dataset", str(SOURCE), "--output", str(destination)]) == 1


def test_generator_detects_template_drift_despite_recomputed_hashes(
    tmp_path: Path,
) -> None:
    from scripts.training.generate_offline_foundations import verify_regeneration

    root = _copy(tmp_path)
    train = _rows(root, "train")
    # Changing a harmless suffix leaves its arithmetic answer correct.
    train[0]["instruction"] += " Please."
    _change_rows(root, "train", train)
    _change_corpus(root, train)
    assert validate_curriculum(root)["oracle_verified_rows"] == 720
    with pytest.raises(SyntheticCurriculumError, match="does not reproduce"):
        verify_regeneration(root)


def test_dataset_operator_cli_checks_rights_and_nonclobber_exports(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.verify_offline_foundations import main

    assert main(["--dataset", str(SOURCE)]) == 0
    assert json.loads(capsys.readouterr().out)["oracle_verified_rows"] == 720
    output = tmp_path / "train-only.txt"
    assert main([
        "--dataset", str(SOURCE), "--export-train", str(output),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["held_out_examples_exported"] == 0
    assert result["exported_training_rows"] == 36
    assert result["full_bank_explicitly_selected"] is False
    from skeleton.ai.training.sparse_capability import build_sparse_capability_plan
    assert output.read_bytes() == build_sparse_capability_plan(SOURCE)["training_text"]
    assert main([
        "--dataset", str(SOURCE), "--export-train", str(output),
    ]) == 1
    from skeleton.ai.training.sparse_capability import build_sparse_capability_plan
    assert output.read_bytes() == build_sparse_capability_plan(SOURCE)["training_text"]
    assert "requires a new local file" in capsys.readouterr().err
    assert main(["--dataset", str(SOURCE), "--split", "test"]) == 2
    assert main([
        "--dataset", str(SOURCE), "--register-db", str(tmp_path / "training.sqlite"),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["governed_training_ready"] is True
    assert receipt["registered_training_rows"] == 36
    assert receipt["full_bank_explicitly_selected"] is False
    assert receipt["trained_weights_promoted"] is False
    assert len(receipt["registered_dataset_digest"]) == 64


def test_training_dataset_export_never_clobbers_or_writes_into_source(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.verify_offline_foundations import main
    from scripts.training.generate_offline_foundations import main as generator

    data = _copy(tmp_path)
    assert main([
        "--dataset", str(data),
        "--export-train", str(data / "outside.txt"),
    ]) == 1
    assert not (data / "outside.txt").exists()
    assert main([
        "--dataset", str(data),
        "--register-db", str(data / "new-registry.sqlite"),
    ]) == 1
    assert not (data / "new-registry.sqlite").exists()
    assert generator([
        "--dataset", str(data), "--output", str(data / "subfolder"),
    ]) == 1
    assert not (data / "subfolder").exists()


def test_rights_or_split_policy_cannot_be_silently_redeclared(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    manifest_file = root / "manifest.json"
    manifest = json.loads(manifest_file.read_text("utf-8"))
    manifest["rights"]["independent_legal_review_performed"] = True
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    with pytest.raises(SyntheticCurriculumError, match="manifest"):
        validate_curriculum(root)
    manifest["rights"]["independent_legal_review_performed"] = False
    manifest["split_protocol"]["template_overlap_across_splits"] = False
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    with pytest.raises(SyntheticCurriculumError, match="manifest"):
        validate_curriculum(root)


def test_extra_manifest_authority_and_duplicate_json_fields_fail_closed(
    tmp_path: Path,
) -> None:
    root = _copy(tmp_path)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["production_weights_promoted"] = True
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SyntheticCurriculumError, match="manifest"):
        validate_curriculum(root)

    manifest.pop("production_weights_promoted")
    raw = json.dumps(manifest)
    raw = raw.replace(
        '"seed": 1729', '"seed": 1729, "seed": 1729', 1,
    )
    assert raw.count('"seed":') == 2
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(SyntheticCurriculumError, match="duplicate"):
        validate_curriculum(root)


def test_operator_reference_bank_requires_explicit_full_training_selection(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.verify_offline_foundations import main

    # Default export is tiny; full training bank needs a deliberately
    # different flag and is *never* selected by default.
    sparse = tmp_path / "default.txt"
    full = tmp_path / "reference.txt"
    assert main(["--dataset", str(SOURCE), "--export-train", str(sparse)]) == 0
    capsys.readouterr()
    assert sparse.read_bytes().count(b"<user>\n") == 36

    assert main([
        "--dataset", str(SOURCE), "--export-reference-bank", str(full),
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["exported_training_rows"] == 504
    assert result["full_bank_explicitly_selected"] is True
    assert full.read_bytes() == (SOURCE / "train_corpus.txt").read_bytes()
    assert full.read_bytes().count(b"<user>\n") == 504
    assert main([
        "--dataset", str(SOURCE), "--export-reference-bank", str(full),
    ]) == 1
    assert full.read_bytes().count(b"<user>\n") == 504


def test_operator_heldout_score_defaults_to_validation_split(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.verify_offline_foundations import main

    rows = _rows(SOURCE, "validation")
    file = tmp_path / "predictions.jsonl"
    file.write_text(
        "".join(
            json.dumps({"id": item["id"], "prediction": item["response"]}) + "\n"
            for item in rows
        ), encoding="utf-8",
    )
    assert main(["--dataset", str(SOURCE), "--evaluate", str(file)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["split"] == "validation"
    assert report["correct"] == 108
    assert report["total"] == 108
    assert report["trained_weights_promoted"] is False
