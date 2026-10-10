from __future__ import annotations

import pytest

from skeleton.automation import architecture_fitness as compatibility
from skeleton.contracts import architecture_fitness as canonical
from skeleton.contracts.architecture_fitness import (
    FitnessError,
    FitnessFunction,
    FitnessRegistry,
    FitnessSeverity,
    FitnessStatus,
    FitnessViolation,
    FitnessWaiver,
)


def rule(
    *,
    rule_id: str = "RULE.NO_DIRECT_SQL",
    decision_ref: str = "ADR.DATA_ACCESS",
    pattern: str = r"\bsqlite3\.connect\(",
    severity: FitnessSeverity = FitnessSeverity.ERROR,
    include_paths: tuple[str, ...] = ("skeleton/*",),
    exclude_paths: tuple[str, ...] = (),
    max_matches_per_file: int = 100,
) -> FitnessFunction:
    return FitnessFunction(
        rule_id=rule_id,
        decision_ref=decision_ref,
        pattern=pattern,
        severity=severity,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        max_matches_per_file=max_matches_per_file,
    )


def registry() -> FitnessRegistry:
    return FitnessRegistry((rule(),))


def violation(
    *,
    path: str = "skeleton/service.py",
    text: str = "db = sqlite3.connect('state.db')",
) -> FitnessViolation:
    found = registry().evaluate(path, text)
    assert len(found) == 1
    return found[0]


def exact_waiver(
    subject: FitnessViolation,
    *,
    owner_id: str = "OWNER.RUNTIME",
    approver_id: str = "APPROVER.ARCH",
    issued_tick: int = 1,
    expires_tick: int = 10,
    rule_digest: str | None = None,
    violation_digest: str | None = None,
) -> FitnessWaiver:
    assert subject.rule_digest is not None
    return FitnessWaiver(
        rule_id=subject.rule_id,
        path=subject.path,
        owner_id=owner_id,
        reason="temporary migration bridge",
        expires_tick=expires_tick,
        violation_digest=violation_digest or subject.digest,
        rule_digest=rule_digest or subject.rule_digest,
        approver_id=approver_id,
        issued_tick=issued_tick,
    )


def test_automation_surface_has_no_parallel_authority() -> None:
    assert compatibility.__all__ == canonical.__all__
    for name in canonical.__all__:
        assert getattr(compatibility, name) is getattr(canonical, name)


def test_rule_violation_binds_exact_rule_content_and_match() -> None:
    subject = violation()
    assert subject.exact is True
    assert subject.rule_id == "RULE.NO_DIRECT_SQL"
    assert subject.decision_ref == "ADR.DATA_ACCESS"
    assert subject.path == "skeleton/service.py"
    assert subject.line == 1
    assert subject.column == 6
    assert subject.rule_digest is not None
    assert subject.content_digest is not None
    assert subject.match_digest is not None


def test_rule_scope_includes_and_excludes_paths() -> None:
    scoped = FitnessRegistry(
        (
            rule(
                include_paths=("skeleton/*",),
                exclude_paths=("skeleton/testing/*",),
            ),
        )
    )
    assert scoped.evaluate(
        "skeleton/runtime.py",
        "sqlite3.connect('x')",
    )
    assert (
        scoped.evaluate(
            "skeleton/testing/test_runtime.py",
            "sqlite3.connect('x')",
        )
        == ()
    )
    assert (
        scoped.evaluate(
            "docs/example.py",
            "sqlite3.connect('x')",
        )
        == ()
    )


def test_multiple_matches_are_deterministically_ordered() -> None:
    subject = registry().evaluate(
        "skeleton/service.py",
        "sqlite3.connect('a')\nvalue = 1\nsqlite3.connect('b')",
    )
    assert [(item.line, item.column) for item in subject] == [
        (1, 1),
        (3, 1),
    ]


def test_duplicate_rule_identity_rejected() -> None:
    item = rule()
    with pytest.raises(FitnessError, match="duplicate fitness rule"):
        FitnessRegistry((item, item))


def test_invalid_rule_regex_rejected() -> None:
    with pytest.raises(FitnessError, match="invalid rule pattern"):
        rule(pattern="(")


def test_duplicate_scope_globs_rejected() -> None:
    with pytest.raises(FitnessError, match="duplicate include"):
        rule(include_paths=("skeleton/*", "skeleton/*"))
    with pytest.raises(FitnessError, match="duplicate exclude"):
        rule(exclude_paths=("vendor/*", "vendor/*"))


def test_path_must_be_repository_relative_and_canonical() -> None:
    subject = registry()
    for bad in (
        "/absolute.py",
        "../escape.py",
        "skeleton/../escape.py",
        "skeleton\\file.py",
        "skeleton//file.py",
    ):
        with pytest.raises(FitnessError, match="repository-relative"):
            subject.evaluate(bad, "sqlite3.connect('x')")


def test_scan_text_must_be_string() -> None:
    with pytest.raises(TypeError, match="text must be str"):
        registry().evaluate(
            "skeleton/service.py",
            b"sqlite3.connect('x')",  # type: ignore[arg-type]
        )


