"""Tests for the deep stack: byzantine, chaos, causal inference, differential privacy."""

from __future__ import annotations

import unittest


class TestByzantine(unittest.TestCase):
    def _engine(self, node="n1", nodes=None, secret=b"s1"):
        from skeleton.galaxy.byzantine import ByzantineEngine
        return ByzantineEngine(node, nodes or ["n1", "n2", "n3", "n4"], secret,
                               secrets={n: (b"s1" if n == "n1" else b"s" + n[-1].encode().__str__().encode()) for n in (nodes or [])})

    def test_signed_envelope_verifies(self):
        from skeleton.galaxy.byzantine import SignedEnvelope
        env = SignedEnvelope.create("n1", 1, {"v": 42}, "genesis", b"secret")
        self.assertTrue(env.verify(b"secret"))
        self.assertFalse(env.verify(b"wrong"))

    def test_tampered_payload_fails(self):
        from skeleton.galaxy.byzantine import SignedEnvelope
        env = SignedEnvelope.create("n1", 1, {"v": 42}, "genesis", b"secret")
        env.payload["v"] = 43
        self.assertFalse(env.verify(b"secret"))

    def test_equivocation_detected(self):
        from skeleton.galaxy.byzantine import EquivocationLedger, SignedEnvelope
        ledger = EquivocationLedger()
        e1 = SignedEnvelope.create("byz", 5, {"v": "a"}, "p", b"k")
        e2 = SignedEnvelope.create("byz", 5, {"v": "b"}, "p", b"k")
        self.assertIsNone(ledger.record(e1))
        proof = ledger.record(e2)
        self.assertIsNotNone(proof)
        self.assertEqual(proof["node_id"], "byz")

    def test_quorum_certificate_forms(self):
        from skeleton.galaxy.byzantine import QuorumCollector, SignedEnvelope
        qc = QuorumCollector(n_nodes=4)  # f=1, need 3
        secrets = {"a": b"sa", "b": b"sb", "c": b"sc"}
        cert = None
        for nid, sec in secrets.items():
            env = SignedEnvelope.create(nid, 1, {"x": 1}, "v0", sec)
            cert = qc.add_vote(env, sec) or cert
        self.assertIsNotNone(cert)
        self.assertEqual(len(set(cert.voters)), 3)

    def test_forged_vote_rejected_and_penalized(self):
        from skeleton.galaxy.byzantine import ByzantineEngine
        eng = ByzantineEngine("n1", ["n1", "n2", "n3", "n4"], b"s1")
        from skeleton.galaxy.byzantine import SignedEnvelope
        forged = SignedEnvelope.create("n2", 1, {"x": 1}, "v0", b"not-the-secret")
        result = eng.receive_vote(forged, voter_secret=b"s2")
        self.assertIsNone(result)
        self.assertLess(eng.trust.record("n2").score, 1.0)

    def test_view_change_on_stall(self):
        from skeleton.galaxy.byzantine import ByzantineEngine
        eng = ByzantineEngine("n1", ["n1", "n2", "n3", "n4"], b"s1")
        eng._view_started -= 10.0
        new_view = eng.maybe_view_change()
        self.assertEqual(new_view, 1)
        self.assertEqual(eng._primary(), "n2")


class TestChaosHarness(unittest.TestCase):
    def test_schedule_replayable_by_seed(self):
        from skeleton.resilience.chaos import ChaosSchedule
        a = ChaosSchedule(seed=7).generate("storm", ["rag", "mesh"])
        b = ChaosSchedule(seed=7).generate("storm", ["rag", "mesh"])
        self.assertEqual([(e.kind, e.target, round(e.at_offset_s, 3)) for e in a],
                         [(e.kind, e.target, round(e.at_offset_s, 3)) for e in b])

    def test_monsoon_cascades(self):
        from skeleton.resilience.chaos import ChaosSchedule
        events = ChaosSchedule(seed=3).generate("monsoon", ["rag"])
        self.assertGreater(len(events), 6)
        offsets = [e.at_offset_s for e in events]
        self.assertEqual(offsets, sorted(offsets))

    def test_injection_scoped_and_reverted(self):
        from skeleton.resilience.chaos import FaultInjector
        inj = FaultInjector()
        state = {"value": "original"}
        i = inj.inject("payload_corrupt", "rag", ttl_s=0.01)
        state["value"] = "corrupted"
        inj.register_restore(i.injection_id, lambda: state.update({"value": "original"}))
        import time as _t
        _t.sleep(0.02)
        inj.sweep()
        self.assertEqual(state["value"], "original")
        self.assertEqual(inj.stats()["reverted"], 1)

    def test_experiment_verdict(self):
        from skeleton.resilience.chaos import ChaosHarness, SteadyStateHypothesis
        harness = ChaosHarness()
        hyp = SteadyStateHypothesis()
        hyp.expect("health", lambda: True, lambda v: v, "healthy stays true")
        report = harness.run_experiment("drizzle", ["rag"], hyp, seed=1)
        self.assertTrue(report.passed)
        self.assertGreater(report.injections, 0)
        self.assertEqual(report.checks_failed, 0)


