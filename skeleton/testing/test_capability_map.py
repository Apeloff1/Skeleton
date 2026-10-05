from __future__ import annotations

import pytest

import skeleton.ai as public_ai
from skeleton.ai import capability_map as canonical_capability_map
from skeleton.ai.capability_map import (
    Availability,
    CapabilityDescriptor,
    CapabilityError,
    CapabilityEvidence,
    CapabilityMap,
    CapabilitySnapshot,
    Maturity,
)


ZERO = "0" * 64
ONE = "1" * 64


def descriptor(
    capability_id: str,
    maturity: Maturity = Maturity.PRODUCTION,
    dependencies: tuple[str, ...] = (),
    guarantees: tuple[str, ...] = ("deterministic",),
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id,
        "OWNER.AI",
        maturity,
        dependencies,
        guarantees,
    )


def evidence(
    subject: CapabilityDescriptor,
    *,
    evidence_id: str = "EVID.CAP",
    state: Availability = Availability.AVAILABLE,
    guarantees: tuple[str, ...] | None = None,
    reason: str = "",
    descriptor_digest: str | None = None,
) -> CapabilityEvidence:
    return CapabilityEvidence(
        evidence_id=evidence_id,
        capability_id=subject.capability_id,
        descriptor_digest=descriptor_digest or subject.digest,
        state=state,
        guarantees=(
            subject.guarantees
            if guarantees is None
            else guarantees
        ),
        artifact_digest=ONE,
        reason=reason,
    )


def test_planned_intent_is_not_advertised_as_live() -> None:
    planned = descriptor("CAP.A", Maturity.PLANNED)
    subject = CapabilityMap((planned,), (evidence(planned),))
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.UNAVAILABLE
    assert resolved.reason == "planned_not_live"
    assert resolved.evidence_digest is None


def test_missing_live_evidence_is_unavailable() -> None:
    subject = CapabilityMap((descriptor("CAP.A"),), ())
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.UNAVAILABLE
    assert resolved.reason == "no_live_evidence"


def test_live_evidence_must_bind_exact_descriptor_revision() -> None:
    item = descriptor("CAP.A")
    subject = CapabilityMap(
        (item,),
        (
            evidence(
                item,
                descriptor_digest=ZERO,
            ),
        ),
    )
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.UNAVAILABLE
    assert resolved.reason == "descriptor_evidence_mismatch"


def test_dependency_failure_degrades_parent_without_silent_fallback() -> None:
    child = descriptor("CAP.A")
    parent = descriptor("CAP.B", dependencies=("CAP.A",))
    subject = CapabilityMap(
        (child, parent),
        (
            evidence(
                child,
                evidence_id="EVID.A",
                state=Availability.UNAVAILABLE,
                guarantees=(),
                reason="offline",
            ),
            evidence(parent, evidence_id="EVID.B"),
        ),
    )
    resolved = subject.resolve("CAP.B")
    assert resolved.state is Availability.DEGRADED
    assert resolved.reason == "dependency:CAP.A=unavailable"
    assert resolved.dependency_states == (
        ("CAP.A", Availability.UNAVAILABLE),
    )
    with pytest.raises(CapabilityError, match="guarantee unavailable"):
        subject.require("CAP.B")


def test_transitive_dependency_degradation_propagates_explicitly() -> None:
    leaf = descriptor("CAP.A")
    middle = descriptor("CAP.B", dependencies=("CAP.A",))
    root = descriptor("CAP.C", dependencies=("CAP.B",))
    subject = CapabilityMap(
        (leaf, middle, root),
        (
            evidence(
                leaf,
                evidence_id="EVID.A",
                state=Availability.UNAVAILABLE,
                guarantees=(),
                reason="offline",
            ),
            evidence(middle, evidence_id="EVID.B"),
            evidence(root, evidence_id="EVID.C"),
        ),
    )
    assert subject.resolve("CAP.B").state is Availability.DEGRADED
    root_state = subject.resolve("CAP.C")
    assert root_state.state is Availability.DEGRADED
    assert root_state.reason == "dependency:CAP.B=degraded"


def test_all_live_dependencies_allow_capability() -> None:
    child = descriptor("CAP.A")
    parent = descriptor("CAP.B", dependencies=("CAP.A",))
    subject = CapabilityMap(
        (child, parent),
        (
            evidence(child, evidence_id="EVID.A"),
            evidence(parent, evidence_id="EVID.B"),
        ),
    )
    assert subject.require("CAP.B").capability_id == "CAP.B"
    assert subject.resolve("CAP.B").state is Availability.AVAILABLE


