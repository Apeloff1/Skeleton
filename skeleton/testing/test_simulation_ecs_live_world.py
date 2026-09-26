"""Live ECS world: handles, archetype/sparse storage, queries, commands, events."""
from __future__ import annotations

import json
import unittest

from skeleton.simulation.ecs.channels import EventBus
from skeleton.simulation.ecs.components import ComponentRegistry, StorageKind, ValueKind
from skeleton.simulation.ecs.entities import (
    MAX_GENERATION,
    HandleAllocator,
    handle_from_text,
    handle_generation,
    handle_index,
    handle_to_text,
    pack_handle,
)
from skeleton.simulation.ecs.errors import (
    BoundsError,
    CommandError,
    ComponentNotFoundError,
    ComponentTypeError,
    EntityHandleError,
    EventError,
    EventOverflowError,
    QueryError,
    ResourceNotFoundError,
    StructuralChangeError,
    ValidationError,
)
from skeleton.simulation.ecs.identity import validate_entity_id
from skeleton.simulation.ecs.live import LiveWorld
from skeleton.simulation.ecs.rng import DeterministicRng
from skeleton.simulation.ecs.schema import FieldKind, FieldSpec
from skeleton.simulation.ecs.storage import ArchetypeGraph, SparseSet
from skeleton.simulation.ecs.values import (
    canonical_copy,
    check_value,
    from_json,
    to_json,
)


def make_world(**kwargs) -> LiveWorld:
    world = LiveWorld(**kwargs)
    world.register_component("pos", fields=[FieldSpec("x", FieldKind.FLOAT, default=0.0), FieldSpec("y", FieldKind.FLOAT, default=0.0)])
    world.register_component("vel", fields=[FieldSpec("dx", FieldKind.FLOAT, default=0.0), FieldSpec("dy", FieldKind.FLOAT, default=0.0)])
    world.register_component("hp", fields=[FieldSpec("hp", FieldKind.INT, minimum=0, maximum=1000)])
    world.register_component("frozen", tag=True)
    world.register_component("burning", storage="sparse")
    world.register_component("stun", tag=True, storage="sparse")
    world.register_component("inventory")
    return world


class HandleTests(unittest.TestCase):
    def test_pack_roundtrip(self):
        h = pack_handle(7, 3)
        self.assertEqual((handle_index(h), handle_generation(h)), (7, 3))
        self.assertEqual(handle_from_text(handle_to_text(h)), h)

    def test_text_form_is_a_valid_store_entity_id(self):
        self.assertEqual(validate_entity_id(handle_to_text(pack_handle(123456, 99))), "live:e0001e240g63")

    def test_bad_handles_rejected(self):
        for bad in (-1, True, "1", 1.0):
            with self.assertRaises(EntityHandleError):
                handle_to_text(bad)
        with self.assertRaises(EntityHandleError):
            handle_from_text("live:eXYZ")
        with self.assertRaises(EntityHandleError):
            pack_handle(0, MAX_GENERATION + 1)

    def test_generations_prevent_aba(self):
        alloc = HandleAllocator()
        a = alloc.allocate()
        alloc.release(a)
        b = alloc.allocate()
        self.assertEqual(handle_index(a), handle_index(b))
        self.assertNotEqual(a, b)
        self.assertFalse(alloc.is_alive(a))
        self.assertTrue(alloc.is_alive(b))
        with self.assertRaises(EntityHandleError):
            alloc.release(a)

    def test_fifo_recycling_is_deterministic(self):
        def run():
            alloc = HandleAllocator()
            hs = [alloc.allocate() for _ in range(6)]
            for h in (hs[4], hs[1], hs[3]):
                alloc.release(h)
            return [alloc.allocate() for _ in range(4)]
        first = run()
        self.assertEqual(first, run())
        self.assertEqual([handle_index(h) for h in first], [4, 1, 3, 6])

    def test_reserve_commit_cancel(self):
        alloc = HandleAllocator()
        r = alloc.reserve()
        self.assertFalse(alloc.is_alive(r))
        alloc.commit(r)
        self.assertTrue(alloc.is_alive(r))
        r2 = alloc.reserve()
        alloc.cancel(r2)
        again = alloc.allocate()
        self.assertEqual(handle_index(again), handle_index(r2))
        self.assertNotEqual(again, r2)

    def test_capacity_bound(self):
        alloc = HandleAllocator(capacity=2)
        alloc.allocate(); alloc.allocate()
        with self.assertRaises(BoundsError):
            alloc.allocate()

    def test_snapshot_restore_continues_identically(self):
        alloc = HandleAllocator()
        hs = [alloc.allocate() for _ in range(5)]
        alloc.release(hs[2]); alloc.release(hs[0])
        clone = HandleAllocator.restore(json.loads(json.dumps(alloc.snapshot())))
        self.assertEqual([alloc.allocate() for _ in range(3)], [clone.allocate() for _ in range(3)])

    def test_restore_rejects_inconsistent_records(self):
        good = HandleAllocator()
        good.allocate()
        rec = good.snapshot()
        with self.assertRaises(EntityHandleError):
            HandleAllocator.restore({**rec, "free": [0]})
        with self.assertRaises(EntityHandleError):
            HandleAllocator.restore({**rec, "states": [7]})
        with self.assertRaises(EntityHandleError):
            HandleAllocator.restore({**rec, "generations": [0, 0]})

    def test_generation_exhaustion_retires_slot(self):
        alloc = HandleAllocator()
        h = alloc.allocate()
        alloc._generations[0] = MAX_GENERATION
        alloc.release(pack_handle(0, MAX_GENERATION))
        fresh = alloc.allocate()
        self.assertEqual(handle_index(fresh), 1)
        del h


