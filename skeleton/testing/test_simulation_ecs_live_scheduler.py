"""Live ECS scheduler, deterministic ticking, snapshots, rollback and store bridge."""
from __future__ import annotations

import json
import unittest

from skeleton.simulation.ecs.errors import (
    AccessViolationError,
    ScheduleCycleError,
    ScheduleError,
    SnapshotDigestError,
    SnapshotError,
    ValidationError,
)
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.live_snapshot import (
    SnapshotRing,
    decode_snapshot,
    encode_snapshot,
    from_entity_store,
    to_entity_store,
    world_from_snapshot,
)
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec
from skeleton.simulation.ecs.ticker import (
    FixedStepRunner,
    SystemDef,
    SystemFailure,
    TickScheduler,
)
from skeleton.simulation.ecs.world import WorldSession


def build(seed: int = 11, units: int = 12):
    world = LiveWorld(name="arena", seed=seed)
    world.register_component("pos", fields=[FieldSpec("x", FieldKind.FLOAT, default=0.0), FieldSpec("y", FieldKind.FLOAT, default=0.0)])
    world.register_component("vel", fields=[FieldSpec("dx", FieldKind.FLOAT, default=0.0), FieldSpec("dy", FieldKind.FLOAT, default=0.0)])
    world.register_component("hp", fields=[FieldSpec("hp", FieldKind.INT, minimum=0)])
    world.register_component("dead", tag=True)
    world.register_component("poison", storage="sparse")
    for i in range(units):
        world.spawn({"pos": {"x": float(i)}, "vel": {"dx": 0.5 + i * 0.25, "dy": -0.125}, "hp": {"hp": 20 + i}})

    sched = TickScheduler()

    def movement(ctx):
        for _, pos, vel in ctx.query("pos", "vel", without=("dead",), mut=("pos",)):
            pos["x"] += vel["dx"] * ctx.dt * 60
            pos["y"] += vel["dy"] * ctx.dt * 60

    def hazards(ctx):
        for h, _ in ctx.query("hp", without=("dead", "poison")):
            if ctx.rng.chance(0.2):
                ctx.commands.insert(h, "poison", {"dps": ctx.rng.randint(1, 3)})

    def poison(ctx):
        for h, hp, p in ctx.query("hp", "poison", mut=("hp",)):
            hp["hp"] = max(0, hp["hp"] - p["dps"])
            if hp["hp"] == 0:
                ctx.commands.insert(h, "dead")
                ctx.commands.remove(h, "poison")
                ctx.send("deaths", {"entity": h, "tick": ctx.tick})

    def scoreboard(ctx):
        total = ctx.resource("score", 0)
        ctx.set_resource("score", total + len(ctx.read("deaths")))

    def reaper(ctx):
        for h in ctx.query("dead").entities():
            if ctx.rng.chance(0.5):
                ctx.commands.despawn(h)

    sched.add_system(movement, reads=("vel", "dead"), writes=("pos",))
    sched.add_system(hazards, reads=("hp", "dead"), writes=("poison",), after=("movement",))
    sched.add_system(poison, reads=("poison",), writes=("hp", "dead", "poison", "event:deaths"), after=("hazards",))
    sched.add_system(scoreboard, phase=30, reads=("event:deaths",), writes=("res:score",))
    sched.add_system(reaper, phase=30, reads=("dead",), every=3, offset=1)
    return world, sched


