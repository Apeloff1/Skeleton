from __future__ import annotations

import pytest

from skeleton.ai.runtime.security.key_management import (
    KeyId,
    KeyManagementError,
    KeyRotation,
    KeyVersion,
    record_key_rotation,
    validate_key_history,
)


def _v1(*, state: str = "retired") -> KeyVersion:
    return KeyVersion(
        key_id="signing-key",
        version=1,
        state=state,
        created_at_ns=100,
    )


def _next(
    previous: KeyVersion,
    version: int,
    *,
    state: str = "active",
    created_at_ns: int = 200,
) -> KeyVersion:
    return KeyVersion(
        key_id=previous.key_id,
        version=version,
        state=state,
        created_at_ns=created_at_ns,
        predecessor_digest=previous.digest,
    )


def test_key_identity_and_versions_never_carry_material() -> None:
    identity = KeyId(
        key_id="signing-key",
        provider_id="kms-primary",
        purpose="artifact-signing",
    )
    version = _v1(state="active")

    assert identity.key_material_present is False
    assert version.key_material_present is False
    assert not hasattr(identity, "key")
    assert not hasattr(identity, "secret")
    assert not hasattr(version, "key")
    assert not hasattr(version, "secret")
    assert len(identity.digest) == 64
    assert len(version.digest) == 64


def test_key_version_requires_predecessor_after_version_one() -> None:
    with pytest.raises(KeyManagementError, match="predecessor"):
        KeyVersion(
            key_id="signing-key",
            version=2,
            state="active",
            created_at_ns=200,
        )

    with pytest.raises(KeyManagementError, match="first key version"):
        KeyVersion(
            key_id="signing-key",
            version=1,
            state="active",
            created_at_ns=100,
            predecessor_digest="a" * 64,
        )


def test_rotation_binds_exact_old_and_new_version_digests() -> None:
    previous = _v1()
    current = _next(previous, 2)

    rotation = record_key_rotation(
        rotation_id="rotate-1-2",
        previous=previous,
        current=current,
        reason_code="scheduled",
        rotated_at_ns=250,
    )

    assert rotation.from_version == 1
    assert rotation.to_version == 2
    assert rotation.from_version_digest == previous.digest
    assert rotation.to_version_digest == current.digest
    assert rotation.key_material_present is False
    assert len(rotation.digest) == 64


def test_rotation_rejects_identity_drift_and_bad_predecessor() -> None:
    previous = _v1()
    other = KeyVersion(
        key_id="other-key",
        version=2,
        state="active",
        created_at_ns=200,
        predecessor_digest=previous.digest,
    )
    with pytest.raises(KeyManagementError, match="key identity"):
        record_key_rotation(
            rotation_id="bad-identity",
            previous=previous,
            current=other,
            reason_code="scheduled",
            rotated_at_ns=250,
        )

    wrong_predecessor = KeyVersion(
        key_id="signing-key",
        version=2,
        state="active",
        created_at_ns=200,
        predecessor_digest="f" * 64,
    )
    with pytest.raises(KeyManagementError, match="predecessor digest"):
        record_key_rotation(
            rotation_id="bad-link",
            previous=previous,
            current=wrong_predecessor,
            reason_code="scheduled",
            rotated_at_ns=250,
        )


def test_rotation_receipt_cannot_predate_new_version() -> None:
    previous = _v1()
    current = _next(previous, 2, created_at_ns=200)

    with pytest.raises(KeyManagementError, match="cannot predate"):
        record_key_rotation(
            rotation_id="too-early",
            previous=previous,
            current=current,
            reason_code="scheduled",
            rotated_at_ns=199,
        )


def test_history_accepts_retired_and_revoked_versions_as_verifiable_metadata() -> None:
    first = _v1(state="revoked")
    second = _next(first, 2, state="retired", created_at_ns=200)
    third = _next(second, 3, state="active", created_at_ns=300)
    rotate_1 = record_key_rotation(
        rotation_id="r-1-2",
        previous=first,
        current=second,
        reason_code="incident",
        rotated_at_ns=210,
    )
    rotate_2 = record_key_rotation(
        rotation_id="r-2-3",
        previous=second,
        current=third,
        reason_code="scheduled",
        rotated_at_ns=310,
    )

    digest = validate_key_history(
        versions=(third, first, second),
        rotations=(rotate_2, rotate_1),
    )

    assert len(digest) == 64


def test_history_digest_is_independent_of_input_order() -> None:
    first = _v1()
    second = _next(first, 2, created_at_ns=200)
    third = _next(second, 3, created_at_ns=300)
    r1 = record_key_rotation(
        rotation_id="r-1-2",
        previous=first,
        current=second,
        reason_code="scheduled",
        rotated_at_ns=210,
    )
    r2 = record_key_rotation(
        rotation_id="r-2-3",
        previous=second,
        current=third,
        reason_code="scheduled",
        rotated_at_ns=310,
    )

    left = validate_key_history((first, second, third), (r1, r2))
    right = validate_key_history((third, first, second), (r2, r1))

    assert left == right


def test_history_rejects_missing_or_forged_rotation_evidence() -> None:
    first = _v1()
    second = _next(first, 2)
    with pytest.raises(KeyManagementError, match="one rotation per transition"):
        validate_key_history((first, second), ())

    forged = KeyRotation(
        rotation_id="forged",
        key_id="signing-key",
        from_version=1,
        to_version=2,
        from_version_digest="a" * 64,
        to_version_digest=second.digest,
        reason_code="scheduled",
        rotated_at_ns=250,
    )
    with pytest.raises(KeyManagementError, match="source digest"):
        validate_key_history((first, second), (forged,))


def test_history_rejects_version_gaps_and_mixed_keys() -> None:
    first = _v1()
    third = _next(first, 3, created_at_ns=300)
    with pytest.raises(KeyManagementError, match="contiguous"):
        validate_key_history((first, third), ())

    other = KeyVersion(
        key_id="other-key",
        version=2,
        state="active",
        created_at_ns=200,
        predecessor_digest=first.digest,
    )
    with pytest.raises(KeyManagementError, match="mix key identities"):
        validate_key_history((first, other), ())


def test_key_metadata_rejects_material_flags_and_unknown_states() -> None:
    with pytest.raises(KeyManagementError, match="cannot carry key material"):
        KeyId(
            key_id="signing-key",
            provider_id="kms-primary",
            purpose="artifact-signing",
            key_material_present=True,
        )
    with pytest.raises(KeyManagementError, match="active, retired, or revoked"):
        KeyVersion(
            key_id="signing-key",
            version=1,
            state="destroyed",
            created_at_ns=100,
        )