class ValueTests(unittest.TestCase):
    def test_lossless_json_roundtrip(self):
        value = {"t": (1, (2.5, b"\x00\xff")), "l": [None, True, -3], "$t": 1, "nested": {"$b": "x"}}
        wire = json.loads(json.dumps(to_json(value)))
        self.assertEqual(from_json(wire), value)
        self.assertIsInstance(from_json(wire)["t"], tuple)

    def test_rejects_non_plain_data(self):
        for bad in ({1, 2}, object(), float("nan"), {1: "x"}, [lambda: 0], float("inf")):
            with self.assertRaises(ValidationError):
                check_value(bad)

    def test_depth_bound(self):
        deep = []
        cur = deep
        for _ in range(40):
            nxt = []
            cur.append(nxt)
            cur = nxt
        with self.assertRaises(ValidationError):
            check_value(deep)

    def test_canonical_copy_sorts_keys(self):
        self.assertEqual(list(canonical_copy({"b": 1, "a": {"d": 1, "c": 2}})), ["a", "b"])


class ComponentRegistryTests(unittest.TestCase):
    def test_register_idempotent_and_conflicts(self):
        reg = ComponentRegistry()
        a = reg.register("tagx", tag=True)
        self.assertIs(reg.register("tagx", tag=True), a)
        with self.assertRaises(ComponentTypeError):
            reg.register("tagx", storage="sparse", tag=True)
        with self.assertRaises(ComponentTypeError):
            reg.register("bad name")
        with self.assertRaises(ComponentTypeError):
            reg.register("both", tag=True, fields=[])

    def test_normalise_schema_defaults_and_errors(self):
        w = make_world()
        self.assertEqual(w.components.normalise("pos", {"x": 2}), {"x": 2.0, "y": 0.0})
        with self.assertRaises(ValidationError):
            w.components.normalise("pos", {"z": 1})
        with self.assertRaises(ValidationError):
            w.components.normalise("hp", {"hp": -1})
        with self.assertRaises(ValidationError):
            w.components.normalise("frozen", {"x": 1})

    def test_catalog_roundtrip(self):
        w = make_world()
        clone = ComponentRegistry.from_catalog(json.loads(json.dumps(w.components.catalog())))
        self.assertEqual(clone.fingerprint, w.components.fingerprint)
        self.assertIs(clone.get("burning").storage, StorageKind.SPARSE)
        self.assertIs(clone.get("frozen").value_kind, ValueKind.TAG)

    def test_unknown_component(self):
        with self.assertRaises(ComponentTypeError):
            make_world().spawn({"nope": 1})


