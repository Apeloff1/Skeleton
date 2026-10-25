import pytest
from skeleton.frontier.worldsim.scene_contract import SceneDocument, SceneEntity, SceneContractError, diff_scenes, apply_diff
from skeleton.frontier.worldsim.procgen import generate_batch, generate


def _scene():
    return SceneDocument("s", (SceneEntity("root", "group"), SceneEntity("a", "mesh", "root", (1, 2, 3), {"m": "x"})))


def test_scene_roundtrip_and_diff():
    s = _scene()
    assert SceneDocument.from_dict(s.to_dict()).digest() == s.digest()
    t = SceneDocument("s", (SceneEntity("root", "group"), SceneEntity("b", "light", "root")))
    ops = diff_scenes(s, t)
    assert [o["op"] for o in ops] == ["remove", "add"]
    assert apply_diff(s, ops).digest() == t.digest()


def test_scene_rejects_cycles_and_unknown_parent():
    with pytest.raises(SceneContractError):
        SceneDocument("s", (SceneEntity("a", "g", "b"), SceneEntity("b", "g", "a")))
    with pytest.raises(SceneContractError):
        SceneDocument("s", (SceneEntity("a", "g", "zz"),))


def gen(rng, p):
    return {"rooms": rng.randint(1, p["max"]), "theme": rng.choice(["ice", "fire", "moss"])}


def test_procgen_seeded_and_metrics():
    assert generate(gen, 7, {"max": 9}).digest == generate(gen, 7, {"max": 9}).digest
    res, m = generate_batch(gen, 1, 20, {"max": 9}, {"min_rooms": lambda a: a["rooms"] >= 3})
    assert m.count == 20 and 0 < m.validity_rate < 1 and m.diversity > 0.3
    assert all(r.valid == (r.artifact["rooms"] >= 3) for r in res)
