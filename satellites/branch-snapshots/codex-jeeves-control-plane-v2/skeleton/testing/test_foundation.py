"""Tests for the foundation: Merkle DAG, journal/replay, ocap, temporal."""

from __future__ import annotations

import time
import unittest


class TestMerkleDAG(unittest.TestCase):
    def test_content_addressing_and_dedup(self):
        from skeleton.foundation import MerkleDAG
        dag = MerkleDAG()
        h1 = dag.put({"a": 1, "b": 2})
        h2 = dag.put({"b": 2, "a": 1})  # same content, different order
        self.assertEqual(h1, h2)
        self.assertEqual(dag.stats()["deduped"], 1)

    def test_tamper_detection(self):
        from skeleton.foundation import MerkleDAG
        dag = MerkleDAG()
        h = dag.put({"secret": "data"})
        self.assertTrue(dag.verify(h))
        dag._nodes[h].payload["secret"] = "tampered"
        self.assertFalse(dag.verify(h))

    def test_linked_provenance_chain(self):
        from skeleton.foundation import MerkleDAG
        dag = MerkleDAG()
        h1 = dag.put({"gen": 0})
        h2 = dag.put({"gen": 1}, links=[h1])
        h3 = dag.put({"gen": 2}, links=[h2])
        ancestry = dag.ancestry(h3)
        self.assertEqual(len(ancestry), 3)
        self.assertTrue(dag.verify(h3))

    def test_diff_between_roots(self):
        from skeleton.foundation import MerkleDAG
        dag = MerkleDAG()
        a = dag.put({"shared": 1})
        b = dag.put({"left": 1}, links=[a])
        c = dag.put({"right": 1}, links=[a])
        d = dag.diff(b, c)
        self.assertEqual(d["shared"], 1)
        self.assertEqual(len(d["only_a"]), 1)
        self.assertEqual(len(d["only_b"]), 1)


class TestEventJournal(unittest.TestCase):
    def test_hash_chain_integrity(self):
        from skeleton.foundation import EventJournal
        j = EventJournal()
        j.append("a.b", {"x": 1})
        j.append("a.c", {"x": 2})
        self.assertTrue(j.integrity())
        j._entries[1].payload["x"] = 999
        self.assertFalse(j.integrity())

    def test_deterministic_replay(self):
        from skeleton.foundation import EventJournal, ReplayEngine
        j = EventJournal()
        for i in range(5):
            j.append("counter.tick", {"n": i})
        re = ReplayEngine(j)
        re.on("counter.tick", lambda e, s: s.update(n=s.get("n", 0) + 1))
        state = re.replay()
        self.assertEqual(state["n"], 5)
        self.assertTrue(re.verify_determinism())

    def test_time_travel(self):
        from skeleton.foundation import EventJournal, ReplayEngine
        j = EventJournal()
        for i in range(10):
            j.append("tick", {"i": i})
        re = ReplayEngine(j)
        re.on("tick", lambda e, s: s.update(last=e.payload["i"]))
        state = re.time_travel(4)
        self.assertEqual(state["last"], 4)

    def test_journaled_bus_captures_everything(self):
        from skeleton.foundation import EventJournal, JournaledBus
        from skeleton.kernel.events import EventBus
        journal = EventJournal()
        bus = JournaledBus(EventBus(), journal)
        received = []
        bus.subscribe("test.x", lambda e: received.append(e))
        bus.emit("test.x", {"v": 1})
        self.assertEqual(len(received), 1)
        self.assertEqual(len(journal), 1)
        self.assertTrue(journal.integrity())


