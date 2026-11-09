import pytest
from skeleton.gameforge.batch_b09x import b092_ir as m


def proj():
    p = m.IRProject()
    p.add_node("root", "Node2D")
    p.add_node("hero", "Sprite", "root", tex="h.png")
    p.add_mechanic("jump", "impulse", {"y": 5})
    p.assets["h.png"] = "a" * 64
    return p


def test_roundtrip_digest_stable():
    p = proj()
    q = m.IRProject.from_dict(p.to_dict())
    assert q.digest == p.digest == proj().digest


def test_validation():
    p = proj()
    for args in [("hero", "Sprite"), ("x", "Teapot"), ("y", "Node", "ghost")]:
        with pytest.raises(m.ContractError):
            p.add_node(*args)
    with pytest.raises(m.ContractError):
        m.IRProject.from_dict({**p.to_dict(), "ir_version": 2})


def test_cycle_detected():
    d = proj().to_dict()
    d["nodes"]["root"] = {**d["nodes"]["root"], "parent": "hero"}
    with pytest.raises(m.ContractError):
        m.IRProject.from_dict(d)
