"""The swarm does not invent agreement, and it does not grow past the cap."""

import pytest

from skeleton.swarm.law import N_CAP
from skeleton.swarm.mesh import (
    CapabilityNegotiator,
    HiveMind,
    Mesh,
    PheromoneField,
    Platoons,
    SwarmMesh,
)


def test_a_handoff_frees_its_offer_slot() -> None:
    mesh = Mesh()
    for index in range(N_CAP):
        mesh.offer(f"a{index}", "task")
        mesh.accept(f"a{index}", "peer")
    mesh.offer("again", "task")
    assert mesh.accept("again", "peer") == "accept"
    assert mesh.accept("again", "peer") == "refuse"


def test_disagreement_is_not_a_consensus() -> None:
    hive = HiveMind()
    hive.contribute("load", "a", 0)
    hive.contribute("load", "b", 100)
    assert hive.consensus("load") is None
    hive.contribute("load", "a", 10)
    hive.contribute("load", "b", 10)
    assert hive.consensus("load") == 10
    hive.contribute("halt", "a", "stop")
    hive.contribute("halt", "b", "stop")
    hive.contribute("halt", "c", "go")
    assert hive.consensus("halt") == "stop"
    with pytest.raises(ValueError):
        hive.contribute("load", "a", 10, confidence=5)


def test_platoon_and_pheromone_obey_the_cap() -> None:
    mesh = SwarmMesh()
    platoons = Platoons()
    agents = platoons.deploy(mesh, "council")
    assert len(agents) == 7
    with pytest.raises(ValueError, match="n-cap"):
        platoons.deploy(mesh, "guard")
    with pytest.raises(ValueError, match="unknown"):
        Platoons().deploy(SwarmMesh(), "navy")
    field = PheromoneField()
    with pytest.raises(ValueError):
        field.deposit("here", "food", strength=-1)
    field.deposit("here", "food", strength=1)
    assert field.sense("here")["food"] == 1
    negotiator = CapabilityNegotiator()
    negotiator.advertise("ada", {"search"})
    negotiator.advertise("ada", {"compile"})
    assert negotiator.discover("search") == set()
    assert negotiator.discover("compile") == {"ada"}
    assert negotiator.negotiate("ada", {"compile", "search"})["can_fulfill"] is False
