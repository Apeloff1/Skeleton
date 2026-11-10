import hashlib

import pytest

from skeleton.ai.build.build_farm import BuildFarmArtifact
from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.farm_bridge import entry_from_reproducible, witness_metadata
from skeleton.build.delivery.remote_bridge import entries_from_receipts
from skeleton.build.remote_build import RemoteArtifactRef, VerifiedRemoteReceipt

D = hashlib.sha256(b"out").hexdigest()


def _receipt(status="success", artifact="dist/skel.whl", digest=D):
    return VerifiedRemoteReceipt("job1", "runner1", status, (RemoteArtifactRef(artifact, digest, 3),), "0" * 64, "1" * 64)


def test_remote_receipts_to_entries():
    entries = entries_from_receipts([_receipt(), _receipt()])
    assert len(entries) == 1 and entries[0].kind == "wheel" and entries[0].sha256 == D
    mapped = entries_from_receipts([_receipt()], paths={"dist/skel.whl": "release/skel.whl"})
    assert mapped[0].path == "release/skel.whl"


def test_remote_receipt_rejections():
    with pytest.raises(DeliveryError):
        entries_from_receipts([_receipt(status="failure")])
    with pytest.raises(DeliveryError, match="conflicting"):
        entries_from_receipts([_receipt(), _receipt(digest="2" * 64)])
    with pytest.raises(DeliveryError):
        entries_from_receipts([object()])


def _farm(worker, digest=D, job="j"):
    return BuildFarmArtifact(job, worker, "e" * 64, digest, f"ev-{worker}")


def test_farm_reproducible_entry():
    entry = entry_from_reproducible([_farm("w1"), _farm("w2")], path="skel.whl", kind="wheel", size=3)
    assert entry.sha256 == D
    meta = witness_metadata([_farm("w2"), _farm("w1")])
    assert meta["farm.workers"] == "w1,w2"


@pytest.mark.parametrize(
    "items",
    [
        [_farm("w1")],
        [_farm("w1"), _farm("w1")],
        [_farm("w1"), _farm("w2", digest="3" * 64)],
        [_farm("w1"), _farm("w2", job="other")],
    ],
)
def test_farm_rejections(items):
    with pytest.raises(DeliveryError):
        entry_from_reproducible(items, path="a", kind="wheel", size=1)


def test_remote_receipt_stream_and_artifact_budgets_fail_closed(monkeypatch):
    """An infinite or duplicate-heavy verified stream must never allocate forever."""
    from itertools import repeat
    from skeleton.build.delivery import remote_bridge

    monkeypatch.setattr(remote_bridge, "MAX_REMOTE_RECEIPTS", 2)
    with pytest.raises(DeliveryError, match="receipt count exceeds bound"):
        remote_bridge.entries_from_receipts(repeat(_receipt()))

    monkeypatch.setattr(remote_bridge, "MAX_REMOTE_RECEIPTS", 10)
    monkeypatch.setattr(remote_bridge, "MAX_REMOTE_ARTIFACTS", 1)
    with pytest.raises(DeliveryError, match="artifact count exceeds bound"):
        remote_bridge.entries_from_receipts([_receipt(), _receipt()])

    monkeypatch.setattr(remote_bridge, "MAX_REMOTE_ARTIFACTS", 2)
    assert len(remote_bridge.entries_from_receipts([_receipt(), _receipt()])) == 1

def test_remote_bridge_rejects_conflicting_receipts_and_unbounded_evidence():
    from dataclasses import replace
    from itertools import repeat
    from skeleton.build.delivery.remote_bridge import MAX_REMOTE_RECEIPTS

    original = _receipt()
    with pytest.raises(DeliveryError, match="conflicting remote receipts"):
        entries_from_receipts([original, replace(original, runner_id="other")])
    with pytest.raises(DeliveryError, match="remote receipt count exceeds"):
        entries_from_receipts(repeat(original, MAX_REMOTE_RECEIPTS + 1))
    with pytest.raises(DeliveryError, match="remote receipt digest"):
        entries_from_receipts([replace(original, receipt_digest="bad")])
    with pytest.raises(DeliveryError, match="artifact reference"):
        entries_from_receipts([replace(original, output_artifacts=(object(),))])


def test_remote_bridge_rejects_distinct_sources_mapped_to_one_release_path():
    from dataclasses import replace
    from skeleton.ai.build.core.delivery import remote_bridge as mirrored

    first = _receipt(artifact="dist/first.whl")
    second = replace(
        _receipt(artifact="dist/second.whl"), job_id="job2", runner_id="runner2"
    )
    aliases = {"dist/first.whl": "release/shared.whl",
               "dist/second.whl": "release/shared.whl"}
    for convert in (entries_from_receipts, mirrored.entries_from_receipts):
        with pytest.raises(DeliveryError, match="alias collision"):
            convert([first, second], paths=aliases)
        assert len(convert([first, first])) == 1


def test_farm_requires_distinct_attestation_evidence():
    from dataclasses import replace

    good = [_farm("w1"), _farm("w2")]
    forged = [good[0], replace(good[1], attestation_evidence=good[0].attestation_evidence)]
    for bad in (forged,
                [good[0], replace(good[1], attestation_evidence="")],
                [good[0], replace(good[1], environment_digest="invalid")],
                [good[0], replace(good[1], output_digest="invalid")]):
        with pytest.raises(DeliveryError, match="attestation evidence"):
            entry_from_reproducible(bad, path="artifact.whl", kind="wheel", size=3)
        with pytest.raises(DeliveryError):
            witness_metadata(bad)
    with pytest.raises(DeliveryError):
        witness_metadata([])


def test_farm_bridge_rejects_ambiguous_identity_and_oversized_manifest_metadata():
    from dataclasses import replace
    from skeleton.ai.build.core.delivery import farm_bridge as mirrored

    good = [_farm("w1"), _farm("w2")]
    for module in (None, mirrored):
        entry = entry_from_reproducible if module is None else module.entry_from_reproducible
        metadata = witness_metadata if module is None else module.witness_metadata
        for bad in (
            [good[0], replace(good[1], worker_id="w2,forged")],
            [good[0], replace(good[1], attestation_evidence="ev\nforged")],
        ):
            with pytest.raises(DeliveryError):
                entry(bad, path="artifact.whl", kind="wheel", size=3)
        long_witnesses = [
            replace(_farm(f"w{i}"), attestation_evidence="ev-" + str(i) + "x" * 100)
            for i in range(8)
        ]
        with pytest.raises(DeliveryError, match="metadata exceeds manifest bound"):
            metadata(long_witnesses)
