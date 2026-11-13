"""Ensure the game-training checkpoint loaders cannot execute pickle globals.

This is a fail-closed source-level regression contract: the complete checkpoint
payloads (state_dict tensors, scalars, dictionaries and simple sequences) are
supported by the PyTorch weights-only unpickler.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_MODULES = (
    "game_adaptive_ratchet.py",
    "game_coherent_english.py",
    "game_focus_finetune.py",
    "game_map_variants.py",
    "game_planetary_passes.py",
)


@pytest.mark.parametrize("name", CHECKPOINT_MODULES)
def test_game_checkpoint_loads_are_explicitly_weights_only(name: str) -> None:
    path = ROOT / "skeleton" / "ai" / "runtime" / "inference" / name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    loads = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "load"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "torch"
    ]
    assert loads, f"{name}: expected training checkpoint loads"
    for node in loads:
        values = [arg.value for arg in node.keywords if arg.arg == "weights_only"]
        assert len(values) == 1, f"{name}:{node.lineno}: missing weights_only keyword"
        assert isinstance(values[0], ast.Constant), (
            f"{name}:{node.lineno}: weights_only must be a literal"
        )
        assert values[0].value is True, (
            f"{name}:{node.lineno}: unsafe checkpoint deserialization forbidden"
        )


def test_checkpoint_payload_remains_loadable_without_pickle_globals() -> None:
    """The real checkpoint shapes must be supported without unsafe fallback."""
    from collections import OrderedDict
    from io import BytesIO

    torch = pytest.importorskip("torch")
    payload = {
        "model": OrderedDict([("weight", torch.tensor([1, 2]))]),
        "best_state": {"weight": torch.tensor([1, 2])},
        "optimizer": {
            "state": {},
            "param_groups": [{"params": [0], "lr": 0.001, "betas": (0.9, 0.999)}],
        },
        "ratchet": {"margin": 0.1, "recent": [0, 1, 0]},
        "replay": [("game-world", "training text")],
        "sam_records": [{"text": "example", "approved": True}],
        "domain_ema": {"rpg": 0.9},
        "source_digest": None,
    }
    stream = BytesIO()
    torch.save(payload, stream)
    stream.seek(0)
    safe = torch.load(stream, map_location="cpu", weights_only=True)
    torch.testing.assert_close(safe["model"]["weight"], payload["model"]["weight"])
    assert safe["replay"] == payload["replay"]
    assert safe["optimizer"] == payload["optimizer"]


def test_checkpoint_rejects_non_allowlisted_python_objects() -> None:
    """A checkpoint with non-allowlisted Python globals must fail closed."""
    import pickle
    from io import BytesIO

    torch = pytest.importorskip("torch")
    stream = BytesIO()
    torch.save({"unexpected_object": Path("untrusted")}, stream)
    stream.seek(0)
    with pytest.raises(pickle.UnpicklingError):
        torch.load(stream, map_location="cpu", weights_only=True)
