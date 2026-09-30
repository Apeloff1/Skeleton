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
RESIDUAL = {"AC-01", "AC-08", "AC-10", "AC-21"}
EXPECTED = {
    "AC-19": {
        "obligation_id": "P1-ADVERSARIAL-AC-19-e54597c74279060f",
        "obligation_digest": "92e62c90aa0f786e39dbde96c977092e43561393f0b11185175a1463fc4cacc7",
        "verifier_head": "e0be4f30379fa99a31d6ec17234db21367257e8b",
        "verifier_run_id": 36782752779,
        "verifier_job_id": 110116782073,
        "report_digest": "4843a9ef3a11b21392b88ca4e4052da099fc933b8126d80b9d919743ce289bf1",
        "modes": {
            "break_glass_drill": "fa73d6ae5955cc6688de2e3fb959d60f1a40e8c1bb972d998b7bdf6bc82f0e0b",
            "operator_error_simulation": "8c259684a65a98225ff7d5ff0fe54cd53e733828c7e18cd8f52be02eabdabcac",
            "approval_fatigue": "a0369ba21158abfc6aa169a56021bac002251d212d16c8e2a89be2f108eda701",
            "undo_recovery": "f788119eaca047a46105e6728fc8d5628e96f619735f9afab17103f72d96572f",
        },
    },
    "AC-23": {
        "obligation_id": "P1-ADVERSARIAL-AC-23-22bd0e0ac706c216",
        "obligation_digest": "47bdac98bfdd06deb23e600dd418abae3f03ebcf08a11c551bdccbdade97e065",
        "verifier_head": "f15a30b856a857a267b3cfcb5633b6ed19a9618a",
        "verifier_run_id": 36782789242,
        "verifier_job_id": 110116903625,
        "report_digest": "3d6f56fb5f686011a85b402c632bfe5fe8d53c76c0f8d3324e426964f7c88079",
        "modes": {
            "soak": "b70df20f7ed41953a2d1dab12366e39735bd24a97b22b05ad26d90e7ee2e2817",
            "accelerated_time": "63f2c2d92a793d468a99c15b7d7c5ec9156204b6fc37a8781f6cfa65f6cb4295",
            "aging_simulation": "6b191a2cb9ee3f2f2621e398826ac8078586470a629f9ef571b94db75e0bd51d",
            "retirement_migration": "5be90488bd3a8a011907fdf4cd450ef148376ab7f4590a2e1a177b14f72fc5d1",
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


def test_ac19_ac23_bindings_advance_frontier_to_509_4_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 509
    assert report["resolved_count"] == 509
    assert report["unresolved_blocking_count"] == 4
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 509, "unbound": 4}

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == RESIDUAL
