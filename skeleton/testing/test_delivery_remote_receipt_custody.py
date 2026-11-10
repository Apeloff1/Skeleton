"""Adversarial remote receipt reconciliation, without altering farm bridge tests."""
from __future__ import annotations

from dataclasses import replace
from itertools import repeat

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.remote_build import RemoteArtifactRef, VerifiedRemoteReceipt
from skeleton.build.delivery import remote_bridge as canonical
from skeleton.ai.build.core.delivery import remote_bridge as mirrored

SHA = "a" * 64


def receipt(*, job="job1", runner="runner1", artifact="dist/first.whl"):
    return VerifiedRemoteReceipt(
        job, runner, "success", (RemoteArtifactRef(artifact, SHA, 3),),
        "0" * 64, "1" * 64,
    )


@pytest.mark.parametrize("convert", [canonical.entries_from_receipts, mirrored.entries_from_receipts])
def test_exact_duplicate_receipt_is_idempotent(convert):
    first = receipt()
    result = convert([first, first])
    assert len(result) == 1 and result[0].path == "dist/first.whl"


@pytest.mark.parametrize("convert", [canonical.entries_from_receipts, mirrored.entries_from_receipts])
def test_same_job_must_have_one_receipt_identity(convert):
    first = receipt()
    forged = replace(first, runner_id="runner2")
    with pytest.raises(DeliveryError, match="conflicting remote receipts"):
        convert([first, forged])


@pytest.mark.parametrize("convert", [canonical.entries_from_receipts, mirrored.entries_from_receipts])
def test_different_source_ids_cannot_alias_one_release_path(convert):
    first = receipt()
    second = receipt(job="job2", runner="runner2", artifact="dist/second.whl")
    mapping = {
        "dist/first.whl": "release/collision.whl",
        "dist/second.whl": "release/collision.whl",
    }
    with pytest.raises(DeliveryError, match="alias collision"):
        convert([first, second], paths=mapping)


@pytest.mark.parametrize("convert", [canonical.entries_from_receipts, mirrored.entries_from_receipts])
def test_bogus_receipt_digests_and_ref_type_are_denied(convert):
    good = receipt()
    with pytest.raises(DeliveryError, match="remote receipt digest"):
        convert([replace(good, receipt_digest="not-a-digest")])
    with pytest.raises(DeliveryError, match="remote artifact reference"):
        convert([replace(good, output_artifacts=(object(),))])
    with pytest.raises(DeliveryError, match="remote output inventory"):
        convert([replace(good, output_artifacts=None)])


@pytest.mark.parametrize("module", [canonical, mirrored])
def test_unbounded_receipt_generator_and_outputs_fail_closed(module, monkeypatch):
    original = receipt()
    monkeypatch.setattr(module, "MAX_REMOTE_RECEIPTS", 3)
    monkeypatch.setattr(module, "MAX_REMOTE_OUTPUTS", 10)
    with pytest.raises(DeliveryError, match="remote receipt count exceeds bound"):
        module.entries_from_receipts(repeat(original))
    monkeypatch.setattr(module, "MAX_REMOTE_RECEIPTS", 10)
    monkeypatch.setattr(module, "MAX_REMOTE_OUTPUTS", 1)
    with pytest.raises(DeliveryError, match="remote output inventory exceeds bound"):
        module.entries_from_receipts([original, original])


@pytest.mark.parametrize("convert", [canonical.entries_from_receipts, mirrored.entries_from_receipts])
def test_invalid_mapping_type_fails_as_domain_error(convert):
    with pytest.raises(DeliveryError, match="path remapping"):
        convert([receipt()], paths=[("dist/first.whl", "release/first.whl")])


def test_all_prior_farm_attestation_contracts_remain_in_primary_suite():
    from pathlib import Path
    existing = (Path(__file__).resolve().parent / "test_delivery_bridges.py").read_text("utf-8")
    assert "test_farm_requires_distinct_attestation_evidence" in existing
    assert "test_farm_bridge_rejects_ambiguous_identity_and_oversized_manifest_metadata" in existing
