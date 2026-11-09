import importlib

import pytest

from skeleton.cs300.registry import admit


def _card(layer_id: str, key: str) -> dict:
    card = {"layer": layer_id, "bound": 32, "evidence": key, "stored_prose": 0, key: 1}
    if layer_id.endswith("0"):
        card["finality"] = layer_id
    return card


@pytest.mark.parametrize("stratum", range(1, 31))
def test_stratum_module_admits_ten_and_rejects_gap(stratum: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.strata.s{stratum:02d}")
    assert len(module.LAYERS) == 10
    for layer_id, key in module.LAYERS.items():
        receipt = admit(layer_id, _card(layer_id, key))
        assert receipt["admitted"] and receipt["key"] == key
        bad = _card(layer_id, key)
        bad[key] = ""
        with pytest.raises(module.StratumReject):
            module.admit(layer_id, bad)
