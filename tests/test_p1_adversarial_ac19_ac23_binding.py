from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.reconcile_p1_risk_evidence import (
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
    reconcile_repository,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
RESIDUAL: set[str] = set()
EXPECTED = {
    "AC-19": {
        "obligation_id": "P1-ADVERSARIAL-AC-19-e54597c74279060f",
        "obligation_digest": "92e62c90aa0f786e39dbde96c977092e43561393f0b11185175a1463fc4cacc7",
        "verifier_head": "c5e9dc1c9260ca9de629e8a8325d3eb413a4af69",
        "verifier_run_id": 36784948675,
        "verifier_job_id": 110124018921,
        "report_digest": "49f618b48a68905f92b029e60e316086b3518463d8a9f315f29c2fbf33fd91c4",
        "modes": {
            "break_glass_drill": "e542a940abb72a69c2a5f3ba4f3c3fb95c086dfb31f6bba277d312d714a52df3",
            "operator_error_simulation": "fc8d3c4b80b53ce0b3d1d63e470e81d9f98b779678bc45debf67de5c4b9fc2e7",
            "approval_fatigue": "f3b025040eeaa05c3e43ad37c85b1b2f6f6514505b9f877e2c045fc1e4263ef5",
            "undo_recovery": "f16464b3b2e09bbb149d1cf4fafb24d60b6655f1189e2482063c4df6b35c4c5c",
        },
    },
    "AC-23": {
        "obligation_id": "P1-ADVERSARIAL-AC-23-22bd0e0ac706c216",
        "obligation_digest": "47bdac98bfdd06deb23e600dd418abae3f03ebcf08a11c551bdccbdade97e065",
        "verifier_head": "7847bbadb5c0c245fcdf00212c064b3d00169786",
        "verifier_run_id": 36784985795,
        "verifier_job_id": 110124134360,
        "report_digest": "6b7732ea4af5cc0a2b65cb2b53abc677fa266301f8c2161427f5248c5c5d67bb",
        "modes": {
            "soak": "106e36efadfba58b8dda00d1b6fa4ee5aba035e2d0f30b80461aa270700182d0",
            "accelerated_time": "0e7fced251b4c94cf39f887aa7329fc783cb66dfd2b7c21416e8ffc06f27b318",
            "aging_simulation": "ba9fcccd7168c1669c66afbf4a3fe98cb305e334a9fde37a3f8f5424a8813789",
            "retirement_migration": "58d7cf96853f730af5e7c384f069cc9334d237452dc0c970ae070a843d8d3094",
        },
    },
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _obligations():
    return derive_obligations(
        _load(ROOT / MASTER),
        _load(ROOT / P1_MAP),
        _load(ROOT / ADVERSARIAL),
        _load(ROOT / POLICY),
    )


def test_ac19_ac23_bindings_pin_successful_exact_head_receipts() -> None:
    registry = _load(ROOT / REGISTRY)
    by_id = {row["obligation_id"]: row for row in registry["records"]}

    for axis_id, expected in EXPECTED.items():
        assert expected["verifier_run_id"] > 0
        assert expected["verifier_job_id"] > 0
        assert len(expected["report_digest"]) == 64

        row = by_id[expected["obligation_id"]]
        assert row["obligation_digest"] == expected["obligation_digest"]
        assert row["owner_id"] == "ACC-P1-EVID-04"
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["accepted_risk"] is None

        by_category = {item["category"]: item for item in row["evidence"]}
        assert set(by_category) == set(expected["modes"])
        for category, digest in expected["modes"].items():
            evidence = by_category[category]
            assert evidence["digest"] == digest
            assert evidence["source"] == (
                f"p1:adversarial-ac{axis_id[-2:]}-evidence:"
                f"{axis_id}:{category}:{expected['verifier_head']}"
            )


def test_ac19_ac23_bindings_match_live_canonical_obligations() -> None:
    by_axis = {
        item.source_ref: item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL
    }
    for axis_id, expected in EXPECTED.items():
        obligation = by_axis[axis_id]
        assert obligation.obligation_id == expected["obligation_id"]
        assert obligation.obligation_digest == expected["obligation_digest"]
        assert set(obligation.required_evidence_modes) == set(expected["modes"])


def test_ac19_ac23_bindings_advance_frontier_to_513_0_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 513
    assert report["resolved_count"] == 513
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 513}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
