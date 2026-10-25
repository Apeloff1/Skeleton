"""Regression contract for safe PyTorch game-inference checkpoint imports."""

from __future__ import annotations

import ast
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INFERENCE = ROOT / "skeleton" / "ai" / "runtime" / "inference"
LOAD_SITES = {
    "game_adaptive_ratchet.py": 1,
    "game_coherent_english.py": 2,
    "game_focus_finetune.py": 3,
    "game_map_variants.py": 2,
    "game_planetary_passes.py": 2,
}


@pytest.mark.parametrize(("filename", "expected"), sorted(LOAD_SITES.items()))
def test_game_checkpoint_loads_are_tensor_only(filename: str, expected: int) -> None:
    source = (INFERENCE / filename).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=filename)
    loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "torch"
        and node.func.attr == "load"
    ]
    assert len(loads) == expected
    for call in loads:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert isinstance(keywords.get("weights_only"), ast.Constant)
        assert keywords["weights_only"].value is True
        assert isinstance(keywords.get("map_location"), ast.Constant)
        assert keywords["map_location"].value == "cpu"


def test_checkpoint_primitives_round_trip_without_pickle_execution() -> None:
    torch = pytest.importorskip("torch")
    checkpoint = {
        "hidden": 4,
        "bytes_done": 17,
        "best_state": {"embedding.weight": torch.ones((2, 4))},
        "optimizer": {"state": {0: {"exp_avg": torch.zeros(4)}}},
        "sam_records": [{"domain": "rpg", "score": 0.9}],
        "replay": [("world", "dialogue")],
        "domain_ema": {"rpg": 0.5},
        "ratchet": {"recent": [1, 0, 1], "scale": 0.75},
    }
    handle = io.BytesIO()
    torch.save(checkpoint, handle)
    handle.seek(0)
    restored = torch.load(handle, map_location="cpu", weights_only=True)
    assert restored["hidden"] == checkpoint["hidden"]
    assert restored["sam_records"] == checkpoint["sam_records"]
    assert restored["replay"] == checkpoint["replay"]
    assert torch.equal(
        restored["best_state"]["embedding.weight"],
        checkpoint["best_state"]["embedding.weight"],
    )
