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
BOUND_AT = "2026-09-30T18:45:00Z"
REVIEW_AT = "2026-10-30T18:45:00Z"
RESOLVED_AXES = frozenset({"AC-11", "AC-13", "AC-14", "AC-15", "AC-20"})
EXPECTED_RESIDUAL_AXIS_COUNT = 19

EXPECTED = {
    "AC-11": {
        "obligation_id": "P1-ADVERSARIAL-AC-11-3d29c2151a6e3351",
        "obligation_digest": "0c867539f12df396af4716514ff7abb81ba649ea020ccd285f99de27847a184a",
        "verifier_head": "9f7a70b8dda16e50d8c642165b0c90da9fed29db",
        "verifier_run": 36758958895,
        "verifier_job": 110036293521,
        "evidence": {
            "semantic_canary": "806c9b16e2361b498232189821337428d66da5ee00293024f853d15a7b4b745a",
            "contract_probe": "d57fc24f73d225383b70356364e9c9a2a22f7cbc0e7d6516a98b38b9f99a2d79",
            "drift_eval": "d823da5c04ff8b1abb70f3415f4bc57a13874a4fcee43e95be1594bcee5006fc",
            "evidence_invalidation": "2e003c962809a28c2901c732ddbd3147be2c62621316f9230747a570181ebd21",
        },
    },
    "AC-15": {
        "obligation_id": "P1-ADVERSARIAL-AC-15-f7f89f2c5b94ede2",
        "obligation_digest": "f40e7b2b95b734e8fad7419baa251d47e9e05a3ec343f677d0a6e93fa7dab98d",
        "verifier_head": "32d7f55345db9f081ed8c6a8adb72a7012489e27",
        "verifier_run": 36758921559,
        "verifier_job": 110036166551,
        "evidence": {
            "budget_fault": "1f824dd862945c00e379e256dd0613a4c35e0a78c74cc8b4097899a624b677d2",
            "fanout_stress": "38856b532fe1671f5a9d06b456b2ca81fa7c7b6d834673d7a1e5422ff480a88b",
            "quota_isolation": "2b6a39fdb1f6ffa6f41edd55ca25c045770888e81c1d571ffe61a99c401206ee",
            "provider_reprice_simulation": "6cb6f58f37905309803f8a3fe990c977d29a1e250143f1234906f287ee0c3e44",
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


def _registry_rows() -> dict[str, dict]:
    registry = _load(ROOT / REGISTRY)
    return {
        row["obligation_id"]: row
        for row in registry["records"]
        if row["obligation_id"] in {
            EXPECTED["AC-11"]["obligation_id"],
            EXPECTED["AC-15"]["obligation_id"],
        }
    }


def test_wave2_bindings_pin_successful_exact_head_verifiers() -> None:
    rows = _registry_rows()
    assert len(rows) == 2

    for axis_id, expected in EXPECTED.items():
        row = rows[expected["obligation_id"]]
        assert row["obligation_digest"] == expected["obligation_digest"]
        assert row["owner_id"] == "ACC-P1-EVID-04"
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert expected["verifier_run"] > 0
        assert expected["verifier_job"] > 0

        by_category = {item["category"]: item for item in row["evidence"]}
        assert set(by_category) == set(expected["evidence"])
        for category, digest in expected["evidence"].items():
            evidence = by_category[category]
            assert evidence["digest"] == digest
            assert evidence["source"] == (
                f"p1:adversarial-{axis_id.lower().replace('-', '')}-evidence:"
                f"{axis_id}:{category}:{expected['verifier_head']}"
            )


def test_wave2_bindings_match_live_adversarial_obligations() -> None:
    obligations = {
        item.source_ref: item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL
    }
    rows = _registry_rows()

    for axis_id, expected in EXPECTED.items():
        obligation = obligations[axis_id]
        row = rows[expected["obligation_id"]]
        assert obligation.obligation_id == expected["obligation_id"]
        assert obligation.obligation_digest == expected["obligation_digest"]
        assert row["obligation_digest"] == obligation.obligation_digest
        assert set(obligation.required_evidence_modes) == set(expected["evidence"])


def test_wave2_advances_governed_frontier_to_494_19_0() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["binding_count"] == 494
    assert report["resolved_count"] == 494
    assert report["unresolved_blocking_count"] == 19
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 494,
        "unbound": 19,
    }

    registry = _load(ROOT / REGISTRY)
    bound = {row["obligation_id"] for row in registry["records"]}
    unbound = [
        item
        for item in _obligations()
        if item.kind is RiskKind.ADVERSARIAL
        and item.obligation_id not in bound
    ]
    assert len(unbound) == EXPECTED_RESIDUAL_AXIS_COUNT
    assert {item.source_ref for item in unbound} == {
        f"AC-{index:02d}" for index in range(1, 25)
    } - RESOLVED_AXES
