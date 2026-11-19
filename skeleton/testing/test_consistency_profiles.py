from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.persistence.consistency import (
    ConsistencyError,
    ConsistencyProfile,
    FreshnessState,
    ReadDisposition,
    ReadGuarantee,
    ReadObservation,
    WriteGuarantee,
    evaluate_read,
    require_readable,
)


ROOT = Path(__file__).resolve().parents[2]


def _profile(**overrides) -> ConsistencyProfile:
    values = {
        "domain_id": "canonical-operation-state",
        "physical_store": "operation-state-sqlite",
        "authority": "authoritative",
        "source_of_truth": True,
        "read_guarantee": ReadGuarantee.AUTHORITATIVE_COMMITTED,
        "write_guarantee": WriteGuarantee.DURABLE_COMMIT_ACK,
        "stale_policy": "reject",
        "unknown_policy": "reject",
    }
    values.update(overrides)
    return ConsistencyProfile(**values)


def test_machine_registry_covers_every_state_domain() -> None:
    topology = json.loads((ROOT / "machine/state_topology.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "machine/consistency_profiles.json").read_text(encoding="utf-8"))

    assert registry["profile_count"] == len(topology["state_domains"]) == 21
    assert [row["domain_id"] for row in registry["profiles"]] == [
        row["id"] for row in topology["state_domains"]
    ]


def test_machine_profiles_round_trip_runtime_contract() -> None:
    registry = json.loads((ROOT / "machine/consistency_profiles.json").read_text(encoding="utf-8"))
    for row in registry["profiles"]:
        runtime_row = {
            key: row[key]
            for key in (
                "schema_version",
                "domain_id",
                "physical_store",
                "authority",
                "source_of_truth",
                "read_guarantee",
                "write_guarantee",
                "stale_policy",
                "unknown_policy",
                "source_refs",
                "max_staleness_ms",
            )
        }
        profile = ConsistencyProfile.from_mapping(runtime_row)
        assert profile.domain_id == row["domain_id"]
        assert len(profile.digest) == 64


def test_authoritative_profile_rejects_stale_policy() -> None:
    with pytest.raises(ConsistencyError, match="cannot serve stale"):
        _profile(stale_policy="explicit_only")


def test_projection_requires_sources_and_source_first_write() -> None:
    with pytest.raises(ConsistencyError, match="requires source"):
        _profile(
            domain_id="projection",
            physical_store="chroma-service",
            authority="derived",
            source_of_truth=False,
            read_guarantee=ReadGuarantee.EVENTUAL_PROJECTION,
            write_guarantee=WriteGuarantee.SOURCE_FIRST_THEN_PROJECT,
            stale_policy="explicit_only",
            source_refs=(),
        )

    with pytest.raises(ConsistencyError, match="source-first"):
        _profile(
            domain_id="projection",
            physical_store="chroma-service",
            authority="derived",
            source_of_truth=False,
            read_guarantee=ReadGuarantee.EVENTUAL_PROJECTION,
            write_guarantee=WriteGuarantee.DURABLE_COMMIT_ACK,
            stale_policy="explicit_only",
            source_refs=("canonical-operation-state",),
        )


def test_unknown_state_always_fails_closed() -> None:
    profile = _profile()
    observation = ReadObservation(
        domain_id=profile.domain_id,
        freshness=FreshnessState.UNKNOWN,
    )
    decision = evaluate_read(profile, observation, allow_stale=True)

    assert decision.allowed is False
    assert decision.disposition is ReadDisposition.BLOCK_UNKNOWN
    with pytest.raises(ConsistencyError, match="block_unknown"):
        require_readable(profile, observation, allow_stale=True)


def test_authoritative_stale_read_is_blocked_even_with_opt_in() -> None:
    profile = _profile()
    observation = ReadObservation(
        domain_id=profile.domain_id,
        freshness=FreshnessState.STALE,
        observed_version="v1",
        authoritative_version="v2",
        lag_ms=10,
    )
    decision = evaluate_read(profile, observation, allow_stale=True)
    assert decision.allowed is False
    assert decision.disposition is ReadDisposition.BLOCK_STALE


def test_projection_stale_read_requires_explicit_opt_in() -> None:
    profile = _profile(
        domain_id="optional-vector-index",
        physical_store="chroma-service",
        authority="derived",
        source_of_truth=False,
        read_guarantee=ReadGuarantee.EVENTUAL_PROJECTION,
        write_guarantee=WriteGuarantee.SOURCE_FIRST_THEN_PROJECT,
        stale_policy="explicit_only",
        source_refs=("canonical-ai-memory-records",),
    )
    observation = ReadObservation(
        domain_id=profile.domain_id,
        freshness=FreshnessState.STALE,
        observed_version="v1",
        authoritative_version="v2",
        lag_ms=50,
    )

    assert evaluate_read(profile, observation).allowed is False
    accepted = require_readable(profile, observation, allow_stale=True)
    assert accepted.allowed is True
    assert accepted.disposition is ReadDisposition.SERVE_EXPLICIT_STALE


def test_projection_numeric_staleness_bound_is_enforced_when_declared() -> None:
    profile = _profile(
        domain_id="projection",
        physical_store="chroma-service",
        authority="derived",
        source_of_truth=False,
        read_guarantee=ReadGuarantee.EVENTUAL_PROJECTION,
        write_guarantee=WriteGuarantee.SOURCE_FIRST_THEN_PROJECT,
        stale_policy="explicit_only",
        source_refs=("canonical-operation-state",),
        max_staleness_ms=100,
    )
    observation = ReadObservation(
        domain_id="projection",
        freshness=FreshnessState.STALE,
        lag_ms=101,
    )
    assert evaluate_read(profile, observation, allow_stale=True).allowed is False


def test_recovery_aid_never_becomes_normal_read_authority() -> None:
    profile = _profile(
        domain_id="manual-memory-snapshots",
        physical_store="snapshot-files",
        authority="recovery-aid",
        source_of_truth=False,
        read_guarantee=ReadGuarantee.RECOVERY_AID_ONLY,
        write_guarantee=WriteGuarantee.RECOVERY_AID_NO_AUTHORITY,
        source_refs=("in-process-retrieval-memory",),
    )
    decision = evaluate_read(
        profile,
        ReadObservation(
            domain_id=profile.domain_id,
            freshness=FreshnessState.FRESH,
        ),
    )
    assert decision.allowed is False
    assert decision.disposition is ReadDisposition.BLOCK_RECOVERY_AID


def test_stale_observation_cannot_claim_same_authoritative_version() -> None:
    with pytest.raises(ConsistencyError, match="version equality"):
        ReadObservation(
            domain_id="projection",
            freshness=FreshnessState.STALE,
            observed_version="v2",
            authoritative_version="v2",
        )


def test_consistency_ai_mirror_is_byte_identical() -> None:
    canonical = ROOT / "skeleton/persistence/consistency.py"
    mirror = ROOT / "skeleton/ai/runtime/persistence/consistency.py"
    assert canonical.read_bytes() == mirror.read_bytes()
