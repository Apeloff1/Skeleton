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
    derive_obligations,
    reconcile_repository,
)


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_HEAD = "6384313e29f701eafbe06c00bdaf026115ce1ae3"
VERIFIER_RUN_ID = 36745047454
VERIFIER_JOB_ID = 109988984336
TERMINAL_RUN_ID = 36745047282
TERMINAL_JOB_ID = 109988982027
BOUND_AT = "2026-09-30T16:36:00Z"
REVIEW_AT = "2026-10-30T16:36:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "P1-GAP-VOL-077:gap:015df8ff35-8a709477a51df6cf": {
        "volume": "VOL-077",
        "obligation_digest": "6fd3964219ee55567cb43d0b66318dd83666eff24ef957647b2ab03998e73fe6",
        "evidence_digest": "03802bf5b84765774a6a5706aa35d0694849b747718d46a8fa2066d16207c396",
        "statement": "bind experiments to reproducibility/provenance",
    },
    "P1-GAP-VOL-077:gap:368bfc596e-66a6c319e79875cf": {
        "volume": "VOL-077",
        "obligation_digest": "1e3536efefd50498521c2f5411fb6226843d7e852ebdd7aed7b41d15a858b551",
        "evidence_digest": "f85bc8aa41a822997ad5c0b17fb7f844b62068ed5b4649af248df400dbcfbfff",
        "statement": "define experiment schema",
    },
    "P1-GAP-VOL-082:gap:cc6459c1d7-98f7f47f5f351d79": {
        "volume": "VOL-082",
        "obligation_digest": "46b65d17123254db534f2ffe601d7656bc6ffb6fb4f1312d63a45111490772d2",
        "evidence_digest": "0b62bf7257ec7dcee4077631c07e3f109d21fbf39ae696fd88ec035ce24ffa78",
        "statement": "bind benchmark claims to reproducibility records",
    },
    "P1-GAP-VOL-082:gap:11a839d087-8be4462814c13eaf": {
        "volume": "VOL-082",
        "obligation_digest": "cb1fa53ee78b7b86e8b7112422369eaf68215cbdf492109cbcf5965be5b07c02",
        "evidence_digest": "cf6fc388c6c69126b8d443441ffa3cec569b4624d30076418f77dd4a2a46bdc4",
        "statement": "define canonical benchmark registry",
    },
    "P1-GAP-VOL-324:gap:da08ee0247-f60e51545be71336": {
        "volume": "VOL-324",
        "obligation_digest": "eabb960ec3c99be031ac941be57cc6c3b36e3d926b50fa029b3b77c7f16d8490",
        "evidence_digest": "20446696118a4d172314b3775ba9dcc882557c14d4074d8efa203b5019e3f28e",
        "statement": "bind promotion gates",
    },
    "P1-GAP-VOL-324:gap:58d10be00f-565ffac84c80229b": {
        "volume": "VOL-324",
        "obligation_digest": "ed73da06cfe226044613e964fb1a8656e21b9022e5a405339d1b6362baf037c7",
        "evidence_digest": "2a10311d8f0a0ca54c32d0e3823679797356dac36a04f35145fbe4848b7a2ced",
        "statement": "seed historical failure cases",
    },
    "P1-GAP-VOL-414:gap:360528bb94-27055c7ebf612001": {
        "volume": "VOL-414",
        "obligation_digest": "50fca755e074dbb20ba87a992b0bcb6c60a28985ed7a6455ee1ed5601764a79b",
        "evidence_digest": "aaaec39dfeeadf64043f66353e2cec30cd65be7ef8040019a2d49d3bae21fe3b",
        "statement": "bind champion/challenger",
    },
    "P1-GAP-VOL-414:gap:2ff615d88a-ba34dcd1ac04eb85": {
        "volume": "VOL-414",
        "obligation_digest": "48b1871d1cb9defa80a1aaab00467003242bccd22109718b3b45ef900374b2e8",
        "evidence_digest": "ab074625a3ef8ffc589626d0a1edf890fa54e2aa480020065b4c5ffa3300d45a",
        "statement": "define eligibility/redaction",
    },
    "P1-GAP-VOL-415:gap:210392ecc3-e9e7bc2667a8e33a": {
        "volume": "VOL-415",
        "obligation_digest": "b9b1d64ac7cdf31135e92674a54e8f9f8c02e59117efa7365f04d1540584e9b3",
        "evidence_digest": "b86b35692757af17e3288cada509f051d0bef377297f86f78ffce94a0c34f487",
        "statement": "bind release gates",
    },
    "P1-GAP-VOL-415:gap:99373e5bc1-ec31886904cec4e4": {
        "volume": "VOL-415",
        "obligation_digest": "3cabbcc9f5c334ba51446232c5d379d1879e7b307d2d7f2be54fb30f3ba4538a",
        "evidence_digest": "0159aa3688c14e913d6c9f5fb2ae389cf294191e1fdbfe5826fa4e7ee4884f1e",
        "statement": "unify self-improvement registry",
    },
    "P1-GAP-VOL-419:gap:13aee1138e-6556f2baafb11049": {
        "volume": "VOL-419",
        "obligation_digest": "e5210591c9c7c3c5b80368a099944662de5e71a7ebeaa94dc9b8cb4519e0eab2",
        "evidence_digest": "53134b266a2e0b687eeb77bdf568c7efd2a8d29d249ad5efe8c22314d20f7e86",
        "statement": "bind risk/test generation",
    },
    "P1-GAP-VOL-419:gap:88329581ef-fba1b83d7c94b8f9": {
        "volume": "VOL-419",
        "obligation_digest": "497682d311d5823b7382ee4d0001e6e62ff1b19091939ffadcec26351ba86839",
        "evidence_digest": "e523c03e19f606f98572902481422be058770ec0ac835fc42d256f1f7fc810d5",
        "statement": "ingest incidents/negative results",
    },
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _batch3_records() -> list[dict]:
    registry = _load(ROOT / REGISTRY)
    return [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] == "learning_eval_gap_closure"
    ]


