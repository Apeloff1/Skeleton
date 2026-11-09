"""Tests for distributed consensus over live transport."""

from __future__ import annotations

import time
import unittest


def _node(node_id):
    from skeleton.galaxy import GalaxyNode, NodeTransport
    from skeleton.galaxy.consensus import ConsensusEngine

    node = GalaxyNode(node_id=node_id)
    transport = NodeTransport(node).start()
    engine = ConsensusEngine(node, transport)
    return node, transport, engine


class TestConsensusEngine(unittest.TestCase):
    def test_single_node_accepts_immediately(self):
        node, t, engine = _node("solo")
        try:
            proposal = engine.propose("era.switch", {"era": "neon_dystopia"})
            self.assertEqual(proposal.status, "accepted")
            self.assertEqual(engine.stats()["accepted"], 1)
        finally:
            t.stop()

    def test_two_nodes_reach_consensus(self):
        na, ta, ea = _node("alpha")
        nb, tb, eb = _node("beta")
        try:
            # Register each other
            na._registry.register("beta", tb.address)
            nb._registry.register("alpha", ta.address)

            proposal = ea.propose("config.update", {"sampling": 0.2}, wait=True, timeout=3.0)
            self.assertEqual(proposal.status, "accepted")
            self.assertEqual(proposal.votes.get("beta"), True)
            self.assertEqual(eb.stats()["votes_cast"], 1)

            # Beta recorded the outcome via the broadcast
            time.sleep(0.2)
            tracked = eb.proposals()
            self.assertTrue(any(p.proposal_id == proposal.proposal_id for p in tracked))
        finally:
            ta.stop(); tb.stop()

    def test_policy_voter_rejects(self):
        na, ta, ea = _node("strict-a")
        nb, tb, eb = _node("strict-b")
        try:
            na._registry.register("strict-b", tb.address)
            nb._registry.register("strict-a", ta.address)

            # Beta rejects any topic containing 'danger'
            eb.add_voter(lambda topic, value: "danger" not in topic)

            rejected = ea.propose("danger.zone", {"x": 1}, wait=True, timeout=2.0)
            self.assertEqual(rejected.status, "rejected")
            self.assertEqual(ea.stats()["rejected"], 1)

            accepted = ea.propose("safe.zone", {"x": 2}, wait=True, timeout=2.0)
            self.assertEqual(accepted.status, "accepted")
        finally:
            ta.stop(); tb.stop()

    def test_outcome_broadcast_marks_peer_copy(self):
        na, ta, ea = _node("obs-a")
        nb, tb, eb = _node("obs-b")
        try:
            na._registry.register("obs-b", tb.address)
            nb._registry.register("obs-a", ta.address)

            proposal = ea.propose("era.bind", {"era": "wasteland"}, wait=True, timeout=3.0)
            time.sleep(0.3)
            peer_copy = next((p for p in eb.proposals() if p.proposal_id == proposal.proposal_id), None)
            self.assertIsNotNone(peer_copy)
            self.assertEqual(peer_copy.status, "accepted")
        finally:
            ta.stop(); tb.stop()

    def test_proposal_tally_logic(self):
        from skeleton.galaxy.consensus import Proposal
        p = Proposal(proposal_id="t1", topic="t", value=1, proposer="n0")
        p.votes = {"a": True, "b": True, "c": False}
        self.assertEqual(p.tally(3), "accepted")
        p2 = Proposal(proposal_id="t2", topic="t", value=1, proposer="n0")
        p2.votes = {"a": False, "b": False}
        self.assertEqual(p2.tally(3), "rejected")
        p3 = Proposal(proposal_id="t3", topic="t", value=1, proposer="n0")
        p3.votes = {"a": True}
        self.assertIsNone(p3.tally(4))


if __name__ == "__main__":
    unittest.main(verbosity=2)
