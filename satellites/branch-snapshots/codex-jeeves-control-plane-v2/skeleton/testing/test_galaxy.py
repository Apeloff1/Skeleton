"""Tests for galaxy transport and genesis galaxy wiring."""

from __future__ import annotations

import time
import unittest


class TestNodeTransport(unittest.TestCase):
    def _make_node(self, node_id="n1"):
        from skeleton.galaxy import GalaxyNode, NodeTransport
        node = GalaxyNode(node_id=node_id)
        transport = NodeTransport(node).start()
        return node, transport

    def tearDown(self):
        # Each test stops its transports via the test body; safe no-op guard
        pass

    def test_start_resolves_ephemeral_port(self):
        node, t = self._make_node()
        try:
            self.assertGreater(t.port, 0)
            self.assertIn(":", t.address)
        finally:
            t.stop()

    def test_two_nodes_exchange_messages(self):
        node_a, ta = self._make_node("node-a")
        node_b, tb = self._make_node("node-b")
        try:
            received = []
            tb.on("ping", lambda p: received.append(p))
            ok = ta.send(tb.address, {"type": "ping", "data": "hello"})
            self.assertTrue(ok)
            time.sleep(0.1)  # let the inbox thread handle it
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["data"], "hello")
            # Sender auto-registered at receiver
            self.assertIn("node-a", node_b._registry._nodes)
        finally:
            ta.stop(); tb.stop()

    def test_send_to_dead_peer_fails_gracefully(self):
        node, t = self._make_node()
        try:
            ok = t.send("127.0.0.1:1", {"type": "ping"})  # nothing listening
            self.assertFalse(ok)
            self.assertEqual(t.status()["stats"]["failed"], 1)
        finally:
            t.stop()

    def test_heartbeat_between_nodes(self):
        node_a, ta = self._make_node("hb-a")
        node_b, tb = self._make_node("hb-b")
        try:
            node_b._registry.register("hb-a", ta.address)
            ok = ta.heartbeat(tb.address)
            self.assertTrue(ok)
        finally:
            ta.stop(); tb.stop()

    def test_status_endpoint_shape(self):
        node, t = self._make_node()
        try:
            status = t.status()
            for key in ("node_id", "address", "stats", "inbox_size"):
                self.assertIn(key, status)
        finally:
            t.stop()


class TestGenesisGalaxyWiring(unittest.TestCase):
    def setUp(self):
        from skeleton.genesis import Genesis
        self.genesis = Genesis(seed=42).boot()

    def test_galaxy_phase_boots(self):
        self.assertIn("galaxy", self.genesis.report.phases)

    def test_galaxy_handles_wired(self):
        self.assertIn("galaxy", self.genesis.handles)
        self.assertIn("galaxy_transport", self.genesis.handles)

    def test_galaxy_node_has_capabilities(self):
        node = self.genesis.get("galaxy")
        self.assertIn("reasoning", node._capabilities)
        self.assertIn("forge", node._capabilities)

    def test_galaxy_invariant_registered(self):
        violations = self.genesis.lattice.evaluate()
        self.assertNotIn("galaxy_node_identified", violations)

    def test_phase_order_galaxy_before_cortex(self):
        phases = self.genesis.report.phases
        self.assertLess(phases.index("galaxy"), phases.index("cortex"))

    def test_genesis_node_can_bind_transport(self):
        transport = self.genesis.get("galaxy_transport")
        transport.start()
        try:
            self.assertGreater(transport.port, 0)
        finally:
            transport.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
