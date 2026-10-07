"""Tests for leader election across galaxy nodes."""

from __future__ import annotations

import time
import unittest


def _node(node_id, capabilities=frozenset()):
    from skeleton.galaxy import GalaxyNode, NodeTransport
    from skeleton.galaxy.consensus import ConsensusEngine
    from skeleton.galaxy.election import LeaderElection

    node = GalaxyNode(node_id=node_id)
    for cap in capabilities:
        node.add_capability(cap)
    transport = NodeTransport(node).start()
    consensus = ConsensusEngine(node, transport)
    election = LeaderElection(node, transport, consensus)
    return node, transport, consensus, election


class TestLeaderElection(unittest.TestCase):
    def test_single_node_elects_itself(self):
        node, t, c, e = _node("solo-leader")
        try:
            leader = e.call_election()
            self.assertEqual(leader, "solo-leader")
            self.assertTrue(e.is_leader())
            self.assertEqual(e.state.term, 1)
        finally:
            t.stop()

    def test_most_capable_node_wins(self):
        na, ta, ca, ea = _node("weak", {"a"})
        nb, tb, cb, eb = _node("strong", {"a", "b", "c"})
        try:
            na._registry.register("strong", tb.address, capabilities={"a", "b", "c"})
            nb._registry.register("weak", ta.address, capabilities={"a"})

            leader = ea.call_election(timeout=3.0)
            self.assertEqual(leader, "strong")
            self.assertFalse(ea.is_leader())

            # Peer converges via install broadcast
            time.sleep(0.3)
            self.assertEqual(eb.state.leader_id, "strong")
            self.assertTrue(eb.is_leader())
        finally:
            ta.stop(); tb.stop()

    def test_deterministic_tiebreak_by_node_id(self):
        n1, t1, c1, e1 = _node("aaa", {"x"})
        n2, t2, c2, e2 = _node("zzz", {"x"})
        try:
            n1._registry.register("zzz", t2.address, capabilities={"x"})
            n2._registry.register("aaa", t1.address, capabilities={"x"})
            leader = e1.call_election(timeout=3.0)
            self.assertEqual(leader, "zzz")  # highest id wins the tie
        finally:
            t1.stop(); t2.stop()

    def test_stale_leadership_triggers_reelection(self):
        node, t, c, e = _node("stale-test")
        try:
            e.call_election()
            self.assertTrue(e.is_leader())
            # Force staleness
            e.state.elected_at = time.time() - (e.state.LEADER_TTL + 1)
            self.assertTrue(e.state.is_stale())
            self.assertIsNone(e.leader())
            leader = e.maybe_reelect()
            self.assertEqual(leader, "stale-test")
            self.assertEqual(e.state.term, 2)
        finally:
            t.stop()

    def test_leader_heartbeat_holds_ttl(self):
        na, ta, ca, ea = _node("hb-leader", {"x", "y"})
        nb, tb, cb, eb = _node("hb-follower", {"x"})
        try:
            na._registry.register("hb-follower", tb.address, capabilities={"x"})
            nb._registry.register("hb-leader", ta.address, capabilities={"x", "y"})
            ea.call_election(timeout=3.0)
            time.sleep(0.3)

            # Make follower's clock nearly stale, then heartbeat refreshes it
            eb.state.elected_at = time.time() - (eb.state.LEADER_TTL - 1)
            sent = ea.heartbeat_fleet()
            self.assertEqual(sent, 1)
            time.sleep(0.3)
            self.assertFalse(eb.state.is_stale())
        finally:
            ta.stop(); tb.stop()

    def test_install_ignores_older_terms(self):
        node, t, c, e = _node("term-guard")
        try:
            e._install("leader-v2", term=5)
            e._on_install({"leader_id": "leader-v1", "term": 3})
            self.assertEqual(e.state.leader_id, "leader-v2")
            self.assertEqual(e.state.term, 5)
        finally:
            t.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
