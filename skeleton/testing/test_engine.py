"""Tests for the hardware-specialized Overseer engine."""

from __future__ import annotations

import unittest


class TestHardwareProbe(unittest.TestCase):
    def test_profile_classifies_device(self):
        from skeleton.overseer import HardwareProbe
        probe = HardwareProbe()
        profile = probe.profile()
        self.assertGreaterEqual(profile.cpu_cores, 1)
        self.assertGreater(profile.memory_total_mb, 0)
        self.assertIn(profile.device_class.value,
                      ("embedded", "mobile", "laptop", "workstation", "server"))

    def test_state_reading_never_fails(self):
        from skeleton.overseer import HardwareProbe
        state = HardwareProbe().read_state()
        self.assertGreaterEqual(state.cpu_load, 0.0)
        self.assertLessEqual(state.cpu_load, 1.0)
        self.assertGreaterEqual(state.memory_pressure, 0.0)
        self.assertLessEqual(state.memory_pressure, 1.0)

    def test_change_detection_thresholds(self):
        from skeleton.overseer.hardware import HardwareProbe, HardwareState
        probe = HardwareProbe()
        hot = HardwareState(cpu_load=0.99, cpu_per_core=[0.99], memory_used_mb=900,
                            memory_available_mb=100, memory_pressure=0.95,
                            swap_pressure=0.5, temps_celsius=[95.0],
                            battery_level=0.05, battery_charging=False, io_wait=0.1)
        changes = probe.detect_changes(hot)
        kinds = {c.kind for c in changes}
        self.assertIn("thermal_spike", kinds)
        self.assertIn("battery_low", kinds)
        self.assertIn("memory_pressure", kinds)
        self.assertIn("cpu_spike", kinds)


class TestBudgetProfile(unittest.TestCase):
    def test_profiles_scale_by_device_class(self):
        from skeleton.overseer import BudgetProfile, DeviceClass
        embedded = BudgetProfile.for_device(type("P", (), {"cpu_cores": 1, "memory_total_mb": 512, "device_class": DeviceClass.EMBEDDED})())
        server = BudgetProfile.for_device(type("P", (), {"cpu_cores": 32, "memory_total_mb": 131072, "device_class": DeviceClass.SERVER})())
        self.assertLess(embedded.queue_size, server.queue_size)
        self.assertLess(embedded.max_resident_planes, server.max_resident_planes)

    def test_scaled_budget_respects_floors(self):
        from skeleton.overseer import BudgetProfile, DeviceClass
        base = BudgetProfile.for_device(type("P", (), {"cpu_cores": 8, "memory_total_mb": 16384, "device_class": DeviceClass.WORKSTATION})())
        scaled = base.scaled(0.2)
        self.assertGreaterEqual(scaled.max_resident_planes, 1)
        self.assertGreaterEqual(scaled.queue_size, 4)
        self.assertGreater(scaled.miner_interval_s, base.miner_interval_s)


class TestResourceGovernor(unittest.TestCase):
    def test_throttle_backs_off_under_pressure(self):
        from skeleton.overseer.governor import ResourceGovernor
        from skeleton.overseer.hardware import HardwareProbe, HardwareState

        class HotProbe(HardwareProbe):
            def read_state(self):
                return HardwareState(cpu_load=0.99, cpu_per_core=[0.99],
                                     memory_used_mb=900, memory_available_mb=100,
                                     memory_pressure=0.95, swap_pressure=0.5,
                                     temps_celsius=[92.0], battery_level=0.05,
                                     battery_charging=False, io_wait=0.3)
        gov = ResourceGovernor(probe=HotProbe())
        decision = gov.tick()
        self.assertLessEqual(decision.throttle, 0.25)
        self.assertGreater(len(decision.reasons), 0)
        self.assertLess(decision.active_budget.queue_size, gov.base_budget.queue_size)

    def test_hysteresis_prevents_oscillation(self):
        from skeleton.overseer.governor import ResourceGovernor
        gov = ResourceGovernor()
        d1 = gov.tick()
        d2 = gov.tick()
        self.assertIs(d1, d2)  # same decision object within deadband

    def test_enforcer_applies_to_consumers(self):
        from skeleton.overseer.governor import ResourceGovernor
        gov = ResourceGovernor()
        applied = []
        gov.enforcer.attach("test_consumer", lambda b: applied.append(b.queue_size))
        gov.tick()
        self.assertEqual(len(applied), 1)


class TestOverseerEngine(unittest.TestCase):
    def test_engine_tick_produces_verdict(self):
        from skeleton.overseer import OverseerEngine
        engine = OverseerEngine()
        verdict = engine.engine_tick()
        self.assertIn(verdict.state, ("thriving", "stable", "strained", "critical"))

    def test_bind_loader_applies_budget(self):
        from skeleton.overseer import OverseerEngine
        from skeleton.support import LoadingQueue
        engine = OverseerEngine()
        loader = LoadingQueue(max_resident=99)
        engine.bind_loader(loader)
        engine.engine_tick()
        budget_cap = engine.governor.base_budget.scaled(engine.governor._active_throttle).max_resident_planes
        self.assertEqual(loader.max_resident, budget_cap)

    def test_device_surface_reports_profile(self):
        from skeleton.overseer import OverseerEngine
        engine = OverseerEngine()
        device = engine.device()
        self.assertIn("profile", device)
        self.assertIn("hardware", device)
        self.assertIn("budget", device)
        self.assertIn("device_class", device["profile"])

    def test_equilibrium_surface(self):
        from skeleton.overseer import OverseerEngine
        engine = OverseerEngine()
        engine.engine_tick()
        eq = engine.equilibrium()
        self.assertIn("pressure", eq)
        self.assertIn("throttle", eq)


class TestEngineGenesisWiring(unittest.TestCase):
    def test_engine_handle_wired(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        self.assertIn("engine", g.handles)

    def test_engine_bound_to_consumers(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        engine = g.get("engine")
        consumers = engine.governor.enforcer.consumers()
        self.assertIn("loading_queue", consumers)
        self.assertIn("priority_queue", consumers)
        self.assertIn("backlog_miner", consumers)

    def test_engine_tick_ran_at_boot(self):
        from skeleton.genesis import Genesis
        g = Genesis(seed=42).boot()
        engine = g.get("engine")
        self.assertGreaterEqual(engine.governor._stats["ticks"], 1)
        device = engine.device()
        self.assertIn(device["profile"]["device_class"],
                      ("embedded", "mobile", "laptop", "workstation", "server"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
