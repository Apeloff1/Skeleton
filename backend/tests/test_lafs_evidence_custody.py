"""Preserve knowledge evidence without lost updates or retrospective scoring."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from gameforge.lafs.lafs_engine import CabinetConflict, LeverArchFileSystem, ProbabilityState


class Collection:
    def __init__(self):
        self.doc = None

    def find_one(self, selector):
        return deepcopy(self.doc)

    def insert_one(self, doc):
        assert self.doc is None
        self.doc = deepcopy(doc)

    def replace_one(self, selector, doc, upsert=False):
        expected = selector["revision"]
        actual = self.doc.get("revision")
        matches = (actual == expected or expected == {"$exists": False} and "revision" not in self.doc)
        if matches:
            self.doc = deepcopy(doc)
        return SimpleNamespace(matched_count=int(matches))


def test_revision_fence_and_fresh_read(monkeypatch):
    col = Collection()
    a, b = LeverArchFileSystem(), LeverArchFileSystem()
    for ledger in (a, b):
        monkeypatch.setattr(ledger, "_col", lambda: col)
    first = a.add_sheet("Meta", "Reflection", {"content": "dragon"})
    assert b.stats()["total_sheets"] == 1
    a._load()
    b.add_sheet("Meta", "Reflection", {"content": "vault"})
    with pytest.raises(CabinetConflict):
        a._save()
    assert a.stats()["total_sheets"] == 2
    assert a.probability_search("dragon")[0]["id"] == first.id
    assert a.probability_search("no-such-evidence") == []


def test_forecasts_are_scored_before_evidence_and_invalid_updates_refused():
    state = ProbabilityState()
    state.update(1.0)
    assert state.forecast_log == [(0.5, 1.0)]
    assert state.brier_calibration() == pytest.approx(0.25)
    old = state.to_persist()
    for likelihood, weight in ((float("nan"), 1), (0.5, -1), (1.1, 1)):
        with pytest.raises(ValueError):
            state.update(likelihood, weight)
    assert state.to_persist() == old
    legacy = ProbabilityState.from_persist({"evidence_log": [0.8]})
    assert legacy.forecast_log == []


def test_graph_never_returns_start_node_and_missing_check_is_not_global(monkeypatch):
    ledger = LeverArchFileSystem()
    col = Collection()
    monkeypatch.setattr(ledger, "_col", lambda: col)
    first = ledger.add_sheet("Meta", "Reflection", {"content": "a"})
    second = ledger.add_sheet("Meta", "Reflection", {"content": "b"}, cross_refs=[first.id])
    assert [sheet.id for sheet in ledger.get_related(first.id, 2)] == [second.id]
    assert ledger.posterior_predictive_check("missing")["error"] == "sheet_not_found"
    assert ledger.posterior_predictive_check()["avg_brier"] is None
