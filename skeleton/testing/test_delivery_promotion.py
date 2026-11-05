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
