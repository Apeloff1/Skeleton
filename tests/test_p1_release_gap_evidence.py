from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_p1_release_gap_evidence.py"
REGISTRY = ROOT / "machine/p1_risk_evidence_bindings.json"
MASTER = ROOT / "machine/ai_master_plan.json"
HEAD = "a" * 40

EXPECTED = {
    ("VOL-047", "bind installer to release provenance"),
    ("VOL-047", "materialize interruption checkpoints"),
    ("VOL-048", "define update compatibility graph"),
    ("VOL-048", "bind migrations to restore/rollback proof"),
    ("VOL-050", "define ownership manifest from installer receipts"),
    ("VOL-050", "materialize residual scanner"),
    ("VOL-060", "define release evidence bundle schema"),
    ("VOL-060", "bind installer/updater artifacts to release digest"),
    ("VOL-064", "define backup coverage manifest"),
    ("VOL-065", "materialize full DR evidence bundle"),
    ("VOL-066", "bind postmortem actions into gap/risk ledgers"),
    ("VOL-409", "generate release notices"),
}


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_p1_release_gap_evidence",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_gap_batch_has_exact_bounded_scope() -> None:
    module = _module()
    report = module.build_release_gap_evidence(
        ROOT,
        expected_head=HEAD,
    )

    assert report["covered_gap_count"] == 12
    assert report["covered_volume_count"] == 8
    assert report["already_bound_count"] == 12
    assert report["candidate_binding_count"] == 0
    assert report["category"] == "release_gap_closure"

    covered = {
        (row["volume_key"], row["statement"])
        for row in report["records"]
    }
    assert covered == EXPECTED


def test_release_gap_batch_is_exact_head_and_digest_bound() -> None:
    module = _module()
    report = module.build_release_gap_evidence(
        ROOT,
        expected_head=HEAD,
    )

    assert report["expected_head"] == HEAD
    assert len(report["report_digest"]) == 64

    obligation_ids = []
    for row in report["records"]:
        obligation_ids.append(row["obligation_id"])
        assert row["expected_head"] == HEAD
        assert len(row["obligation_digest"]) == 64
        assert len(row["packet_digest"]) == 64
        assert row["source_ref"].startswith(row["volume_key"] + ":gap:")
        assert row["source_digests"]
        assert row["test_digests"]
        assert row["verified_contract_markers"]
        assert all(len(value) == 64 for value in row["source_digests"].values())
        assert all(len(value) == 64 for value in row["test_digests"].values())

        evidence = row["candidate_evidence_ref"]
        assert evidence["category"] == "release_gap_closure"
        assert evidence["digest"] == row["packet_digest"]
        assert row["obligation_id"] in evidence["source"]
        assert HEAD in evidence["source"]

    assert len(obligation_ids) == len(set(obligation_ids)) == 12


def test_release_gap_batch_never_self_binds_or_clears_gaps() -> None:
    module = _module()
    report = module.build_release_gap_evidence(
        ROOT,
        expected_head=HEAD,
    )

    assert report["non_authoritative"] is True
    assert report["creates_bindings"] is False
    assert report["clears_masterplan_gaps"] is False
    for row in report["records"]:
        assert row["binding_present"] is True
        assert row["non_authoritative"] is True
        assert row["creates_binding"] is False
        assert row["clears_masterplan_gap"] is False


def test_release_gap_batch_does_not_mutate_canonical_sources() -> None:
    module = _module()
    registry_before = REGISTRY.read_bytes()
    master_before = MASTER.read_bytes()

    first = module.build_release_gap_evidence(ROOT, expected_head=HEAD)
    second = module.build_release_gap_evidence(ROOT, expected_head=HEAD)

    assert first == second
    assert REGISTRY.read_bytes() == registry_before
    assert MASTER.read_bytes() == master_before


@pytest.mark.parametrize(
    "head",
    [
        "",
        "abc",
        "A" * 40,
        "g" * 40,
        "a" * 39,
        "a" * 41,
    ],
)
def test_release_gap_batch_rejects_noncanonical_heads(head: str) -> None:
    module = _module()

    with pytest.raises(module.ReleaseGapEvidenceError):
        module.build_release_gap_evidence(ROOT, expected_head=head)
