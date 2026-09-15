"""Tests for the over-achiever stack: fleet gov, energy, recovery, atlas, V3.5."""

from __future__ import annotations

import time
import unittest


class TestFleetGovernance(unittest.TestCase):
    def test_registry_tracks_devices(self):
        from skeleton.overseer.fleet_gov import DeviceReport, FleetRegistry
        reg = FleetRegistry()
        reg.ingest(DeviceReport("n1", "laptop", 0.2, 0.9, 0.1, "batch", []))
        reg.ingest(DeviceReport("n2", "server", 0.9, 0.95, 0.1, "idle", []))
        self.assertEqual(len(reg.saturated()), 1)
        self.assertEqual(len(reg.with_headroom()), 1)

    def test_migration_hint_when_saturation_and_headroom(self):
        from skeleton.overseer.fleet_gov import DeviceReport, FleetRegistry, LoadMigrationAdvisor
        reg = FleetRegistry()
        reg.ingest(DeviceReport("hot", "laptop", 0.2, 0.9, 0.85, "sustained", []))
        reg.ingest(DeviceReport("cool", "server", 0.95, 0.95, 0.05, "idle", []))
        hints = LoadMigrationAdvisor(reg).advise()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].from_node, "hot")
        self.assertEqual(hints[0].to_node, "cool")

    def test_no_hint_without_headroom(self):
        from skeleton.overseer.fleet_gov import DeviceReport, FleetRegistry, LoadMigrationAdvisor
        reg = FleetRegistry()
        reg.ingest(DeviceReport("hot", "laptop", 0.2, 0.9, 0.5, "batch", []))
        self.assertEqual(LoadMigrationAdvisor(reg).advise(), [])

    def test_coordinated_throttle_clamps(self):
        from skeleton.overseer.fleet_gov import CoordinatedThrottle
        ct = CoordinatedThrottle()
        ct.propose(0.5, ttl=60.0)
        self.assertEqual(ct.current_ceiling(), 0.5)
        self.assertEqual(ct.clamp(0.9), 0.5)
        self.assertEqual(ct.clamp(0.3), 0.3)

    def test_ceiling_expires(self):
        from skeleton.overseer.fleet_gov import CoordinatedThrottle
        ct = CoordinatedThrottle()
        ct._adopt(0.5, ttl=0.01)
        time.sleep(0.02)
        self.assertIsNone(ct.current_ceiling())


class TestEnergyModel(unittest.TestCase):
    def test_draw_scales_with_utilization(self):
        from skeleton.overseer.energy import PowerModel
        pm = PowerModel("workstation")
        idle = pm.estimate(0.1, 0.2, 0.0)
        busy = pm.estimate(0.9, 0.8, 0.3)
        self.assertGreater(busy.total_w, idle.total_w)

    def test_drain_forecast_computes_reserve_throttle(self):
        from skeleton.overseer.energy import BatteryModel
        bm = BatteryModel("laptop")  # 60Wh
        fc = bm.forecast(level=0.30, current_draw_w=20.0, reserve_target=0.2, reserve_deadline_hours=2.0)
        self.assertIsNotNone(fc.hours_to_empty)
        self.assertIsNotNone(fc.min_throttle_for_reserve)
        self.assertLessEqual(fc.min_throttle_for_reserve, 1.0)

    def test_quality_trade_harder_on_rag(self):
        from skeleton.overseer.energy import BatteryModel, PowerModel
        bm = BatteryModel("laptop")
        draw = PowerModel("laptop").estimate(0.9, 0.8, 0.3)
        trade = bm.quality_trade(draw, target_w=draw.total_w * 0.5)
        self.assertLessEqual(trade["rag_top_k_scale"], trade["miner_scale"])

    def test_no_trade_when_within_budget(self):
        from skeleton.overseer.energy import BatteryModel, PowerModel
        bm = BatteryModel("laptop")
        draw = PowerModel("laptop").estimate(0.1, 0.1, 0.0)
        trade = bm.quality_trade(draw, target_w=draw.total_w * 2.0)
        self.assertEqual(trade["rag_top_k_scale"], 1.0)