def test_degraded_live_evidence_remains_degraded() -> None:
    item = descriptor(
        "CAP.A",
        guarantees=("deterministic", "streaming"),
    )
    subject = CapabilityMap(
        (item,),
        (
            evidence(
                item,
                state=Availability.DEGRADED,
                guarantees=("deterministic",),
                reason="streaming_offline",
            ),
        ),
    )
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.DEGRADED
    assert resolved.guarantees == ("deterministic",)
    assert resolved.reason == "streaming_offline"


def test_partial_live_guarantees_are_explicit_degradation() -> None:
    item = descriptor(
        "CAP.A",
        guarantees=("deterministic", "streaming"),
    )
    subject = CapabilityMap(
        (item,),
        (
            evidence(
                item,
                guarantees=("deterministic",),
            ),
        ),
    )
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.DEGRADED
    assert resolved.reason == "missing_live_guarantee:streaming"


def test_require_never_falls_back_to_weaker_live_guarantee() -> None:
    item = descriptor(
        "CAP.A",
        guarantees=("deterministic", "streaming"),
    )
    subject = CapabilityMap(
        (item,),
        (
            evidence(
                item,
                state=Availability.DEGRADED,
                guarantees=("deterministic",),
                reason="streaming_offline",
            ),
        ),
    )
    with pytest.raises(CapabilityError, match="guarantee unavailable"):
        subject.require(
            "CAP.A",
            guarantees=("streaming",),
        )


def test_require_rejects_undeclared_guarantee() -> None:
    item = descriptor("CAP.A")
    subject = CapabilityMap((item,), (evidence(item),))
    with pytest.raises(CapabilityError, match="does not declare"):
        subject.require(
            "CAP.A",
            guarantees=("telepathy",),
        )


def test_evidence_cannot_claim_undeclared_guarantee() -> None:
    item = descriptor("CAP.A")
    subject = CapabilityMap(
        (item,),
        (
            evidence(
                item,
                guarantees=("deterministic", "streaming"),
            ),
        ),
    )
    resolved = subject.resolve("CAP.A")
    assert resolved.state is Availability.UNAVAILABLE
    assert (
        resolved.reason
        == "evidence_claims_undeclared_guarantee:streaming"
    )


def test_unknown_dependency_rejected() -> None:
    with pytest.raises(
        CapabilityError,
        match="unknown capability dependency",
    ):
        CapabilityMap(
            (
                descriptor(
                    "CAP.B",
                    dependencies=("CAP.MISSING",),
                ),
            ),
            (),
        )


def test_self_dependency_rejected() -> None:
    with pytest.raises(CapabilityError, match="self dependency"):
        descriptor("CAP.A", dependencies=("CAP.A",))


def test_dependency_cycle_rejected() -> None:
    with pytest.raises(CapabilityError, match="dependency cycle"):
        CapabilityMap(
            (
                descriptor("CAP.A", dependencies=("CAP.B",)),
                descriptor("CAP.B", dependencies=("CAP.A",)),
            ),
            (),
        )


def test_duplicate_descriptor_rejected() -> None:
    item = descriptor("CAP.A")
    with pytest.raises(
        CapabilityError,
        match="duplicate capability descriptor",
    ):
        CapabilityMap((item, item), ())


def test_duplicate_evidence_id_rejected() -> None:
    a = descriptor("CAP.A")
    b = descriptor("CAP.B")
    with pytest.raises(
        CapabilityError,
        match="duplicate capability evidence id",
    ):
        CapabilityMap(
            (a, b),
            (
                evidence(a, evidence_id="EVID.SHARED"),
                evidence(b, evidence_id="EVID.SHARED"),
            ),
        )


def test_multiple_live_records_for_same_capability_rejected() -> None:
    item = descriptor("CAP.A")
    with pytest.raises(CapabilityError, match="multiple live evidence"):
        CapabilityMap(
            (item,),
            (
                evidence(item, evidence_id="EVID.A"),
                evidence(item, evidence_id="EVID.B"),
            ),
        )


