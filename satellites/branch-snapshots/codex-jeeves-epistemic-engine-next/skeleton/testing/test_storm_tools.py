"""F-9: N+1 tool-call storm suppression via Storm + DedupLedger."""

from __future__ import annotations

from skeleton.kernel.bank import boot, get, reset
from skeleton.kernel.orchestrator import Orchestrator
from skeleton.kernel.storm import Storm


def test_admit_tool_allows_first_and_drops_identical():
    storm = Storm(ttl_s=60.0)
    assert storm.admit_tool("search", {"q": "bonfire"}) is True
    assert storm.admit_tool("search", {"q": "bonfire"}) is False
    assert storm.admit_tool("search", {"q": "other"}) is True
    assert storm.admit_tool("fetch", {"q": "bonfire"}) is True
    card = storm.card()
    assert card["tool_seen"] == 3
    assert card["tool_drop"] == 1


def test_admit_tool_args_order_independent():
    storm = Storm(ttl_s=60.0)
    assert storm.admit_tool("write", {"a": 1, "b": 2}) is True
    assert storm.admit_tool("write", {"b": 2, "a": 1}) is False
    assert storm.tool_drop_n == 1


def test_batch_tools_collapses_identical_in_turn():
    storm = Storm(ttl_s=60.0)
    calls = [
        {"name": "search", "args": {"q": "x"}},
        {"name": "search", "args": {"q": "x"}},
        {"name": "search", "args": {"q": "y"}},
        {"name": "search", "args": {"q": "x"}},
    ]
    batched = storm.batch_tools(calls)
    assert len(batched) == 2
    assert batched[0]["name"] == "search"
    assert batched[0]["args"] == {"q": "x"}
    assert batched[0]["batch_n"] == 3
    assert batched[1]["args"] == {"q": "y"}
    assert batched[1]["batch_n"] == 1
    assert storm.tool_batch_collapsed_n == 2
    assert storm.tool_drop_n == 2
    # Second batch in same window drops the already-seen identity entirely.
    again = storm.batch_tools([{"name": "search", "args": {"q": "x"}}])
    assert again == []
    assert storm.tool_drop_n == 3


def test_text_stimulus_admit_still_green():
    """Existing Storm stimulus path must stay green (orch dispatch gate)."""
    storm = Storm(ttl_s=60.0)
    assert storm.admit("plan tensor ttk") is True
    assert storm.admit("plan tensor ttk") is False
    assert storm.admit("other stimulus") is True
    assert storm.seen_n == 2
    assert storm.drop_n == 1
    # Tool ledger is independent of text ledger.
    assert storm.admit_tool("search", {"q": "plan tensor ttk"}) is True
    assert storm.admit("plan tensor ttk") is False


def test_orchestrator_wire_admit_and_batch():
    reset()
    boot("mobile")
    orch = Orchestrator()
    assert orch.admit_tool("mesh.route", {"cap": "translate"}) is True
    assert orch.admit_tool("mesh.route", {"cap": "translate"}) is False
    batched = orch.batch_tools(
        [
            {"name": "vault.read", "args": {"k": "a"}},
            {"name": "vault.read", "args": {"k": "a"}},
            {"name": "vault.read", "args": {"k": "b"}},
        ]
    )
    assert len(batched) == 2
    assert batched[0]["batch_n"] == 2
    storm = get("storm")
    assert storm is not None
    assert storm.card()["tool_seen"] >= 3
    assert storm.card()["tool_drop"] >= 2


def test_dispatch_stimulus_storm_still_drops_duplicates():
    reset()
    orch = Orchestrator()
    first = orch.dispatch("unique f9 stimulus alpha", once=True)
    second = orch.dispatch("unique f9 stimulus alpha", once=True)
    assert first.get("dropped") != 1
    assert second.get("dropped") == 1
    assert second.get("reason") == "storm"
