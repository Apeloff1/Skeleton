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
VERIFIER_HEAD = "82cc895b21128a24c19e7214e15e1c8823267c25"
VERIFIER_RUN_ID = 36732696801
VERIFIER_JOB_ID = 109946225507
BOUND_AT = "2026-09-30T14:55:18Z"
REVIEW_AT = "2026-10-30T14:55:18Z"
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

EXPECTED = {
    "P1-GAP-VOL-056:gap:97327e13f0-fb312c2b30523b6c": {
        "volume": "VOL-056",
        "obligation_digest": "a6b370c58f7bdfbd989c42b7b897582401b166ad0f05a0defbf3322c5ac32ffc",
        "evidence_digest": "d56ab11b824c797bd53dba7eff78d4d271def632f3a2bf21ef86aa9a8220c93f",
        "statement": "bind CI to unresolved blocking gaps",
    },
    "P1-GAP-VOL-056:gap:b8d1c37349-27b01a16de3b9f60": {
        "volume": "VOL-056",
        "obligation_digest": "e830c65cd7963a11acbd5c4420e42da5060b9989eead4dbce2a14c8692fc8f85",
        "evidence_digest": "20ab6e81bf5ffb58d2d0be96ba09c4abbf329004a8abba121849aa43475c0c3c",
        "statement": "establish canonical gap schema",
    },
    "P1-GAP-VOL-057:gap:19c223f2c1-5031e0af7967855e": {
        "volume": "VOL-057",
        "obligation_digest": "c192477cc1fa1020ccf53b0b8718bc07b9cd53d2b6fbe838670d260c23486257",
        "evidence_digest": "0459d5d345ee360108f782ee58612bc5d438dee677fb254ac6bac2b045d7f799",
        "statement": "bind risks to work/evidence graph",
    },
    "P1-GAP-VOL-057:gap:a471b17add-04fc6e13a9b6e800": {
        "volume": "VOL-057",
        "obligation_digest": "1d229363322f22b577cd1f26c79358e968d66db1cdac2faaf1dd6bf2a3a5f9d9",
        "evidence_digest": "c1be4f1cd9adc335e5e17dd415736ef86199c84f2a34e673859b377ad7c3345a",
        "statement": "materialize expiry/review cadence",
    },
    "P1-GAP-VOL-059:gap:67f06b252b-eba88e26ef6db7f2": {
        "volume": "VOL-059",
        "obligation_digest": "0d7c0f532252daf01a3a182b25b359baa48acdc2bbda5cbe347d353d05d4f069",
        "evidence_digest": "ad311045397e0986aa470f03b5f8ea9c2721e3654f4f90e268bfe78a7d59c4ad",
        "statement": "add cancellation/skip fail-closed tests",
    },
    "P1-GAP-VOL-059:gap:c8f3cbba24-b73a3187a7f12551": {
        "volume": "VOL-059",
        "obligation_digest": "b12085bcb05d330f6beafe9f4046471423b9bb59fa590a896d50368f8ce84692",
        "evidence_digest": "4a64f001a9c5682d32c7289ae26ae213dec7e5fd82a3cee95660d9771330aa78",
        "statement": "define required-gate authority map",
    },
    "P1-GAP-VOL-078:gap:1f030c0062-4a165a6a9cac222b": {
        "volume": "VOL-078",
        "obligation_digest": "8ede90b113fc6ae19fe46dee74923fd6754411600612f74e31c6e6123e165c0b",
        "evidence_digest": "1949781642ac48a3433d790c7e2035f99e4e13b8f382de406c4fe889742e21af",
        "statement": "bind qualifying evidence to replay verification",
    },
    "P1-GAP-VOL-078:gap:99ba84e80f-f47580882f19d78c": {
        "volume": "VOL-078",
        "obligation_digest": "e3dfce9b5fd24fe10b610c3753b0981479c2aaecf77efff3d492f439b62c01ea",
        "evidence_digest": "db36c8cae4695e4f0c14c3608fc7acf59f110ee0307795d3f01cb6eebf174783",
        "statement": "define replay bundle format",
    },
    "P1-GAP-VOL-420:gap:7777365012-f77a419f1e16f459": {
        "volume": "VOL-420",
        "obligation_digest": "ab18836c32c33aa3efee8113e75bf697cc30359f73fc4cb778294377ec3456d7",
        "evidence_digest": "4a867785fcd4793872f571190357a7c27e946241f4e13e29a81a81670466c847",
        "statement": "enforce freeze in validator",
    },
    "P1-GAP-VOL-420:gap:380b4042e4-aec1dd0a17dab20a": {
        "volume": "VOL-420",
        "obligation_digest": "d01194836eba7ae4e8327bd8878699ab72bf0c666c629fee4649b9a1bd8e13c8",
        "evidence_digest": "4de862b9783d4e331547673381f6b9527f2cd57d535d1d853eee2af29640e025",
        "statement": "maintain ADR exception workflow",
    },
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _batch2_records() -> list[dict]:
    registry = _load(ROOT / REGISTRY)
    return [
        row
        for row in registry["records"]
        if row["evidence"][0]["category"] == "control_plane_gap_closure"
    ]


def test_batch2_registry_contains_exact_verified_control_plane_bindings() -> None:
    records = _batch2_records()

    assert len(records) == 10
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
                "p1:control-plane-gap-batch2:"
                + row["obligation_id"]
                + ":"
                + VERIFIER_HEAD
            ),
            "digest": expected["evidence_digest"],
            "category": "control_plane_gap_closure",
        }