def test_evidence_for_unknown_capability_rejected() -> None:
    known = descriptor("CAP.A")
    unknown = descriptor("CAP.B")
    with pytest.raises(CapabilityError, match="unknown capability"):
        CapabilityMap(
            (known,),
            (evidence(unknown),),
        )


def test_duplicate_dependencies_and_guarantees_rejected() -> None:
    with pytest.raises(CapabilityError, match="duplicate dependency_id"):
        descriptor(
            "CAP.A",
            dependencies=("CAP.B", "CAP.B"),
        )
    with pytest.raises(CapabilityError, match="duplicate guarantee"):
        descriptor(
            "CAP.A",
            guarantees=("deterministic", "deterministic"),
        )


def test_unavailable_evidence_cannot_advertise_guarantees() -> None:
    item = descriptor("CAP.A")
    with pytest.raises(CapabilityError, match="cannot advertise"):
        evidence(
            item,
            state=Availability.UNAVAILABLE,
            guarantees=("deterministic",),
            reason="offline",
        )


def test_degraded_or_unavailable_evidence_requires_reason() -> None:
    item = descriptor("CAP.A")
    with pytest.raises(CapabilityError, match="requires reason"):
        evidence(
            item,
            state=Availability.DEGRADED,
            guarantees=("deterministic",),
        )
    with pytest.raises(CapabilityError, match="requires reason"):
        evidence(
            item,
            state=Availability.UNAVAILABLE,
            guarantees=(),
        )


def test_registry_identity_is_order_independent() -> None:
    a = descriptor("CAP.A")
    b = descriptor("CAP.B")
    map_one = CapabilityMap(
        (a, b),
        (
            evidence(a, evidence_id="EVID.A"),
            evidence(b, evidence_id="EVID.B"),
        ),
    )
    map_two = CapabilityMap(
        (b, a),
        (
            evidence(b, evidence_id="EVID.B"),
            evidence(a, evidence_id="EVID.A"),
        ),
    )
    assert map_one.digest == map_two.digest
    assert map_one.resolve_all().digest == map_two.resolve_all().digest


def test_snapshot_exposes_global_health_without_hiding_failures() -> None:
    a = descriptor("CAP.A")
    b = descriptor("CAP.B")
    subject = CapabilityMap(
        (a, b),
        (evidence(a, evidence_id="EVID.A"),),
    )
    snapshot = subject.resolve_all()
    assert snapshot.healthy is False
    states = {
        item.capability_id: item.state
        for item in snapshot.capabilities
    }
    assert states == {
        "CAP.A": Availability.AVAILABLE,
        "CAP.B": Availability.UNAVAILABLE,
    }


def test_descriptor_change_invalidates_old_evidence() -> None:
    old = descriptor("CAP.A", guarantees=("deterministic",))
    old_evidence = evidence(old)
    new = descriptor(
        "CAP.A",
        guarantees=("deterministic", "streaming"),
    )
    subject = CapabilityMap((new,), (old_evidence,))
    assert subject.resolve("CAP.A").state is Availability.UNAVAILABLE
    assert (
        subject.resolve("CAP.A").reason
        == "descriptor_evidence_mismatch"
    )


def test_unknown_capability_query_fails_closed() -> None:
    with pytest.raises(CapabilityError, match="unknown capability"):
        CapabilityMap((), ()).resolve("CAP.UNKNOWN")


def test_invalid_object_types_rejected() -> None:
    with pytest.raises(TypeError, match="CapabilityDescriptor"):
        CapabilityMap(("CAP.A",), ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="CapabilityEvidence"):
        CapabilityMap(
            (descriptor("CAP.A"),),
            ("EVID.A",),
        )  # type: ignore[arg-type]


def test_maturity_availability_identifiers_and_guarantees_are_typed() -> None:
    with pytest.raises(CapabilityError, match="maturity must"):
        descriptor("CAP.A", maturity="production")  # type: ignore[arg-type]
    item = descriptor("CAP.A")
    with pytest.raises(CapabilityError, match="state must"):
        CapabilityEvidence(
            "EVID.A",
            "CAP.A",
            item.digest,
            "available",  # type: ignore[arg-type]
            ("deterministic",),
            ONE,
            "",
        )
    with pytest.raises(CapabilityError, match="stable identifier"):
        descriptor("cap.lower")
    with pytest.raises(CapabilityError, match="canonical token"):
        descriptor("CAP.A", guarantees=("Has Space",))


