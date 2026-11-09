import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.payloads import json_snapshot


@pytest.mark.asyncio
async def test_nested_memory_is_detached_on_both_write_and_read():
    store = InMemoryStore()
    payload = {"text": "hello", "nested": {"values": [1]}}
    item_id = await store.put(payload)
    payload["nested"]["values"].append(2)
    result = (await store.search("hello"))[0]
    assert result["id"] == item_id
    result["nested"]["values"].append(3)
    assert (await store.search("hello"))[0]["nested"] == {"values": [1]}


@pytest.mark.asyncio
async def test_capacity_rejects_new_items_but_permits_upsert_and_delete():
    store = InMemoryStore(capacity=1)
    await store.put({"id": "a", "text": "old"})
    with pytest.raises(OverflowError):
        await store.put({"id": "b"})
    await store.put({"id": "a", "text": "new"})
    assert await store.search("old") == []
    await store.delete("a")
    await store.put({"id": "b"})


@pytest.mark.parametrize("payload", [{1: "x"}, {"x": float("nan")}, {"x": object()}, {"x": (1, 2)}])
def test_payload_rejects_non_json_values(payload):
    with pytest.raises(ValueError):
        json_snapshot(payload)


def test_payload_checks_utf8_byte_size_and_cyclic_nesting():
    with pytest.raises(ValueError, match="bytes"):
        json_snapshot({"text": "å" * 10}, max_bytes=15)
    cycle = []
    cycle.append(cycle)
    with pytest.raises(ValueError, match="nesting"):
        json_snapshot(cycle)
