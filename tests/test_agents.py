"""Tests for the agent mesh: roster, routing, liveness, consensus."""

import pytest

from skeleton.agents import AgentMesh
from skeleton.kernel.errors import (
    AgentNotFoundError,
    ConsensusError,
    NoCapableAgentError,
)


class TestMesh:
    def test_join_and_roster(self):
        mesh = AgentMesh()
        a = mesh.join({"npc", "animation"})
        assert a in mesh.roster()
        assert "npc" in mesh.advertised_capabilities()

    def test_route_picks_capable(self):
        mesh = AgentMesh()
        mesh.join({"npc"})
        chosen = mesh.route("npc")
        assert "npc" in chosen.specialisations

    def test_route_without_capability_raises(self):
        mesh = AgentMesh()
        mesh.join({"npc"})
        with pytest.raises(NoCapableAgentError):
            mesh.route("animation")

    def test_leave_unknown_raises(self):
        mesh = AgentMesh()
        a = mesh.join({"x"})
        mesh.leave(a.agent_id)
        with pytest.raises(AgentNotFoundError):
            mesh.leave(a.agent_id)

    def test_quarantine_and_evict(self):
        mesh = AgentMesh(default_ttl=0.0)
        mesh.join({"x"})
        out = mesh.sweep(now=1e12)
        assert len(out["evicted"]) == 1  # grace expired at ttl=0 with far-future now

    def test_consensus_pass_and_fail(self):
        mesh = AgentMesh()
        a = mesh.join({"x"}, weight=2.0)
        b = mesh.join({"x"}, weight=1.0)
        result = mesh.propose("ship it", votes={a.agent_id: (True, "ok"), b.agent_id: (True, "ok")})
        assert result.passed
        with pytest.raises(ConsensusError):
            mesh.propose("nope", votes={a.agent_id: (False, "no"), b.agent_id: (False, "no")})
