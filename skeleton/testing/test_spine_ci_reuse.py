from __future__ import annotations

import pytest

from skeleton.persistence.spine_ci_reuse import (
    SpineCiReuseError,
    can_reuse_verified_qualification,
)


HEAD = "a" * 40
IDENTITY = "b" * 64


def verified(*, head_sha: str = HEAD, identity: str = IDENTITY) -> dict[str, object]:
    return {
        "kind": "spine_ci_qualification_verify",
        "repository": "Apeloff1/Skeleton",
        "head_sha": head_sha,
        "required_check_policy_digest": "e" * 64,
        "qualification_identity": identity,
        "verified": True,
        "ci_green": True,
        "merge_authority": False,
    }


def test_reuse_requires_same_exact_head_and_identity() -> None:
    assert can_reuse_verified_qualification(verified(), verified()) is True
    assert (
        can_reuse_verified_qualification(
            verified(),
            verified(head_sha="c" * 40),
        )
        is False
    )
    assert (
        can_reuse_verified_qualification(
            verified(),
            verified(identity="d" * 64),
        )
        is False
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("verified", False, "not green"),
        ("ci_green", False, "not green"),
        ("merge_authority", True, "overclaims merge authority"),
        ("head_sha", "bad", "head SHA is invalid"),
        ("qualification_identity", "bad", "qualification identity is invalid"),
    ],
)
def test_reuse_fails_closed_on_invalid_verified_card(
    field: str,
    value: object,
    message: str,
) -> None:
    candidate = verified()
    candidate[field] = value
    with pytest.raises(SpineCiReuseError, match=message):
        can_reuse_verified_qualification(verified(), candidate)


def test_reuse_rejects_unverified_card_kind() -> None:
    candidate = verified()
    candidate["kind"] = "spine_ci_qualification"
    with pytest.raises(SpineCiReuseError, match="not verified"):
        can_reuse_verified_qualification(verified(), candidate)


def test_reuse_primitive_is_available_from_canonical_persistence_surface() -> None:
    from skeleton import persistence

    assert persistence.SpineCiReuseError is SpineCiReuseError
    assert (
        persistence.can_reuse_verified_qualification
        is can_reuse_verified_qualification
    )
    assert "SpineCiReuseError" in persistence.__all__
    assert "can_reuse_verified_qualification" in persistence.__all__


def test_reuse_rejects_cross_repository_or_policy_alias() -> None:
    foreign = verified()
    foreign["repository"] = "Other/Skeleton"
    assert can_reuse_verified_qualification(verified(), foreign) is False

    changed_policy = verified()
    changed_policy["required_check_policy_digest"] = "f" * 64
    assert can_reuse_verified_qualification(verified(), changed_policy) is False