class StorageTests(unittest.TestCase):
    def test_archetype_edges_are_cached_and_symmetric(self):
        g = ArchetypeGraph()
        t1 = g.with_component(g.empty, 3)
        t2 = g.with_component(t1, 1)
        self.assertEqual(t2.signature, (1, 3))
        self.assertIs(g.without_component(t2, 1), t1)
        gen = g.generation
        self.assertIs(g.with_component(t1, 1), t2)
        self.assertEqual(g.generation, gen)

    def test_sparse_set_swap_remove(self):
        s = SparseSet(0)
        hs = [pack_handle(i, 0) for i in range(4)]
        for i, h in enumerate(hs):
            s.insert(h, i, tick=1)
        self.assertEqual(s.remove(hs[1]), 1)
        self.assertEqual(s.entities, [hs[0], hs[3], hs[2]])
        self.assertEqual(s.get(hs[3]), 3)
        self.assertNotIn(pack_handle(3, 1), s)
        with self.assertRaises(KeyError):
            s.remove(hs[1])


class WorldTests(unittest.TestCase):
    def test_spawn_get_insert_remove_moves_archetypes(self):
        w = make_world()
        e = w.spawn({"pos": {"x": 1.0}})
        t0 = w.table_of(e)
        w.insert(e, "vel", {"dx": 2.0})
        self.assertNotEqual(w.table_of(e).table_id, t0.table_id)
        self.assertEqual(w.components_of(e), ("pos", "vel"))
        self.assertEqual(w.remove(e, "vel"), {"dx": 2.0, "dy": 0.0})
        self.assertIs(w.table_of(e), t0)
        with self.assertRaises(ComponentNotFoundError):
            w.get(e, "vel")
        self.assertIsNone(w.get(e, "vel", None))
        w.check_integrity()

    def test_swap_remove_keeps_locations_valid(self):
        w = make_world()
        es = [w.spawn({"pos": {"x": float(i)}}) for i in range(10)]
        for e in es[::3]:
            w.despawn(e)
        w.insert(es[4], "vel", {})
        w.remove(es[5], "pos")
        w.check_integrity()
        for i, e in enumerate(es):
            if e in es[::3]:
                self.assertFalse(w.is_alive(e))
            elif e != es[5]:
                self.assertEqual(w.get(e, "pos")["x"], float(i))

    def test_sparse_components_do_not_move_rows(self):
        w = make_world()
        e = w.spawn({"pos": {}})
        table, row = w._location(e)
        w.insert(e, "burning", {"dps": 3})
        w.insert(e, "stun")
        self.assertEqual(w._location(e), (table, row))
        self.assertTrue(w.has(e, "stun"))
        self.assertIsNone(w.get(e, "stun"))
        w.remove(e, "burning")
        self.assertFalse(w.has(e, "burning"))
        self.assertEqual(w.removed("burning"), (e,))

    def test_despawn_clears_everything_and_stale_handle_fails(self):
        w = make_world()
        e = w.spawn({"pos": {}, "burning": 1})
        w.despawn(e)
        self.assertFalse(w.has(e, "pos"))
        self.assertEqual(len(w.sparse[w.components.id_of("burning")]), 0)
        with self.assertRaises(EntityHandleError):
            w.insert(e, "vel", {})
        with self.assertRaises(EntityHandleError):
            w.despawn(e)
        e2 = w.spawn({})
        self.assertEqual(handle_index(e2), handle_index(e))
        self.assertFalse(w.has(e, "pos"))

    def test_values_are_validated_and_owned(self):
        w = make_world()
        src = {"items": ["sword"]}
        e = w.spawn({"inventory": src})
        src["items"].append("leak")
        self.assertEqual(w.get(e, "inventory"), {"items": ["sword"]})
        with self.assertRaises(ValidationError):
            w.insert(e, "inventory", {"bad": {1, 2}})
        with self.assertRaises(ValidationError):
            w.insert(e, "hp", {"hp": "lots"})

    def test_patch_revalidates(self):
        w = make_world()
        e = w.spawn({"hp": {"hp": 10}})
        self.assertEqual(w.patch(e, "hp", {"hp": 7}), {"hp": 7})
        with self.assertRaises(ValidationError):
            w.patch(e, "hp", {"hp": 5000})
        self.assertEqual(w.get(e, "hp"), {"hp": 7})

    def test_resources(self):
        w = make_world()
        w.set_resource("gravity", -9.8)
        self.assertEqual(w.get_resource("gravity"), -9.8)
        self.assertEqual(w.get_resource("missing", 3), 3)
        with self.assertRaises(ResourceNotFoundError):
            w.get_resource("missing")
        with self.assertRaises(ValidationError):
            w.set_resource("obj", object())
        self.assertEqual(w.remove_resource("gravity"), -9.8)

    def test_spawn_batch_and_bulk(self):
        w = make_world()
        hs = w.spawn_batch({"pos": {"x": float(i)}, "vel": {"dx": 1.0}} for i in range(200))
        self.assertEqual(len(hs), 200)
        self.assertEqual(w.query("pos", "vel").count(), 200)
        w.check_integrity()

    def test_spawn_with_invalid_value_leaves_no_entity(self):
        w = make_world()
        with self.assertRaises(ValidationError):
            w.spawn({"pos": {}, "hp": {"hp": -5}})
        self.assertEqual(w.entity_count, 0)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.w = make_world()
        self.a = self.w.spawn({"pos": {"x": 1.0}, "vel": {"dx": 1.0}})
        self.b = self.w.spawn({"pos": {"x": 2.0}, "vel": {"dx": 2.0}, "frozen": None})
        self.c = self.w.spawn({"pos": {"x": 3.0}})
        self.d = self.w.spawn({"pos": {"x": 4.0}, "vel": {}, "burning": {"dps": 1}})

    def test_fetch_with_without(self):
        rows = self.w.query("pos", "vel", without=("frozen",)).entities()
        self.assertEqual(rows, [self.a, self.d])
        self.assertEqual(self.w.query("pos", with_=("frozen",)).entities(), [self.b])

    def test_sparse_filters(self):
        self.assertEqual(self.w.query("pos", with_=("burning",)).entities(), [self.d])
        self.assertEqual(set(self.w.query("pos", without=("burning",)).entities()), {self.a, self.b, self.c})
        self.assertEqual(self.w.query("burning").rows(), [(self.d, {"dps": 1})])

    def test_optional(self):
        rows = {h: v for h, _, v in self.w.query("pos", optional=("vel",))}
        self.assertIsNone(rows[self.c])
        self.assertEqual(rows[self.a], {"dx": 1.0, "dy": 0.0})

    def test_invalid_query_shapes(self):
        with self.assertRaises(QueryError):
            self.w.query("pos", without=("pos",))
        with self.assertRaises(QueryError):
            self.w.query("pos", mut=("vel",))
        with self.assertRaises(QueryError):
            self.w.query("pos", optional=("pos",))
        with self.assertRaises(ComponentTypeError):
            self.w.query("ghost")

    def test_cache_refreshes_when_new_archetypes_appear(self):
        q = self.w.query("pos", "vel")
        self.assertEqual(q.count(), 3)
        e = self.w.spawn({"pos": {}, "vel": {}, "hp": {"hp": 1}})
        self.assertEqual(q.count(), 4)
        self.assertTrue(q.contains(e))
        self.assertFalse(q.contains(self.c))

    def test_structural_change_during_iteration_is_rejected(self):
        with self.assertRaises(StructuralChangeError):
            for handle, _ in self.w.query("pos"):
                self.w.despawn(handle)
        # iterator closed -> world usable again
        self.w.despawn(self.a)
        # value writes during iteration are fine
        for handle, pos in self.w.query("pos"):
            self.w.insert(handle, "pos", {"x": pos["x"] + 10})
        self.assertEqual(self.w.get(self.c, "pos")["x"], 13.0)

    def test_changed_and_added_filters(self):
        w = self.w
        base = w.change_tick
        w.change_tick += 1
        w.get_mut(self.c, "pos")["x"] = 30.0
        self.assertEqual(w.query("pos", changed=("pos",), since=base).entities(), [self.c])
        w.change_tick += 1
        e = w.spawn({"pos": {}})
        self.assertEqual(w.query("pos", added=("pos",), since=base + 1).entities(), [e])
        self.assertEqual(w.query("pos", changed=("pos",), since=base).count(), 2)

    def test_mut_stamps_changed(self):
        w = self.w
        w.change_tick = 50
        for _, pos in w.query("pos", with_=("frozen",), mut=("pos",)):
            pos["x"] = -1.0
        self.assertEqual(w.component_ticks(self.b, "pos")[1], 50)
        self.assertEqual(w.query("pos", changed=("pos",), since=49).entities(), [self.b])

    def test_ordered_iteration_is_layout_independent(self):
        w = self.w
        w.insert(self.a, "hp", {"hp": 1})  # move a to a newer table
        self.assertEqual(w.query("pos", ordered=True).entities(), [self.a, self.b, self.c, self.d])
        self.assertNotEqual(w.query("pos").entities(), [self.a, self.b, self.c, self.d])

    def test_single_and_get(self):
        self.assertEqual(self.w.query("burning").single()[0], self.d)
        with self.assertRaises(QueryError):
            self.w.query("pos").single()
        self.assertEqual(self.w.query("pos", "vel").get(self.a)[1]["x"], 1.0)
        with self.assertRaises(ComponentNotFoundError):
            self.w.query("pos", "vel").get(self.c)


