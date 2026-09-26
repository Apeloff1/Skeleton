"""A blank observation is not an era, and a copied mouth is not a vertex."""

import pytest

from skeleton.context.dodeca import ADJ, FACES, Dodecahedron
from skeleton.context.oracle import MOUTHS, VERTEX_FACES, acquire
from skeleton.context.questionnaire import intake
from skeleton.context.tensor import AXES, ContextTensor, detect_era
from skeleton.forge.eras import compile_era


def test_blank_and_unmatched_observations_raise() -> None:
    with pytest.raises(ValueError):
        detect_era("   ")
    with pytest.raises(ValueError):
        detect_era("zzzz no dialect here")
    with pytest.raises(ValueError):
        ContextTensor.from_era("not-an-era")
    with pytest.raises(ValueError):
        ContextTensor.from_mapping({"risk": 0.2}, era="custom")
    with pytest.raises(ValueError):
        acquire("   ")
    with pytest.raises(ValueError):
        acquire("zzzz no dialect here")
    with pytest.raises(ValueError):
        intake({})
    with pytest.raises(ValueError):
        intake({"era_explicit": "unspecified"})


def test_observation_acquires_a_unique_mouth() -> None:
    assert len(VERTEX_FACES) == 20
    assert len(set(VERTEX_FACES)) == 20
    assert len(MOUTHS) == 20
    found = acquire("a soulslike with bonfire rest and i-frame rolls")
    again = acquire("a soulslike with bonfire rest and i-frame rolls")
    assert found.era == "soulslike"
    assert found.scores["soulslike"] >= 2
    assert found.reading.text == again.reading.text
    assert found.reading.text in MOUTHS
    assert found.reading.index == again.reading.index
    assert found.tensor.fingerprint() == again.tensor.fingerprint()
    assert found.reading.seed == again.reading.seed
    other = acquire("a soulslike with bonfire rest and i-frame rolls", nonce=1)
    assert found.reading.seed != other.reading.seed
    soul = ContextTensor.from_era("soulslike")
    assert 0.8 < soul["lethality"] <= 1.0
    assert soul["tempo"] < ContextTensor.from_era("boomer_shooter")["tempo"]
    cozy = ContextTensor.from_era("cozy_wholesome")
    horror = ContextTensor.from_era("horror_survival")
    mid = cozy.lerp(horror, 0.5)
    assert cozy.fingerprint() != mid.fingerprint() != horror.fingerprint()
    assert abs(mid["risk"] - (cozy["risk"] + horror["risk"]) / 2) < 1e-9
    clamped = ContextTensor.from_era("extraction_now").with_axis("risk", 1.5)
    assert clamped["risk"] == 1.0
    assert len(AXES) == 10
    cube = ContextTensor.from_era("fighting_game")
    pack = compile_era("fighting_game")
    assert cube["risk"] == pytest.approx(pack["meta"]["permadeath"])
    assert cube["risk"] == 0.0
    assert cube["authorial"] == pytest.approx(pack["meta"]["authorial"])
    lattice = Dodecahedron.from_tensor(ContextTensor.from_era("soulslike"))
    assert abs(sum(lattice.activations) - 1.0) < 1e-9
    assert lattice.hottest(1)[0][1] > 1 / 12 / 2
    assert lattice.geodesic("combat", "combat") == 0
    assert lattice.geodesic("combat", FACES[ADJ[0][0]]) == 1
    assert 1 <= lattice.geodesic("combat", "meta") <= 3
