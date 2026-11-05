import pytest
from skeleton.build.delivery.promotion import PromotionRequest, evaluate
from skeleton.build.delivery.release_history import ReleaseHistory

M = "1" * 64


def _histories():
    staging = ReleaseHistory("staging")
    staging.record(release_id="r1", manifest_digest=M, config_digest="c" * 64, outcome="deployed", recorded_at=1)
    return {"staging": staging}


def _req(**kw):
    base = dict(release_id="r1", version="1.0.0", manifest_digest=M, source_tier="staging",
                target_tier="production", approvals=("a", "b"), checks=(("smoke", "success"),))
    return PromotionRequest(**(base | kw))


def test_allowed():
    v = evaluate(_req(), histories=_histories(), required_checks=["smoke"])
    assert v.allowed, v.reasons


def test_reasons():
    v = evaluate(_req(approvals=("a", "a"), version="1.0.0-rc.1", manifest_digest="2" * 64),
                 histories=_histories(), required_checks=["smoke", "e2e"], freeze=True)
    assert not v.allowed
    assert set(v.reasons) == {"approvals:1<2", "prerelease-to-production", "manifest-mismatch",
                              "check:e2e:missing", "change-freeze"}


def test_cannot_skip_tiers_or_promote_unknown_release():
    v = evaluate(_req(source_tier="dev"), histories=_histories())
    assert "skip:dev->production" in v.reasons and "not-live-in-source" in v.reasons

def test_promotion_rejects_duplicate_and_invalid_caller_evidence():
    duplicated = _req(checks=(("smoke", "failure"), ("smoke", "success")))
    result = evaluate(duplicated, histories=_histories(), required_checks=["smoke"])
    assert not result.allowed and "duplicate-check-evidence" in result.reasons

    invalid = _req(approvals=("reviewer", None), checks=(("smoke", "success"),))
    result = evaluate(invalid, histories=_histories(), required_checks=["smoke"])
    assert not result.allowed and "invalid-approval-evidence" in result.reasons

    invalid_checks = _req(checks=(("smoke", "success"), ("invalid",)))
    result = evaluate(invalid_checks, histories=_histories(), required_checks=["smoke"])
    assert not result.allowed and "invalid-check-evidence" in result.reasons


def test_promotion_rejects_missing_or_unbounded_required_check_policy():
    from itertools import repeat
    from skeleton.ai.build.core.delivery import promotion as mirrored

    for evaluate_fn in (evaluate, mirrored.evaluate):
        absent = evaluate_fn(_req(), histories=_histories())
        assert not absent.allowed
        assert "required-check-policy-missing" in absent.reasons

        duplicated = evaluate_fn(
            _req(), histories=_histories(), required_checks=["smoke", "smoke"]
        )
        assert not duplicated.allowed
        assert "invalid-required-check-policy" in duplicated.reasons

        unbounded = evaluate_fn(
            _req(), histories=_histories(), required_checks=repeat("smoke")
        )
        assert not unbounded.allowed
        assert "invalid-required-check-policy" in unbounded.reasons
