import importlib

import pytest


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_builds_ladder_cases(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    card = {
        "layer": module.LAYER_ID,
        "bound": 64,
        module.TITLE_KEY: 1,
        "stored_prose": 0,
        "authority_expansion": False,
        "adversary": False,
        "generation": ordinal,
        "finality": module.LAYER_ID,
    }
    receipt = module.build(card)
    assert receipt["built"] and receipt["state"] == "restore"
    bad = dict(card)
    bad["generation"] = 0
    with pytest.raises(module.LayerReject):
        module.build(bad)
