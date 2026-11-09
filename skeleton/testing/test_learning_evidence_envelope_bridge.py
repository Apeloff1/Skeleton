"""Cross-contract Jeeves read-only evidence -> learning-store custody tests."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.learning import (
    LearningEvidenceError,
    LearningEvidenceStore,
    Observation,
    canonical_fingerprint,
    make_provenance,
    make_provenance_from_evidence_envelope,
)


def _envelope(payload, *, observed_at=1050.0, retrieved_at=1000.0):
    wire = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "source_id": "fixture.learning",
        "observed_at": observed_at,
        "retrieved_at": retrieved_at,
        "revision": "r7",
        "sha256": hashlib.sha256(wire.encode("utf-8")).hexdigest(),
    }


def test_distinct_wire_sha_and_learning_fingerprint_round_trip():
    data = {"label": "café", "score": 1}
    provenance = make_provenance_from_evidence_envelope(data, _envelope(data))
    assert provenance.source_id == "fixture.learning"
    assert provenance.source_digest == _envelope(data)["sha256"]
    assert provenance.fingerprint == canonical_fingerprint(data)
    assert provenance.source_digest != provenance.fingerprint
    assert provenance.revision == "r7"
    assert provenance.retrieved_at == 1000.0
    store = LearningEvidenceStore(
        clock=lambda: 1000.0,
        max_age_seconds=60.0,
        future_skew_seconds=60.0,
    )
    store.record_observation(
        Observation("obs-core", "skill-unicode", data, provenance)
    )
    assert store.observations()[0].provenance.source_digest == provenance.source_digest


def test_changed_payload_rejected_before_store_admission():
    original = {"score": 1}
    with pytest.raises(LearningEvidenceError) as caught:
        make_provenance_from_evidence_envelope(
            {"score": 2}, _envelope(original)
        )
    assert caught.value.context["reason"] == "fingerprint_mismatch"


@pytest.mark.parametrize("broken", ["not-a-digest", "f" * 63, "F" * 64])
def test_invalid_source_digest_is_never_imported(broken):
    data = {"score": 1}
    receipt = _envelope(data)
    receipt["sha256"] = broken
    with pytest.raises(LearningEvidenceError):
        make_provenance_from_evidence_envelope(data, receipt)


def test_untrusted_future_and_opt_in_skew_fail_closed():
    data = {"score": 1}
    with pytest.raises(LearningEvidenceError):
        make_provenance_from_evidence_envelope(
            data, _envelope(data, observed_at=1061.0)
        )
    provenance = make_provenance_from_evidence_envelope(data, _envelope(data))
    store = LearningEvidenceStore(clock=lambda: 1000.0)
    with pytest.raises(LearningEvidenceError):
        store.record_observation(Observation("obs-default", "skill", data, provenance))
    with pytest.raises(LearningEvidenceError):
        LearningEvidenceStore(clock=lambda: 1000.0, future_skew_seconds=61.0)


def test_legacy_provenance_receipt_stays_byte_identity_compatible():
    value = {"score": 1}
    provenance = make_provenance(value)
    assert provenance.as_dict() == {
        "source_id": "fixture",
        "source_kind": "fixture",
        "observed_at": 1000.0,
        "clock_version": 1,
        "fingerprint": canonical_fingerprint(value),
        "parent_ids": [],
        "uri": None,
    }
    assert provenance.source_digest is None
    assert provenance.retrieved_at is None
