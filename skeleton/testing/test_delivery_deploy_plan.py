import hashlib

import pytest

from skeleton.build.delivery._util import DeliveryError
from skeleton.build.delivery.artifact_manifest import ArtifactEntry, build_manifest
from skeleton.build.delivery.deploy_plan import compile_plan
from skeleton.build.delivery.env_config import resolve

BASE = {"tier": "staging", "replicas": 4, "health": {"path": "/h"}}


def _manifest(version="1.0.0"):
    e = ArtifactEntry("a.whl", "wheel", 1, hashlib.sha256(b"a").hexdigest())
    return build_manifest(release_id="r1", version=version, source_commit="f" * 40, artifacts=[e])


def _env(rollout, tier="staging"):
    return resolve("e", {"e": BASE | {"tier": tier, "rollout": rollout}})


def _kinds(plan):
    return [s.kind for s in plan.steps]


def test_rolling_batches():
    plan = compile_plan(_manifest(), _env({"strategy": "rolling", "max_unavailable": 2, "bake_seconds": 0}))
    pcts = [dict(s.params)["percent"] for s in plan.steps if s.kind == "shift-traffic"]
    assert pcts == [50, 100]
    assert _kinds(plan)[0] == "lock" and _kinds(plan)[-1] == "unlock"


def test_canary_with_bake():
    plan = compile_plan(_manifest(), _env({"strategy": "canary", "stages": [10, 100], "bake_seconds": 60}))
    assert _kinds(plan)[4:] == ["shift-traffic", "health-gate", "bake", "shift-traffic", "health-gate", "finalize", "unlock"]


def test_blue_green_single_switch():
    plan = compile_plan(_manifest(), _env({"strategy": "blue-green"}))
    assert _kinds(plan).count("shift-traffic") == 1
    assert plan.steps[3].target == "green"


def test_plan_digest_binds_inputs():
    env = _env({"strategy": "blue-green"})
    a = compile_plan(_manifest(), env)
    b = compile_plan(_manifest(), env)
    assert a.digest == b.digest and a.config_digest == env.digest
    assert '"digest"' in a.serialize()


def test_rejections():
    with pytest.raises(DeliveryError):
        compile_plan(_manifest(), _env({"strategy": "canary", "stages": [50, 10]}))
    with pytest.raises(DeliveryError):
        compile_plan(_manifest(), _env({"strategy": "canary", "stages": [10, 50]}))
    with pytest.raises(DeliveryError, match="prerelease"):
        compile_plan(_manifest("1.0.0-rc.1"), _env({"strategy": "blue-green"}, tier="production"))
