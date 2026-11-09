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
VERIFIER_HEAD = "66cc408a2a26dbfee74648b60e58ba9d82a40c55"
VERIFIER_RUN_ID = 36784998532
VERIFIER_JOB_ID = 110124179449
REPORT_DIGEST = "f8fef4c3a50a41e48212d5a2716142bf78e7f27fd5bf665ffbdf683989980d4a"
EXPECTED = {
    "AC-10": {
        "obligation_id": "P1-ADVERSARIAL-AC-10-2359b7c9fd5bddd4",
        "obligation_digest": "7b3090648ad00329ba08d07b80177ba1187fffcae5519bec9b283fabc16c6e4e",
        "modes": {
            "credential_rotation": "17c3b265f44820df59de4ec4d2e031a235eafa9063ef38150250302efabd1310",
            "revocation_replay": "60af119722dad4651b16052cd15e381f5bb06f1eee47735a589fccf5754a5a37",
            "identity_restore": "7c9f42b16f5d42a6729fd17a64308bf4fa6e6e585f2fa5cd167bf86dcdd7b410",
            "historical_signature_verify": "7e66c5e51ffc4d4c6daa1bc4e8bffc172c5353be5708001a9f73f9c8a036b92f",
        },
    },
    "AC-21": {
        "obligation_id": "P1-ADVERSARIAL-AC-21-bd22a94e26b15053",
        "obligation_digest": "a7c8d0be5f47977fa5a11d8a02177f7f3aa37f1692fd183b67aa40ef3511b7c7",
        "modes": {
            "recovery_dependency_graph": "9446547c41c54663847c6420ff0d25509a180f6f94e1646aa3074c6e6f5371af",
            "safe_mode_drill": "43f58297430c6bce7fa0993e26ebbe3743c3cdc11809861c02a1d67032b9efa3",
            "control_plane_isolation": "a3cc1826b3842c2fd60a3b7efe4c1af6a1fc2bf19d059e00d25ac47826da5649",
            "cold_restore": "c19299f0cf71374bce83e30d5d1d145037cb21b366e25eca4337f1db1dc657d9",
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


def test_ac10_ac21_bindings_pin_successful_exact_head_receipt() -> None:
    assert VERIFIER_RUN_ID == 36784998532
    assert VERIFIER_JOB_ID == 110124179449
    assert len(REPORT_DIGEST) == 64

    registry = _load(ROOT / REGISTRY)
    by_id = {row["obligation_id"]: row for row in registry["records"]}

    for axis_id, expected in EXPECTED.items():
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
                f"p1:adversarial-ac10-ac21-evidence:{axis_id}:"
                f"{category}:{VERIFIER_HEAD}"
            )


def test_ac10_ac21_bindings_match_live_canonical_obligations() -> None:
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


def test_ac10_ac21_bindings_close_terminal_513_0_0_frontier() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 513
    assert report["resolved_count"] == 513
    assert report["unresolved_blocking_count"] == 0
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {"evidence": 513}

    unresolved = [
        row
        for row in report["records"]
        if not row["evaluation"]["resolved"]
    ]
    assert unresolved == []

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    residual = {
        item.source_ref
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL and item.obligation_id not in bound
    }
    assert residual == set()