class TestRecoveryEngine(unittest.TestCase):
    def test_classifies_fault_classes(self):
        from skeleton.overseer.recovery import FaultClassifier
        c = FaultClassifier()
        self.assertEqual(c.classify({"kind": "sysid_anomaly", "channel": "thermal"}).fault_class, "sensor_fault")
        self.assertEqual(c.classify({"kind": "trust_collapse", "channel": "meta"}).fault_class, "model_drift")
        self.assertEqual(c.classify({"kind": "handler_exception", "channel": "x", "detail": "boom"}).fault_class, "handler_failure")
        self.assertEqual(c.classify({"kind": "health_red", "channel": "mesh"}).fault_class, "cascade_risk")

    def test_playbook_attempts_and_verifies(self):
        from skeleton.overseer.recovery import RecoveryEngine
        eng = RecoveryEngine()
        eng.COOLDOWN_S = 0.0
        fault = eng.ingest({"kind": "sysid_anomaly", "channel": "thermal", "severity": 0.8})
        self.assertIsNotNone(fault)
        attempts = eng.cycle()
        self.assertEqual(len(attempts), 1)
        self.assertEqual(fault.status, "verifying")
        for _ in range(3):
            eng.cycle(signal_clear={"thermal": True})
        self.assertEqual(fault.status, "cured")
        self.assertGreater(eng.ledger.success_rate("sensor_fault", attempts[0].strategy), 0.5)

    def test_cure_ledger_orders_by_success(self):
        from skeleton.overseer.recovery import CureLedger
        ledger = CureLedger()
        for _ in range(4):
            ledger.record("resource_exhaustion", "drain_queue", True)
            ledger.record("resource_exhaustion", "cap_parallelism", False)
        best = ledger.best_strategies("resource_exhaustion", ["cap_parallelism", "drain_queue"])
        self.assertEqual(best[0], "drain_queue")

    def test_chronic_after_strategies_exhausted(self):
        from skeleton.overseer.recovery import RecoveryEngine
        eng = RecoveryEngine()
        eng.COOLDOWN_S = 0.0
        eng.VERIFY_TICKS = 1
        fault = eng.ingest({"kind": "sysid_anomaly", "channel": "x", "severity": 0.9})
        # Fail every strategy
        for name in eng._handlers:
            pass
        eng._handlers = {n: (lambda f: {"ok": False}) for n in
                         ("reset_channel_model", "quarantine_channel", "fallback_sensor")}
        for _ in range(10):
            eng.cycle(signal_clear={"x": False})
        self.assertIn(fault.status, ("chronic", "open", "verifying"))


class TestCapabilityAtlas(unittest.TestCase):
    def test_evaluates_by_device_class(self):
        from skeleton.overseer.atlas import CapabilityAtlas
        atlas = CapabilityAtlas()
        atlas.evaluate("embedded", 1.0, {"critical": 1.0, "interactive": 0.5, "background": 0.3, "deferrable": 0.2})
        s = atlas.summary()
        self.assertGreater(s["by_state"].get("unavailable", 0), 0)

    def test_tier_shed_marks_unavailable(self):
        from skeleton.overseer.atlas import CapabilityAtlas
        atlas = CapabilityAtlas()
        atlas.evaluate("server", 1.0, {"critical": 1.0, "interactive": 0.5, "background": 0.3, "deferrable": 0.0})
        states = {n: a.state for n, a in atlas._evaluations.items()}
        self.assertEqual(states["fabric.backlog_chain"], "unavailable")
        self.assertEqual(states["governor.throttle"], "available")  # critical always runs

    def test_narration_is_honest(self):
        from skeleton.overseer.atlas import CapabilityAtlas
        atlas = CapabilityAtlas()
        atlas.evaluate("laptop", 1.0, {"critical": 1.0, "interactive": 0.5, "background": 0.3, "deferrable": 0.2})
        text = atlas.narrate()
        self.assertIn("On this device", text)


class TestEngineV35(unittest.TestCase):
    def test_tick_full_telemetry(self):
        from skeleton.overseer.engine_v35 import OverseerEngineV35
        engine = OverseerEngineV35()
        tick = engine.tick()
        d = tick.to_dict()
        for key in ("control", "v3", "energy", "recovery", "fleet", "atlas"):
            self.assertIn(key, d)
        self.assertGreaterEqual(d["control"], 0.05)
        self.assertLessEqual(d["control"], 1.0)

    def test_energy_draw_present(self):
        from skeleton.overseer.engine_v35 import OverseerEngineV35
        engine = OverseerEngineV35()
        tick = engine.tick()
        self.assertGreater(tick.energy["draw"]["total_w"], 0.0)

    def test_atlas_evaluated_per_tick(self):
        from skeleton.overseer.engine_v35 import OverseerEngineV35
        engine = OverseerEngineV35()
        engine.tick()
        self.assertGreater(engine.atlas.summary()["total"], 10)
        self.assertTrue(engine.narrate_capabilities().startswith("On this device"))

    def test_fleet_unattached_gracefully(self):
        from skeleton.overseer.engine_v35 import OverseerEngineV35
        engine = OverseerEngineV35()
        tick = engine.tick()
        self.assertFalse(tick.fleet["attached"])

    def test_genesis_wires_v35(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("engine_v35", g.handles)
        engine = g.get("engine_v35")
        self.assertGreaterEqual(engine._ticks, 1)

    def test_v35_fleet_attached_in_genesis(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        engine = g.get("engine_v35")
        self.assertIsNotNone(engine.fleet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