class TestCausalEngine(unittest.TestCase):
    def _feed(self, n=40):
        from skeleton.contexts.causal import CausalEngine
        eng = CausalEngine()
        for i in range(n):
            x = (i % 10) / 10.0
            y = 0.8 * x + 0.05 * ((i * 7) % 3)  # y driven by x
            z = (i % 5) / 5.0                     # independent
            eng.observe({"x": x, "y": y, "z": z})
        return eng

    def test_learns_causal_edge_direction(self):
        eng = self._feed()
        parents_of_y = eng.graph.parents("y", min_strength=0.05)
        self.assertTrue(any(e.src == "x" for e in parents_of_y))

    def test_intervention_propagates(self):
        eng = self._feed()
        iv = eng.what_if("x", 1.0)
        self.assertIn("y", iv.deltas)
        self.assertGreater(abs(iv.deltas["y"]), 0)

    def test_what_if_severs_parents(self):
        eng = self._feed()
        iv = eng.what_if("y", 0.0)
        self.assertIn("x", iv.severed)

    def test_attribution_decomposes(self):
        eng = self._feed()
        attr = eng.why("y", outcome_value=1.0)
        self.assertGreater(len(attr.contributions), 0)
        total = sum(attr.contributions.values())
        self.assertAlmostEqual(total, 1.0, places=1)

    def test_confounder_watch_runs(self):
        eng = self._feed()
        alerts = eng.spurious()
        self.assertIsInstance(alerts, list)


class TestDifferentialPrivacy(unittest.TestCase):
    def test_accountant_enforces_budget(self):
        from skeleton.memory.dp import PrivacyAccountant
        acc = PrivacyAccountant(session_budget=0.3, per_plane_budget=0.2)
        self.assertTrue(acc.spend(0.2, "laplace", "count", "rag"))
        self.assertFalse(acc.spend(0.2, "laplace", "count", "rag"))  # over session budget
        self.assertEqual(acc.remaining(), 0.1)

    def test_laplace_count_noised_and_reproducible(self):
        from skeleton.memory.dp import LaplaceMechanism, PrivacyAccountant
        mech = LaplaceMechanism(PrivacyAccountant(session_budget=10.0))
        a = mech.privatize_count(100, 0.5, "q1")
        b = mech.privatize_count(100, 0.5, "q1")
        self.assertEqual(a, b)  # same query id → same noise
        self.assertNotEqual(a, 100.0)  # noise actually applied (overwhelmingly likely)

    def test_laplace_mean_within_sensitivity_scale(self):
        from skeleton.memory.dp import LaplaceMechanism, PrivacyAccountant
        mech = LaplaceMechanism(PrivacyAccountant(session_budget=10.0))
        out = mech.privatize_mean([0.5] * 100, 0.5, "m1", value_range=(0.0, 1.0))
        self.assertIsNotNone(out)
        self.assertLess(abs(out - 0.5), 0.5)  # scale = 1/100/0.5 = 0.02, tight

    def test_exponential_selects_from_options(self):
        from skeleton.memory.dp import ExponentialMechanism, PrivacyAccountant
        mech = ExponentialMechanism(PrivacyAccountant(session_budget=10.0))
        pick = mech.select({"a": 1.0, "b": 0.1, "c": 0.0}, 1.0, "s1")
        self.assertIn(pick, {"a", "b", "c"})

    def test_budget_exhaustion_refuses_query(self):
        from skeleton.memory.dp import LaplaceMechanism, PrivacyAccountant
        acc = PrivacyAccountant(session_budget=0.15)
        mech = LaplaceMechanism(acc)
        self.assertIsNotNone(mech.privatize_count(5, 0.1, "q1"))
        self.assertIsNone(mech.privatize_count(5, 0.1, "q2"))  # budget exhausted

    def test_private_plane_adapter_no_raw_leak(self):
        from skeleton.memory.dp import DifferentialPrivacy
        from skeleton.memory.core import MAGStore
        mag = MAGStore("dp-test")
        mag.record("e1", "secret episode content", tags=["alpha"])
        mag.record("e2", "another private note", tags=["alpha", "beta"])
        dp = DifferentialPrivacy(session_budget=5.0)
        adapter = dp.wrap("mag", mag)
        hist = adapter.tag_histogram(epsilon=0.5)
        self.assertIsNotNone(hist)
        # Noised histogram contains bucket names but no record content
        for bucket_text in hist.keys():
            self.assertNotIn("secret", str(bucket_text))
        count = adapter.document_count(epsilon=0.2)
        self.assertIsNotNone(count)
        self.assertGreater(dp.accountant.stats()["spent_total"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
