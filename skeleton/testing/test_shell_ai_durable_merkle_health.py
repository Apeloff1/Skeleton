"""Inspection-only durable Merkle health guard tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.durable_merkle_health import (
    DurableMerkleHealthError,
    DurableMerkleHealthFinding,
    DurableMerkleHealthGuard,
    DurableMerkleHealthPolicy,
    DurableMerkleHealthReport,
    DurableMerkleHealthSeverity,
)
from skeleton.shells.ai.durable_merkle_operator import (
    DurableMerkleOperatorResult,
    DurableMerkleOperatorStatus,
    DurableSessionMerkleOperator,
)


def fp(char: str) -> str:
    return char * 64


def operator_result(
    finalization_id: str,
    status: DurableMerkleOperatorStatus,
) -> DurableMerkleOperatorResult:
    if status is DurableMerkleOperatorStatus.VERIFIED:
        from skeleton.shells.ai.durable_merkle_session import (
            DurableSessionMerkleVerification,
        )

        verification = DurableSessionMerkleVerification(
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            2,
            1,
            (),
        )
        return DurableMerkleOperatorResult(
            finalization_id,
            f"session-{finalization_id}",
            status,
            fp("a"),
            1,
            False,
            False,
            fp("b"),
            2,
            1,
            verification,
            (),
        )
    return DurableMerkleOperatorResult(
        finalization_id,
        f"session-{finalization_id}",
        status,
        "",
        None,
        False,
        False,
        fp("b"),
        0,
        0,
        None,
        (
            f"state is {status.value}",
        ),
    )


class FakeOperator(
    DurableSessionMerkleOperator
):
    def __init__(
        self,
        reports: dict[
            str,
            DurableMerkleOperatorResult,
        ],
        *,
        raise_for: set[str] | None = None,
    ):
        self.reports = dict(reports)
        self.raise_for = set(
            raise_for or ()
        )
        self.inspected: list[str] = []
        self.prepare_calls = 0

    def inspect(
        self,
        finalization_id: str,
    ) -> DurableMerkleOperatorResult:
        self.inspected.append(
            finalization_id
        )
        if finalization_id in self.raise_for:
            raise RuntimeError(
                "synthetic operator failure"
            )
        return self.reports[
            finalization_id
        ]

    def prepare(
        self,
        finalization_id: str,
    ):
        self.prepare_calls += 1
        raise AssertionError(
            "health guard must not prepare bundles"
        )


def guard(
    reports,
    *,
    policy=None,
    raise_for=None,
):
    operator = FakeOperator(
        reports,
        raise_for=raise_for,
    )
    return (
        DurableMerkleHealthGuard(
            operator,
            policy,
        ),
        operator,
    )


def test_default_policy_allows_verified():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        )
    }
    health, operator = guard(reports)
    report = health.require(["a"])
    assert report.allowed
    assert report.verified == 1
    assert report.missing == 0
    assert report.incomplete == 0
    assert report.manual_review == 0
    assert report.errors == 0
    assert operator.prepare_calls == 0


def test_default_policy_allows_optional_missing_with_warning():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.MISSING,
        )
    }
    health, operator = guard(reports)
    report = health.require(["a"])
    assert report.allowed
    assert report.missing == 1
    assert report.warnings >= 1
    assert report.errors == 0
    assert any(
        finding.code
        == "merkle_health.missing_optional"
        for finding in report.findings
    )
    assert operator.prepare_calls == 0


def test_required_bundle_policy_blocks_missing():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.MISSING,
        )
    }
    policy = DurableMerkleHealthPolicy(
        require_bundles=True,
        maximum_missing=0,
    )
    health, _ = guard(
        reports,
        policy=policy,
    )
    report = health.inspect(["a"])
    assert not report.allowed
    assert report.errors >= 1
    with pytest.raises(
        DurableMerkleHealthError,
        match="missing",
    ):
        health.require(["a"])


def test_manual_review_always_blocks():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.MANUAL_REVIEW,
        )
    }
    health, _ = guard(reports)
    report = health.inspect(["a"])
    assert not report.allowed
    assert report.manual_review == 1
    assert report.errors >= 1
    assert any(
        finding.code
        == "merkle_health.manual_review"
        for finding in report.findings
    )


def test_default_policy_blocks_incomplete():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.INCOMPLETE,
        )
    }
    health, _ = guard(reports)
    report = health.inspect(["a"])
    assert not report.allowed
    assert report.incomplete == 1
    assert any(
        finding.code
        == "merkle_health.incomplete_bound"
        for finding in report.findings
    )


def test_policy_can_tolerate_bounded_incomplete():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.INCOMPLETE,
        )
    }
    policy = DurableMerkleHealthPolicy(
        maximum_incomplete=1,
    )
    health, _ = guard(
        reports,
        policy=policy,
    )
    report = health.require(["a"])
    assert report.allowed
    assert report.incomplete == 1
    assert report.errors == 0
    assert report.warnings >= 1


def test_incomplete_above_bound_blocks():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.INCOMPLETE,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.INCOMPLETE,
        ),
    }
    policy = DurableMerkleHealthPolicy(
        maximum_incomplete=1,
    )
    report = guard(
        reports,
        policy=policy,
    )[0].inspect(["a", "b"])
    assert not report.allowed
    assert report.incomplete == 2
    assert report.errors >= 1


def test_missing_above_bound_blocks_even_when_optional():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.MISSING,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.MISSING,
        ),
    }
    policy = DurableMerkleHealthPolicy(
        maximum_missing=1,
    )
    report = guard(
        reports,
        policy=policy,
    )[0].inspect(["a", "b"])
    assert not report.allowed
    assert report.missing == 2
    assert any(
        finding.code
        == "merkle_health.missing_bound"
        for finding in report.findings
    )


def test_minimum_verified_is_enforced():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.MISSING,
        ),
    }
    policy = DurableMerkleHealthPolicy(
        minimum_verified=2,
    )
    report = guard(
        reports,
        policy=policy,
    )[0].inspect(["a", "b"])
    assert not report.allowed
    assert report.verified == 1
    assert any(
        finding.code
        == "merkle_health.minimum_verified"
        for finding in report.findings
    )


def test_require_nonempty_blocks_empty_set():
    policy = DurableMerkleHealthPolicy(
        require_nonempty=True,
    )
    report = guard(
        {},
        policy=policy,
    )[0].inspect(())
    assert not report.allowed
    assert any(
        finding.code
        == "merkle_health.empty_required_set"
        for finding in report.findings
    )


def test_empty_set_allowed_by_default():
    report = guard({})[0].require(())
    assert report.allowed
    assert report.finalization_ids == ()
    assert report.reports == ()


def test_ids_are_sorted_before_inspection():
    reports = {
        name: operator_result(
            name,
            DurableMerkleOperatorStatus.VERIFIED,
        )
        for name in ("a", "b", "c")
    }
    health, operator = guard(reports)
    report = health.inspect(
        ("c", "a", "b")
    )
    assert report.finalization_ids == (
        "a",
        "b",
        "c",
    )
    assert operator.inspected == [
        "a",
        "b",
        "c",
    ]


def test_duplicate_ids_rejected():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        )
    }
    with pytest.raises(
        ValueError,
        match="duplicate",
    ):
        guard(reports)[0].inspect(
            ("a", "a")
        )


@pytest.mark.parametrize(
    "value",
    ["", "x" * 257, 3],
)
def test_invalid_finalization_id_rejected(value):
    with pytest.raises(
        ValueError,
        match="invalid",
    ):
        guard({})[0].inspect(
            (value,)
        )


def test_finalization_bound_enforced():
    policy = DurableMerkleHealthPolicy(
        max_finalizations=2,
    )
    reports = {
        name: operator_result(
            name,
            DurableMerkleOperatorStatus.VERIFIED,
        )
        for name in ("a", "b", "c")
    }
    with pytest.raises(
        ValueError,
        match="bound exceeded",
    ):
        guard(
            reports,
            policy=policy,
        )[0].inspect(
            ("a", "b", "c")
        )


def test_probe_exception_becomes_manual_review():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        )
    }
    health, _ = guard(
        reports,
        raise_for={"a"},
    )
    report = health.inspect(["a"])
    assert not report.allowed
    assert report.manual_review == 1
    assert report.reports[0].status is (
        DurableMerkleOperatorStatus.MANUAL_REVIEW
    )
    assert any(
        "operator raised RuntimeError"
        in issue
        for issue in report.reports[0].issues
    )


def test_health_guard_never_calls_prepare():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.MISSING,
        )
    }
    health, operator = guard(reports)
    health.inspect(["a"])
    assert operator.prepare_calls == 0


def test_health_report_digest_is_deterministic():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.MISSING,
        ),
    }
    health, _ = guard(reports)
    first = health.inspect(
        ("b", "a")
    )
    second = health.inspect(
        ("a", "b")
    )
    assert first.digest == second.digest
    assert first == second


def test_health_report_serialization():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        )
    }
    report = guard(reports)[0].inspect(
        ["a"]
    )
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["verified"] == 1
    assert data["missing"] == 0
    assert data["incomplete"] == 0
    assert data["manual_review"] == 0
    assert data["digest"] == report.digest


def test_health_report_digest_excludes_recursive_digest():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        )
    }
    report = guard(reports)[0].inspect(
        ["a"]
    )
    assert "digest" not in report.to_dict(
        include_digest=False
    )


def test_policy_digest_is_deterministic():
    first = DurableMerkleHealthPolicy()
    second = DurableMerkleHealthPolicy()
    assert first.digest == second.digest


def test_policy_digest_changes_with_requirement():
    first = DurableMerkleHealthPolicy()
    second = DurableMerkleHealthPolicy(
        require_bundles=True,
        maximum_missing=0,
    )
    assert first.digest != second.digest


def test_policy_serialization():
    policy = DurableMerkleHealthPolicy(
        max_finalizations=10,
        require_nonempty=True,
        maximum_missing=3,
        maximum_incomplete=2,
        minimum_verified=1,
    )
    assert policy.to_dict() == {
        "max_finalizations": 10,
        "require_nonempty": True,
        "require_bundles": False,
        "maximum_missing": 3,
        "maximum_incomplete": 2,
        "minimum_verified": 1,
        "reject_manual_review": True,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_finalizations", 0),
        ("max_finalizations", True),
        ("maximum_missing", -1),
        ("maximum_incomplete", -1),
        ("minimum_verified", -1),
    ],
)
def test_policy_count_validation(field, value):
    values = {
        "max_finalizations": 512,
        "require_nonempty": False,
        "require_bundles": False,
        "maximum_missing": 512,
        "maximum_incomplete": 0,
        "minimum_verified": 0,
        "reject_manual_review": True,
    }
    values[field] = value
    with pytest.raises(ValueError):
        DurableMerkleHealthPolicy(
            **values
        )


@pytest.mark.parametrize(
    "field",
    [
        "maximum_missing",
        "maximum_incomplete",
        "minimum_verified",
    ],
)
def test_policy_limits_may_not_exceed_maximum(field):
    values = {
        "max_finalizations": 2,
        "maximum_missing": 2,
        "maximum_incomplete": 0,
        "minimum_verified": 0,
    }
    values[field] = 3
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        DurableMerkleHealthPolicy(
            **values
        )


@pytest.mark.parametrize(
    "field",
    [
        "require_nonempty",
        "require_bundles",
        "reject_manual_review",
    ],
)
def test_policy_bool_validation(field):
    values = {
        "require_nonempty": False,
        "require_bundles": False,
        "reject_manual_review": True,
    }
    values[field] = "yes"
    with pytest.raises(
        ValueError,
        match="bool",
    ):
        DurableMerkleHealthPolicy(
            **values
        )


def test_policy_reject_manual_review_cannot_be_disabled():
    with pytest.raises(
        ValueError,
        match="manual-review",
    ):
        DurableMerkleHealthPolicy(
            reject_manual_review=False
        )


def test_require_bundles_requires_zero_missing_budget():
    with pytest.raises(
        ValueError,
        match="maximum_missing=0",
    ):
        DurableMerkleHealthPolicy(
            require_bundles=True,
        )


def test_guard_constructor_validates_operator():
    with pytest.raises(
        TypeError,
        match="operator",
    ):
        DurableMerkleHealthGuard(
            object()
        )


def test_guard_constructor_validates_policy():
    operator = FakeOperator({})
    with pytest.raises(
        TypeError,
        match="policy",
    ):
        DurableMerkleHealthGuard(
            operator,
            object(),
        )


def test_finding_serialization():
    finding = DurableMerkleHealthFinding(
        DurableMerkleHealthSeverity.WARNING,
        "merkle.warning",
        "warning",
        "finalization",
    )
    assert finding.to_dict() == {
        "severity": "warning",
        "code": "merkle.warning",
        "message": "warning",
        "finalization_id": "finalization",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("code", ""),
        ("code", "x" * 129),
        ("message", ""),
        ("message", "x" * 2049),
        ("finalization_id", "x" * 257),
    ],
)
def test_finding_validation(field, value):
    values = {
        "severity": DurableMerkleHealthSeverity.WARNING,
        "code": "code",
        "message": "message",
        "finalization_id": "",
    }
    values[field] = value
    with pytest.raises(ValueError):
        DurableMerkleHealthFinding(
            **values
        )


def test_report_validates_sorted_ids():
    with pytest.raises(
        ValueError,
        match="sorted",
    ):
        DurableMerkleHealthReport(
            fp("p"),
            ("b", "a"),
            (
                operator_result(
                    "b",
                    DurableMerkleOperatorStatus.VERIFIED,
                ),
                operator_result(
                    "a",
                    DurableMerkleOperatorStatus.VERIFIED,
                ),
            ),
            (),
        )


def test_report_validates_report_identity_order():
    with pytest.raises(
        ValueError,
        match="reports",
    ):
        DurableMerkleHealthReport(
            fp("p"),
            ("a", "b"),
            (
                operator_result(
                    "b",
                    DurableMerkleOperatorStatus.VERIFIED,
                ),
                operator_result(
                    "a",
                    DurableMerkleOperatorStatus.VERIFIED,
                ),
            ),
            (),
        )


def test_report_validates_policy_digest():
    with pytest.raises(
        ValueError,
        match="policy_digest",
    ):
        DurableMerkleHealthReport(
            "bad",
            (),
            (),
            (),
        )


@pytest.mark.parametrize(
    "status",
    [
        DurableMerkleOperatorStatus.VERIFIED,
        DurableMerkleOperatorStatus.MISSING,
        DurableMerkleOperatorStatus.INCOMPLETE,
        DurableMerkleOperatorStatus.MANUAL_REVIEW,
    ],
)
def test_count_properties_partition_reports(status):
    reports = {
        "a": operator_result(
            "a",
            status,
        )
    }
    report = guard(
        reports,
        policy=(
            DurableMerkleHealthPolicy(
                maximum_missing=1,
                maximum_incomplete=1,
            )
        ),
    )[0].inspect(["a"])
    total = (
        report.verified
        + report.missing
        + report.incomplete
        + report.manual_review
    )
    assert total == 1


def test_mixed_rollout_mode_counts_all_states():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.MISSING,
        ),
        "c": operator_result(
            "c",
            DurableMerkleOperatorStatus.INCOMPLETE,
        ),
        "d": operator_result(
            "d",
            DurableMerkleOperatorStatus.MANUAL_REVIEW,
        ),
    }
    policy = DurableMerkleHealthPolicy(
        max_finalizations=4,
        maximum_missing=1,
        maximum_incomplete=1,
    )
    report = guard(
        reports,
        policy=policy,
    )[0].inspect(
        ("d", "c", "b", "a")
    )
    assert report.verified == 1
    assert report.missing == 1
    assert report.incomplete == 1
    assert report.manual_review == 1
    assert not report.allowed


def test_strict_rollout_mode_requires_every_bundle():
    reports = {
        "a": operator_result(
            "a",
            DurableMerkleOperatorStatus.VERIFIED,
        ),
        "b": operator_result(
            "b",
            DurableMerkleOperatorStatus.VERIFIED,
        ),
    }
    policy = DurableMerkleHealthPolicy(
        max_finalizations=2,
        require_nonempty=True,
        require_bundles=True,
        maximum_missing=0,
        maximum_incomplete=0,
        minimum_verified=2,
    )
    report = guard(
        reports,
        policy=policy,
    )[0].require(
        ("b", "a")
    )
    assert report.allowed
    assert report.verified == 2
    assert report.errors == 0
    assert report.warnings == 0
