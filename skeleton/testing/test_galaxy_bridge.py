"""Tests for cross-node task routing via GalaxyBridge."""

from __future__ import annotations

import time
import unittest
import uuid


def _node(node_id):
    from skeleton.galaxy import GalaxyNode, NodeTransport
    node = GalaxyNode(node_id=node_id)
    transport = NodeTransport(node).start()
    return node, transport


class TestGalaxyBridge(unittest.TestCase):
    def _pair(self):
        from skeleton.galaxy import GalaxyNode, NodeTransport
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.swarm.mesh import SwarmMesh
        from skeleton.agents.bridge import MeshBridge

        # Node A: client, no local agents
        na, ta = _node("gb-client")
        mesh_a = SwarmMesh()
        bridge_a = GalaxyBridge(MeshBridge(mesh_a), na, ta)

        # Node B: server, serves 'reasoning'
        nb, tb = _node("gb-server")
        mesh_b = SwarmMesh()
        bridge_b = GalaxyBridge(MeshBridge(mesh_b), nb, tb)
        bridge_b.serve("reasoning", lambda payload: {"answer": f"handled: {payload['description']}"})

        # Register each other
        na._registry.register("gb-server", tb.address, capabilities={"reasoning"})
        nb._registry.register("gb-client", ta.address)
        return na, ta, bridge_a, nb, tb, bridge_b

    def test_local_dispatch_preferred(self):
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.swarm.mesh import SwarmMesh
        from skeleton.agents.bridge import MeshBridge
        from skeleton.agents import Task

        node, t = _node("gb-local")
        try:
            mesh = SwarmMesh()
            mesh.join({"compute"})
            bridge = GalaxyBridge(MeshBridge(mesh), node, t)
            task = Task(task_id=str(uuid.uuid4())[:8], description="local job")
            self.assertTrue(bridge.dispatch(task, "compute"))
            self.assertEqual(bridge.stats()["local"], 1)
            self.assertEqual(bridge.stats()["offered"], 0)
        finally:
            t.stop()

    def test_remote_offer_and_result_roundtrip(self):
        from skeleton.agents import Task
        na, ta, bridge_a, nb, tb, bridge_b = self._pair()
        try:
            task = Task(task_id=str(uuid.uuid4())[:8], description="solve this")
            ok = bridge_a.dispatch(task, "reasoning")  # no local agents → remote
            self.assertTrue(ok)
            self.assertEqual(bridge_a.stats()["offered"], 1)

            remote = bridge_a.wait_result(task.task_id, timeout=3.0)
            self.assertIsNotNone(remote)
            self.assertEqual(remote.status, "completed")
            self.assertIn("solve this", remote.result["answer"])
            self.assertEqual(bridge_b.stats()["served"], 1)
        finally:
            ta.stop(); tb.stop()

    def test_offer_fails_without_capable_peer(self):
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.swarm.mesh import SwarmMesh
        from skeleton.agents.bridge import MeshBridge
        from skeleton.agents import Task

        node, t = _node("gb-alone")
        try:
            bridge = GalaxyBridge(MeshBridge(SwarmMesh()), node, t)
            task = Task(task_id=str(uuid.uuid4())[:8], description="nobody home")
            self.assertFalse(bridge.dispatch(task, "teleportation"))
            self.assertEqual(bridge.stats()["failed"], 1)
        finally:
            t.stop()

    def test_expire_stale_offers(self):
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge, RemoteTask
        from skeleton.swarm.mesh import SwarmMesh
        from skeleton.agents.bridge import MeshBridge

        node, t = _node("gb-expire")
        try:
            bridge = GalaxyBridge(MeshBridge(SwarmMesh()), node, t)
            stale = RemoteTask(task_id="old", specialisation="x", description="")
            stale.offered_at = time.time() - 60
            bridge._remote_tasks["old"] = stale
            self.assertEqual(bridge.expire_offers(), 1)
            self.assertEqual(stale.status, "expired")
        finally:
            t.stop()

    def test_bus_events_on_offer_and_complete(self):
        from skeleton.galaxy.galaxy_bridge import GalaxyBridge
        from skeleton.swarm.mesh import SwarmMesh
        from skeleton.agents.bridge import MeshBridge
        from skeleton.agents import Task
        from skeleton.kernel.events import EventBus

        bus = EventBus()
        seen = []
        bus.subscribe("galaxy.task.offered", lambda e: seen.append(e.payload))
        bus.subscribe("galaxy.task.completed", lambda e: seen.append(e.payload))

        na, ta, bridge_a, nb, tb, bridge_b = self._pair()
        bridge_a._bus = bus
        try:
            task = Task(task_id=str(uuid.uuid4())[:8], description="bus task")
            bridge_a.dispatch(task, "reasoning")
            bridge_a.wait_result(task.task_id, timeout=3.0)
            topics = [p.get("task_id") for p in seen]
            self.assertIn(task.task_id, topics)
            self.assertGreaterEqual(len(seen), 2)
        finally:
            ta.stop(); tb.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
