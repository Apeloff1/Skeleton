from skeleton.agents.swarm_fairness import FairShareLedger
from skeleton.agents.swarm_quota import Quota, QuotaLedger


def test_quota_config_snapshot_is_detached_from_ledger() -> None:
    ledger = QuotaLedger()
    ledger.configure("gold", Quota(max_queued=7, max_leased=3, max_payload_bytes=700))

    snapshot = ledger.configured_limits()
    snapshot["gold"] = Quota(max_queued=1, max_leased=1, max_payload_bytes=1)
    snapshot["new"] = Quota()

    assert ledger.limit("gold") == Quota(max_queued=7, max_leased=3, max_payload_bytes=700)
    assert "new" not in ledger.configured_limits()


def test_fairness_weight_snapshot_is_detached_from_ledger() -> None:
    ledger = FairShareLedger(default_weight=2)
    ledger.configure("gold", weight=5)
    ledger.admit("gold")

    snapshot = ledger.configured_weights()
    snapshot["gold"] = 99
    snapshot["new"] = 3

    assert ledger.configured_weights() == {"gold": 5}
    assert ledger.snapshot()["gold"]["inflight"] == 1


def test_public_weight_validator_is_non_mutating() -> None:
    ledger = FairShareLedger()
    assert ledger.validate_weight(7) == 7
    assert ledger.snapshot() == {}