def test_match_count_bound_fails_closed() -> None:
    bounded = FitnessRegistry(
        (
            rule(
                pattern="x",
                max_matches_per_file=2,
            ),
        )
    )
    with pytest.raises(FitnessError, match="match count"):
        bounded.evaluate("skeleton/a.py", "xxx")


def test_exact_active_waiver_resolves_one_violation() -> None:
    subject = violation()
    waiver = exact_waiver(subject)
    assert (
        registry().unresolved(
            (subject,),
            (waiver,),
            5,
        )
        == ()
    )


def test_legacy_broad_waiver_does_not_hide_violation() -> None:
    subject = violation()
    broad = FitnessWaiver(
        subject.rule_id,
        subject.path,
        "OWNER.RUNTIME",
        "old broad waiver",
        10,
    )
    assert broad.exact is False
    assert registry().unresolved((subject,), (broad,), 5) == (subject,)


def test_expired_waiver_does_not_hide_violation() -> None:
    subject = violation()
    waiver = exact_waiver(subject, expires_tick=4)
    assert registry().unresolved((subject,), (waiver,), 5) == (subject,)


def test_future_waiver_does_not_hide_violation() -> None:
    subject = violation()
    waiver = exact_waiver(
        subject,
        issued_tick=6,
        expires_tick=10,
    )
    assert registry().unresolved((subject,), (waiver,), 5) == (subject,)


def test_waiver_requires_independent_approver() -> None:
    subject = violation()
    waiver = exact_waiver(
        subject,
        owner_id="OWNER.RUNTIME",
        approver_id="OWNER.RUNTIME",
    )
    assert registry().unresolved((subject,), (waiver,), 5) == (subject,)


def test_waiver_bound_to_exact_rule_revision() -> None:
    subject = violation()
    waiver = exact_waiver(subject, rule_digest="0" * 64)
    assert registry().unresolved((subject,), (waiver,), 5) == (subject,)


def test_waiver_bound_to_exact_violation_digest() -> None:
    subject = violation()
    waiver = exact_waiver(subject, violation_digest="0" * 64)
    assert registry().unresolved((subject,), (waiver,), 5) == (subject,)


def test_changed_content_invalidates_old_waiver() -> None:
    first = violation(
        text="db = sqlite3.connect('state.db')",
    )
    waiver = exact_waiver(first)

    changed = violation(
        text="prefix = 1\ndb = sqlite3.connect('state.db')",
    )
    assert changed.digest != first.digest
    assert registry().unresolved((changed,), (waiver,), 5) == (changed,)


def test_changed_match_column_invalidates_old_waiver() -> None:
    first = violation(
        text="sqlite3.connect('state.db')",
    )
    waiver = exact_waiver(first)
    moved = violation(
        text="db = sqlite3.connect('state.db')",
    )
    assert moved.match_digest != first.match_digest
    assert registry().unresolved((moved,), (waiver,), 5) == (moved,)


def test_changed_rule_revision_invalidates_old_waiver() -> None:
    old_registry = registry()
    old_violation = old_registry.evaluate(
        "skeleton/service.py",
        "sqlite3.connect('x')",
    )[0]
    waiver = exact_waiver(old_violation)

    new_registry = FitnessRegistry(
        (
            rule(
                pattern=r"(?:sqlite3|sqlite)\.connect\(",
            ),
        )
    )
    new_violation = new_registry.evaluate(
        "skeleton/service.py",
        "sqlite3.connect('x')",
    )[0]
    assert new_violation.rule_digest != old_violation.rule_digest
    assert new_registry.unresolved(
        (new_violation,),
        (waiver,),
        5,
    ) == (new_violation,)


def test_warning_violation_produces_warn_status() -> None:
    warnings = FitnessRegistry(
        (
            rule(
                rule_id="RULE.DEBUG_PRINT",
                decision_ref="ADR.LOGGING",
                pattern=r"\bprint\(",
                severity=FitnessSeverity.WARNING,
            ),
        )
    )
    result = warnings.evaluate_file(
        "skeleton/service.py",
        "print('debug')",
    )
    assert result.status is FitnessStatus.WARN


def test_error_or_blocker_violation_produces_fail_status() -> None:
    result = registry().evaluate_file(
        "skeleton/service.py",
        "sqlite3.connect('x')",
    )
    assert result.status is FitnessStatus.FAIL

    blocker = FitnessRegistry(
        (
            rule(
                severity=FitnessSeverity.BLOCKER,
            ),
        )
    ).evaluate_file(
        "skeleton/service.py",
        "sqlite3.connect('x')",
    )
    assert blocker.status is FitnessStatus.FAIL


def test_exact_waiver_changes_file_status_to_pass() -> None:
    subject = violation()
    waiver = exact_waiver(subject)
    result = registry().evaluate_file(
        subject.path,
        "db = sqlite3.connect('state.db')",
        waivers=(waiver,),
        tick=5,
    )
    assert result.status is FitnessStatus.PASS
    assert result.waived_violation_digests == (subject.digest,)
    assert result.unresolved_violation_digests == ()


