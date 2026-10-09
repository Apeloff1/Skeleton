import importlib

import pytest

from skeleton.cs300.contract import CASES, ContractReject


def _card(layer_id: str, key: str) -> dict:
    return {
        "layer": layer_id,
        "bound": 32,
        "stored_prose": 0,
        "authority_expansion": False,
        "finality": layer_id,
        "cases": {
            "normal": {key: 1},
            "adversarial": {"accepted": False},
            "boundary": {"at_bound": True},
            "failure": {"failed": True, "opened": False},
            "recovery": {"restored": True},
        },
    }


@pytest.mark.parametrize("ordinal", range(1, 301))
def test_layer_builds_ladder_cases(ordinal: int) -> None:
    module = importlib.import_module(f"skeleton.cs300.layers.l{ordinal:03d}")
    receipt = module.build(_card(module.LAYER_ID, module.KEY))
    assert receipt["built"] and receipt["cases"] == list(CASES)
    bad = _card(module.LAYER_ID, module.KEY)
    bad["authority_expansion"] = True
    with pytest.raises(ContractReject):
        module.build(bad)