def test_batch3_registry_contains_exact_verified_learning_eval_bindings() -> None:
    records = _batch3_records()

    assert len(records) == 12
    assert {row["obligation_id"] for row in records} == set(EXPECTED)

    for row in records:
        expected = EXPECTED[row["obligation_id"]]
        assert row["owner_id"] == "ACC-" + expected["volume"]
        assert row["obligation_digest"] == expected["obligation_digest"]
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert len(row["evidence"]) == 1

        evidence = row["evidence"][0]
        assert evidence == {
            "source": (
                "p1:learning-eval-gap-batch3:"
                + row["obligation_id"]
                + ":"
                + VERIFIER_HEAD
            ),
            "digest": expected["evidence_digest"],
            "category": "learning_eval_gap_closure",
        }


def test_batch3_bindings_match_live_canonical_gap_obligations() -> None:
    obligations = {
        item.obligation_id: item
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
    }

    for row in _batch3_records():
        expected = EXPECTED[row["obligation_id"]]
        obligation = obligations[row["obligation_id"]]
        assert obligation.statement == expected["statement"]
        assert obligation.obligation_digest == expected["obligation_digest"]
        assert row["obligation_digest"] == obligation.obligation_digest
        assert obligation.kind.value == "gap"
        assert obligation.default_severity.value == "high"
        assert obligation.blocking_by_default is True


def test_batch3_verifier_identity_is_exact_and_auditable() -> None:
    assert len(VERIFIER_HEAD) == 40
    assert VERIFIER_RUN_ID == 36745047454
    assert VERIFIER_JOB_ID == 109988984336
    assert TERMINAL_RUN_ID == 36745047282
    assert TERMINAL_JOB_ID == 109988982027

    for row in _batch3_records():
        source = row["evidence"][0]["source"]
        assert source.endswith(":" + VERIFIER_HEAD)
        assert row["obligation_id"] in source


def test_combined_risk_reconciliation_resolves_thirty_four_obligations() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["inventory"] == {
        "p1_primary_volume_count": 107,
        "volume_risk_count": 281,
        "volume_gap_count": 208,
        "applicable_adversarial_axis_count": 24,
        "total_obligation_count": 513,
    }
    assert report["binding_count"] == 34
    assert report["resolved_count"] == 34
    assert report["unresolved_blocking_count"] == 479
    assert report["unclassified_count"] == 281
    assert report["disposition_counts"] == {
        "evidence": 34,
        "unbound": 479,
    }


def test_batch3_does_not_delete_canonical_masterplan_gaps() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}

    expected = {
        "VOL-077": {
            "define experiment schema",
            "bind experiments to reproducibility/provenance",
        },
        "VOL-082": {
            "define canonical benchmark registry",
            "bind benchmark claims to reproducibility records",
        },
        "VOL-324": {
            "seed historical failure cases",
            "bind promotion gates",
        },
        "VOL-414": {
            "define eligibility/redaction",
            "bind champion/challenger",
        },
        "VOL-415": {
            "unify self-improvement registry",
            "bind release gates",
        },
        "VOL-419": {
            "ingest incidents/negative results",
            "bind risk/test generation",
        },
    }
    for key, statements in expected.items():
        assert statements <= set(by_key[key]["gaps"])
