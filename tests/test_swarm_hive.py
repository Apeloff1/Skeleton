"""Tests for hive, stigmergy, and negotiation."""

from skeleton.swarm import HiveMind, SwarmMesh
from skeleton.swarm.negotiation import CapabilityNegotiator
from skeleton.swarm.platoons import standard_platoons
from skeleton.swarm.stigmergy import PheromoneField, StigmergicRouter


class TestSwarmComposition:
    def test_mesh_and_hive(self):
        assert SwarmMesh() is not None
        assert HiveMind() is not None

    def test_stigmergy(self):
        field = PheromoneField()
        assert StigmergicRouter(field) is not None

    def test_negotiator_and_platoons(self):
        assert CapabilityNegotiator() is not None
        assert standard_platoons() is not None
