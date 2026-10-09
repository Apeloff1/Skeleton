import pytest

from skeleton.cs300.layers import LayerReject, admit, layer_ids, stratum_of


def _card(layer_id: str) -> dict:
    stratum = stratum_of(layer_id)
    card = {"layer": layer_id, "bound": 64, "evidence": "skeleton/cs300/layers.py", "stored_prose": 0}
    extras = {
        1: {"halt_claim": False},
        2: {"fanout": 4},
        3: {"sound": True},
        4: {"ir": "ssa"},
        5: {"sandbox": True},
        6: {"privilege": "user"},
        7: {"race_free": True},
        8: {"quorum": 3},
        9: {"checksum": "crc"},
        10: {"durable": True},
        11: {"isolation": "ser"},
        12: {"watermark": "t"},
        13: {"rate": 2},
        14: {"nonce": "n", "secret": ""},
        15: {"proof_id": "p"},
        16: {"coupling": 2},
        17: {"checkpoint": "c"},
        18: {"sample": 1},
        19: {"unsigned": False},
        20: {"purpose": "ops"},
        21: {"nan_policy": "fail"},
        22: {"occupancy": 1},
        23: {"device": "cpu"},
        24: {"cold_start": 1},
        25: {"deadline": "d"},
        26: {"frame": 1},
        27: {"decoherence": 1},
        28: {"spikes": 1},
        29: {"budget": "b"},
        30: {"reproduction": "r"},
    }[stratum]
    card.update(extras)
    if layer_id == "CS300-300":
        card["finality"] = "CS300-300"
    return card


def test_all_layers_admit() -> None:
    ids = layer_ids()
    assert len(ids) == 300
    receipts = [admit(layer_id, _card(layer_id)) for layer_id in ids]
    assert all(row["admitted"] and row["stored_prose"] == 0 for row in receipts)
    assert len({row["stratum"] for row in receipts}) == 30


@pytest.mark.parametrize("stratum", range(1, 31))
def test_stratum_rejects_its_adversary(stratum: int) -> None:
    layer_id = f"CS300-{(stratum - 1) * 10 + 1:03d}"
    bad = _card(layer_id)
    if stratum == 1:
        bad["halt_claim"] = True
    elif stratum == 3:
        bad["sound"] = False
    elif stratum == 5:
        bad["sandbox"] = False
    elif stratum == 6:
        bad["privilege"] = "kernel"
    elif stratum == 7:
        bad["race_free"] = False
    elif stratum == 10:
        bad["durable"] = False
    elif stratum == 11:
        bad["isolation"] = "none"
    elif stratum == 14:
        bad["secret"] = "token"
    elif stratum == 19:
        bad["unsigned"] = True
    elif stratum == 21:
        bad["nan_policy"] = "ignore"
    elif stratum == 30:
        bad["reproduction"] = ""
    else:
        bad["bound"] = 1
        for key in ("fanout", "quorum", "rate", "coupling", "sample", "occupancy", "cold_start", "frame", "decoherence", "spikes"):
            if key in bad:
                bad[key] = 99
        if stratum in (4, 9, 12, 15, 17, 20, 23, 25, 29):
            bad[next(k for k in bad if k not in {"layer", "bound", "evidence", "stored_prose"})] = ""
    with pytest.raises(LayerReject):
        admit(layer_id, bad)
