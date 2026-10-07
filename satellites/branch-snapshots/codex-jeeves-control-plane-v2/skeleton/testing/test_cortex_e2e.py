"""End-to-end cortex integration test — the heaviest path in the package.

Everything else in the cortex suite pins one subsystem in isolation; this
constructs a real JeevesCortex (tiny transformers, dim=8) and runs the full
think() pipeline: midbrain route → hemisphere fire → PFC → hive aggregate →
amalgam → own-system ingest → distill step → event emission.

If this goes green, the organism boots and thinks. If it fails, the failure
names which subsystem drifted.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def cortex():
    from skeleton.cortex.neocortex import JeevesCortex
    return JeevesCortex()


def test_cortex_constructs_with_local_slots(cortex):
    assert set(cortex.slots) >= {"pfc", "midbrain", "left", "right"}
    assert cortex.transformer is not None
    assert cortex.neo_rms is not None


def test_cortex_status_shape(cortex):
    status = cortex.status()
    assert "backends" in status
    assert "own" in status
    assert isinstance(status["backends"], dict)


def test_think_returns_full_trace(cortex):
    trace = cortex.think("plan a soulslike extraction run", {"era": "extraction_now"})
    d = trace.to_dict()
    assert d["stimulus"].startswith("plan a soulslike")
    assert d["fingerprint"]
    assert d["route"] is not None
    assert d["pfc"] is not None
    assert isinstance(d["used_own"], bool)
    assert 0.0 <= d["hive_value"]


def test_think_twice_grows_own_system(cortex):
    before = cortex.own.size
    cortex.think("ttk elite mix trash elite boss")
    cortex.think("second turn about extraction pacing")
    assert cortex.own.size > before


def test_recall_after_ingest(cortex):
    cortex.think("recall me: corridor ambush pacing")
    hits = cortex.recall("corridor ambush")
    # recall shape is a dict per neocortex.recall; own-system ingested the turn
    assert isinstance(hits, dict)


def test_genesis_cortex_handle_matches(cortex):
    """The genesis twin (fresh cortex) and this module cortex are the same class."""
    from skeleton.genesis import Genesis
    from skeleton.cortex.neocortex import JeevesCortex

    g = Genesis(seed=7).boot()
    handle = g.get("cortex")
    assert isinstance(handle, JeevesCortex)
    assert type(handle) is type(cortex)
