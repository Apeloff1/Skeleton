"""On-demand capability probes leave persisted training data unchanged."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.training.probe_sparse_capabilities import (
    ChallengeError, challenge_cases, challenge_prompts, challenge_receipt,
    main, score_challenge,
)


def test_procedural_probe_covers_all_36_modes_and_exports_no_answers() -> None:
    rows = challenge_cases()
    assert len(rows) == 36
    assert len(set(x["id"] for x in rows)) == 36
    assert len(set(x["capability_id"] for x in rows)) == 36
    assert len(set(x["scenario_group"] for x in rows)) == 36
    assert all(int(x["scenario_group"].rsplit("-", 1)[1]) >= 20 for x in rows)
    exported = challenge_prompts()
    prompts = [json.loads(x) for x in exported.decode("utf-8").splitlines()]
    assert len(prompts) == 36
    for item, truth in zip(prompts, rows):
        assert item["instruction"] == truth["instruction"]
        assert item["id"] == truth["id"]
        assert set(item) == {
            "id", "family", "capability_id", "scenario_group", "instruction",
        }
        assert "expected" not in item and "response" not in item
    receipt = challenge_receipt()
    assert receipt["challenge_count"] == 36
    assert receipt["modes_covered"] == 36
    assert receipt["no_answer_labels_exported"] is True
    assert receipt["training_corpus_expanded"] is False
    assert receipt["model_capability_qualified"] is False


@pytest.mark.parametrize("n", [1, 2, 4, 12])
def test_scales_challenge_evaluation_without_persisting_training(n: int) -> None:
    rows = challenge_cases(seed=234, probes_per_mode=n)
    assert len(rows) == 36 * n
    assert len(set(x["id"] for x in rows)) == 36 * n
    assert len(set(x["scenario_group"] for x in rows)) == 36 * n
    assert all("train" not in x["id"] for x in rows)
    assert len(challenge_prompts(seed=234, probes_per_mode=n).splitlines()) == 36 * n


@pytest.mark.parametrize("seed", [-1, 100001, True, "1729"])
def test_invalid_generator_seed_rejected(seed) -> None:
    with pytest.raises(ChallengeError, match="seed"):
        challenge_cases(seed=seed)


@pytest.mark.parametrize("count", [-1, 0, 13, 100, 1.0, True])
def test_invalid_generator_budget_rejected(count) -> None:
    with pytest.raises(ChallengeError, match="budget"):
        challenge_cases(probes_per_mode=count)


def _prediction_file(target: Path, *, seed: int = 1729,
                     count: int = 1, wrong: bool = False) -> None:
    examples = list(challenge_cases(seed=seed, probes_per_mode=count))
    if wrong:
        examples[0]["expected"] = "explicitly-wrong"
    target.write_text(
        "".join(json.dumps({"id": x["id"], "prediction": x["expected"]}) + "\n"
                for x in examples),
        encoding="utf-8",
    )


def test_reference_predictions_are_scored_without_increasing_training_data(
    tmp_path: Path,
) -> None:
    predictions = tmp_path / "answers.jsonl"
    _prediction_file(predictions)
    report = score_challenge(predictions)
    assert report["correct"] == report["total"] == 36
    assert len(report["by_mode"]) == 36
    assert all(x["total"] == x["correct"] == 1
               for x in report["by_mode"].values())
    assert report["training_corpus_expanded"] is False
    assert report["model_capability_qualified"] is False

    _prediction_file(predictions, wrong=True)
    wrong = score_challenge(predictions)
    assert wrong["correct"] == 35
    assert wrong["total"] == 36
    assert len([x for x in wrong["by_mode"].values()
                if x["correct"] != x["total"]]) == 1


def test_score_fails_closed_for_missing_unknown_duplicate_predictions(
    tmp_path: Path,
) -> None:
    target = tmp_path / "predictions.jsonl"
    _prediction_file(target)
    rows = [json.loads(x) for x in target.read_text("utf-8").splitlines()]
    target.write_text("".join(json.dumps(x) + "\n" for x in rows[:-1]), "utf-8")
    with pytest.raises(ChallengeError, match="one prediction"):
        score_challenge(target)
    rows[0]["id"] = "unexpected-prediction-id"
    target.write_text("".join(json.dumps(x) + "\n" for x in rows), "utf-8")
    with pytest.raises(ChallengeError, match="identity"):
        score_challenge(target)
    rows[0]["id"] = rows[1]["id"]
    target.write_text("".join(json.dumps(x) + "\n" for x in rows), "utf-8")
    with pytest.raises(ChallengeError, match="identity"):
        score_challenge(target)


def test_cli_emits_only_prompt_data_and_preserves_existing_file(
    tmp_path: Path, capsys,
) -> None:
    path = tmp_path / "challenge.jsonl"
    assert main(["--export-prompts", str(path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["challenge_count"] == 36
    assert receipt["training_data_mutated"] is False
    content = path.read_bytes()
    assert content == challenge_prompts()
    assert b'"expected":' not in content
    assert b'"response":' not in content
    assert main(["--export-prompts", str(path)]) == 1
    assert path.read_bytes() == content
    capsys.readouterr()

    predictions = tmp_path / "answers.jsonl"
    _prediction_file(predictions)
    assert main(["--score", str(predictions)]) == 0
    assert json.loads(capsys.readouterr().out)["correct"] == 36


def test_procedural_challenge_is_deterministic_for_same_seed() -> None:
    first = challenge_prompts(seed=100, probes_per_mode=3)
    second = challenge_prompts(seed=100, probes_per_mode=3)
    third = challenge_prompts(seed=101, probes_per_mode=3)
    assert first == second
    assert first != third


def test_data_bank_does_not_change_while_running_procedural_probe() -> None:
    root = Path(__file__).resolve().parents[2] / (
        "skeleton/ai/training/datasets/offline_foundations_v1"
    )
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    challenge_cases(seed=1729, probes_per_mode=12)
    after = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    assert before == after
