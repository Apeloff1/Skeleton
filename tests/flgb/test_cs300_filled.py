import hashlib
import importlib
from pathlib import Path

import pytest

ROOT = Path("skeleton/cs300/layers")


def test_no_shared_trunk() -> None:
    bodies = set()
    for path in sorted(ROOT.glob("l*.py")):
        text = path.read_text()
        assert "from skeleton.cs300.contract import" not in text
        assert "return run(" not in text
        bodies.add(hashlib.sha256(text.encode()).hexdigest())
    assert len(bodies) == 300


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_fills_its_title(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    card = {
        "layer": module.LAYER_ID,
        "bound": 64,
        module.TITLE_KEY: 3,
        "stored_prose": 0,
        "authority_expansion": False,
        "adversary": False,
        "failed": False,
        "opened": False,
        "generation": ordinal,
        "finality": module.LAYER_ID,
    }
    receipt = module.build(card)
    assert receipt["built"] and receipt["trunk"] is False
    assert receipt["state"] == "restore"
    bad = dict(card)
    bad["generation"] = 0
    with pytest.raises(module.LayerReject):
        module.build(bad)
