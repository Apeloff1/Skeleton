"""Tests for leader-coordinated fleet operations."""

from __future__ import annotations

import time
import unittest


def _fleet_node(node_id, caps=frozenset()):
    from skeleton.galaxy import GalaxyNode, NodeTransport
    from skeleton.galaxy.consensus import ConsensusEngine
    from skeleton.galaxy.election import LeaderElection
    from skeleton.galaxy.fleet import FleetCoordinator
    from skeleton.galaxy.kag_sync import KAGSync
    from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

    node = GalaxyNode(node_id=node_id)
    for cap in caps:
        node.add_capability(cap)
    transport = NodeTransport(node).start()
    consensus = ConsensusEngine(node, transport)
    election = LeaderElection(node, transport, consensus)
    kag = KAGRetriever(KnowledgeGraph())
    sync = KAGSync(kag, node, transport, consensus=consensus)
    fleet = FleetCoordinator(node, transport, election, kag_sync=sync, tick_interval=0.05)
    return node, transport, consensus, election, kag, sync, fleet


class TestLoadLedger(unittest.TestCase):
    def test_least_loaded_picks_min(self):
        from skeleton.galaxy.fleet import LoadLedger
        ledger = LoadLedger()
        ledger.loads = {"a": 3, "b": 1, "c": 2}
        self.assertEqual(ledger.least_loaded(["a", "b", "c"]), "b")

    def test_tiebreak_lexicographic(self):
        from skeleton.galaxy.fleet import LoadLedger
        ledger = LoadLedger()
        ledger.loads = {"b": 0, "a": 0}
        self.assertEqual(ledger.least_loaded(["b", "a"]), "a")

    def test_complete_decrements_floor_zero(self):
        from skeleton.galaxy.fleet import LoadLedger
        ledger = LoadLedger()
        ledger.record_accept("n")
        ledger.record_complete("n")
        ledger.record_complete("n")
        self.assertEqual(ledger.loads["n"], 0)


class TestFleetCoordinator(unittest.TestCase):
    def test_follower_cannot_assign(self):
        node, t, c, e, kag, sync, fleet = _fleet_node("f-solo")
        try:
            chosen = fleet.assign("x", [], "t1")
            self.assertIsNone(chosen)
        finally:
            t.stop()

    def test_leader_assigns_least_loaded(self):
        node, t, c, e, kag, sync, fleet = _fleet_node("f-leader", {"x", "y"})
        try:
            e.call_election()
            self.assertTrue(e.is_leader())

            class C:
                def __init__(self, nid):
                    self.node_id = nid
                    self.address = "none"
            candidates = [C("busy"), C("idle")]
            fleet.ledger.loads = {"busy": 5, "idle": 0}
            chosen = fleet.assign("reasoning", candidates, "task-1")
            self.assertEqual(chosen.node_id, "idle")
            self.assertEqual(fleet.ledger.loads["idle"], 1)
        finally:
            t.stop()

    def test_sync_tick_fires_and_throttles(self):
        node, t, c, e, kag, sync, fleet = _fleet_node("f-tick", {"x"})
        try:
            e.call_election()
            self.assertTrue(fleet.tick())
            self.assertFalse(fleet.tick())  # throttled by interval
            time.sleep(0.06)
            self.assertTrue(fleet.tick())  # interval passed
            self.assertEqual(fleet.stats()["ticks"], 2)
        finally:
            t.stop()

    def test_tick_triggers_peer_gossip(self):
        na, ta, ca, ea, kaga, sa, fa = _fleet_node("tick-leader", {"x", "y"})
        nb, tb, cb, eb, kagb, sb, fb = _fleet_node("tick-peer", {"x"})
        try:
            na._registry.register("tick-peer", tb.address, capabilities={"x"})
            nb._registry.register("tick-leader", ta.address, capabilities={"x", "y"})
            ea.call_election(timeout=3.0)
            time.sleep(0.4)  # peer installs leader

            kaga.graph.add("fleet", "is_a", "concept")
            fa.tick(force=True)
            time.sleep(0.8)
            self.assertGreaterEqual(kagb.graph.stats()["triples"], 1)
            self.assertGreaterEqual(kaga.graph.stats()["triples"], 1)
        finally:
            ta.stop(); tb.stop()

    def test_follower_ignores_tick_from_nonleader(self):
        node, t, c, e, kag, sync, fleet = _fleet_node("f-follower")
        try:
            fleet._on_sync_tick({"leader_id": "someone-else"})
            self.assertEqual(fleet.stats()["tick_gossips"], 0)
        finally:
            t.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
