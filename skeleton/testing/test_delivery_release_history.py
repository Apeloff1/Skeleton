import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.release_history import GENESIS, ReleaseHistory

M1, M2, C = "1" * 64, "2" * 64, "c" * 64


def _history():
    h = ReleaseHistory("production")
    h.record(release_id="r1", manifest_digest=M1, config_digest=C, outcome="deployed", recorded_at=10)
    h.record(release_id="r2", manifest_digest=M2, config_digest=C, outcome="deployed", recorded_at=20)
    return h


def test_chain_and_roundtrip():
    h = _history()
    assert h.records[0].previous == GENESIS
    assert h.records[1].previous == h.records[0].digest
    clone = ReleaseHistory.from_list("production", h.to_list())
    assert clone.head == h.head


def test_tamper_detected():
    items = _history().to_list()
    items[0]["release_id"] = "evil"
    with pytest.raises(DeliveryError):
        ReleaseHistory.from_list("production", items)


def test_current_and_last_known_good():
    h = _history()
    h.record(release_id="r3", manifest_digest=M1, config_digest=C, outcome="failed", recorded_at=30)
    assert h.current().release_id == "r2"
    assert h.last_known_good(exclude_release="r2").release_id == "r1"


def test_rejects_bad_records():
    h = _history()
    with pytest.raises(DeliveryError):
        h.record(release_id="r", manifest_digest=M1, config_digest=C, outcome="weird", recorded_at=40)
    with pytest.raises(DeliveryError):
        h.record(release_id="r", manifest_digest=M1, config_digest=C, outcome="deployed", recorded_at=5)
    with pytest.raises(DeliveryError):
        ReleaseHistory("Bad Name")

def test_rehydration_rejects_semantically_invalid_but_rehashed_records():
    from skeleton.build.delivery._util import sha256_json

    baseline = _history().to_list()
    for field, value in (
        ("recorded_at", -1), ("outcome", "trusted"),
        ("manifest_digest", "not-a-digest"), ("release_id", "../escape"),
        ("sequence", True), ("config_digest", None),
    ):
        record = dict(baseline[0])
        record[field] = value
        record["digest"] = sha256_json({k: v for k, v in record.items() if k != "digest"})
        with pytest.raises(DeliveryError):
            ReleaseHistory.from_list("production", [record])
    with pytest.raises(DeliveryError, match="missing required"):
        ReleaseHistory.from_list("production", [{"sequence": 0}])


def test_release_history_import_is_bounded_before_materializing():
    from itertools import repeat
    from skeleton.build.delivery.release_history import MAX_RELEASE_RECORDS

    from skeleton.build.delivery import release_history as module
    original = module.MAX_RELEASE_RECORDS
    module.MAX_RELEASE_RECORDS = 1
    try:
        history = ReleaseHistory("production")
        history.record(release_id="r1", manifest_digest=M1, config_digest=C,
                       outcome="deployed", recorded_at=10)
        with pytest.raises(DeliveryError, match="record count exceeds"):
            history.record(release_id="r2", manifest_digest=M2, config_digest=C,
                           outcome="deployed", recorded_at=20)
    finally:
        module.MAX_RELEASE_RECORDS = original
