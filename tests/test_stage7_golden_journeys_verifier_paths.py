from scripts.verify_stage7_golden_journeys import BOUNDARIES, MIRROR_PAIRS


def test_stage7_verifier_follows_canonical_frontier_stream_store() -> None:
    canonical = "skeleton/frontier/runtime/operation_stream_store_mongo.py"
    legacy = "skeleton/frontier/operation_stream_store_mongo.py"

    assert canonical in BOUNDARIES
    assert legacy not in BOUNDARIES
    assert any(
        source == canonical
        and mirror == "skeleton/ai/runtime/frontier/operation_stream_store_mongo.py"
        for source, mirror in MIRROR_PAIRS
    )
    assert all(source != legacy for source, _mirror in MIRROR_PAIRS)
