from datetime import UTC, datetime
import hashlib
import json

from core.transparency_witness import TransparencyWitnessLedger, TrustedWitness


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def test_stale_and_future_witness_receipts_do_not_satisfy_quorum(tmp_path):
    witnesses = (TrustedWitness("w-a", "lab-a"), TrustedWitness("w-b", "lab-b"))
    ledger = TransparencyWitnessLedger(tmp_path, trusted_witnesses=witnesses, required_groups=2, max_age_seconds=30)
    root = "a" * 64
    ledger.observe(log_id="epistemic", tree_size=4, root_sha256=root, witness_id="w-a",
                   transport_authenticated=True, observed_at="2026-09-14T16:00:00+00:00")
    ledger.observe(log_id="epistemic", tree_size=4, root_sha256=root, witness_id="w-b",
                   transport_authenticated=True, observed_at="2026-09-14T16:01:10+00:00")
    quorum = ledger.quorum(log_id="epistemic", tree_size=4, root_sha256=root,
                           now=datetime(2026, 9, 14, 16, 1, 0, tzinfo=UTC))
    assert quorum.trusted_receipts == 2
    assert quorum.fresh_receipts == 0
    assert quorum.stale_receipts == 2
    assert quorum.independent_groups == 0
    assert quorum.reached is False


def test_fresh_same_domain_witnesses_count_once(tmp_path):
    witnesses = (
        TrustedWitness("w-a1", "lab-a"), TrustedWitness("w-a2", "lab-a"), TrustedWitness("w-b", "lab-b"),
    )
    ledger = TransparencyWitnessLedger(tmp_path, trusted_witnesses=witnesses, required_groups=2, max_age_seconds=120)
    root = "b" * 64; stamp = "2026-09-14T16:00:30+00:00"
    for witness_id in ("w-a1", "w-a2", "w-b"):
        ledger.observe(log_id="epistemic", tree_size=5, root_sha256=root, witness_id=witness_id,
                       transport_authenticated=True, observed_at=stamp)
    quorum = ledger.quorum(log_id="epistemic", tree_size=5, root_sha256=root,
                           now=datetime(2026, 9, 14, 16, 1, 0, tzinfo=UTC))
    assert quorum.fresh_receipts == 3
    assert quorum.independent_groups == 2
    assert quorum.groups == ("lab-a", "lab-b")
    assert quorum.reached is True


def test_v1_ledger_remains_verifiable_and_accepts_v2_receipts(tmp_path):
    path = tmp_path / "transparency-witnesses.json"
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1, "log_id": "epistemic", "tree_size": 7, "root_sha256": "c" * 64,
        "witness_id": "w-a", "independence_group": "lab-a",
        "observed_at": "2026-09-14T16:00:00+00:00", "transport_authenticated": True,
    }
    receipt = {**payload, "receipt_sha256": _sha(payload)}
    receipts = [receipt]; incidents = []
    env = {"version": 1, "receipts": receipts, "incidents": incidents}
    env["sha256"] = _sha(env)
    path.write_bytes(_canonical(env))

    ledger = TransparencyWitnessLedger(
        tmp_path,
        trusted_witnesses=(TrustedWitness("w-a", "lab-a"), TrustedWitness("w-b", "lab-b")),
        required_groups=2, max_age_seconds=3600,
    )
    assert ledger.status()["historical_receipt_versions"] == [1]
    ledger.observe(log_id="epistemic", tree_size=7, root_sha256="c" * 64, witness_id="w-b",
                   transport_authenticated=True, observed_at="2026-09-14T16:00:10+00:00")
    assert ledger.status()["historical_receipt_versions"] == [1, 2]
    quorum = ledger.quorum(log_id="epistemic", tree_size=7, root_sha256="c" * 64,
                           now=datetime(2026, 9, 14, 16, 0, 20, tzinfo=UTC))
    assert quorum.reached is True
    assert quorum.independent_groups == 2
