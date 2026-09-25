"""A corrupt filler snapshot is not an empty store, and a failed save is not success."""

import json
from pathlib import Path

import pytest

from skeleton.memory.warmer import Filler, FillerStore


def _filler() -> Filler:
    return Filler(key="prefix", sha="abc", text="law", tokens=1, ttl_s=10, built_at=1.0, refreshed_at=1.0)


def test_corrupt_snapshot_and_failed_save_raise(tmp_path: Path) -> None:
    broken = tmp_path / "fillers.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        FillerStore(broken)
    parent = tmp_path / "not-a-directory"
    parent.write_text("x", encoding="utf-8")
    store = FillerStore()
    store.path = parent / "fillers.json"
    with pytest.raises(OSError):
        store.put(_filler())
    good = tmp_path / "good.json"
    saved = FillerStore(good)
    saved.put(_filler())
    loaded = FillerStore(good)
    assert loaded.get("prefix") is not None
    assert json.loads(good.read_text(encoding="utf-8"))["fillers"]["prefix"]["sha"] == "abc"