class CommandQueueTests(unittest.TestCase):
    def test_spawn_handle_usable_before_apply(self):
        w = make_world()
        q = w.commands()
        e = q.spawn({"pos": {"x": 5.0}})
        q.insert(e, "vel", {"dx": 1.0})
        q.insert(e, "burning", 2)
        self.assertFalse(w.is_alive(e))
        receipt = q.apply()
        self.assertTrue(receipt.ok)
        self.assertEqual(receipt.spawned, (e,))
        self.assertEqual(w.components_of(e), ("burning", "pos", "vel"))

    def test_invalid_value_rejects_whole_queue(self):
        w = make_world()
        keep = w.spawn({"pos": {}})
        q = w.commands()
        q.despawn(keep)
        spawned = q.spawn({"pos": {}})
        q.insert(keep, "hp", {"hp": -1})
        with self.assertRaises(CommandError):
            q.apply()
        self.assertTrue(w.is_alive(keep))
        self.assertFalse(w.is_alive(spawned))
        self.assertEqual(w.entity_count, 1)
        with self.assertRaises(CommandError):
            q.apply()

    def test_dead_targets_are_skipped_deterministically(self):
        w = make_world()
        e = w.spawn({"pos": {}})
        q = w.commands()
        q.despawn(e)
        q.insert(e, "vel", {})
        q.remove(e, "pos")
        receipt = q.apply()
        self.assertEqual(receipt.applied, 1)
        self.assertEqual([s.kind for s in receipt.skipped], ["insert", "remove"])

    def test_discard_cancels_reservations(self):
        w = make_world()
        q = w.commands()
        e = q.spawn({})
        q.discard()
        self.assertFalse(w.is_alive(e))
        self.assertEqual(w.entity_count, 0)
        w.snapshot()  # no dangling reservations

    def test_resources_and_events(self):
        w = make_world()
        q = w.commands()
        q.set_resource("score", 3)
        q.send("hits", {"n": 1})
        q.remove_resource("never")
        receipt = q.apply()
        self.assertEqual(w.get_resource("score"), 3)
        self.assertEqual(w.reader("hits", "t").payloads(), [{"n": 1}])
        self.assertEqual(len(receipt.skipped), 1)

    def test_extend_merges_in_order(self):
        w = make_world()
        q1, q2 = w.commands(), w.commands()
        e = q2.spawn({"pos": {}})
        q1.set_resource("a", 1)
        q1.extend(q2)
        receipt = q1.apply()
        self.assertEqual(receipt.spawned, (e,))
        with self.assertRaises(CommandError):
            q2.apply()


