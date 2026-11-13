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
