"""Regression coverage for deterministic creator work leases (#807 B013)."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.forge.creator.work_leases import (
    MAX_TTL_SECONDS,
    WORK_LEASE_SCHEMA,
    WORK_LEASE_VERSION,
    WorkLeaseError,
    WorkLeaseVersionError,
    claim_work,
    conflicts_for_scope,
    empty_lease_state,
    parse_lease_state,
    release_lease,
    renew_lease,
    serialize_lease_state,
    sweep_expired_leases,
)
from skeleton.repo_intelligence.batch_plan import load_plan


@pytest.fixture(scope="module")
def plan():
    return load_plan()


def _claim(
    state,
    *,
    plan,
    lease_id="lease-1",
    owner_id="agent-1",
    batch_ids=(),
    paths=(),
    now=100,
    ttl_seconds=60,
):
    return claim_work(
        state,
        lease_id=lease_id,
        owner_id=owner_id,
        batch_ids=batch_ids,
        paths=paths,
        now=now,
        ttl_seconds=ttl_seconds,
        plan=plan,
        expected_state_digest=state.digest,
    )


def test_empty_state_is_deterministic_and_plan_bound(plan) -> None:
    first = empty_lease_state(plan=plan, logical_time=12)
    second = empty_lease_state(plan=plan, logical_time=12)

    assert first == second
    assert first.schema == WORK_LEASE_SCHEMA
    assert first.schema_version == WORK_LEASE_VERSION
    assert first.plan_digest == plan.digest
    assert first.logical_time == 12
    assert first.leases == ()
    assert len(first.digest) == 64


def test_claim_canonicalizes_scope_order(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, lease = _claim(
        state,
        plan=plan,
        batch_ids=("B013", "B001"),
        paths=("zeta/file.py", "alpha/file.py"),
    )

    assert lease.scope.batch_ids == ("B001", "B013")
    assert lease.scope.paths == ("alpha/file.py", "zeta/file.py")
    assert lease.issued_at == 100
    assert lease.expires_at == 160
    assert lease.revision == 1
    assert state.leases == (lease,)


def test_disjoint_agents_can_claim_in_parallel(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, first = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        batch_ids=("B013",),
        paths=("skeleton/forge/creator",),
    )
    state, second = _claim(
        state,
        plan=plan,
        lease_id="lease-b",
        owner_id="agent-b",
        batch_ids=("B014",),
        paths=("frontend/src/creator",),
        now=101,
    )

    assert {item.lease_id for item in state.leases} == {"lease-a", "lease-b"}
    assert first.owner_id != second.owner_id


def test_batch_overlap_is_rejected_with_conflict_evidence(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        batch_ids=("B013",),
    )

    with pytest.raises(WorkLeaseError) as caught:
        _claim(
            state,
            plan=plan,
            lease_id="lease-b",
            owner_id="agent-b",
            batch_ids=("B013",),
            now=101,
        )

    assert caught.value.context["reason"] == "scope_conflict"
    assert caught.value.context["conflicts"] == [
        {
            "lease_id": "lease-a",
            "owner_id": "agent-a",
            "batch_ids": ["B013"],
            "paths": [],
        }
    ]


@pytest.mark.parametrize(
    ("claimed", "requested"),
    [
        ("skeleton/forge", "skeleton/forge"),
        ("skeleton/forge", "skeleton/forge/creator/work_leases.py"),
        ("skeleton/forge/creator/work_leases.py", "skeleton/forge"),
    ],
)
def test_exact_ancestor_and_descendant_path_overlap_fail(
    plan, claimed: str, requested: str
) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        paths=(claimed,),
    )

    conflicts = conflicts_for_scope(
        state,
        paths=(requested,),
        now=101,
        plan=plan,
    )
    assert len(conflicts) == 1
    assert conflicts[0].lease_id == "lease-a"
    assert conflicts[0].paths == (requested,)

    with pytest.raises(WorkLeaseError) as caught:
        _claim(
            state,
            plan=plan,
            lease_id="lease-b",
            owner_id="agent-b",
            paths=(requested,),
            now=101,
        )
    assert caught.value.context["reason"] == "scope_conflict"


def test_similar_prefix_without_path_segment_overlap_is_allowed(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        paths=("skeleton/forge",),
    )
    state, second = _claim(
        state,
        plan=plan,
        lease_id="lease-b",
        paths=("skeleton/forge_tools",),
        now=101,
    )

    assert second.scope.paths == ("skeleton/forge_tools",)
    assert len(state.leases) == 2


def test_same_owner_cannot_silently_overlap_itself(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        paths=("skeleton/forge",),
    )

    with pytest.raises(WorkLeaseError) as caught:
        _claim(
            state,
            plan=plan,
            lease_id="lease-b",
            owner_id="agent-a",
            paths=("skeleton/forge/creator",),
            now=101,
        )
    assert caught.value.context["reason"] == "scope_conflict"


def test_scope_rejects_redundant_self_overlap(plan) -> None:
    state = empty_lease_state(plan=plan)
    with pytest.raises(WorkLeaseError) as caught:
        _claim(
            state,
            plan=plan,
            paths=("skeleton/forge", "skeleton/forge/creator"),
        )
    assert caught.value.context["reason"] == "self_overlap"


@pytest.mark.parametrize(
    "path",
    [
        "/absolute/path",
        "../escape",
        "skeleton/../escape",
        "skeleton//creator",
        "skeleton/creator/",
        "./skeleton/creator",
        "C:/repo/file.py",
        "skeleton\\creator\\file.py",
        "skeleton/\x00bad",
    ],
)
def test_unsafe_paths_fail_closed(plan, path: str) -> None:
    state = empty_lease_state(plan=plan)
    with pytest.raises(WorkLeaseError):
        _claim(state, plan=plan, paths=(path,))


def test_unknown_batch_and_empty_scope_fail_closed(plan) -> None:
    state = empty_lease_state(plan=plan)
    with pytest.raises(WorkLeaseError) as caught:
        _claim(state, plan=plan, batch_ids=("B999",))
    assert caught.value.context["reason"] == "unknown_batch"

    with pytest.raises(WorkLeaseError) as caught:
        _claim(state, plan=plan)
    assert caught.value.context["reason"] == "empty_scope"


def test_duplicate_active_lease_id_is_rejected(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="same-id",
        batch_ids=("B013",),
    )

    with pytest.raises(WorkLeaseError) as caught:
        _claim(
            state,
            plan=plan,
            lease_id="same-id",
            batch_ids=("B014",),
            now=101,
        )
    assert caught.value.context["reason"] == "duplicate_lease_id"


def test_stale_lease_is_swept_before_new_claim(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, old = _claim(
        state,
        plan=plan,
        lease_id="old",
        owner_id="agent-old",
        batch_ids=("B013",),
        now=10,
        ttl_seconds=5,
    )
    assert old.expires_at == 15

    state, fresh = _claim(
        state,
        plan=plan,
        lease_id="fresh",
        owner_id="agent-new",
        batch_ids=("B013",),
        now=15,
        ttl_seconds=20,
    )

    assert fresh.lease_id == "fresh"
    assert tuple(item.lease_id for item in state.leases) == ("fresh",)
    assert state.logical_time == 15


def test_sweep_reports_expired_ids_in_canonical_order(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-b",
        batch_ids=("B013",),
        now=10,
        ttl_seconds=5,
    )
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        batch_ids=("B014",),
        now=10,
        ttl_seconds=7,
    )

    sweep = sweep_expired_leases(state, now=20, plan=plan)

    assert sweep.expired_lease_ids == ("lease-a", "lease-b")
    assert sweep.state.leases == ()
    assert sweep.state.logical_time == 20


def test_time_cannot_regress(plan) -> None:
    state = empty_lease_state(plan=plan, logical_time=100)
    with pytest.raises(WorkLeaseError) as caught:
        sweep_expired_leases(state, now=99, plan=plan)
    assert caught.value.context["reason"] == "time_regression"


def test_renew_preserves_scope_and_increments_revision(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, lease = _claim(
        state,
        plan=plan,
        lease_id="renew-me",
        owner_id="agent-a",
        batch_ids=("B013",),
        paths=("skeleton/forge/creator",),
        now=100,
        ttl_seconds=30,
    )

    renewed_state, renewed = renew_lease(
        state,
        lease_id=lease.lease_id,
        owner_id=lease.owner_id,
        now=120,
        ttl_seconds=50,
        expected_revision=lease.revision,
        plan=plan,
        expected_state_digest=state.digest,
    )

    assert renewed.scope == lease.scope
    assert renewed.issued_at == lease.issued_at
    assert renewed.expires_at == 170
    assert renewed.revision == 2
    assert renewed.digest != lease.digest
    assert renewed_state.leases == (renewed,)


def test_renew_rejects_wrong_owner_stale_revision_and_expiry(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, lease = _claim(
        state,
        plan=plan,
        batch_ids=("B013",),
        now=100,
        ttl_seconds=10,
    )

    with pytest.raises(WorkLeaseError) as caught:
        renew_lease(
            state,
            lease_id=lease.lease_id,
            owner_id="other-agent",
            now=105,
            ttl_seconds=10,
            expected_revision=1,
            plan=plan,
        )
    assert caught.value.context["reason"] == "owner_mismatch"

    with pytest.raises(WorkLeaseError) as caught:
        renew_lease(
            state,
            lease_id=lease.lease_id,
            owner_id=lease.owner_id,
            now=105,
            ttl_seconds=10,
            expected_revision=2,
            plan=plan,
        )
    assert caught.value.context["reason"] == "revision_mismatch"

    with pytest.raises(WorkLeaseError) as caught:
        renew_lease(
            state,
            lease_id=lease.lease_id,
            owner_id=lease.owner_id,
            now=110,
            ttl_seconds=10,
            expected_revision=1,
            plan=plan,
        )
    assert caught.value.context["reason"] == "lease_unavailable"


def test_release_removes_only_owned_target(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, first = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        batch_ids=("B013",),
    )
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-b",
        owner_id="agent-b",
        batch_ids=("B014",),
        now=101,
    )

    with pytest.raises(WorkLeaseError) as caught:
        release_lease(
            state,
            lease_id=first.lease_id,
            owner_id="agent-b",
            now=102,
            expected_revision=1,
            plan=plan,
        )
    assert caught.value.context["reason"] == "owner_mismatch"

    state = release_lease(
        state,
        lease_id=first.lease_id,
        owner_id=first.owner_id,
        now=102,
        expected_revision=first.revision,
        plan=plan,
        expected_state_digest=state.digest,
    )
    assert tuple(item.lease_id for item in state.leases) == ("lease-b",)


def test_compare_and_swap_digest_blocks_lost_update(plan) -> None:
    state = empty_lease_state(plan=plan)
    stale_digest = state.digest
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        batch_ids=("B013",),
    )

    with pytest.raises(WorkLeaseError) as caught:
        claim_work(
            state,
            lease_id="lease-b",
            owner_id="agent-b",
            batch_ids=("B014",),
            now=101,
            ttl_seconds=30,
            plan=plan,
            expected_state_digest=stale_digest,
        )
    assert caught.value.context["reason"] == "concurrent_update"


def test_ttl_is_bounded(plan) -> None:
    state = empty_lease_state(plan=plan)
    with pytest.raises(WorkLeaseError):
        _claim(state, plan=plan, batch_ids=("B013",), ttl_seconds=0)
    with pytest.raises(WorkLeaseError):
        _claim(
            state,
            plan=plan,
            batch_ids=("B013",),
            ttl_seconds=MAX_TTL_SECONDS + 1,
        )


def test_serialization_round_trip_is_canonical(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-b",
        owner_id="agent-b",
        batch_ids=("B014",),
        paths=("frontend/src/creator",),
    )
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        owner_id="agent-a",
        batch_ids=("B013",),
        paths=("skeleton/forge/creator",),
        now=101,
    )

    raw = serialize_lease_state(state, plan=plan)
    restored = parse_lease_state(raw, plan=plan)

    assert restored == state
    assert serialize_lease_state(restored, plan=plan) == raw
    assert b" " not in raw
    assert tuple(item.lease_id for item in restored.leases) == (
        "lease-a",
        "lease-b",
    )


def test_state_and_nested_lease_tampering_fail_closed(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(state, plan=plan, batch_ids=("B013",))

    root_tamper = json.loads(serialize_lease_state(state, plan=plan))
    root_tamper["logical_time"] += 1
    with pytest.raises(WorkLeaseError) as caught:
        parse_lease_state(json.dumps(root_tamper), plan=plan)
    assert caught.value.context["reason"] == "digest_mismatch"

    lease_tamper = json.loads(serialize_lease_state(state, plan=plan))
    lease_tamper["leases"][0]["expires_at"] += 10
    with pytest.raises(WorkLeaseError) as caught:
        parse_lease_state(json.dumps(lease_tamper), plan=plan)
    assert caught.value.context["reason"] == "digest_mismatch"


def test_duplicate_and_unknown_json_fields_fail_closed(plan) -> None:
    with pytest.raises(WorkLeaseError) as caught:
        parse_lease_state('{"schema":"a","schema":"b"}', plan=plan)
    assert caught.value.context["reason"] == "duplicate_field"

    state = empty_lease_state(plan=plan)
    payload = json.loads(serialize_lease_state(state, plan=plan))
    payload["unexpected"] = True
    with pytest.raises(WorkLeaseError) as caught:
        parse_lease_state(json.dumps(payload), plan=plan)
    assert caught.value.context["reason"] == "field_set"

    state, _ = _claim(state, plan=plan, batch_ids=("B013",))
    payload = json.loads(serialize_lease_state(state, plan=plan))
    payload["leases"][0]["unexpected"] = True
    with pytest.raises(WorkLeaseError) as caught:
        parse_lease_state(json.dumps(payload), plan=plan)
    assert caught.value.context["reason"] == "field_set"


def test_version_and_plan_drift_fail_closed(plan) -> None:
    state = empty_lease_state(plan=plan)
    payload = json.loads(serialize_lease_state(state, plan=plan))
    payload["schema_version"] = WORK_LEASE_VERSION + 1

    with pytest.raises(WorkLeaseVersionError):
        parse_lease_state(json.dumps(payload), plan=plan)

    drifted = replace(plan, digest="f" * 64)
    with pytest.raises(WorkLeaseError) as caught:
        serialize_lease_state(state, plan=drifted)
    assert caught.value.context["reason"] == "plan_drift"


def test_conflict_probe_does_not_mutate_original_state(plan) -> None:
    state = empty_lease_state(plan=plan)
    state, _ = _claim(
        state,
        plan=plan,
        lease_id="lease-a",
        batch_ids=("B013",),
        now=10,
        ttl_seconds=5,
    )
    original = state

    assert conflicts_for_scope(
        state,
        batch_ids=("B013",),
        now=15,
        plan=plan,
    ) == ()
    assert state == original


def test_invalid_owner_and_lease_tokens_fail_closed(plan) -> None:
    state = empty_lease_state(plan=plan)
    with pytest.raises(WorkLeaseError):
        claim_work(
            state,
            lease_id="bad lease",
            owner_id="agent-a",
            batch_ids=("B013",),
            now=1,
            ttl_seconds=1,
            plan=plan,
        )
    with pytest.raises(WorkLeaseError):
        claim_work(
            state,
            lease_id="lease-a",
            owner_id="bad owner",
            batch_ids=("B013",),
            now=1,
            ttl_seconds=1,
            plan=plan,
        )
