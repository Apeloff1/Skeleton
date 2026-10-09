import importlib

import pytest


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_module_admits_and_rejects(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    card = {"layer": module.LAYER_ID, "bound": 32, "stored_prose": 0, module.KEY: 1, "ordinal": ordinal}
    if module.FINALITY:
        card["finality"] = module.LAYER_ID
    receipt = module.admit(card)
    assert receipt["admitted"] and receipt["ordinal"] == ordinal
    bad = dict(card)
    bad[module.KEY] = ""
    with pytest.raises(module.LayerReject):
        module.admit(bad)
