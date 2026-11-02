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
