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
VERIFIER_HEAD = "7c3932ad71705ba0c6a95bf9bae620fa51866914"
VERIFIER_RUN_ID = 36784502045
VERIFIER_JOB_ID = 110122546683
RESIDUAL: set[str] = set()
EXPECTED = {
    "AC-01": {
        "obligation_id": "P1-ADVERSARIAL-AC-01-a8229f80cbb43d7c",
        "obligation_digest": "7d467940f8a5792ae8672d4afe7617de5b3a60d1558f8dbf13a8152471add481",
        "report_digest": "fb01ba202132bdadded0ac4cc5af8517f0f52569110ddcb9bf9dc370caac6246",
        "modes": {
            "clean_machine_e2e": "78892afd018913b33ec3ad3e5da2976283430f383d406b659120bfdd585d2fcd",
            "trust_root_rotation": "0fdb446237b2606ccf0eada73198e2b7c8ed06291f2888d0c9157e6cab6a30c6",
            "bootstrap_fault_injection": "e5d489c27558c560958102a053420f3988865394e05cf0a59d1b7e64e5b53258",
            "recovery_drill": "cae8710e47a94c7f17b6eec7564c817360332489498ed92d55619dd6e99f3b30",
        },
    },
    "AC-08": {
        "obligation_id": "P1-ADVERSARIAL-AC-08-17b003d162aa15f0",
        "obligation_digest": "d772b28ffe6bacfa91412e9b61dd1527291c59a0ceb1f674f8e3535d395e9318",
        "report_digest": "ebae7c1459af81ab5894a2456a4d932d2e91e77cfb80316e3c8d867fb154a21b",
        "modes": {
            "restore_drill": "2e4b416e4a17aa6bbd285aa2a39bf349d1532759dd2dbb6cc3dda4155584791c",
            "tombstone_propagation": "0f1e4f3afdef4aa0a6eec7c14e575d674f21307c29f68a2e5ae80e88c6ab0a0f",
            "external_reconciliation": "506d8e744dcad6e9f8873deb906dcad7aefe3bb62906766e691f3ff70a5f4e9f",
            "credential_revalidation": "9bc1c2b3cb7c7c1af348623245ef45ec4ac02fea886f3d93d5725f477df8e30b",
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


def test_ac01_ac08_bindings_pin_successful_exact_head_receipts() -> None:
    assert VERIFIER_RUN_ID == 36784502045
    assert VERIFIER_JOB_ID == 110122546683

    registry = _load(ROOT / REGISTRY)
    by_id = {row["obligation_id"]: row for row in registry["records"]}

    for axis_id, expected in EXPECTED.items():
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
                f"p1:adversarial-wave4-evidence:{axis_id}:"
                f"{category}:{VERIFIER_HEAD}"
            )


def test_ac01_ac08_bindings_match_live_canonical_obligations() -> None:
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


def test_ac01_ac08_bindings_advance_frontier_to_513_0_0() -> None:
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
