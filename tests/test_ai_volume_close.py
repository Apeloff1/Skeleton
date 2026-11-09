"""Shippable close. The deferred tree is not claimed."""

from skeleton.ai.volume_close import close


def test_close() -> None:
    body = close()
    assert body["percent"] == 100
    assert body["claimed_lines"] == 280085289
    assert body["full_tree"] is False
    assert body["deferred"] == "x100_200_shards"
    assert body["stored_prose"] == 0