class EventTests(unittest.TestCase):
    def test_every_reader_sees_every_event_once_across_two_updates(self):
        bus = EventBus()
        bus.register("hit")
        early = bus.reader("hit", "early")
        bus.send("hit", 1, tick=1)
        late = bus.reader("hit", "late")
        self.assertEqual([r.payload for r in early.read()], [1])
        bus.update()
        bus.send("hit", 2, tick=2)
        self.assertEqual([r.payload for r in late.read()], [1, 2])
        self.assertEqual([r.payload for r in early.read()], [2])
        self.assertEqual(early.read(), [])

    def test_events_expire_after_two_updates_and_misses_are_counted(self):
        bus = EventBus()
        bus.register("e")
        r = bus.reader("e", "slow")
        bus.send("e", "a", tick=1)
        bus.update(); bus.update()
        bus.send("e", "b", tick=3)
        self.assertEqual(r.payloads(), ["b"])
        self.assertEqual(r.missed, 1)

    def test_payload_isolation_between_readers(self):
        bus = EventBus()
        bus.register("e")
        r1, r2 = bus.reader("e", "1"), bus.reader("e", "2")
        bus.send("e", {"hp": 1}, tick=0)
        r1.payloads()[0]["hp"] = 999
        self.assertEqual(r2.payloads(), [{"hp": 1}])

    def test_capacity_and_validation(self):
        bus = EventBus()
        bus.register("small", capacity=1)
        bus.send("small", 1, tick=0)
        with self.assertRaises(EventOverflowError):
            bus.send("small", 2, tick=0)
        with self.assertRaises(EventError):
            bus.send("unknown", 1, tick=0)
        with self.assertRaises(ValidationError):
            bus.register("x").send(object(), tick=0)

    def test_record_roundtrip_preserves_cursors(self):
        bus = EventBus()
        bus.register("e")
        r = bus.reader("e", "r")
        bus.send("e", (1, 2), tick=0)
        clone = EventBus.from_record(json.loads(json.dumps(bus.to_record())))
        self.assertEqual(clone.reader("e", "r").payloads(), [(1, 2)])
        self.assertEqual(r.payloads(), [(1, 2)])
        self.assertEqual(clone.fingerprint, bus.fingerprint)


