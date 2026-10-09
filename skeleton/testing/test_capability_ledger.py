"""Aggregate-only capability history: durability, tampering and no data growth."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from skeleton.ai.training.capability_ledger import (
    MAX_REPORTS, CapabilityLedgerError, OfflineCapabilityLedger,
    make_capability_receipt,
)
from skeleton.ai.training.offline_foundations import validate_curriculum


SOURCE = Path(__file__).resolve().parents[2] / (
    "skeleton/ai/training/datasets/offline_foundations_v1"
)


def _predictions(target: Path, *, wrong_mode: str | None = None) -> Path:
    data = [
        json.loads(line)
        for line in (SOURCE / "validation.jsonl").read_text("utf-8").splitlines()
    ]
    for row in data:
        if wrong_mode and row["family"] == wrong_mode:
            row["response"] = "WRONG-INTENTIONAL-REFERENCE-MODEL-OUTPUT"
    target.write_text(
        "".join(json.dumps({"id": x["id"], "prediction": x["response"]})
                + "\n" for x in data),
        encoding="utf-8",
    )
    return target


def test_aggregate_receipts_store_no_source_answers_or_predictions(
    tmp_path: Path,
) -> None:
    answers = _predictions(tmp_path / "answers.jsonl")
    receipt = make_capability_receipt(
        SOURCE, answers, model_tag="fixture-model-0",
    )
    assert receipt["split"] == "validation"
    assert receipt["correct"] == receipt["total"] == 108
    assert len(receipt["per_mode"]) == 36
    assert "instruction" not in json.dumps(receipt)
    assert "prediction" not in str(list(receipt["per_mode"].values()))
    ledger = tmp_path / "history.sqlite"
    with OfflineCapabilityLedger(ledger) as store:
        identity = store.record(receipt)
        assert len(identity) == 64
        assert store.record(receipt) == identity
        latest = store.latest(
            "fixture-model-0",
            source_manifest_sha256=receipt["source_manifest_sha256"],
        )
        assert latest == (receipt,)
        comparison = store.compare(
            "fixture-model-0",
            source_manifest_sha256=receipt["source_manifest_sha256"],
        )
        assert comparison["latest_correct"] == 108
        assert comparison["evaluations"] == 1
        assert comparison["proficiency_claimed"] is False
    with sqlite3.connect(ledger) as conn:
        assert conn.execute("SELECT COUNT(*) FROM capability_reports").fetchone()[0] == 1
        stored = conn.execute("SELECT report_json FROM capability_reports").fetchone()[0]
        assert "WRONG-INTENTIONAL" not in stored
        assert '"instruction"' not in stored
        assert '"response"' not in stored
    assert ledger.stat().st_size < 128000


def test_restarted_ledger_marks_improved_modes_without_saving_answers(
    tmp_path: Path,
) -> None:
    full = _predictions(tmp_path / "correct.jsonl")
    wrong = _predictions(tmp_path / "wrong.jsonl", wrong_mode="offline_authority")
    older = make_capability_receipt(SOURCE, wrong, model_tag="candidate-v1")
    newer = make_capability_receipt(SOURCE, full, model_tag="candidate-v1")
    assert older["correct"] == 99
    assert newer["correct"] == 108
    storefile = tmp_path / "history.sqlite"
    with OfflineCapabilityLedger(storefile) as store:
        store.record(older)
    with OfflineCapabilityLedger(storefile) as reopened:
        reopened.record(newer)
        comparison = reopened.compare(
            "candidate-v1",
            source_manifest_sha256=newer["source_manifest_sha256"],
        )
        assert len(comparison["improved_modes"]) == 3
        assert comparison["regressed_modes"] == []
        assert len(comparison["unchanged_modes"]) == 33
        assert comparison["previous_correct"] == 99
        assert comparison["latest_correct"] == 108
        assert comparison["training_samples_added"] == 0
        assert comparison["production_promotion_authorized"] is False


def test_ledger_rejects_invalid_source_counts_and_promotion_flags(
    tmp_path: Path,
) -> None:
    receipt = make_capability_receipt(
        SOURCE, _predictions(tmp_path / "pred.jsonl"), model_tag="candidate",
    )
    cases = [
        {**receipt, "promotion_authorized": True},
        {**receipt, "training_data_modified": True},
        {**receipt, "split": "test"},
        {**receipt, "correct": 900},
        {**receipt, "total": 107},
        {**receipt, "per_mode": {}},
    ]
    with OfflineCapabilityLedger(tmp_path / "ledger.sqlite") as store:
        for forged in cases:
            with pytest.raises(CapabilityLedgerError):
                store.record(forged)
        assert store.latest(
            "candidate", source_manifest_sha256=receipt["source_manifest_sha256"]
        ) == ()


def test_stored_receipt_digest_detects_sqlite_corruption(
    tmp_path: Path,
) -> None:
    receipt = make_capability_receipt(
        SOURCE, _predictions(tmp_path / "pred.jsonl"), model_tag="candidate",
    )
    database = tmp_path / "ledger.sqlite"
    with OfflineCapabilityLedger(database) as ledger:
        ledger.record(receipt)
    with sqlite3.connect(database) as conn:
        content = conn.execute("SELECT report_json FROM capability_reports").fetchone()[0]
        damaged = json.loads(content)
        damaged["correct"] = 0
        conn.execute(
            "UPDATE capability_reports SET report_json=?",
            (json.dumps(damaged),),
        )
    with OfflineCapabilityLedger(database) as ledger:
        with pytest.raises(CapabilityLedgerError, match="totals"):
            ledger.latest(
                "candidate",
                source_manifest_sha256=receipt["source_manifest_sha256"],
            )


@pytest.mark.parametrize("tag", ["", "../../escape", "not legal", "bad:tag", "a" * 65])
def test_invalid_model_tag_never_opens_or_writes_database(
    tmp_path: Path, tag: str,
) -> None:
    with OfflineCapabilityLedger(tmp_path / "ledger.sqlite") as ledger:
        with pytest.raises(CapabilityLedgerError, match="model tag"):
            ledger.latest(tag, source_manifest_sha256="0" * 64)


def test_bound_maximum_report_count_is_a_hard_stop(tmp_path: Path, monkeypatch) -> None:
    import skeleton.ai.training.capability_ledger as module

    base = make_capability_receipt(
        SOURCE, _predictions(tmp_path / "pred.jsonl"), model_tag="fixture",
    )
    monkeypatch.setattr(module, "MAX_REPORTS", 1)
    with OfflineCapabilityLedger(tmp_path / "ledger.sqlite") as ledger:
        ledger.record(base)
        # Identical report remains idempotent at quota.
        ledger.record(base)
        changed = dict(base)
        changed["model_tag"] = "another-model"
        with pytest.raises(CapabilityLedgerError, match="retention limit"):
            ledger.record(changed)


def test_read_only_history_does_not_change_synthetic_source_files(
    tmp_path: Path,
) -> None:
    before = {
        x.name: x.read_bytes()
        for x in SOURCE.iterdir() if x.is_file()
    }
    receipt = make_capability_receipt(
        SOURCE, _predictions(tmp_path / "pred.jsonl"), model_tag="fixture",
    )
    with OfflineCapabilityLedger(tmp_path / "ledger.sqlite") as store:
        store.record(receipt)
        store.compare(
            "fixture", source_manifest_sha256=receipt["source_manifest_sha256"],
        )
    after = {
        x.name: x.read_bytes()
        for x in SOURCE.iterdir() if x.is_file()
    }
    assert before == after
    assert MAX_REPORTS == 500


def test_capability_ledger_cli_records_and_displays_aggregate_status(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.capability_ledger import main

    predictions = _predictions(tmp_path / "val.jsonl", wrong_mode="inventory")
    store = tmp_path / "capabilities.sqlite"
    args = [
        "--dataset", str(SOURCE), "--ledger", str(store),
        "--model-tag", "candidate-v2",
    ]
    assert main([*args, "--record-predictions", str(predictions)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["latest_correct"] == 99
    assert receipt["raw_predictions_stored"] is False
    assert receipt["training_corpus_mutated"] is False
    assert receipt["added_receipt_digest"] is not None
    assert main([*args, "--status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["latest_correct"] == 99
    assert status["added_receipt_digest"] is None
    assert status["last_prediction_sha256"] == receipt["last_prediction_sha256"]
    assert "instruction" not in json.dumps(status)
    assert "response" not in json.dumps(status)
    assert "prediction" not in json.dumps(status).replace(
        "last_prediction_sha256", ""
    ).replace("raw_predictions_stored", "")


def test_capability_ledger_cli_rejects_state_inside_source_directory(
    tmp_path: Path, capsys,
) -> None:
    from scripts.training.capability_ledger import main
    from shutil import copytree

    copied = tmp_path / "copy"
    copytree(SOURCE, copied)
    dest = copied / "new-ledger.sqlite"
    assert main([
        "--dataset", str(copied), "--ledger", str(dest),
        "--model-tag", "trial", "--status",
    ]) == 1
    assert not dest.exists()
    assert "inside the source dataset" in capsys.readouterr().err
