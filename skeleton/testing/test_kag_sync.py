"""Tests for federated KAG sync between galaxy nodes."""

from __future__ import annotations

import time
import unittest


def _node_with_kag(node_id):
    from skeleton.galaxy import GalaxyNode, NodeTransport
    from skeleton.galaxy.consensus import ConsensusEngine
    from skeleton.galaxy.kag_sync import KAGSync
    from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

    node = GalaxyNode(node_id=node_id)
    transport = NodeTransport(node).start()
    consensus = ConsensusEngine(node, transport)
    kag = KAGRetriever(KnowledgeGraph())
    sync = KAGSync(kag, node, transport, consensus=consensus)
    return node, transport, consensus, kag, sync


class TestKAGSync(unittest.TestCase):
    def test_digest_reflects_local_graph(self):
        node, t, c, kag, sync = _node_with_kag("dig-1")
        try:
            kag.graph.add("forge", "produces", "blueprints")
            d = sync.digest()
            self.assertEqual(d["count"], 1)
            self.assertEqual(len(d["hashes"]), 1)
        finally:
            t.stop()

    def test_two_nodes_converge_via_gossip(self):
        na, ta, ca, kaga, sa = _node_with_kag("sync-a")
        nb, tb, cb, kagb, sb = _node_with_kag("sync-b")
        try:
            na._registry.register("sync-b", tb.address)
            nb._registry.register("sync-a", ta.address)

            # Node A has facts B lacks
            kaga.graph.add("forge", "produces", "blueprints")
            kaga.graph.add("blueprints", "target", "godot")
            self.assertEqual(kagb.graph.stats()["triples"], 0)

            # A gossips digest → B requests missing → A sends triples → B merges
            sa.sync_now()
            time.sleep(0.5)

            self.assertEqual(kagb.graph.stats()["triples"], 2)
            self.assertIn("forge", [t.subject for t in kagb.graph._triples])
            self.assertEqual(sb.stats()["triples_received"], 2)
            self.assertEqual(sa.stats()["triples_sent"], 2)
        finally:
            ta.stop(); tb.stop()

    def test_no_duplicate_merges(self):
        na, ta, ca, kaga, sa = _node_with_kag("dup-a")
        nb, tb, cb, kagb, sb = _node_with_kag("dup-b")
        try:
            na._registry.register("dup-b", tb.address)
            nb._registry.register("dup-a", ta.address)

            kaga.graph.add("x", "is_a", "y")
            sa.sync_now()
            time.sleep(0.5)
            first = kagb.graph.stats()["triples"]

            # Gossip again — idempotent, nothing new merges
            sa.sync_now()
            time.sleep(0.5)
            self.assertEqual(kagb.graph.stats()["triples"], first)
        finally:
            ta.stop(); tb.stop()

    def test_push_all_bootstraps_empty_peer(self):
        na, ta, ca, kaga, sa = _node_with_kag("boot-a")
        nb, tb, cb, kagb, sb = _node_with_kag("boot-b")
        try:
            na._registry.register("boot-b", tb.address)
            nb._registry.register("boot-a", ta.address)

            for i in range(5):
                kaga.graph.add(f"entity-{i}", "has", f"value-{i}")
            sent = sa.push_all()
            self.assertEqual(sent, 5)
            time.sleep(0.4)
            self.assertEqual(kagb.graph.stats()["triples"], 5)
        finally:
            ta.stop(); tb.stop()

    def test_bus_event_on_merge(self):
        from skeleton.kernel.events import EventBus
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.kag_sync import KAGSync
        from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

        bus = EventBus()
        received = []
        bus.subscribe("galaxy.kag.synced", lambda e: received.append(e.payload))

        node = GalaxyNode(node_id="bus-kag")
        transport = NodeTransport(node).start()
        kag = KAGRetriever(KnowledgeGraph())
        sync = KAGSync(kag, node, transport, bus=bus)
        try:
            sync._on_triples({"node_id": "peer", "triples": [["a", "is_a", "b"]]})
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["merged"], 1)
        finally:
            transport.stop()


class TestGenesisKAGSyncWiring(unittest.TestCase):
    def test_kag_sync_handle_wired(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("kag_sync", g.handles)

    def test_kag_sync_bound_to_quad_kag(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        sync = g.get("kag_sync")
        quad_kag = g.get("quad")._planes["kag"]
        self.assertIs(sync._kag, quad_kag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
