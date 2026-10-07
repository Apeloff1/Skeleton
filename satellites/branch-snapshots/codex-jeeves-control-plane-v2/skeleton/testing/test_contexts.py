"""Tests for the Context Fabric: workorders, backlog, planning, queue, oracle, syntax."""

from __future__ import annotations

import time
import unittest


class TestWorkOrderEngine(unittest.TestCase):
    def test_parses_only_external_workload(self):
        from skeleton.contexts import WorkOrderEngine
        engine = WorkOrderEngine()
        orders = engine.parse(
            "Let me explain the architecture. Then push these files to github. "
            "The design is elegant. Also search the web for references."
        )
        connectors = {o.connector for o in orders}
        self.assertIn("github.push", connectors)
        self.assertIn("web.search", connectors)
        self.assertEqual(len(orders), 2)  # conversational sentences ignored

    def test_no_external_work_means_no_orders(self):
        from skeleton.contexts import WorkOrderEngine
        engine = WorkOrderEngine()
        orders = engine.parse("The matrix weaves the strings of fate beautifully.")
        self.assertEqual(orders, [])

    def test_mag_enhancement_attaches_episodes(self):
        from skeleton.contexts import WorkOrderEngine
        from skeleton.memory.core import MAGStore
        mag = MAGStore("wo-test")
        mag.record("e1", "previous github push succeeded with 5 files", tags=["github.push"])
        engine = WorkOrderEngine(mag=mag)
        orders = engine.parse("push the new batch")
        engine.enhance(orders[0])
        self.assertGreater(len(orders[0].mag_context), 0)

    def test_distill_fills_context_and_spills_to_backlog(self):
        from skeleton.contexts import WorkOrderEngine, WorkOrder, BacklogContext, CONTEXT_SIZE
        backlog = BacklogContext()
        engine = WorkOrderEngine(backlog=backlog)
        # Overfill the context plane
        for i in range(CONTEXT_SIZE + 3):
            engine.context.add(WorkOrder(order_id=f"fill-{i}", connector="github.push", action="push"))
        spilled = engine.context.add(WorkOrder(order_id="overflow", connector="web.search", action="search"))
        self.assertIsNotNone(spilled)

    def test_interjected_summary_is_positive(self):
        from skeleton.contexts import WorkOrderEngine
        engine = WorkOrderEngine()
        orders = engine.parse("push files")
        engine.context.add(orders[0])
        engine.mark(orders[0].order_id, "done")
        summary = engine.interjected_summary()
        self.assertIsNotNone(summary)
        self.assertIn("landed", summary)


class TestBacklogContext(unittest.TestCase):
    def test_defer_and_resume_by_priority(self):
        from skeleton.contexts import BacklogContext
        ctx = BacklogContext()
        ctx.defer(type("W", (), {"order_id": "low", "payload": {}, "priority": 1.0})())
        ctx.defer(type("W", (), {"order_id": "high", "payload": {}, "priority": 9.0})())
        self.assertEqual(ctx.resume_next().item_id, "high")

    def test_tensor_cube_argmax_finds_hot_band(self):
        from skeleton.contexts.backlog import TensorCube, BacklogItem
        cube = TensorCube()
        cube.insert(BacklogItem(item_id="a", priority=9.0, age_cycles=2))
        cube.insert(BacklogItem(item_id="b", priority=9.5, age_cycles=3))
        p, a, c, v = cube.argmax()
        self.assertGreater(v, 0)
        self.assertGreaterEqual(p, cube.dim - 1)

    def test_blockchain_seals_and_verifies(self):
        from skeleton.contexts.backlog import WorkChain, TensorCube, BacklogItem
        chain = WorkChain(difficulty=2)
        cube = TensorCube()
        cube.insert(BacklogItem(item_id="x", priority=5.0))
        block = chain.seal(cube, ["x"])
        self.assertEqual(block.index, 1)
        self.assertTrue(block.block_hash.startswith("00"))
        self.assertTrue(chain.verify())

    def test_chain_tamper_detected(self):
        from skeleton.contexts.backlog import WorkChain, TensorCube, BacklogItem
        chain = WorkChain(difficulty=1)
        cube = TensorCube()
        cube.insert(BacklogItem(item_id="y", priority=1.0))
        chain.seal(cube, ["y"])
        chain._chain[1].item_ids = ["tampered"]
        self.assertFalse(chain.verify())

    def test_idle_miner_seals_cubes(self):
        from skeleton.contexts import BacklogContext
        ctx = BacklogContext(chain_difficulty=1)
        ctx.defer(type("W", (), {"order_id": "m1", "payload": {}, "priority": 3.0})())
        ctx.build_cube()
        ctx.start_idle_miner(idle_seconds=0.05)
        time.sleep(0.3)
        ctx.stop_idle_miner()
        self.assertGreaterEqual(ctx.chain.stats()["blocks"], 2)