class SchedulerPlanTests(unittest.TestCase):
    def test_plan_orders_and_batches_conflict_free(self):
        _, sched = build()
        plan = sched.plan()
        order = plan.ordered_system_ids
        self.assertLess(order.index("movement"), order.index("hazards"))
        self.assertLess(order.index("hazards"), order.index("poison"))
        self.assertEqual(order[-2:], ("reaper", "scoreboard"))
        # reaper and scoreboard touch disjoint data -> same batch
        self.assertTrue(any(set(b.system_ids) == {"reaper", "scoreboard"} for b in plan.batches))

    def test_cycles_and_unknown_dependencies_fail(self):
        s = TickScheduler()
        s.add_system(lambda c: None, name="a", after=("b",))
        s.add_system(lambda c: None, name="b", after=("a",))
        with self.assertRaises(ScheduleCycleError):
            s.plan()
        s2 = TickScheduler()
        s2.add_system(lambda c: None, name="a", after=("ghost",))
        with self.assertRaises(ScheduleError):
            s2.run_tick(LiveWorld())

    def test_definition_validation(self):
        with self.assertRaises(ValidationError):
            SystemDef("bad name", lambda c: None)
        with self.assertRaises(ValidationError):
            SystemDef("ok", lambda c: None, every=2, offset=2)
        s = TickScheduler()
        s.add_system(lambda c: None, name="x")
        with self.assertRaises(ScheduleError):
            s.add_system(lambda c: None, name="x")

    def test_exclusive_system_runs_alone(self):
        s = TickScheduler()
        s.add_system(lambda c: None, name="a", reads=("pos",))
        s.add_system(lambda c: None, name="b", reads=("vel",))
        s.add_system(lambda c: None, name="world_edit", exclusive=True)
        for batch in s.plan().batches:
            if "world_edit" in batch.system_ids:
                self.assertEqual(batch.system_ids, ("world_edit",))

    def test_remove_and_disable(self):
        s = TickScheduler()
        s.add_system(lambda c: None, name="a")
        s.add_system(lambda c: None, name="b", after=("a",))
        with self.assertRaises(ScheduleError):
            s.remove("a")
        s.set_enabled("b", False)
        w = LiveWorld()
        self.assertEqual(s.run_tick(w).ran, ("a",))
        s.remove("b")
        s.remove("a")
        self.assertEqual(s.names(), ())


class AccessTests(unittest.TestCase):
    def test_undeclared_reads_and_writes_are_rejected(self):
        w, _ = build(units=1)
        s = TickScheduler()
        s.add_system(lambda c: c.query("pos").count(), name="sneaky_read", reads=("vel",))
        with self.assertRaises(SystemFailure) as cm:
            s.run_tick(w)
        self.assertIsInstance(cm.exception.__cause__, AccessViolationError)

        s2 = TickScheduler()
        s2.add_system(lambda c: list(c.query("pos", mut=("pos",))), name="sneaky_write", reads=("pos",))
        with self.assertRaises(SystemFailure):
            s2.run_tick(w)

        s3 = TickScheduler()
        s3.add_system(lambda c: c.set_resource("r", 1), name="res_write", reads=("res:r",))
        with self.assertRaises(SystemFailure):
            s3.run_tick(w)

    def test_non_strict_mode_allows_everything(self):
        w, _ = build(units=1)
        s = TickScheduler(strict_access=False)
        s.add_system(lambda c: c.set_resource("r", c.query("pos").count()), name="anything")
        s.run_tick(w)
        self.assertEqual(w.get_resource("r"), 1)