class RngTests(unittest.TestCase):
    def test_reproducible_and_forks_are_independent(self):
        a, b = DeterministicRng("seed"), DeterministicRng("seed")
        self.assertEqual([a.next_u64() for _ in range(5)], [b.next_u64() for _ in range(5)])
        f1 = a.fork("ai")
        self.assertEqual(a.state(), b.state())
        self.assertNotEqual(f1.next_u64(), a.fork("physics").next_u64())

    def test_ranges(self):
        r = DeterministicRng(1)
        vals = [r.randint(3, 5) for _ in range(300)]
        self.assertEqual(set(vals), {3, 4, 5})
        self.assertTrue(all(0.0 <= r.random() < 1.0 for _ in range(200)))
        items = list(range(10))
        r.shuffle(items)
        self.assertEqual(sorted(items), list(range(10)))
        self.assertEqual(r.weighted_index([0, 0, 1]), 2)

    def test_state_roundtrip(self):
        r = DeterministicRng(99)
        r.next_u64()
        clone = DeterministicRng.from_state(r.state())
        self.assertEqual(r.next_u64(), clone.next_u64())
        with self.assertRaises(ValidationError):
            clone.set_state([0, 0, 0, 0])

    def test_uniformity_smoke(self):
        r = DeterministicRng(2024)
        buckets = [0] * 8
        for _ in range(8000):
            buckets[r.randint(0, 7)] += 1
        self.assertTrue(all(850 < b < 1150 for b in buckets), buckets)


if __name__ == "__main__":
    unittest.main()
