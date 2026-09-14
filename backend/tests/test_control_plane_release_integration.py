from core.product_control_plane import ProductControlPlane


def _deployment(artifact="release-artifact-v1"):
    return {
        "target": "product-runtime",
        "environment": "staging",
        "strategy": "rolling",
        "artifact": artifact,
    }


def test_authorization_does_not_mutate_bound_root_but_release_activation_does(tmp_path):
    plane = ProductControlPlane(tmp_path, bind_native_executors=False)
    before = plane.system_root()
    before_components = {row["name"]: row["sha256"] for row in before["components"]}

    prepared = plane.deployments.prepare(_deployment())
    after_prepare = plane.system_root()
    assert prepared.authorization.system_root_sha256 == before["root_sha256"]
    assert after_prepare["root_sha256"] == before["root_sha256"]

    executed = plane.deployments.execute(prepared.authorization.id, prepared.plan)
    after_execute = plane.system_root()
    after_components = {row["name"]: row["sha256"] for row in after_execute["components"]}

    assert executed.resumed is False
    assert after_execute["root_sha256"] != before["root_sha256"]
    assert before_components["deployments"] != after_components["deployments"]
    assert plane.deployments.status()["release_backend"]["releases"] == 1

    replay = plane.deployments.execute(prepared.authorization.id, prepared.plan)
    assert replay.resumed is True
    assert replay.release.release_id == executed.release.release_id
    assert plane.deployments.status()["release_backend"]["releases"] == 1