class TickingTests(unittest.TestCase):
    def test_cadence_and_run_if(self):
        w = LiveWorld()
        s = TickScheduler()
        seen = []
        s.add_system(lambda c: seen.append(("every2", c.tick)), name="every2", every=2)
        s.add_system(lambda c: seen.append(("gated", c.tick)), name="gated", run_if=lambda world: world.get_resource("go", False))
        s.run(w, 4)
        w.set_resource("go", True)
        s.run_tick(w)
        self.assertEqual(seen, [("every2", 2), ("every2", 4), ("gated", 5)])

    def test_commands_apply_at_sync_points_not_mid_batch(self):
        w = LiveWorld()
        w.register_component("m", tag=True)
        s = TickScheduler(strict_access=False)
        counts = []
        s.add_system(lambda c: c.commands.spawn({"m": None}), name="spawner")
        s.add_system(lambda c: counts.append(c.query("m").count()), name="counter", reads=("x",))
        s.add_system(lambda c: counts.append(c.query("m").count()), name="later", after=("spawner",))
        s.run_tick(w)
        # 'counter' shares spawner's batch (no conflicts) and sees nothing;
        # 'later' runs after the sync point and sees the spawn.
        self.assertEqual(counts, [0, 1])

    def test_change_detection_across_ticks_regardless_of_order(self):
        w = LiveWorld()
        w.register_component("v", fields=[FieldSpec("n", FieldKind.INT, default=0)])
        e = w.spawn({"v": {}})
        s = TickScheduler()
        observed = []
        # observer runs *before* the writer each tick (phase PRE)
        s.add_system(lambda c: observed.append((c.tick, c.query("v", changed=("v",)).entities())), name="observer", phase=10, reads=("v",))
        s.add_system(lambda c: c.tick % 2 == 0 and c.patch(e, "v", {"n": c.tick}), name="writer", phase=20, writes=("v",))
        s.run(w, 5)
        self.assertEqual(observed, [(1, [e]), (2, []), (3, [e]), (4, []), (5, [e])])

    def test_removed_trackers_are_double_buffered(self):
        w = LiveWorld()
        w.register_component("t", tag=True)
        e = w.spawn({"t": None})
        s = TickScheduler(strict_access=False)
        seen = []
        s.add_system(lambda c: seen.append(c.removed("t")), name="early", phase=10)
        s.add_system(lambda c: c.tick == 1 and c.commands.remove(e, "t"), name="remover", phase=20)
        s.run(w, 3)
        self.assertEqual(seen, [(), (e,), ()])

    def test_atomic_tick_rolls_back_on_failure(self):
        w, s = build()
        s.atomic = True
        s.run(w, 3)
        before = w.snapshot()

        def boom(ctx):
            ctx.commands.spawn({})
            raise RuntimeError("kaboom")

        s.add_system(boom, phase=30, name="boom")
        with self.assertRaises(SystemFailure) as cm:
            s.run_tick(w)
        self.assertTrue(cm.exception.context["rolled_back"])
        self.assertEqual(w.snapshot().snapshot_digest, before.snapshot_digest)

    def test_non_atomic_failure_discards_reservations(self):
        w = LiveWorld()
        s = TickScheduler()
        s.add_system(lambda c: (c.commands.spawn({}), 1 / 0), name="bad")
        with self.assertRaises(SystemFailure):
            s.run_tick(w)
        self.assertEqual(w.entity_count, 0)
        w.snapshot()

    def test_fixed_step_runner(self):
        w = LiveWorld()
        s = TickScheduler(fixed_dt=0.01)
        runner = FixedStepRunner(s, w, max_substeps=4)
        self.assertEqual(runner.advance(5_000_000).ticks, 0)
        report = runner.advance(20_000_000)
        self.assertEqual(report.ticks, 2)
        self.assertAlmostEqual(report.alpha, 0.5)
        clamp = runner.advance(1_000_000_000)
        self.assertEqual(clamp.ticks, 4)
        self.assertGreater(clamp.dropped_ns, 0)
        self.assertLess(runner.accumulator_ns, runner.step_ns)
        self.assertEqual(w.tick, 6)


class DeterminismTests(unittest.TestCase):
    def run_digests(self, seed, ticks=40):
        w, s = build(seed)
        return [s.run_tick(w) and w.state_digest for _ in range(ticks)], w

    def test_identical_seeds_identical_histories(self):
        a, wa = self.run_digests(5)
        b, wb = self.run_digests(5)
        self.assertEqual(a, b)
        self.assertEqual(wa.snapshot().snapshot_digest, wb.snapshot().snapshot_digest)
        self.assertGreater(wa.get_resource("score"), 0)

    def test_different_seeds_diverge(self):
        self.assertNotEqual(self.run_digests(5, 20)[0][-1], self.run_digests(6, 20)[0][-1])

    def test_restore_midway_continues_bit_identically(self):
        w, s = build(21)
        s.run(w, 15)
        snap = w.snapshot()
        s.run(w, 25)
        expected = w.snapshot().snapshot_digest

        w2, s2 = build(21, units=0)  # fresh world, same systems
        w2.restore(decode_snapshot(encode_snapshot(snap)))
        s2.run(w2, 25)
        self.assertEqual(w2.snapshot().snapshot_digest, expected)

    def test_system_registration_order_does_not_matter(self):
        w1, s1 = build(3)
        w2, _ = build(3)
        s2 = TickScheduler()
        for name in reversed(s1.names()):
            d = s1.get(name)
            s2.add(d)
        s1.run(w1, 20)
        s2.run(w2, 20)
        self.assertEqual(w1.state_digest, w2.state_digest)

    def test_layout_independent_state_digest(self):
        w1, _ = build(units=0)
        w2, _ = build(units=0)
        a = w1.spawn({"pos": {}, "vel": {}})
        w1.insert(a, "hp", {"hp": 1})
        b = w2.spawn({"hp": {"hp": 1}})
        w2.insert(b, "vel", {})
        w2.insert(b, "pos", {})
        self.assertEqual(w1.state_digest, w2.state_digest)
        self.assertNotEqual(w1.snapshot().snapshot_digest, w2.snapshot().snapshot_digest)


