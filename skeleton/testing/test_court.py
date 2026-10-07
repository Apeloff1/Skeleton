"""Tests for skeleton.kernel.court (gameforge-rs quorum::Court port).

Covers attest threshold 2f+1, value_hash, and suspects — the Lana-locked
Quorum Court slice. Does not exercise court_attest (ed25519 envelopes).
"""

from __future__ import annotations

import hashlib
import json
import threading

from skeleton.kernel.court import Court, Verdict, value_hash


def test_quorum_size_is_two_f_plus_one():
    assert Court("c0", 0).quorum_size() == 1
    assert Court("c1", 1).quorum_size() == 3
    assert Court("c2", 2).quorum_size() == 5
    assert Court("c3", 3).quorum_size() == 7
    assert Court("c1", 1).electorate() == 4
    assert Court("c2", 2).electorate() == 7


def test_value_hash_is_sha256_of_canonical_json():
    payload = {"b": 2, "a": 1}
    expected = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    assert value_hash(payload) == expected
    assert Court.value_hash(payload) == expected
    # Insertion order must not change the hash.
    assert value_hash({"a": 1, "b": 2}) == value_hash({"b": 2, "a": 1})
    # Distinct values diverge.
    assert value_hash({"a": 1}) != value_hash({"a": 2})
    assert value_hash("x") != value_hash("y")
    assert len(value_hash(None)) == 64


def test_attest_decides_at_two_f_plus_one_matching():
    court = Court("high-court", f=1)  # quorum 3
    v = {"op": "mint", "amount": 10}
    assert court.attest("p1", "a1", v) is Verdict.PENDING
    assert court.attest("p1", "a2", v) is Verdict.PENDING
    assert court.attest("p1", "a3", v) is Verdict.DECIDED
    # Lane cleared after decide.
    assert court.pending_attestations("p1") == []
    assert court.suspects() == {}


def test_one_voice_per_attester_ignored_as_pending():
    court = Court("high-court", f=1)
    v = {"x": 1}
    assert court.attest("p2", "alice", v) is Verdict.PENDING
    # Same attester again — ignored, still pending (only 1 unique voice).
    assert court.attest("p2", "alice", v) is Verdict.PENDING
    assert court.attest("p2", "bob", v) is Verdict.PENDING
    assert court.attest("p2", "carol", v) is Verdict.DECIDED


def test_suspects_recorded_for_divergent_attesters():
    court = Court("high-court", f=1)  # quorum 3
    good = {"choice": "alpha"}
    bad = {"choice": "omega"}
    assert court.attest("p3", "loyal-1", good) is Verdict.PENDING
    assert court.attest("p3", "traitor", bad) is Verdict.PENDING
    assert court.attest("p3", "loyal-2", good) is Verdict.PENDING
    # Third matching good vote decides; traitor marked suspect.
    assert court.attest("p3", "loyal-3", good) is Verdict.DECIDED
    suspects = court.suspects()
    assert suspects.get("traitor") == 1
    assert "loyal-1" not in suspects
    assert "loyal-2" not in suspects
    assert "loyal-3" not in suspects


def test_suspects_accumulate_across_proposals():
    court = Court("high-court", f=0)  # quorum 1 — first matching voice decides
    assert court.attest("q1", "good", {"n": 1}) is Verdict.DECIDED
    # On a fresh proposal, a lone divergent voice still decides (f=0),
    # and does not self-suspect (they *are* the winning hash).
    assert court.attest("q2", "solo", {"n": 2}) is Verdict.DECIDED
    assert court.suspects() == {}

    court2 = Court("high-court", f=1)
    good = {"v": "yes"}
    bad = {"v": "no"}
    court2.attest("r1", "a", good)
    court2.attest("r1", "evil", bad)
    court2.attest("r1", "b", good)
    assert court2.attest("r1", "c", good) is Verdict.DECIDED
    court2.attest("r2", "a", good)
    court2.attest("r2", "evil", bad)
    court2.attest("r2", "b", good)
    assert court2.attest("r2", "c", good) is Verdict.DECIDED
    assert court2.suspects()["evil"] == 2


def test_deadlocked_when_remaining_cannot_reach_quorum():
    # f=1 → quorum 3, electorate 4. Two vs two on distinct hashes → deadlock.
    court = Court("high-court", f=1)
    assert court.attest("d1", "a1", {"side": "A"}) is Verdict.PENDING
    assert court.attest("d1", "a2", {"side": "A"}) is Verdict.PENDING
    assert court.attest("d1", "b1", {"side": "B"}) is Verdict.PENDING
    # After 4 casts: max bucket 2, remaining 0 → both sides < 3 → Deadlocked.
    assert court.attest("d1", "b2", {"side": "B"}) is Verdict.DEADLOCKED
    assert court.pending_attestations("d1") == []
    # No winner → no suspects from this proposal.
    assert court.suspects() == {}


def test_f0_single_attest_decides():
    court = Court("solo", f=0)
    assert court.quorum_size() == 1
    assert court.attest("p", "only", {"ok": True}) is Verdict.DECIDED


def test_snapshot_and_thread_safety_smoke():
    court = Court("high-court", f=1)
    v = {"k": "v"}
    errors: list[BaseException] = []

    def cast(attester: str) -> None:
        try:
            court.attest("t1", attester, v)
        except BaseException as exc:  # noqa: BLE001 — collect for assert
            errors.append(exc)

    threads = [threading.Thread(target=cast, args=(f"n{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    snap = court.snapshot()
    assert snap["name"] == "high-court"
    assert snap["f"] == 1
    assert snap["quorum_size"] == 3
    assert snap["electorate"] == 4
    # Exactly one decide should have cleared the lane.
    assert snap["open_proposals"] == []