def test_evidence_count_is_bounded_before_registry_construction() -> None:
    item = descriptor("CAP.A")
    oversized = tuple(
        evidence(item, evidence_id=f"EVID.{index:05d}")
        for index in range(10_001)
    )
    with pytest.raises(CapabilityError, match="evidence count exceeds safety bound"):
        CapabilityMap((item,), oversized)


def test_non_iterable_registry_inputs_fail_with_stable_type_errors() -> None:
    with pytest.raises(TypeError, match="descriptors must be iterable"):
        CapabilityMap(None, ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="evidence must be iterable"):
        CapabilityMap((), None)  # type: ignore[arg-type]


def test_generator_materialization_stops_at_safety_bound() -> None:
    consumed = 0

    def descriptors():
        nonlocal consumed
        while True:
            consumed += 1
            yield descriptor(f"CAP.{consumed}")

    with pytest.raises(CapabilityError, match="capability count exceeds safety bound"):
        CapabilityMap(descriptors(), ())
    assert consumed == 10_001


def test_canonical_ai_package_exports_capability_contract_by_identity() -> None:
    expected = set(canonical_capability_map.__all__)
    assert set(public_ai.__all__) == expected
    for name in expected:
        assert getattr(public_ai, name) is getattr(canonical_capability_map, name)


def test_snapshot_round_trip_preserves_authoritative_identity() -> None:
    root = descriptor("CAP.ROOT")
    live_evidence = evidence(root)
    snapshot = CapabilityMap((root,), (live_evidence,)).resolve_all()
    replayed = CapabilitySnapshot.from_dict(snapshot.to_dict())
    assert replayed == snapshot
    assert replayed.digest == snapshot.digest


def test_snapshot_replay_rejects_tampered_health_and_digest() -> None:
    root = descriptor("CAP.ROOT")
    snapshot = CapabilityMap((root,), (evidence(root),)).resolve_all()
    payload = snapshot.to_dict()
    payload["healthy"] = False
    with pytest.raises(CapabilityError, match="health mismatch"):
        CapabilitySnapshot.from_dict(payload)

    payload = snapshot.to_dict()
    payload["digest"] = "0" * 64
    with pytest.raises(CapabilityError, match="digest mismatch"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_rejects_unknown_fields() -> None:
    root = descriptor("CAP.ROOT")
    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["authority_override"] = True
    with pytest.raises(CapabilityError, match="unknown or missing fields"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_rejects_duplicate_authority() -> None:
    root = descriptor("CAP.ROOT")
    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["capabilities"].append(dict(payload["capabilities"][0]))
    with pytest.raises(CapabilityError, match="duplicate snapshot capability"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_rejects_noncanonical_order() -> None:
    first = descriptor("CAP.AAA")
    second = descriptor("CAP.BBB")
    snapshot = CapabilityMap(
        (first, second),
        (evidence(first, evidence_id="EVID.AAA"), evidence(second, evidence_id="EVID.BBB")),
    ).resolve_all()
    payload = snapshot.to_dict()
    payload["capabilities"].reverse()
    with pytest.raises(CapabilityError, match="canonical order"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_rejects_non_boolean_health() -> None:
    root = descriptor("CAP.ROOT")
    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["healthy"] = 1
    with pytest.raises(CapabilityError, match="health must be boolean"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_rejects_unbounded_nested_payloads() -> None:
    root = descriptor("CAP.ROOT")
    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["capabilities"][0]["guarantees"] = ["deterministic"] * 257
    with pytest.raises(CapabilityError, match="guarantees exceed safety bound"):
        CapabilitySnapshot.from_dict(payload)

    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["capabilities"][0]["dependency_states"] = [
        ["CAP.DEP", "available"]
    ] * 257
    with pytest.raises(CapabilityError, match="dependency states exceed safety bound"):
        CapabilitySnapshot.from_dict(payload)


def test_snapshot_replay_requires_json_array_shapes() -> None:
    root = descriptor("CAP.ROOT")
    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["capabilities"][0]["guarantees"] = "deterministic"
    with pytest.raises(CapabilityError, match="guarantees must be list"):
        CapabilitySnapshot.from_dict(payload)

    payload = CapabilityMap((root,), (evidence(root),)).resolve_all().to_dict()
    payload["capabilities"][0]["dependency_states"] = {}
    with pytest.raises(CapabilityError, match="dependency states must be list"):
        CapabilitySnapshot.from_dict(payload)
