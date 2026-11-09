"""gameforge-rs ``gf-gameforge::delta_memory`` parity (Pack J, round 2).

The RS crate ships no unit tests for ``DeltaMemory``; these encode its
observable contract as golden traces against
``/workspace/gameforge-rs/crates/gf-gameforge/src/lib.rs``:

- ``write``: push, then drain into the snapshot when ``len >= window_cap``
  (insert order, so last write wins) and bump ``compactions``.
- ``read`` returns ``Option<Value>``: ``Some(Null)`` != ``None``; values
  are clones (``.cloned()``), never shared references.
- ``stats``: exactly ``window_len`` / ``snapshot_keys`` / ``compactions``.
- ``Zaibatsu::new`` uses ``DeltaMemory::new(512)``.
"""

from __future__ import annotations

import math

import pytest

from skeleton.memory.delta_memory import DEFAULT_WINDOW_CAP, DeltaMemory

RS_STATS_KEYS = {"window_len", "snapshot_keys", "compactions"}


def _rs_reference_trace(cap, ops):
    """Literal transliteration of the RS write/read/stats bodies."""
    window, snapshot, compactions = [], {}, 0
    trace = []
    for op in ops:
        if op[0] == "w":
            window.append((op[1], op[2]))
            if len(window) >= cap:
                for k, v in window:
                    snapshot[k] = v
                window.clear()
                compactions += 1
        else:
            hit = next((v for k, v in reversed(window) if k == op[1]), None)
            found = hit is not None or any(k == op[1] for k, _ in window)
            if not found and op[1] in snapshot:
                found, hit = True, snapshot[op[1]]
            trace.append((found, hit))
        trace.append(
            {"window_len": len(window), "snapshot_keys": len(snapshot), "compactions": compactions}
        )
    return trace


OPS = [
    ("w", "a", 1), ("w", "b", 2), ("r", "a"), ("w", "a", 3),
    ("r", "a"), ("w", "c", None), ("r", "c"), ("r", "zz"),
    ("w", "b", {"n": 1}), ("w", "d", [1, 2]), ("r", "b"), ("w", "a", 9),
    ("w", "e", 0), ("r", "a"), ("r", "e"), ("w", "c", "x"), ("r", "c"),
]


@pytest.mark.parametrize("cap", [1, 2, 3, 4, 5, 7, 64])
@pytest.mark.parametrize("json_values", [False, True])
def test_golden_trace_matches_rs_reference(cap, json_values):
    dm = DeltaMemory(window_cap=cap, json_values=json_values)
    got = []
    for op in OPS:
        if op[0] == "w":
            dm.write(op[1], op[2])
        else:
            got.append(dm.lookup(op[1]))
        st = dm.stats()
        got.append({k: st[k] for k in RS_STATS_KEYS})
    assert got == _rs_reference_trace(cap, OPS)


def test_rs_stats_superset_and_default_cap():
    assert DEFAULT_WINDOW_CAP == 512  # Zaibatsu::new -> DeltaMemory::new(512)
    assert RS_STATS_KEYS <= set(DeltaMemory().stats())


def test_lookup_distinguishes_stored_null_from_absent():
    dm = DeltaMemory(window_cap=2)
    dm.write("n", None)
    assert dm.lookup("n") == (True, None)  # window: Some(Null)
    assert dm.lookup("missing") == (False, None)  # None
    dm.write("x", 1)  # compacts
    assert dm.stats()["window_len"] == 0
    assert dm.lookup("n") == (True, None)  # snapshot: Some(Null)
    assert dm.get("n", "dflt") is None
    assert dm.get("missing", "dflt") == "dflt"


def test_lookup_treats_tombstone_as_absent_and_counts_reads():
    dm = DeltaMemory(window_cap=8)
    dm.write("k", 1)
    dm.delete("k")
    before = dm.stats()["reads"]
    assert dm.lookup("k") == (False, None)
    assert dm.get("k", 7) == 7
    assert dm.stats()["reads"] == before + 2


def test_reference_mode_keeps_1649_identity_semantics():
    dm = DeltaMemory(window_cap=8)
    v = {"a": [1]}
    dm.write("k", v)
    assert dm.read("k") is v  # default mode unchanged: no copies


def test_json_mode_reads_are_independent_clones():
    dm = DeltaMemory(window_cap=2, json_values=True)
    src = {"a": [1]}
    dm.write("k", src)
    src["a"].append(2)  # caller mutation after write must not leak in
    out = dm.read("k")
    assert out == {"a": [1]}
    out["a"].append(3)  # mutation of a read result must not leak in
    dm.write("z", 0)  # compact; snapshot path must clone too
    assert dm.read("k") == {"a": [1]}
    assert dm.materialize()["k"] == {"a": [1]}
    dm.materialize()["k"]["a"].append(4)
    assert dm.items()[0] == ("k", {"a": [1]})


def test_json_mode_normalizes_like_serde_json():
    dm = DeltaMemory(window_cap=4, json_values=True)
    dm.write("t", (1, 2))
    dm.write("m", {1: "one"})
    assert dm.read("t") == [1, 2]
    assert dm.read("m") == {"1": "one"}


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, object(), {1, 2}])
def test_json_mode_rejects_unrepresentable_values_without_mutation(bad):
    dm = DeltaMemory(window_cap=2, json_values=True)
    dm.write("ok", 1)
    with pytest.raises((ValueError, TypeError)):
        dm.write("bad", bad)
    st = dm.stats()
    assert st["writes"] == 1 and st["window_len"] == 1
    assert dm.lookup("bad") == (False, None)


def test_json_mode_write_many_is_all_or_nothing():
    dm = DeltaMemory(window_cap=3, json_values=True)
    with pytest.raises(ValueError):
        dm.write_many([("a", 1), ("b", 2), ("c", math.nan), ("d", 4)])
    assert dm.stats()["writes"] == 0
    assert dm.stats()["compactions"] == 0
    assert dm.materialize() == {}


def test_json_mode_on_compact_hook_cannot_mutate_store():
    seen = []

    def hook(snap):
        snap["k"]["a"].append("hook")
        seen.append(snap)

    dm = DeltaMemory(window_cap=1, json_values=True, on_compact=hook)
    dm.write("k", {"a": []})
    assert seen and dm.read("k") == {"a": []}


def test_json_mode_load_state_and_apply_snapshot_validate():
    dm = DeltaMemory(window_cap=4, json_values=True)
    with pytest.raises(ValueError):
        dm.apply_snapshot({"x": math.nan})
    with pytest.raises(ValueError):
        dm.load_state({"snapshot": {"x": math.inf}})
    state = {"snapshot": {"a": [1]}, "window": [["b", {"c": 1}, False]]}
    dm.load_state(state)
    state["snapshot"]["a"].append(2)
    state["window"][0][1]["c"] = 99
    assert dm.read("a") == [1] and dm.read("b") == {"c": 1}
    exported = dm.export_state()
    exported["snapshot"]["a"].append(5)
    assert dm.read("a") == [1]
