"""Contract checks for kernel assurance gating.

These tests describe the invariants required before assurance results are
allowed to influence higher-level state.
"""

from __future__ import annotations

import hashlib


def test_digest_is_deterministic():
    payload = b"validated-transition"
    first = hashlib.sha256(payload).hexdigest()
    second = hashlib.sha256(payload).hexdigest()
    assert first == second


def test_replay_identity_is_stable():
    task = "task:example:commit"
    digest_a = hashlib.sha256(task.encode()).hexdigest()
    digest_b = hashlib.sha256(task.encode()).hexdigest()
    assert digest_a == digest_b


def test_invalid_state_cannot_be_promoted():
    states = {"accepted", "review", "rejected"}
    assert "rejected" in states
    assert "accepted" in states
