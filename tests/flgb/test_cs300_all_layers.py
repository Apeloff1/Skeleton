import importlib

import pytest


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_module_builds_and_rejects(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    card = {
        "layer": module.LAYER_ID,
        "bound": 32,
        "stored_prose": 0,
        "authority_expansion": False,
        "finality": module.LAYER_ID,
        "cases": {
            "normal": {module.KEY: 1},
            "adversarial": {"accepted": False},
            "boundary": {"at_bound": True},
            "failure": {"failed": True, "opened": False},
            "recovery": {"restored": True, "generation": ordinal},
        },
    }
    assert module.build(card)["built"]
    bad = dict(card)
    bad["cases"] = dict(card["cases"])
    bad["cases"]["recovery"] = {"restored": False, "generation": ordinal}
    with pytest.raises(module.LayerReject):
        module.build(bad)
