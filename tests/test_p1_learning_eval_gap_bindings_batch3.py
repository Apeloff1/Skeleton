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
VERIFIER_HEAD = "12f914521b59f26299d2e9c621649cdc95fac9dc"
VERIFIER_RUN_ID = 36746419769
VERIFIER_JOB_ID = 109993642569
TERMINAL_RUN_ID = 36746419690
TERMINAL_JOB_ID = 109993641733
BOUND_AT = "2026-09-30T16:47:00Z"
REVIEW_AT = "2026-10-30T16:47:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "P1-GAP-VOL-077:gap:015df8ff35-8a709477a51df6cf": {
        "volume": "VOL-077",
        "obligation_digest": "6fd3964219ee55567cb43d0b66318dd83666eff24ef957647b2ab03998e73fe6",
        "evidence_digest": "454e2c7be9238a0e84015810cdf9185b14c1e06e70bacbe6d13ae672538fc9a9",
        "statement": "bind experiments to reproducibility/provenance",
    },
    "P1-GAP-VOL-077:gap:368bfc596e-66a6c319e79875cf": {
        "volume": "VOL-077",
        "obligation_digest": "1e3536efefd50498521c2f5411fb6226843d7e852ebdd7aed7b41d15a858b551",
        "evidence_digest": "ffb26d7c60f52a2cb434a686cde87b6c74584837ddf567cfb949abe33890d1e0",
        "statement": "define experiment schema",
    },
    "P1-GAP-VOL-082:gap:cc6459c1d7-98f7f47f5f351d79": {
        "volume": "VOL-082",
        "obligation_digest": "46b65d17123254db534f2ffe601d7656bc6ffb6fb4f1312d63a45111490772d2",
        "evidence_digest": "c7a3a81c175533745791b192019d06169f120cbca76aa9014b2da9657fb9da89",
        "statement": "bind benchmark claims to reproducibility records",
    },
    "P1-GAP-VOL-082:gap:11a839d087-8be4462814c13eaf": {
        "volume": "VOL-082",
        "obligation_digest": "cb1fa53ee78b7b86e8b7112422369eaf68215cbdf492109cbcf5965be5b07c02",
        "evidence_digest": "77a890005c31ff820ee9b1e7b96ff2903a7b3cb9770fbcc7c14ab32e7d9a6b85",
        "statement": "define canonical benchmark registry",
    },
    "P1-GAP-VOL-324:gap:da08ee0247-f60e51545be71336": {
        "volume": "VOL-324",
        "obligation_digest": "eabb960ec3c99be031ac941be57cc6c3b36e3d926b50fa029b3b77c7f16d8490",
        "evidence_digest": "1e43ab7bf93546b2146befd153fe86d21cf1f64eb9b76852a96439e3bfc307f9",
        "statement": "bind promotion gates",
    },
    "P1-GAP-VOL-324:gap:58d10be00f-565ffac84c80229b": {
        "volume": "VOL-324",
        "obligation_digest": "ed73da06cfe226044613e964fb1a8656e21b9022e5a405339d1b6362baf037c7",
        "evidence_digest": "1e5ad1ce29f103c7aeebbdb78bdde5c0768b7eece520b3ada7da2f14aa4e4835",
        "statement": "seed historical failure cases",
    },
    "P1-GAP-VOL-414:gap:360528bb94-27055c7ebf612001": {
        "volume": "VOL-414",
        "obligation_digest": "50fca755e074dbb20ba87a992b0bcb6c60a28985ed7a6455ee1ed5601764a79b",
        "evidence_digest": "db6a38387d06c39170f33ee8c9ed63ae40004c519bd41c3e46f0a223e4fa743b",
        "statement": "bind champion/challenger",
    },
    "P1-GAP-VOL-414:gap:2ff615d88a-ba34dcd1ac04eb85": {
        "volume": "VOL-414",
        "obligation_digest": "48b1871d1cb9defa80a1aaab00467003242bccd22109718b3b45ef900374b2e8",
        "evidence_digest": "8558e985ddcea32487e0b9a81f3a91bb544e355b70d0f40160fb0d9fe91ae31b",
        "statement": "define eligibility/redaction",
    },
    "P1-GAP-VOL-415:gap:210392ecc3-e9e7bc2667a8e33a": {
        "volume": "VOL-415",
        "obligation_digest": "b9b1d64ac7cdf31135e92674a54e8f9f8c02e59117efa7365f04d1540584e9b3",
        "evidence_digest": "4b1572b17b4238660456b15ad9528207edd399d6fa754298eb5f1ae8dc620224",
        "statement": "bind release gates",
    },
    "P1-GAP-VOL-415:gap:99373e5bc1-ec31886904cec4e4": {
        "volume": "VOL-415",
        "obligation_digest": "3cabbcc9f5c334ba51446232c5d379d1879e7b307d2d7f2be54fb30f3ba4538a",
        "evidence_digest": "2e8a7a1529f6747f17dade4319bc0f4306c90619ccb32adcb21e318405618ed2",
        "statement": "unify self-improvement registry",
    },
    "P1-GAP-VOL-419:gap:13aee1138e-6556f2baafb11049": {
        "volume": "VOL-419",
        "obligation_digest": "e5210591c9c7c3c5b80368a099944662de5e71a7ebeaa94dc9b8cb4519e0eab2",
        "evidence_digest": "b1211922645e1223617628bfdd48e1b0729e49a381a25a82f3c007326b751ca3",
        "statement": "bind risk/test generation",
    },
    "P1-GAP-VOL-419:gap:88329581ef-fba1b83d7c94b8f9": {
        "volume": "VOL-419",
        "obligation_digest": "497682d311d5823b7382ee4d0001e6e62ff1b19091939ffadcec26351ba86839",
        "evidence_digest": "ec9faa29cce6f663ba3cc13d229036eb5f8bb7b0bb7f5c7d595cf82dcd30909b",
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
        assert row["evidence"][0] == {
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


def test_batch3_mainline_verifier_identity_is_exact_and_auditable() -> None:
    assert len(VERIFIER_HEAD) == 40
    assert VERIFIER_RUN_ID == 36746419769
    assert VERIFIER_JOB_ID == 109993642569
    assert TERMINAL_RUN_ID == 36746419690
    assert TERMINAL_JOB_ID == 109993641733

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