class TestPlanningAndQueue(unittest.TestCase):
    def test_plan_respects_dependencies(self):
        from skeleton.contexts import PlanningContext
        ctx = PlanningContext()
        plan = ctx.decompose("ship feature", [
            {"description": "design"},
            {"description": "build", "depends_on": []},
            {"description": "ship", "depends_on": []},
        ])
        plan.steps[1].depends_on = [plan.steps[0].step_id]
        plan.steps[2].depends_on = [plan.steps[1].step_id]
        self.assertEqual(plan.next_step().description, "design")
        ctx.complete_step(plan, plan.steps[0].step_id)
        self.assertEqual(plan.next_step().description, "build")

    def test_all_18_probability_systems_score(self):
        from skeleton.contexts.planning import PROBABILITY_SYSTEMS, QueByPriority
        self.assertEqual(len(PROBABILITY_SYSTEMS), 18)
        q = QueByPriority()
        card = q.score({"priority": 5.0, "attempts": 4, "done": 3, "appearances": 2})
        self.assertEqual(len(card), 18)
        for name, value in card.items():
            self.assertGreaterEqual(value, 0.0, f"{name} below range")
            self.assertLessEqual(value, 1.0, f"{name} above range")

    def test_queue_dequeues_highest_blend(self):
        from skeleton.contexts import QueByPriority
        q = QueByPriority()
        q.enqueue("response", "low", record={"priority": 0.5})
        q.enqueue("workorder", "high", record={"priority": 9.0, "attempts": 5, "done": 5})
        item = q.dequeue()
        self.assertEqual(item.payload, "high")

    def test_weight_adaptation(self):
        from skeleton.contexts import QueByPriority
        q = QueByPriority()
        before = dict(q._weights)
        q.adapt_weights({"urgency": 1.0, "recency": 0.0})
        self.assertGreater(q._weights["urgency"], before["urgency"])
        total = sum(q._weights.values())
        self.assertAlmostEqual(total, 1.0, places=5)


class TestOracleMatrix(unittest.TestCase):
    def _fabric_oracle(self):
        from skeleton.contexts import ContextFabric
        fabric = ContextFabric()
        fabric.planning.decompose("finish the product", [
            {"description": "gather requirements"},
            {"description": "build core", "connector": "github.push"},
            {"description": "verify quality"},
            {"description": "ship it", "connector": "github.push"},
        ])
        return fabric.oracle

    def test_reading_has_all_three_sights(self):
        oracle = self._fabric_oracle()
        reading = oracle.read()
        self.assertTrue(reading.next_event)
        self.assertIn("quality_band", reading.completion_forecast)
        self.assertGreater(len(reading.strings), 0)

    def test_golden_path_marked(self):
        oracle = self._fabric_oracle()
        reading = oracle.read()
        self.assertIsNotNone(reading.golden_path)
        self.assertTrue(reading.golden_path.golden)

    def test_narration_is_positive(self):
        oracle = self._fabric_oracle()
        text = oracle.guide()
        self.assertIn("golden path", text.lower())

    def test_strings_reweave_on_every_read(self):
        oracle = self._fabric_oracle()
        oracle.read()
        oracle.read()
        self.assertEqual(oracle.stats()["readings"], 2)


class TestContextSyntaxFixer(unittest.TestCase):
    def test_grammar_roundtrip(self):
        from skeleton.contexts import ContextSyntaxFixer
        fixer = ContextSyntaxFixer()
        raw = fixer.serialize("workorder", "abc123", "github.push", 0.8, "queued")
        fields, error = fixer.parse_entry(raw)
        self.assertIsNone(error)
        self.assertEqual(fields["connector"], "github.push")

    def test_repairs_unknown_status(self):
        from skeleton.contexts import ContextSyntaxFixer
        fixer = ContextSyntaxFixer()
        fixed, issues = fixer.fix_entry("workorder", "workorder:x1@github.push#1.0!complete")
        self.assertTrue(any(i.rule == "unknown_status" for i in issues))
        self.assertIn("!done", fixed)

    def test_rebinds_dangling_connector(self):
        from skeleton.contexts import ContextSyntaxFixer
        fixer = ContextSyntaxFixer()
        fixed, issues = fixer.fix_entry("workorder", "workorder:x2@github.pu#1.0!queued")
        self.assertTrue(any(i.rule == "dangling_connector" for i in issues))
        self.assertIn("@github.push", fixed)

    def test_clamps_priority(self):
        from skeleton.contexts import ContextSyntaxFixer
        fixer = ContextSyntaxFixer()
        fixed, issues = fixer.fix_entry("workorder", "workorder:x3#99.0")
        self.assertTrue(any(i.rule == "priority_out_of_range" for i in issues))
        self.assertIn("#10.00", fixed)

    def test_salvages_malformed_grammar(self):
        from skeleton.contexts import ContextSyntaxFixer
        fixer = ContextSyntaxFixer()
        fixed, issues = fixer.fix_entry("queue", "###garbage###")
        self.assertTrue(any(i.rule == "malformed_grammar" for i in issues))
        self.assertTrue(fixed.startswith("queue:"))

    def test_scan_covers_all_connected_planes(self):
        from skeleton.contexts import ContextFabric
        fabric = ContextFabric()
        fabric.connect_all()
        fabric.workorders.distill("push files to github", 100)
        issues = fabric.syntax.scan()
        self.assertEqual(fabric.syntax.stats()["planes_connected"], 4)


class TestContextFabricIntegration(unittest.TestCase):
    def test_full_distill_cycle(self):
        from skeleton.contexts import ContextFabric
        fabric = ContextFabric()
        fabric.connect_all()
        result = fabric.distill(
            "Here is the plan. Push these files to github. Then search the web for docs. "
            "Build pdf of the report. That covers everything.",
            token_count=4000,
        )
        self.assertGreater(result["orders_active"], 0)
        self.assertGreater(result["queued"], 0)

    def test_genesis_wires_fabric(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("contexts", g.report.phases)
        for handle in ("fabric", "workorders", "backlog", "planning", "queue", "oracle", "syntax_fixer"):
            self.assertIn(handle, g.handles)

    def test_genesis_invariant_holds(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        violations = g.lattice.evaluate()
        self.assertNotIn("contexts_planes_connected", violations)

    def test_fabric_uses_genesis_mag(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        fabric = g.get("fabric")
        self.assertIs(fabric.workorders._mag, g.get("mag"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
