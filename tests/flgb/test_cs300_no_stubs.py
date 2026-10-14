import importlib
from pathlib import Path

import pytest

ROOT = Path("skeleton/cs300/layers")


def _card(layer_id: str, key: str, ordinal: int) -> dict:
    return {
        "layer": layer_id,
        "bound": 64,
        "stored_prose": 0,
        "authority_expansion": False,
        "finality": layer_id,
        "cases": {
            "normal": {key: 2},
            "adversarial": {"accepted": False},
            "boundary": {"at_bound": True},
            "failure": {"failed": True, "opened": False},
            "recovery": {"restored": True, "generation": ordinal},
        },
    }


def test_no_layer_delegates() -> None:
    for path in sorted(ROOT.glob("l*.py")):
        text = path.read_text()
        assert "def build" in text
        assert "from skeleton.cs300.contract import run" not in text
        assert "return run(" not in text


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_is_complete(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    receipt = module.build(_card(module.LAYER_ID, module.KEY, ordinal))
    assert receipt["built"] and receipt["stub"] is False
    assert receipt["cost"] == 2 + ordinal
    bad = _card(module.LAYER_ID, module.KEY, ordinal)
    bad["cases"]["recovery"]["generation"] = 0
    with pytest.raises(module.LayerReject):
        module.build(bad)