class TestOCap(unittest.TestCase):
    def _kernel_with_resource(self):
        from skeleton.foundation import CapabilityKernel
        class Vault:
            def read(self):
                return "data"
            def write(self, v):
                return f"wrote {v}"
            def delete(self):
                return "deleted"
        k = CapabilityKernel()
        root = k.mint("vault", {"read", "write", "delete"}, target=Vault())
        return k, root

    def test_invoke_through_capability(self):
        k, root = self._kernel_with_resource()
        self.assertEqual(k.invoke(root, "read"), "data")

    def test_attenuation_shrinks_rights(self):
        k, root = self._kernel_with_resource()
        reader = k.attenuate(root, rights={"read"})
        self.assertIsNotNone(reader)
        self.assertEqual(k.invoke(reader, "read"), "data")
        with self.assertRaises(PermissionError):
            k.invoke(reader, "delete")

    def test_attenuation_cannot_strengthen(self):
        k, root = self._kernel_with_resource()
        reader = k.attenuate(root, rights={"read"})
        forged = k.attenuate(reader, rights={"read", "admin"})
        self.assertIsNone(forged)

    def test_expiry_enforced(self):
        k, root = self._kernel_with_resource()
        short = k.attenuate(root, rights={"read"}, expiry=time.time() - 1)
        self.assertIsNotNone(short)
        with self.assertRaises(PermissionError):
            k.invoke(short, "read")

    def test_revocation_kills_descendants(self):
        k, root = self._kernel_with_resource()
        child = k.attenuate(root, rights={"read", "write"})
        grandchild = k.attenuate(child, rights={"read"})
        dead = k.revoke(child)
        self.assertGreaterEqual(dead, 2)
        with self.assertRaises(PermissionError):
            k.invoke(grandchild, "read")
        # Root still works
        self.assertEqual(k.invoke(root, "read"), "data")

    def test_chain_audit(self):
        k, root = self._kernel_with_resource()
        child = k.attenuate(root, rights={"read"})
        chain = k.chain(child)
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[1]["cap_id"], root.cap_id)

    def test_membrane_attenuates_to_needs(self):
        from skeleton.foundation import Membrane
        k, root = self._kernel_with_resource()
        m = Membrane(k)
        m.declare("analytics", {"read"})
        crossed = m.cross(root, "analytics")
        self.assertEqual(crossed.rights, {"read"})
        with self.assertRaises(PermissionError):
            k.invoke(crossed, "write", "x")


class TestTemporalLattice(unittest.TestCase):
    def _timeline(self, n=10, panic_at=None):
        tl = []
        for i in range(n):
            event = {"index": i, "topic": "tick"}
            if panic_at is not None and i == panic_at:
                event["topic"] = "system.panic"
            tl.append(event)
        return tl

    def test_always_violation_locates_index(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.always("no_panics", lambda e: e["topic"] != "system.panic")
        violations = lat.violations(self._timeline(panic_at=5))
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].at_index, 5)
        self.assertGreater(len(violations[0].window), 0)

    def test_eventually_satisfied(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.eventually("boot_happens", lambda e: e["topic"] == "tick")
        self.assertEqual(lat.violations(self._timeline()), [])

    def test_eventually_violated_when_never(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.eventually("never_seen", lambda e: e["topic"] == "boot")
        self.assertEqual(len(lat.violations(self._timeline())), 1)

    def test_response_pattern(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.response("requests_answered",
                     lambda e: e["topic"] == "tick",
                     lambda e: e["topic"] == "tick")  # trivially satisfied
        self.assertEqual(lat.violations(self._timeline()), [])

    def test_until_pattern(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.until("quiet_until_boot",
                  lambda e: e["topic"] == "tick",
                  lambda e: e["index"] >= 3)
        self.assertEqual(lat.violations(self._timeline()), [])

    def test_precedes_violation(self):
        from skeleton.foundation import TemporalLattice
        lat = TemporalLattice()
        lat.precedes("boot_before_work",
                     lambda e: e["topic"] == "boot",
                     lambda e: e["topic"] == "tick")
        self.assertEqual(len(lat.violations(self._timeline())), 1)


class TestFoundationGenesis(unittest.TestCase):
    def test_foundation_phase_boots_first(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertEqual(g.report.phases[0], "foundation")
        for handle in ("dag", "journal", "replay", "ocap", "membrane", "temporal"):
            self.assertIn(handle, g.handles)

    def test_all_events_journaled(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        journal = g.get("journal")
        self.assertGreater(len(journal), 0)
        self.assertTrue(journal.integrity())
        topics = [e.topic for e in journal.slice(0)]
        self.assertIn("kernel.genesis.booted", topics)

    def test_temporal_boot_invariant_holds(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        temporal = g.get("temporal")
        violations = temporal.violations()
        boot_violations = [v for v in violations if v.invariant == "genesis_boots_eventually"]
        self.assertEqual(boot_violations, [])

    def test_health_reports_journal_integrity(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        health = g.health()
        self.assertTrue(health["journal_integrity"])
        self.assertTrue(health["temporal_healthy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
