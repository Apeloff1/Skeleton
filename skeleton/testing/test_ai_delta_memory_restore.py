from __future__ import annotations

import pytest

from skeleton.memory.delta_memory import DeltaMemory as CanonicalDeltaMemory
from skeleton.ai.runtime.memory.delta_memory import DeltaMemory as AIDeltaMemory


@pytest.mark.parametrize("memory_type",[CanonicalDeltaMemory,AIDeltaMemory])
def test_restore_rejects_malformed_window_without_partial_mutation(memory_type) -> None:
    memory=memory_type(window_cap=4,json_values=True)
    memory.write("existing",{"value":1})
    before=memory.export_state()

    corrupt={
        "version":1,
        "window_cap":4,
        "compactions":0,
        "writes":1,
        "reads":0,
        "deletes":0,
        "snapshot":{"new":{"value":2}},
        "window":[["valid",{"value":3},False],["broken"]],
    }

    with pytest.raises(ValueError,match="window entry 1"):
        memory.load_state(corrupt)

    assert memory.export_state()==before


@pytest.mark.parametrize("memory_type",[CanonicalDeltaMemory,AIDeltaMemory])
def test_restore_rejects_boolean_or_negative_counters(memory_type) -> None:
    memory=memory_type(window_cap=4)
    base=memory.export_state()

    boolean=dict(base)
    boolean["writes"]=True
    with pytest.raises(ValueError,match="writes"):
        memory.load_state(boolean)

    negative=dict(base)
    negative["deletes"]=-1
    with pytest.raises(ValueError,match="deletes"):
        memory.load_state(negative)


@pytest.mark.parametrize("memory_type",[CanonicalDeltaMemory,AIDeltaMemory])
def test_restore_rejects_truthy_non_boolean_tombstone(memory_type) -> None:
    memory=memory_type(window_cap=4)
    state=memory.export_state()
    state["window"]=[["key","value","yes"]]

    with pytest.raises(TypeError,match="tombstone flag"):
        memory.load_state(state)


@pytest.mark.parametrize("memory_type",[CanonicalDeltaMemory,AIDeltaMemory])
def test_restore_rejects_window_at_or_above_cap(memory_type) -> None:
    memory=memory_type(window_cap=2)
    state=memory.export_state()
    state["window"]=[
        ["a",1,False],
        ["b",2,False],
    ]

    with pytest.raises(ValueError,match="bounded-window invariant"):
        memory.load_state(state)


@pytest.mark.parametrize("memory_type",[CanonicalDeltaMemory,AIDeltaMemory])
def test_valid_export_restore_round_trip_is_exact(memory_type) -> None:
    source=memory_type(window_cap=4,json_values=True)
    source.write("snap",{"value":1})
    source.compact()
    source.write("live",[1,2,3])
    state=source.export_state()

    restored=memory_type(window_cap=9,json_values=True)
    restored.load_state(state)

    assert restored.export_state()==state
    assert restored.materialize()==source.materialize()
