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
VERIFIER_HEAD = "a3925c5ac8e9b402bf92129fcec44688f09ebbfe"
VERIFIER_RUN_ID = 36751635100
VERIFIER_JOB_ID = 110011467161
BOUND_AT = "2026-09-30T17:30:00Z"
REVIEW_AT = "2026-10-30T17:30:00Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "P1-RISK-VOL-000:risk:947b57f6b9-047ba09004303349": ("VOL-000", "4531786454e5d1e82989a71e3f791fcf7368f5bc035113a42842be216bf6a8d8", "dde21edc83cb9b34acd543f0a737a22eb4a31191fd85d2babe60241277e9223a", "human/machine plan divergence"),
    "P1-RISK-VOL-000:risk:8a0e6cc591-ad0ad56c5a6d02c2": ("VOL-000", "dff5d6c860383b3e655d41a4e78305cf8952b93440019ee3a84cb0013c4146d3", "35aade58460e1aba9a0b41e79b00b617c1113bc47f65dbd8c42aac2945d2c631", "parallel planning systems bypassing canonical authority"),
    "P1-RISK-VOL-000:risk:6a720a8603-f539d90abe09b8bf": ("VOL-000", "89c7026703a918b2c4e708294c44a2c6d1e189ca5a1bb79d6f11046a8faf6212", "a36adc6e50d089e8b4f4034bb49fc6429e93d1e96a8901477e601b2a317ef4d4", "status inflation without evidence"),
    "P1-RISK-VOL-038:risk:57039003e8-29e47fc7c41dc91b": ("VOL-038", "57902e5c952132ee663ef279a254f9314cbddfaa365e036f2130ef79c5c1c2d1", "167ec7b43f1df3f0f8532d35f68854315c1c49ce85b5b5000f87e35bd65e3b13", "canonicalization mismatch"),
    "P1-RISK-VOL-038:risk:6c8763dbe7-1303cab6d17bd5b8": ("VOL-038", "62f1bde2568fc2b6625f43c7a7001e64078f537d07cad55ce070302f2913f0f6", "c06001d43484fac8f866b8f479b0688081473861119735e752dec4bd3b4f3be2", "missing lineage edge"),
    "P1-RISK-VOL-038:risk:7678e98834-42c2794c94e84d53": ("VOL-038", "9103e4ee964ea46f2350bb53cc043fdea012c9847490d688e461a99fbe2331c3", "2373c9f8f727245922e3c708a0910aafe5d54f6afd2547d2d4f518a16b52b8ad", "signature detached from semantic content"),
    "P1-RISK-VOL-056:risk:2022c8293c-22f89a3fd1f0e1c0": ("VOL-056", "c2670a3c9fadec306b8b8830205bf2a0756c468fba4e34e7085a9368cf0470d2", "6ac60c14f2053485bbaa46be4d2fed44702552bcfed823aea2b532fe9f0f70eb", "duplicate/conflicting records"),
    "P1-RISK-VOL-056:risk:33b74f9171-e831de5028cebb7b": ("VOL-056", "fe3dd58158f106298bbd731edcf4a81b01b1eab4101b959d0a4668cd7254a847", "e06f578f6308693b6286264ab7f5d98ad129df376d23b93227441bea12081af9", "orphan gaps"),
    "P1-RISK-VOL-056:risk:be5e15b86f-b936d9a800c95958": ("VOL-056", "9a9b31ef90e2746dcb1f5728de4cc366788a84af78e69cfaf491b8ebafeab6aa", "fba1380cfe51a316584d8ca77670790645d8c5e50d306f20480ffab8ed328e16", "status inflation"),
    "P1-RISK-VOL-057:risk:c99d0b6eef-d557975af885804d": ("VOL-057", "4a682fbbd1864a0dae0e7f8354f1ba433a8f376d878aa6cbf24f4cc1e0b69eed", "5ec43e571e18c2e4689a0712285d2e99ea366a68572db86057163aee4a5d1eae", "critical risk hidden by aggregate status"),
    "P1-RISK-VOL-057:risk:fa961d0ce2-d924d729e90b4dcf": ("VOL-057", "14c5f6823a25ddee760c7d9d2a8b237a9788a1a45ae3961e1bd3db07b5334bd1", "6ab1e5406561f97b27abeb2dab1f77ca9089af915469ed2930954b90cfe913fc", "paper control without evidence"),
    "P1-RISK-VOL-057:risk:a11b2c56e4-bee070e340b69ccf": ("VOL-057", "55df2639ad38f7cbd1ad835ea485e7d3f5e38ed5bc2ce0b6ec6c8b7842fa714f", "4f6ce32a492b3b3b00bafb1331146b80418fb1149b8fc316634714e578a4e471", "stale risk owner"),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _records() -> list[dict]:
    registry = _load(ROOT / REGISTRY)
    return [
        row for row in registry["records"]
        if row["evidence"][0]["category"] == "risk_control_evidence"
    ]


def test_batch1_contains_exact_high_severity_evidence_bindings() -> None:
    records = _records()
    assert len(records) == 12
    assert {row["obligation_id"] for row in records} == set(EXPECTED)

    for row in records:
        volume, obligation_digest, evidence_digest, _ = EXPECTED[row["obligation_id"]]
        assert row["owner_id"] == "ACC-" + volume
        assert row["obligation_digest"] == obligation_digest
        assert row["severity"] == "high"
        assert row["disposition"] == "evidence"
        assert row["bound_at"] == BOUND_AT
        assert row["review_at"] == REVIEW_AT
        assert row["accepted_risk"] is None
        assert row["evidence"] == [{
            "source": (
                "p1:risk-classification-evidence-batch1:"
                + row["obligation_id"]
                + ":"
                + VERIFIER_HEAD
            ),
            "digest": evidence_digest,
            "category": "risk_control_evidence",
        }]


def test_batch1_bindings_match_live_risk_obligations() -> None:
    obligations = {
        item.obligation_id: item
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
    }
    for row in _records():
        _, digest, _, statement = EXPECTED[row["obligation_id"]]
        obligation = obligations[row["obligation_id"]]
        assert obligation.kind.value == "risk"
        assert obligation.statement == statement
        assert obligation.obligation_digest == digest
        assert row["obligation_digest"] == digest


def test_batch1_verifier_identity_is_exact() -> None:
    assert VERIFIER_RUN_ID == 36751635100
    assert VERIFIER_JOB_ID == 110011467161
    assert len(VERIFIER_HEAD) == 40
    for row in _records():
        assert row["evidence"][0]["source"].endswith(":" + VERIFIER_HEAD)


def test_reconciliation_reduces_blocking_and_unclassified_together() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)
    assert report["binding_count"] == 496
    assert report["resolved_count"] == 496
    assert report["unresolved_blocking_count"] == 17
    assert report["unclassified_count"] == 0
    assert report["disposition_counts"] == {
        "evidence": 496,
        "unbound": 17,
    }


def test_source_risk_statements_remain_canonical() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}
    for _, (volume, _, _, statement) in EXPECTED.items():
        assert statement in by_key[volume]["risks"]