def test_file_result_surfaces_rejected_waiver_reason() -> None:
    subject = violation()
    broad = FitnessWaiver(
        subject.rule_id,
        subject.path,
        "OWNER.RUNTIME",
        "old broad waiver",
        10,
    )
    result = registry().evaluate_file(
        subject.path,
        "db = sqlite3.connect('state.db')",
        waivers=(broad,),
        tick=5,
    )
    assert result.status is FitnessStatus.FAIL
    assert any(
        item.reason == "waiver_not_exact" and not item.accepted
        for item in result.waiver_evaluations
    )


def test_repository_report_aggregates_file_status() -> None:
    report = registry().evaluate_repository(
        {
            "skeleton/clean.py": "value = 1",
            "skeleton/bad.py": "sqlite3.connect('x')",
        },
        tick=2,
    )
    assert report.status is FitnessStatus.FAIL
    assert report.unresolved_count == 1
    assert tuple(
        item.path for item in report.file_results
    ) == (
        "skeleton/bad.py",
        "skeleton/clean.py",
    )


def test_repository_report_identity_is_input_order_independent() -> None:
    first = registry().evaluate_repository(
        {
            "skeleton/a.py": "value = 1",
            "skeleton/b.py": "sqlite3.connect('x')",
        },
        tick=2,
    )
    second = registry().evaluate_repository(
        {
            "skeleton/b.py": "sqlite3.connect('x')",
            "skeleton/a.py": "value = 1",
        },
        tick=2,
    )
    assert first.digest == second.digest


def test_registry_identity_is_rule_order_independent() -> None:
    first = rule(
        rule_id="RULE.A",
        decision_ref="ADR.A",
        pattern="alpha",
    )
    second = rule(
        rule_id="RULE.B",
        decision_ref="ADR.B",
        pattern="beta",
    )
    assert FitnessRegistry((first, second)).digest == (
        FitnessRegistry((second, first)).digest
    )


def test_rule_revision_changes_registry_identity() -> None:
    first = registry().digest
    changed = FitnessRegistry(
        (
            rule(
                pattern=r"sqlite3\.connect\(",
                severity=FitnessSeverity.BLOCKER,
            ),
        )
    ).digest
    assert first != changed


def test_source_change_changes_file_result_identity() -> None:
    first = registry().evaluate_file(
        "skeleton/service.py",
        "sqlite3.connect('a')",
    )
    second = registry().evaluate_file(
        "skeleton/service.py",
        "sqlite3.connect('b')",
    )
    assert first.content_digest != second.content_digest
    assert first.digest != second.digest


def test_unknown_rule_query_fails_with_domain_error() -> None:
    with pytest.raises(FitnessError, match="unknown fitness rule"):
        registry().rule("RULE.UNKNOWN")


def test_waiver_tick_inputs_reject_boolean_aliases() -> None:
    subject = violation()
    with pytest.raises(FitnessError, match="issued_tick"):
        FitnessWaiver(
            subject.rule_id,
            subject.path,
            "OWNER.RUNTIME",
            "temporary bridge",
            10,
            subject.digest,
            subject.rule_digest,
            "APPROVER.ARCH",
            True,  # type: ignore[arg-type]
        )
    with pytest.raises(FitnessError, match="tick"):
        registry().unresolved((subject,), (), True)  # type: ignore[arg-type]


def test_waiver_cannot_be_issued_after_expiry() -> None:
    subject = violation()
    with pytest.raises(FitnessError, match="cannot exceed"):
        exact_waiver(
            subject,
            issued_tick=11,
            expires_tick=10,
        )


def test_invalid_rule_and_waiver_container_types_fail_closed() -> None:
    with pytest.raises(TypeError, match="FitnessFunction"):
        FitnessRegistry(("RULE.A",))  # type: ignore[arg-type]

    subject = violation()
    with pytest.raises(TypeError, match="FitnessViolation"):
        registry().unresolved(
            ("RULE.A",),  # type: ignore[arg-type]
            (),
            1,
        )
    with pytest.raises(TypeError, match="FitnessWaiver"):
        registry().unresolved(
            (subject,),
            ("WAIVER.A",),  # type: ignore[arg-type]
            1,
        )


def test_repository_file_values_must_be_text() -> None:
    with pytest.raises(TypeError, match="file contents"):
        registry().evaluate_repository(
            {
                "skeleton/a.py": b"value = 1",  # type: ignore[dict-item]
            }
        )


def test_violation_legacy_shape_is_not_exact_and_cannot_be_waived() -> None:
    legacy = FitnessViolation(
        "RULE.NO_DIRECT_SQL",
        "skeleton/service.py",
        1,
    )
    assert legacy.exact is False
    broad = FitnessWaiver(
        legacy.rule_id,
        legacy.path,
        "OWNER.RUNTIME",
        "legacy waiver",
        10,
    )
    assert registry().unresolved((legacy,), (broad,), 5) == (legacy,)
