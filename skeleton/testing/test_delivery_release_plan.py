import hashlib

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.artifact_manifest import ArtifactEntry
from skeleton.build.delivery.release_plan import prepare

ART = [ArtifactEntry("skel.whl", "wheel", 3, hashlib.sha256(b"abc").hexdigest())]


def test_prepare_candidate():
    rc = prepare(product="skeleton", current_version="16.0.0", source_commit="e" * 40,
                 commits=[("1" * 40, "feat(build): delivery tooling"), ("2" * 40, "fix: x")],
                 artifacts=ART, date="2026-10-31")
    assert rc.version == "16.1.0"
    assert rc.manifest.release_id == "skeleton-16.1.0"
    assert dict(rc.manifest.metadata)["product"] == "skeleton"
    assert "delivery tooling" in rc.changelog


def test_no_changes():
    kw = dict(product="s", current_version="1.0.0", source_commit="e" * 40,
              commits=[("1" * 40, "ci: x")], artifacts=ART, date="2026-10-31")
    with pytest.raises(DeliveryError):
        prepare(**kw)
    assert prepare(**kw, allow_empty=True).version == "1.0.0"

def test_release_commit_provenance_is_unique_and_bounded(monkeypatch):
    from skeleton.build.delivery import release_plan as module

    kw = dict(product="s", current_version="1.0.0", source_commit="e" * 40,
              artifacts=ART, date="2026-10-31")
    for bad in (
        [("not-a-sha", "feat: invalid")],
        [("1" * 40, "feat: one"), ("1" * 40, "fix: duplicate")],
        [("1" * 40, 42)],
        [("1" * 40, "x" * (module.MAX_COMMIT_MESSAGE_CHARS + 1))],
        [("1" * 40,)],
    ):
        with pytest.raises(DeliveryError):
            prepare(**kw, commits=bad)
    monkeypatch.setattr(module, "MAX_RELEASE_COMMITS", 1)
    with pytest.raises(DeliveryError, match="inventory exceeds"):
        prepare(**kw, commits=[("1" * 40, "feat: one"),
                               ("2" * 40, "fix: two")])


def test_release_candidate_rejects_forged_product_metadata():
    from skeleton.ai.build.core.delivery import release_plan as mirrored

    kw = dict(
        product="skeleton", current_version="1.0.0", source_commit="e" * 40,
        commits=[("1" * 40, "feat: source")], artifacts=ART, date="2026-10-31",
    )
    for prepare_fn in (prepare, mirrored.prepare):
        with pytest.raises(DeliveryError, match="product metadata identity mismatch"):
            prepare_fn(**kw, metadata={"product": "attacker"})
        accepted = prepare_fn(**kw, metadata={"product": "skeleton", "channel": "stable"})
        assert dict(accepted.manifest.metadata)["product"] == "skeleton"
        assert accepted.manifest.release_id == "skeleton-1.1.0"