class SnapshotTests(unittest.TestCase):
    def test_encode_decode_and_tamper_detection(self):
        w, s = build()
        s.run(w, 5)
        text = encode_snapshot(w.snapshot())
        clone = world_from_snapshot(decode_snapshot(text))
        clone.check_integrity()
        self.assertEqual(clone.state_digest, w.state_digest)
        doc = json.loads(text)
        doc["payload"]["payload"]["tick"] = 999
        with self.assertRaises(ValidationError):
            decode_snapshot(json.dumps(doc))

    def test_forged_snapshot_payload_is_rejected(self):
        w, _ = build()
        snap = w.snapshot()
        forged = type(snap)({**snap.payload, "tick": 5}, snap.snapshot_digest, snap.state_digest, snap.tick)
        with self.assertRaises(SnapshotDigestError):
            w.restore(forged)

    def test_snapshot_refused_mid_iteration_or_with_reservations(self):
        w, _ = build()
        q = w.commands()
        q.spawn({})
        with self.assertRaises(SnapshotError):
            w.snapshot()
        q.discard()
        with self.assertRaises(SnapshotError):
            for _ in w.query("pos"):
                w.snapshot()

    def test_ring_rollback(self):
        w, s = build(8)
        ring = SnapshotRing(capacity=4)
        digests = {}
        for _ in range(6):
            s.run_tick(w)
            ring.capture(w)
            digests[w.tick] = w.state_digest
        self.assertEqual(ring.ticks(), (3, 4, 5, 6))
        ring.rollback(w, 4)
        self.assertEqual(w.tick, 4)
        self.assertEqual(w.state_digest, digests[4])
        self.assertEqual(ring.ticks(), (3, 4))
        s.run_tick(w)
        self.assertEqual(w.state_digest, digests[5])
        with self.assertRaises(SnapshotError):
            ring.at_or_before(1)

    def test_query_objects_survive_restore(self):
        w, _ = build(units=3)
        q = w.query("pos")
        snap = w.snapshot()
        w.spawn({"pos": {}, "hp": {"hp": 1}, "vel": {}, "poison": 1})
        self.assertEqual(q.count(), 4)
        w.restore(snap)
        self.assertEqual(q.count(), 3)


class StoreBridgeTests(unittest.TestCase):
    def test_round_trip_through_entity_store(self):
        w, s = build(4)
        s.run(w, 10)
        store = to_entity_store(w)
        store.assert_invariants()
        clone = from_entity_store(store)
        clone.check_integrity()
        self.assertEqual(clone.state_digest, w.state_digest)
        # the clone keeps simulating identically
        _, s2 = build(4, units=0)
        s.run(w, 5)
        s2.run(clone, 5)
        self.assertEqual(clone.state_digest, w.state_digest)

    def test_store_edits_are_honoured_on_import(self):
        w, _ = build(4, units=3)
        store = to_entity_store(w)
        first = store.entity_ids()[0]
        store.patch_component(first, "hp", {"hp": 777})
        clone = from_entity_store(store)
        self.assertEqual(clone.get(w.entity_list()[0], "hp"), {"hp": 777})
        # structural edit -> canonical rebuild, still consistent
        store.remove_component(first, "vel")
        clone2 = from_entity_store(store)
        clone2.check_integrity()
        self.assertFalse(clone2.has(w.entity_list()[0], "vel"))
        self.assertEqual(clone2.entity_count, 3)

    def test_live_world_checkpoints_into_world_session(self):
        w, s = build(2)
        session = WorldSession("arena", to_entity_store(w))
        session.checkpoint("t0")
        s.run(w, 5)
        session.store.replace_from(to_entity_store(w))
        diff = session.diff_checkpoint("t0")
        self.assertTrue(diff.changed_entities or diff.added_entities or diff.removed_entities)

    def test_foreign_store_import(self):
        from skeleton.simulation.ecs.scenario import build_reference_store

        store = build_reference_store()
        world = from_entity_store(store)
        self.assertEqual(world.entity_count, store.entity_count)
        self.assertEqual(world.query("position", "velocity").count(), store.entity_count)


if __name__ == "__main__":
    unittest.main()
