"""Tests for the support system: planes, loading queue, agentic RAG, overseer."""

from __future__ import annotations

import time
import unittest


class TestSupportPlanes(unittest.TestCase):
    def test_sentinel_blocks_duplicates(self):
        from skeleton.support import SentinelContext, WorkOrder
        s = SentinelContext()
        o1 = WorkOrder(order_id="a", connector="github.push", action="push",
                       payload={"context": "same work"}, priority=5.0)
        o2 = WorkOrder(order_id="b", connector="github.push", action="push",
                       payload={"context": "same work"}, priority=5.0)
        self.assertEqual(s.validate(o1).verdict, "pass")
        dup = s.validate(o2)
        self.assertIn("duplicate_order", dup.reasons)

    def test_hospice_retries_and_resurrects(self):
        from skeleton.support import HospiceContext
        from skeleton.contexts import BacklogContext
        backlog = BacklogContext()
        item = backlog.defer(type("W", (), {"order_id": "retry-me", "payload": {}, "priority": 6.0})(),
                             kind="failed_order")
        h = HospiceContext()
        actions = h.heal(backlog)
        self.assertTrue(any(a.action == "retry" for a in actions))
        item.age_cycles = 40
        actions = h.heal(backlog)
        self.assertTrue(any(a.action == "resurrect" for a in actions))

    def test_blueprint_critical_path_and_lanes(self):
        from skeleton.support import BlueprintContext
        from skeleton.contexts import PlanningContext
        ctx = PlanningContext()
        plan = ctx.decompose("ship", [
            {"description": "a", "estimated_cost": 2.0},
            {"description": "b", "estimated_cost": 3.0},
            {"description": "c", "estimated_cost": 1.0},
        ])
        plan.steps[1].depends_on = [plan.steps[0].step_id]
        plan.steps[2].depends_on = [plan.steps[0].step_id]
        bp = BlueprintContext()
        opt = bp.optimize(plan)
        self.assertEqual(len(opt["critical_path"]), 2)
        self.assertEqual(len(opt["parallel_lanes"]), 1)  # b and c at same depth

    def test_resonance_detects_starvation(self):
        from skeleton.support import ResonanceContext
        from skeleton.contexts import QueByPriority
        q = QueByPriority()
        item = q.enqueue("workorder", "stale", record={"priority": 0.1})
        item.blended = 0.1
        r = ResonanceContext()
        r._first_seen[item.item_id] = time.time() - 100
        out = r.scan(q)
        self.assertIn(item.item_id, out["starving"])
        self.assertGreater(len(out["suggestions"]), 0)

    def test_lens_calibrates_oracle(self):
        from skeleton.support import LensContext
        lens = LensContext()
        reading = type("R", (), {"next_event_probability": 0.9,
                                  "completion_forecast": {"projected_quality": 0.8}})()
        lens.track(reading)
        lens.resolve(0.4)
        cal = lens.calibration()
        self.assertTrue(cal["samples"] >= 1)
        self.assertGreater(cal["bias"], 0.1)
        self.assertIn("over-predicts", cal["verdict"])

    def test_ward_learns_repeated_rules(self):
        from skeleton.support import WardContext, SyntaxIssue
        w = WardContext()
        issues = [SyntaxIssue(plane="workorder", entry=f"e{i}", rule="dangling_connector")
                  for i in range(3)]
        out = w.audit(issues)
        self.assertIn("dangling_connector", out["learned"])


class TestLoadingQueue(unittest.TestCase):
    def test_lazy_load_on_demand(self):
        from skeleton.support import LoadingQueue
        loader = LoadingQueue(idle_ttl=60)
        made = []
        loader.register("lazy", lambda: made.append(1) or object())
        self.assertEqual(made, [])  # nothing loaded at registration
        plane = loader.get("lazy")
        self.assertEqual(len(made), 1)
        self.assertIn("lazy", loader.resident_planes())

    def test_pressure_queues_and_pump_loads(self):
        from skeleton.support import LoadingQueue
        loader = LoadingQueue()
        loader.register("p1", lambda: object())
        loader.signal_pressure("p1", 0.9, "hot")
        loaded = loader.pump()
        self.assertIn("p1", loaded)

    def test_resident_cap_evicts_lru(self):
        from skeleton.support import LoadingQueue
        loader = LoadingQueue(max_resident=2, idle_ttl=1000)
        for name in ("a", "b", "c"):
            loader.register(name, lambda n=name: object())
        loader.get("a")
        loader.get("b")
        time.sleep(0.01)
        loader.get("b")  # touch b so a is LRU
        loader.get("c")  # triggers eviction of a
        resident = loader.resident_planes()
        self.assertNotIn("a", resident)
        self.assertIn("b", resident)
        self.assertIn("c", resident)
        self.assertEqual(loader.stats()["evicted"], 1)

    def test_idle_planes_unload(self):
        from skeleton.support import LoadingQueue
        loader = LoadingQueue(idle_ttl=0.05)
        loader.register("temp", lambda: object())
        loader.get("temp")
        time.sleep(0.1)
        loader.pump()  # eviction pass
        self.assertNotIn("temp", loader.resident_planes())

    def test_bounded_queue_drops_lowest_priority(self):
        from skeleton.support import LoadingQueue
        loader = LoadingQueue(max_in_flight=1)
        loader.register("x", lambda: object())
        for level in (0.1, 0.2, 0.3, 0.4, 0.5):
            loader.signal_pressure("x" + str(level), level, "flood") if loader._factories.get("x" + str(level)) else None
        # register real planes and flood
        for i, level in enumerate((0.1, 0.2, 0.3, 0.4, 0.5)):
            loader.register(f"f{i}", lambda: object())
            loader.signal_pressure(f"f{i}", level, "flood")
        # queue bounded at max_in_flight*4 = 4; lowest priority dropped
        self.assertLessEqual(len(loader._queue), 4)