def test_batch2_bindings_match_live_canonical_gap_obligations() -> None:
    obligations = {
        item.obligation_id: item
        for item in derive_obligations(
            _load(ROOT / MASTER),
            _load(ROOT / P1_MAP),
            _load(ROOT / ADVERSARIAL),
            _load(ROOT / POLICY),
        )
    }

    for row in _batch2_records():
        expected = EXPECTED[row["obligation_id"]]
        obligation = obligations[row["obligation_id"]]
        assert obligation.statement == expected["statement"]
        assert obligation.obligation_digest == expected["obligation_digest"]
        assert row["obligation_digest"] == obligation.obligation_digest
        assert obligation.kind.value == "gap"
        assert obligation.default_severity.value == "high"
        assert obligation.blocking_by_default is True


def test_batch2_verifier_identity_is_exact_and_auditable() -> None:
    assert len(VERIFIER_HEAD) == 40
    assert VERIFIER_RUN_ID == 36732696801
    assert VERIFIER_JOB_ID == 109946225507

    for row in _batch2_records():
        source = row["evidence"][0]["source"]
        assert source.endswith(":" + VERIFIER_HEAD)
        assert row["obligation_id"] in source


def test_combined_risk_reconciliation_resolves_twenty_two_obligations() -> None:
    report = reconcile_repository(ROOT, evaluated_at=NOW)

    assert report["inventory"] == {
        "p1_primary_volume_count": 107,
        "volume_risk_count": 281,
        "volume_gap_count": 208,
        "applicable_adversarial_axis_count": 24,
        "total_obligation_count": 513,
    }
    assert report["binding_count"] == 22
    assert report["resolved_count"] == 22
    assert report["unresolved_blocking_count"] == 491
    assert report["unclassified_count"] == 281
    assert report["disposition_counts"] == {
        "evidence": 22,
        "unbound": 491,
    }


def test_batch2_does_not_delete_canonical_masterplan_gaps() -> None:
    master = _load(ROOT / MASTER)
    by_key = {row["key"]: row for row in master["volumes"]}

    expected = {
        "VOL-056": {
            "establish canonical gap schema",
            "bind CI to unresolved blocking gaps",
        },
        "VOL-057": {
            "bind risks to work/evidence graph",
            "materialize expiry/review cadence",
        },
        "VOL-059": {
            "define required-gate authority map",
            "add cancellation/skip fail-closed tests",
        },
        "VOL-078": {
            "define replay bundle format",
            "bind qualifying evidence to replay verification",
        },
        "VOL-420": {
            "enforce freeze in validator",
            "maintain ADR exception workflow",
        },
    }
    for key, statements in expected.items():
        assert statements <= set(by_key[key]["gaps"])
