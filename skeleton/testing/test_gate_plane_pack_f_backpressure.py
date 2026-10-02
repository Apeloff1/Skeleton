"""Pack F — backpressure adapter: Pack H contract, AdaptiveGate fallback, stage."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import pytest

from skeleton.gate_plane.backpressure import (
    Action,
    AdaptiveGateSource,
    BackpressureGate,
    BackpressureStage,
    CompositeSource,
    FallbackChain,
    PackAPoolSource,
    PackHSource,
    PressureState,
    PressureUnavailable,
    PressureView,
    SchemaMismatch,
    StaticSource,
    backpressure_stage_factory,
    coerce_view,
    default_backpressure_gate,
    default_pressure_source,
    derive_state,
    register_adaptive_gate,
    register_pressure_provider,
    reset_registry_for_tests,
    retry_after_header,
)
from skeleton.gate_plane.backpressure.snapshot import iso_now, parse_iso
from skeleton.gate_plane.pipeline import (
    Deadline,
    DeadlineStage,
    Pipeline,
    PipelineRequest,
    PipelineResponse,
    PipelineRouter,
    RetryBudget,
    RetrySpec,
    RetryStage,
    default_s2s_routes,
)
from skeleton.gate_plane.s2s.clock import ManualClock
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.buffer_pool import BufferPool
from skeleton.kernel.coalesce import Coalescer

GET = PipelineRequest("GET", "/api/v1/things", tenant_id="t-1", priority=1)
CONTROL = PipelineRequest("GET", "/api/v1/control", priority=0)


def snap(clock, **kw):
    base = {
        "schema_version": 1,
        "load": 0.1,
        "queue_depth": 1,
        "max_queue_depth": 100,
        "tenant_queue_depth": None,
        "retry_after_s": 0.0,
        "state": "open",
        "observed_at": iso_now(clock.now()),
    }
    base.update(kw)
    return base


def ok(_r, _c):
    return PipelineResponse(200)


# --------------------------------------------------------------------------- snapshot
class TestSnapshot:
    @pytest.mark.parametrize(
        "load,qd,mq,ra,state",
        [
            (0.0, 0, 10, 0.0, PressureState.OPEN),
            (0.69, 0, 10, 0.0, PressureState.OPEN),
            (0.7, 0, 10, 0.0, PressureState.THROTTLE),
            (0.1, 0, 10, 0.5, PressureState.THROTTLE),
            (0.94, 0, 10, 0.0, PressureState.THROTTLE),
            (0.95, 0, 10, 0.0, PressureState.SHED),
            (0.1, 10, 10, 0.0, PressureState.SHED),
            (0.1, 5, 0, 0.0, PressureState.OPEN),
        ],
    )
    def test_derive_state_thresholds(self, load, qd, mq, ra, state):
        assert derive_state(load, qd, mq, ra) is state

    def test_tenant_full_sheds(self):
        assert derive_state(0.1, 0, 10, 0.0, 5, 5) is PressureState.SHED

    def test_retry_after_header(self):
        assert retry_after_header(0.0) == "1"
        assert retry_after_header(1.01) == "2"
        assert retry_after_header(3.0) == "3"
        assert retry_after_header(-5) == "1"

    def test_coerce_mapping(self):
        c = ManualClock()
        v = coerce_view(snap(c, retry_after_s=1.239, load=1.7), source="x")
        assert v.retry_after_s == 1.24
        assert v.load == 1.0
        assert v.source == "x"
        assert v.as_dict()["state"] == "open"

    @pytest.mark.parametrize("version", [0, 2, "1", True, None])
    def test_schema_mismatch_refused(self, version):
        c = ManualClock()
        with pytest.raises(SchemaMismatch):
            coerce_view(snap(c, schema_version=version), source="x")

    @pytest.mark.parametrize(
        "patch",
        [
            {"state": "melting"},
            {"load": "lots"},
            {"load": float("nan")},
            {"retry_after_s": float("inf")},
            {"queue_depth": -1},
            {"tenant_queue_depth": -2},
        ],
    )
    def test_malformed_refused(self, patch):
        c = ManualClock()
        with pytest.raises(PressureUnavailable):
            coerce_view(snap(c, **patch), source="x")

    def test_missing_field_refused(self):
        c = ManualClock()
        raw = snap(c)
        del raw["max_queue_depth"]
        with pytest.raises(PressureUnavailable):
            coerce_view(raw, source="x")
        with pytest.raises(PressureUnavailable):
            coerce_view(None, source="x")

    def test_coerce_dataclass_with_datetime_and_enum(self):
        class St(str, Enum):
            SHED = "shed"

        @dataclass(frozen=True)
        class Snap:
            load: float
            queue_depth: int
            max_queue_depth: int
            tenant_queue_depth: Optional[int]
            retry_after_s: float
            state: St
            observed_at: datetime
            schema_version: int = 1

        s = Snap(0.97, 5, 10, 2, 2.5, St.SHED, datetime(2026, 1, 1, tzinfo=timezone.utc))
        v = coerce_view(s, source="pack_h")
        assert v.state is PressureState.SHED
        assert v.tenant_queue_depth == 2
        assert parse_iso(v.observed_at) == datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()

    def test_coerce_object_with_as_dict_only(self):
        c = ManualClock()

        class Obj:
            def as_dict(self):
                return snap(c, state="throttle", retry_after_s=0.2)

        assert coerce_view(Obj(), source="x").state is PressureState.THROTTLE

    def test_effective_state_takes_stricter(self):
        c = ManualClock()
        v = coerce_view(snap(c, state="open", load=0.99), source="x")
        assert v.effective_state is PressureState.SHED
        v = coerce_view(snap(c, state="shed", load=0.0), source="x")
        assert v.effective_state is PressureState.SHED

    def test_age_and_parse_iso(self):
        c = ManualClock()
        v = coerce_view(snap(c), source="x")
        c.advance(3)
        assert v.age_s(c.now()) == pytest.approx(3.0)
        bad = coerce_view(snap(c, observed_at="yesterday"), source="x")
        assert bad.age_s(c.now()) == float("inf")
        assert parse_iso("2026-01-01T00:00:00Z") == parse_iso("2026-01-01T00:00:00+00:00")
        assert parse_iso("2026-01-01T00:00:00") == parse_iso("2026-01-01T00:00:00+00:00")


# --------------------------------------------------------------------------- Pack H
class TestPackHSource:
    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        reset_registry_for_tests()
        yield
        reset_registry_for_tests()

    def test_reads_injected_fn_with_tenant(self):
        c = ManualClock()
        seen = []

        def fn(tenant_id=None):
            seen.append(tenant_id)
            return snap(c, tenant_queue_depth=3)

        src = PackHSource(fn)
        v = src.read("t-9")
        assert seen == ["t-9"]
        assert v.source == "pack_h" and v.tenant_queue_depth == 3
        assert src.available
        assert src.status()["injected"]

    def test_unregistered_is_unavailable(self):
        src = PackHSource()
        assert not src.available
        with pytest.raises(PressureUnavailable):
            src.read()
        assert "no Pack H" in src.status()["last_error"]

    def test_late_registration_picked_up(self):
        c = ManualClock()
        src = PackHSource()
        with pytest.raises(PressureUnavailable):
            src.read()
        register_pressure_provider(lambda tenant_id=None: snap(c))
        assert src.read().source == "pack_h"
        register_pressure_provider(None)
        with pytest.raises(PressureUnavailable):
            src.read()

    def test_register_validation(self):
        with pytest.raises(TypeError):
            register_pressure_provider(3)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            register_adaptive_gate(object())

    def test_custom_resolver(self):
        c = ManualClock()
        src = PackHSource(resolver=lambda: (lambda tenant_id=None: snap(c)))
        assert src.read().source == "pack_h"

    def test_snapshot_raising_is_unavailable(self):
        def boom(tenant_id=None):
            raise RuntimeError("db down")

        src = PackHSource(boom)
        with pytest.raises(PressureUnavailable):
            src.read()
        assert "RuntimeError" in src.status()["last_error"]

    def test_schema_v2_refused(self):
        c = ManualClock()
        src = PackHSource(lambda tenant_id=None: snap(c, schema_version=2))
        with pytest.raises(SchemaMismatch):
            src.read()

    def test_gate_plane_never_imports_skeleton_api(self):
        import ast
        import pathlib

        import skeleton.gate_plane.backpressure as pkg

        for path in pathlib.Path(pkg.__file__).parent.glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("skeleton.api"), path
                elif isinstance(node, ast.Import):
                    assert not any(a.name.startswith("skeleton.api") for a in node.names), path
                elif isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "import_module":
                    raise AssertionError(f"dynamic import in {path}")


# --------------------------------------------------------------------------- AdaptiveGate
class TestAdaptiveGateSource:
    def test_full_bucket_open(self):
        c = ManualClock()
        v = AdaptiveGateSource(AdaptiveGate(10, 5), clock=c).read()
        assert v.state is PressureState.OPEN
        assert v.load == 0.0 and v.queue_depth == 0 and v.max_queue_depth == 10
        assert v.source == "adaptive_gate"

    def test_drained_bucket_sheds_with_refill_hint(self):
        g = AdaptiveGate(4, 2)
        for _ in range(4):
            g.admit(1)
        v = AdaptiveGateSource(g, clock=ManualClock()).read()
        assert v.state is PressureState.SHED
        assert v.queue_full
        assert v.retry_after_s == 0.5

    def test_partial_drain_throttles(self):
        g = AdaptiveGate(10, 0)
        for _ in range(8):
            g.admit(1)
        v = AdaptiveGateSource(g, clock=ManualClock()).read()
        assert v.load == pytest.approx(0.8)
        assert v.state is PressureState.THROTTLE

    def test_zero_capacity_and_zero_refill(self):
        v = AdaptiveGateSource(AdaptiveGate(0, 0), clock=ManualClock()).read()
        assert v.state is PressureState.SHED
        assert v.retry_after_s == 30.0

    def test_registered_gate_used_when_not_injected(self):
        reset_registry_for_tests()
        try:
            with pytest.raises(PressureUnavailable):
                AdaptiveGateSource(clock=ManualClock()).read()
            register_adaptive_gate(AdaptiveGate(3, 1))
            v = AdaptiveGateSource(clock=ManualClock()).read()
            assert v.max_queue_depth == 3
        finally:
            reset_registry_for_tests()

    def test_broken_gate_unavailable(self):
        class Broken:
            def stats(self):
                raise RuntimeError("x")

        with pytest.raises(PressureUnavailable):
            AdaptiveGateSource(Broken()).read()


# --------------------------------------------------------------------------- Pack A pool
class TestPackAPoolSource:
    def test_requires_something(self):
        with pytest.raises(ValueError):
            PackAPoolSource()
        with pytest.raises(ValueError):
            PackAPoolSource(pool=BufferPool(), max_leases=0)

    def test_leases_drive_load(self):
        pool = BufferPool()
        leases = [pool.lease(10) for _ in range(9)]
        v = PackAPoolSource(pool=pool, max_leases=10, clock=ManualClock()).read()
        assert v.load == pytest.approx(0.9)
        assert v.state is PressureState.THROTTLE
        assert v.retry_after_s > 0
        for lease in leases:
            lease.release() if hasattr(lease, "release") else None

    def test_coalescer_in_flight(self):
        co = Coalescer()
        started = threading.Event()
        release = threading.Event()

        def slow():
            started.set()
            release.wait(2)
            return 1

        t = threading.Thread(target=lambda: co.get("k", slow))
        t.start()
        started.wait(2)
        v = PackAPoolSource(coalescer=co, max_in_flight=1, clock=ManualClock()).read()
        release.set()
        t.join()
        assert v.state is PressureState.SHED
        assert v.queue_depth == 1
        v2 = PackAPoolSource(coalescer=co, max_in_flight=1, clock=ManualClock()).read()
        assert v2.state is PressureState.OPEN


# --------------------------------------------------------------------------- composite / chain
class TestCombinators:
    def test_composite_worst_of(self):
        c = ManualClock()
        a = StaticSource(snap(c, load=0.2), name="a")
        b = StaticSource(snap(c, load=0.8, state="throttle"), name="b")
        d = StaticSource(PressureUnavailable("down"), name="d")
        v = CompositeSource([a, b, d]).read()
        assert v.source == "b"

    def test_composite_all_down(self):
        with pytest.raises(PressureUnavailable):
            CompositeSource([StaticSource(PressureUnavailable("x"))]).read()
        with pytest.raises(ValueError):
            CompositeSource([])

    def test_chain_falls_back_on_unavailable(self):
        c = ManualClock()
        chain = FallbackChain(
            [StaticSource(PressureUnavailable("no"), name="h"), StaticSource(snap(c), name="g")], clock=c
        )
        assert chain.read().source == "g"
        assert chain.stats() == {"served": {"g": 1}, "skipped": {"h": 1}}

    def test_chain_skips_stale(self):
        c = ManualClock()
        old = snap(c)
        c.advance(60)
        chain = FallbackChain(
            [StaticSource(old, name="h"), StaticSource(lambda t: snap(c), name="g")], clock=c, max_age_s=5
        )
        assert chain.read().source == "g"

    def test_chain_survives_buggy_source(self):
        c = ManualClock()

        def bug(_t):
            raise KeyError("oops")

        chain = FallbackChain([StaticSource(bug, name="h"), StaticSource(snap(c), name="g")], clock=c)
        assert chain.read().source == "g"

    def test_chain_all_fail(self):
        with pytest.raises(PressureUnavailable):
            FallbackChain([StaticSource(PressureUnavailable("x"))]).read()
        with pytest.raises(ValueError):
            FallbackChain([])

    def test_default_source_falls_back_to_adaptive_gate(self):
        reset_registry_for_tests()
        v = default_pressure_source(clock=ManualClock(), gate=AdaptiveGate(5, 5)).read()
        assert v.source == "adaptive_gate"

    def test_default_source_prefers_registered_pack_h(self):
        c = ManualClock()
        reset_registry_for_tests()
        try:
            register_pressure_provider(lambda tenant_id=None: snap(c))
            v = default_pressure_source(clock=c, gate=AdaptiveGate(5, 5)).read()
            assert v.source == "pack_h"
        finally:
            reset_registry_for_tests()


# --------------------------------------------------------------------------- gate
class TestBackpressureGate:
    def gate(self, c, **kw):
        return BackpressureGate(StaticSource(lambda t: snap(c, **kw)))

    def test_open_admits(self):
        c = ManualClock()
        d = self.gate(c).decide(GET)
        assert d.action is Action.ADMIT and d.reason == "open" and d.admitted

    def test_throttle_short_delay(self):
        c = ManualClock()
        d = self.gate(c, state="throttle", load=0.8, retry_after_s=0.1).decide(GET)
        assert d.action is Action.DELAY and d.delay_s == 0.1

    def test_throttle_no_wait(self):
        c = ManualClock()
        d = self.gate(c, state="throttle", load=0.8).decide(GET)
        assert d.action is Action.ADMIT and d.reason == "throttle_no_wait"

    def test_throttle_long_wait_sheds_429(self):
        c = ManualClock()
        d = self.gate(c, state="throttle", load=0.8, retry_after_s=2.3).decide(GET)
        assert d.action is Action.SHED and d.status == 429
        assert d.headers() == [("retry-after", "3")]
        assert d.response().status == 429
        assert d.body()["error"] == "throttled"

    def test_throttle_delay_beyond_deadline_sheds(self):
        c = ManualClock()
        d = self.gate(c, state="throttle", load=0.8, retry_after_s=0.2).decide(GET, budget_s=0.1)
        assert d.action is Action.SHED

    def test_shed_load_429_queue_full_503(self):
        c = ManualClock()
        d = self.gate(c, state="shed", load=0.97, retry_after_s=0.3).decide(GET)
        assert d.status == 429 and d.reason == "load_shed"
        assert d.retry_after_s == 1.0
        d = self.gate(c, state="shed", queue_depth=100, retry_after_s=4.2).decide(GET)
        assert d.status == 503 and d.reason == "queue_full"
        assert d.headers() == [("retry-after", "5")]
        assert d.body()["error"] == "overloaded"

    def test_control_priority_exempt(self):
        c = ManualClock()
        d = self.gate(c, state="shed", load=0.99).decide(CONTROL)
        assert d.action is Action.ADMIT and d.reason == "shed_control_exempt"
        g = BackpressureGate(StaticSource(lambda t: snap(c, state="shed", load=0.99)), exempt_priority=None)
        assert g.decide(CONTROL).action is Action.SHED

    def test_reported_open_but_numbers_say_shed(self):
        c = ManualClock()
        d = self.gate(c, state="open", load=0.99).decide(GET)
        assert d.action is Action.SHED

    def test_no_signal_default_admits(self):
        g = BackpressureGate(StaticSource(PressureUnavailable("x")))
        d = g.decide(GET)
        assert d.action is Action.ADMIT and d.reason == "no_signal"

    def test_no_signal_fail_closed_option(self):
        g = BackpressureGate(StaticSource(PressureUnavailable("x")), on_no_signal="shed")
        d = g.decide(GET)
        assert d.action is Action.SHED and d.status == 503

    def test_validation(self):
        with pytest.raises(ValueError):
            BackpressureGate(StaticSource(None), max_throttle_wait_s=-1)
        with pytest.raises(ValueError):
            BackpressureGate(StaticSource(None), on_no_signal="maybe")

    def test_listeners_and_stats(self):
        c = ManualClock()
        g = self.gate(c)
        seen = []
        g.add_listener(lambda req, d: seen.append(d.reason))
        g.add_listener(lambda req, d: 1 / 0)
        g.decide(GET)
        g.decide(GET)
        assert seen == ["open", "open"]
        assert g.stats() == {"admit:open": 2}

    def test_tenant_passed_through(self):
        c = ManualClock()
        seen = []
        g = BackpressureGate(StaticSource(lambda t: seen.append(t) or snap(c)))
        g.decide(GET)
        assert seen == ["t-1"]

    def test_as_dict(self):
        c = ManualClock()
        d = self.gate(c, state="shed", load=0.99).decide(GET).as_dict()
        assert d["action"] == "shed" and d["state"] == "shed" and d["source"] == "static"

    def test_default_gate(self):
        g = default_backpressure_gate(clock=ManualClock(), gate=AdaptiveGate(5, 5))
        assert g.decide(GET).admitted


# --------------------------------------------------------------------------- stage
class TestBackpressureStage:
    def test_shed_short_circuits_and_spends_no_retry_budget(self):
        c = ManualClock()
        budget = RetryBudget(clock=c)
        g = BackpressureGate(StaticSource(lambda t: snap(c, state="shed", load=0.99)))
        p = Pipeline([BackpressureStage(g), RetryStage(RetrySpec(), budget=budget)], clock=c)
        calls = []
        ctx = p.new_context()
        r = p.run(GET, lambda req, cx: calls.append(1) or PipelineResponse(200), ctx=ctx)
        assert r.status == 429 and r.header("retry-after") == "1"
        assert calls == []
        assert budget.stats()["deposits"] == 0
        assert "backpressure_shed" in ctx.event_names()
        assert ctx.attrs["backpressure"]["action"] == "shed"

    def test_delay_sleeps_virtual_time(self):
        c = ManualClock()
        g = BackpressureGate(StaticSource(lambda t: snap(c, state="throttle", load=0.8, retry_after_s=0.2)))
        p = Pipeline([BackpressureStage(g)], clock=c)
        assert p.run(GET, ok).status == 200
        assert c.sleeps == [0.2]

    def test_delay_respects_deadline(self):
        c = ManualClock()
        g = BackpressureGate(StaticSource(lambda t: snap(c, state="throttle", load=0.8, retry_after_s=0.2)))
        p = Pipeline([BackpressureStage(g), DeadlineStage(10)], clock=c)
        ctx = p.new_context(Deadline.after(0.1, c))
        assert p.run(GET, ok, ctx=ctx).status == 429
        assert c.sleeps == []

    def test_router_factory(self):
        c = ManualClock()
        g = BackpressureGate(StaticSource(lambda t: snap(c)))
        router = PipelineRouter(default_s2s_routes(), clock=c, stage_factories={"backpressure": backpressure_stage_factory(g)})
        resp, ctx = router.call(GET, ok)
        assert resp.status == 200
        assert router.pipeline_for(router.table.routes()[0]).describe()[0]["kind"] == "backpressure"

    def test_view_dataclass_is_frozen(self):
        c = ManualClock()
        v = coerce_view(snap(c), source="x")
        assert isinstance(v, PressureView)
        with pytest.raises(Exception):
            v.load = 0.5  # type: ignore[misc]