class TestAgenticRAG(unittest.TestCase):
    def _rag(self):
        from skeleton.support import AgenticRAG
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        g.get("quad").ingest_document("doc", "The Forge produces blueprints. Skeleton is a game engine.")
        return AgenticRAG(quad=g.get("quad")), g

    def test_classifies_query_classes(self):
        rag, _ = self._rag()
        self.assertEqual(rag.classify("how does the forge relate to blueprints"), "relational")
        self.assertEqual(rag.classify("what happened earlier today"), "episodic")
        self.assertEqual(rag.classify("what if we explore options"), "exploratory")
        self.assertEqual(rag.classify("what is the forge"), "factual")

    def test_retrieve_returns_coverage_and_trace(self):
        rag, _ = self._rag()
        result = rag.retrieve("what does the forge produce?")
        self.assertGreater(result.coverage, 0.0)
        self.assertGreater(len(result.results), 0)
        self.assertGreater(len(result.trace), 0)

    def test_agent_learns_plane_accuracy(self):
        rag, _ = self._rag()
        rag.retrieve("forge blueprints")
        acc = rag.accuracy()
        self.assertGreater(len(acc), 0)

    def test_refinement_rounds_fire_on_low_coverage(self):
        rag, g = self._rag()
        result = rag.retrieve("xyzzy completely unmatched terms here")
        self.assertGreaterEqual(result.rounds, 1)


class TestOverseer(unittest.TestCase):
    def test_graphs_feed_from_events(self):
        from skeleton.overseer import Overseer
        o = Overseer()
        o.observe_event("organism.health.checked", {"checks": {"rag": {"healthy": True}, "mesh": {"healthy": False}}})
        self.assertEqual(o.health.nodes["mesh"].attrs["state"], "red")
        self.assertEqual(o.health.nodes["rag"].attrs["state"], "green")

    def test_verdict_critical_on_red_nodes(self):
        from skeleton.overseer import Overseer
        o = Overseer()
        o.observe_event("organism.health.checked", {"checks": {"x": {"healthy": False}}})
        verdict = o.oversight_cycle()
        self.assertEqual(verdict.state, "critical")
        self.assertGreater(len(verdict.anomalies), 0)
        self.assertGreater(len(verdict.interventions), 0)

    def test_equilibrium_pressure_surface(self):
        from skeleton.overseer import Overseer
        o = Overseer()
        o.load.gauge("queue", 28.0, capacity=32.0)
        o.load.gauge("planes", 2.0, capacity=4.0)
        eq = o.equilibrium()
        self.assertGreater(eq["pressure"], 0.4)
        self.assertIn("queue", eq["saturated"])

    def test_fate_alignment_tracking(self):
        from skeleton.overseer import Overseer
        o = Overseer()
        o.fate.predict("deploy succeeds", 0.8)
        o.fate.realize("deploy succeeds", 0.8)
        self.assertEqual(o.fate.alignment(), 1.0)


class TestSupportGenesisWiring(unittest.TestCase):
    def test_support_phase_wired(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("support", g.report.phases)
        for handle in ("support", "loader", "agentic_rag", "overseer"):
            self.assertIn(handle, g.handles)

    def test_loader_invariant_bounded(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        violations = g.lattice.evaluate()
        self.assertNotIn("support_loader_bounded", violations)

    def test_support_cycle_runs_end_to_end(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        fabric = g.get("fabric")
        fabric.distill("push files to github. search the web for docs. build pdf.", 1500)
        support = g.get("support")
        out = support.support_cycle(fabric)
        self.assertIn("verdict", out)
        self.assertIn("loaded", out)
        self.assertGreaterEqual(len(out["loaded"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
