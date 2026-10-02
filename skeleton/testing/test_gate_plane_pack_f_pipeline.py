"""Pack F — composable request pipeline: deadlines, retry budgets, breaker, routing."""

from __future__ import annotations

import concurrent.futures
import random
import threading
import time

import pytest

from skeleton.gate_plane.pipeline import (
    AttemptTimeout,
    AttemptTimeoutStage,
    BreakerConfig,
    BreakerOpenError,
    BreakerRegistry,
    BreakerStage,
    BreakerState,
    CANONICAL_ORDER,
    CircuitBreaker,
    Deadline,
    DeadlineExceeded,
    DeadlineStage,
    FunctionStage,
    Pipeline,
    PipelineConfigError,
    PipelineRequest,
    PipelineResponse,
    PipelineRouter,
    RetryBudget,
    RetryBudgetRegistry,
    RetrySpec,
    RetryStage,
    RouteConfig,
    RouteTable,
    Verdict,
    default_s2s_routes,
)
from skeleton.gate_plane.pipeline.errors import PipelineError
from skeleton.gate_plane.s2s.clock import ManualClock


GET = PipelineRequest("GET", "/api/v1/things")
POST = PipelineRequest("POST", "/api/v1/things")
POST_IDEM = PipelineRequest("POST", "/api/v1/things", headers={"Idempotency-Key": "k-1"})


def ok(_req, _ctx):
    return PipelineResponse(200, {"ok": True})


class Scripted:
    """Handler returning/raising scripted outcomes; optional virtual latency."""

    def __init__(self, clock, outcomes, latency=0.0):
        self.clock = clock
        self.outcomes = list(outcomes)
        self.latency = latency
        self.calls = 0

    def __call__(self, req, ctx):
        self.calls += 1
        if self.latency:
            self.clock.advance(self.latency)
        item = self.outcomes.pop(0) if self.outcomes else 200
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, PipelineResponse):
            return item
        return PipelineResponse(int(item))


# --------------------------------------------------------------------------- errors
class TestErrors:
    def test_retry_after_rounding_and_header(self):
        e = DeadlineExceeded("x", retry_after_s=1.234)
        assert e.retry_after_s == 1.23
        assert e.retry_after_header() == "2"
        assert e.status == 504
        assert e.as_dict()["retry_after_s"] == 1.23

    def test_retry_after_header_minimum_one(self):
        assert BreakerOpenError("b", retry_after_s=0.01).retry_after_header() == "1"
        assert BreakerOpenError("b").retry_after_header() is None

    def test_negative_retry_after_clamped(self):
        assert PipelineError("x", retry_after_s=-3).retry_after_s == 0.0

    def test_attempt_timeout_is_deadline_subclass(self):
        assert issubclass(AttemptTimeout, DeadlineExceeded)


# --------------------------------------------------------------------------- deadline
class TestDeadline:
    def test_after_and_remaining(self):
        c = ManualClock()
        d = Deadline.after(2.0, c)
        assert d.remaining() == pytest.approx(2.0)
        c.advance(1.5)
        assert d.remaining() == pytest.approx(0.5)
        assert not d.expired()
        c.advance(0.5)
        assert d.expired()
        assert d.remaining() == 0.0

    def test_invalid_timeout(self):
        with pytest.raises(ValueError):
            Deadline.after(0, ManualClock())

    def test_child_only_shrinks(self):
        c = ManualClock()
        d = Deadline.after(2.0, c)
        assert d.child(5.0) is d
        assert d.child(1.0).remaining() == pytest.approx(1.0)
        assert d.child(None) is d
        assert d.child(0) is d

    def test_unbounded(self):
        c = ManualClock()
        d = Deadline.unbounded(c)
        assert not d.bounded
        c.advance(1e6)
        assert not d.expired()
        assert d.child(3).bounded

    def test_wall_skew_does_not_affect_deadline(self):
        c = ManualClock()
        d = Deadline.after(1.0, c)
        c.set_wall(0.0)
        assert d.remaining() == pytest.approx(1.0)


# --------------------------------------------------------------------------- budget
class TestRetryBudget:
    def test_floor_allows_minimum_retries(self):
        c = ManualClock()
        b = RetryBudget(retry_ratio=0.0, min_retries_per_s=0.5, window_s=10, clock=c)
        grants = sum(b.try_withdraw() for _ in range(20))
        assert grants == 5

    def test_ratio_scales_with_traffic(self):
        c = ManualClock()
        b = RetryBudget(retry_ratio=0.1, min_retries_per_s=0.0, window_s=10, clock=c)
        for _ in range(100):
            b.deposit()
        grants = sum(b.try_withdraw() for _ in range(50))
        assert grants == 10
        assert b.stats()["denied"] == 40

    def test_window_expiry_restores_budget(self):
        c = ManualClock()
        b = RetryBudget(retry_ratio=0.0, min_retries_per_s=0.1, window_s=10, clock=c)
        assert b.try_withdraw()
        assert not b.try_withdraw()
        c.advance(10.01)
        assert b.try_withdraw()

    def test_deposits_expire(self):
        c = ManualClock()
        b = RetryBudget(retry_ratio=1.0, min_retries_per_s=0.0, window_s=5, clock=c)
        for _ in range(3):
            b.deposit()
        assert b.balance() == pytest.approx(3.0)
        c.advance(6)
        assert b.balance() == pytest.approx(0.0)

    @pytest.mark.parametrize("kw", [{"retry_ratio": -1}, {"min_retries_per_s": -1}, {"window_s": 0}])
    def test_validation(self, kw):
        with pytest.raises(ValueError):
            RetryBudget(**kw)

    def test_registry_shares_by_name(self):
        reg = RetryBudgetRegistry(clock=ManualClock(), retry_ratio=0.5)
        a = reg.get("up")
        assert reg.get("up") is a
        assert reg.get("other", retry_ratio=0.1).retry_ratio == 0.1
        assert a.retry_ratio == 0.5
        assert reg.names() == ["other", "up"]
        assert set(reg.stats()) == {"other", "up"}

    def test_thread_safety_never_overspends(self):
        c = ManualClock()
        b = RetryBudget(retry_ratio=0.0, min_retries_per_s=10, window_s=10, clock=c)
        granted = []
        lock = threading.Lock()

        def worker():
            for _ in range(100):
                if b.try_withdraw():
                    with lock:
                        granted.append(1)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(granted) == 100


# --------------------------------------------------------------------------- retry spec
class TestRetrySpec:
    def test_backoff_exponential_capped_no_jitter(self):
        s = RetrySpec(max_attempts=6, base_backoff_s=0.1, max_backoff_s=0.5, multiplier=2.0, jitter=0.0)
        assert s.schedule() == (0.1, 0.2, 0.4, 0.5, 0.5)
        assert s.backoff(0) == 0.0

    def test_jitter_bounded_and_deterministic(self):
        s = RetrySpec(max_attempts=4, base_backoff_s=0.1, max_backoff_s=10, jitter=0.5)
        a = s.schedule(random.Random(7))
        b = s.schedule(random.Random(7))
        assert a == b
        for i, d in enumerate(a, start=1):
            raw = 0.1 * 2 ** (i - 1)
            assert raw * 0.5 <= d <= raw * 1.5

    @pytest.mark.parametrize(
        "kw",
        [
            {"max_attempts": 0},
            {"base_backoff_s": -1},
            {"base_backoff_s": 2, "max_backoff_s": 1},
            {"multiplier": 0.5},
            {"jitter": 1.5},
        ],
    )
    def test_validation(self, kw):
        with pytest.raises(ValueError):
            RetrySpec(**kw)

    def test_method_rules(self):
        s = RetrySpec()
        assert s.method_allows_retry(GET)
        assert s.method_allows_retry(PipelineRequest("PUT", "/x"))
        assert s.method_allows_retry(PipelineRequest("DELETE", "/x"))
        assert not s.method_allows_retry(POST)
        assert s.method_allows_retry(POST_IDEM)
        assert not RetrySpec(retry_unsafe_with_idempotency_key=False).method_allows_retry(POST_IDEM)

    def test_blank_idempotency_key_ignored(self):
        req = PipelineRequest("POST", "/x", headers={"idempotency-key": "  "})
        assert req.idempotency_key is None
        assert not RetrySpec().method_allows_retry(req)

    @pytest.mark.parametrize(
        "status,verdict",
        [
            (200, Verdict.SUCCESS),
            (304, Verdict.SUCCESS),
            (404, Verdict.CLIENT_ERROR),
            (429, Verdict.CLIENT_ERROR),
            (500, Verdict.FATAL),
            (502, Verdict.RETRYABLE),
            (503, Verdict.RETRYABLE),
            (504, Verdict.RETRYABLE),
        ],
    )
    def test_classify_response(self, status, verdict):
        assert RetrySpec().classify_response(PipelineResponse(status)) is verdict

    def test_retry_on_429_opt_in(self):
        assert RetrySpec(retry_on_429=True).classify_response(PipelineResponse(429)) is Verdict.RETRYABLE

    @pytest.mark.parametrize(
        "exc,verdict",
        [
            (ConnectionError(), Verdict.RETRYABLE),
            (TimeoutError(), Verdict.RETRYABLE),
            (AttemptTimeout(), Verdict.RETRYABLE),
            (DeadlineExceeded(), Verdict.FATAL),
            (BreakerOpenError("b"), Verdict.FATAL),
            (ValueError(), Verdict.FATAL),
        ],
    )
    def test_classify_error(self, exc, verdict):
        assert RetrySpec.classify_error(exc) is verdict

    def test_retry_after_hint(self):
        s = RetrySpec(max_retry_after_s=2.0)
        assert s.retry_after_hint(PipelineResponse(503, headers=(("Retry-After", "1.5"),))) == 1.5
        assert s.retry_after_hint(PipelineResponse(503, headers=(("retry-after", "30"),))) == 2.0
        assert s.retry_after_hint(PipelineResponse(503, headers=(("retry-after", "soon"),))) is None
        assert s.retry_after_hint(PipelineResponse(503, headers=(("retry-after", "-1"),))) is None
        assert RetrySpec(honor_retry_after=False).retry_after_hint(
            PipelineResponse(503, headers=(("retry-after", "1"),))
        ) is None

    def test_as_dict_roundtrips_fields(self):
        d = RetrySpec().as_dict()
        assert d["retryable_status"] == [502, 503, 504]
        assert d["max_attempts"] == 3


# --------------------------------------------------------------------------- breaker
class TestCircuitBreaker:
    def cfg(self, **kw):
        base = dict(consecutive_failures=3, failure_rate=0.5, window_size=10, min_calls=4, cooldown_s=10.0)
        base.update(kw)
        return BreakerConfig(**base)

    def test_trips_on_consecutive_failures(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(), clock=c)
        for _ in range(2):
            assert b.try_acquire()
            b.record_failure()
        assert b.state is BreakerState.CLOSED
        assert b.try_acquire()
        b.record_failure()
        assert b.state is BreakerState.OPEN
        assert not b.try_acquire()

    def test_trips_on_failure_rate(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=100), clock=c)
        for ok_ in (True, False, True, False):
            assert b.try_acquire()
            b.record_success() if ok_ else b.record_failure()
        assert b.state is BreakerState.OPEN

    def test_rate_needs_min_calls(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=100, min_calls=6, window_size=10), clock=c)
        for ok_ in (False, True, False, True, False):
            b.try_acquire()
            b.record_success() if ok_ else b.record_failure()
        assert b.state is BreakerState.CLOSED

    def test_success_resets_consecutive(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(failure_rate=1.0, min_calls=10), clock=c)
        for _ in range(5):
            b.try_acquire()
            b.record_failure()
            b.try_acquire()
            b.record_failure()
            b.try_acquire()
            b.record_success()
        assert b.state is BreakerState.CLOSED

    def test_half_open_after_cooldown_and_close(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.try_acquire()
        b.record_failure()
        assert b.retry_after_s() == pytest.approx(10.0)
        c.advance(4)
        assert b.retry_after_s() == pytest.approx(6.0)
        c.advance(6)
        assert b.state is BreakerState.HALF_OPEN
        assert b.try_acquire()
        assert not b.try_acquire()  # one probe only
        b.record_success()
        assert b.state is BreakerState.CLOSED
        assert b.retry_after_s() == 0.0

    def test_probe_failure_reopens_with_growth(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1, cooldown_multiplier=2.0, max_cooldown_s=25), clock=c)
        b.try_acquire()
        b.record_failure()
        c.advance(10)
        assert b.try_acquire()
        b.record_failure()
        assert b.state is BreakerState.OPEN
        assert b.retry_after_s() == pytest.approx(20.0)
        c.advance(20)
        assert b.try_acquire()
        b.record_failure()
        assert b.retry_after_s() == pytest.approx(25.0)  # capped
        c.advance(25)
        assert b.try_acquire()
        b.record_success()
        assert b.state is BreakerState.CLOSED
        assert b.stats()["cooldown_s"] == 10.0  # reset after close

    def test_success_threshold_multiple_probes(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1, half_open_max_calls=3, success_threshold=2), clock=c)
        b.try_acquire()
        b.record_failure()
        c.advance(10)
        assert b.try_acquire() and b.try_acquire() and b.try_acquire()
        assert not b.try_acquire()
        b.record_success()
        assert b.state is BreakerState.HALF_OPEN
        b.record_success()
        assert b.state is BreakerState.CLOSED

    def test_ignored_releases_probe(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.try_acquire()
        b.record_failure()
        c.advance(10)
        assert b.try_acquire()
        b.record_ignored()
        assert b.try_acquire()

    def test_late_success_while_open_ignored(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.try_acquire()
        b.try_acquire()
        b.record_failure()
        b.record_success()
        assert b.state is BreakerState.OPEN

    def test_acquire_raises_with_retry_after(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.force_open()
        with pytest.raises(BreakerOpenError) as ei:
            b.acquire()
        assert ei.value.retry_after_s == pytest.approx(10.0)
        assert ei.value.breaker == "up"

    def test_listeners_and_isolation(self):
        c = ManualClock()
        seen = []
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.add_listener(lambda n, o, nw: seen.append((n, o.value, nw.value)))
        b.add_listener(lambda *a: 1 / 0)
        b.try_acquire()
        b.record_failure()
        c.advance(10)
        _ = b.state
        b.try_acquire()
        b.record_success()
        assert seen == [("up", "closed", "open"), ("up", "open", "half_open"), ("up", "half_open", "closed")]

    def test_reset_and_stats(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.try_acquire()
        b.record_failure()
        b.reset()
        assert b.state is BreakerState.CLOSED
        s = b.stats()
        assert s["opened"] == 1 and s["failure"] == 1
        assert [t["to"] for t in s["transitions"]] == ["open", "closed"]

    @pytest.mark.parametrize(
        "kw",
        [
            {"consecutive_failures": 0},
            {"failure_rate": 0},
            {"failure_rate": 1.5},
            {"min_calls": 30, "window_size": 20},
            {"cooldown_s": 0},
            {"cooldown_s": 10, "max_cooldown_s": 5},
            {"cooldown_multiplier": 0.5},
            {"half_open_max_calls": 0},
            {"success_threshold": 2, "half_open_max_calls": 1},
        ],
    )
    def test_config_validation(self, kw):
        with pytest.raises(ValueError):
            BreakerConfig(**kw)

    def test_registry(self):
        c = ManualClock()
        reg = BreakerRegistry(clock=c, default=self.cfg(consecutive_failures=1))
        seen = []
        reg.add_listener(lambda n, o, nw: seen.append(n))
        a = reg.get("a")
        assert reg.get("a") is a
        a.try_acquire()
        a.record_failure()
        b = reg.get("b")
        b.try_acquire()
        b.record_failure()
        assert reg.states() == {"a": "open", "b": "open"}
        assert seen == ["a", "b"]
        assert set(reg.stats()) == {"a", "b"}

    def test_concurrent_half_open_single_probe(self):
        c = ManualClock()
        b = CircuitBreaker("up", self.cfg(consecutive_failures=1), clock=c)
        b.try_acquire()
        b.record_failure()
        c.advance(10)
        results = []
        lock = threading.Lock()

        def w():
            r = b.try_acquire()
            with lock:
                results.append(r)

        ts = [threading.Thread(target=w) for _ in range(16)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert results.count(True) == 1


# --------------------------------------------------------------------------- ordering
class _K:
    def __init__(self, name, kind):
        self.name, self.kind = name, kind

    def invoke(self, req, ctx, nxt):
        ctx.event(f"enter:{self.name}")
        r = nxt(req, ctx)
        ctx.event(f"exit:{self.name}")
        return r


class TestOrdering:
    def test_canonical_order_constant(self):
        assert CANONICAL_ORDER[0] == "telemetry" and CANONICAL_ORDER[-1] == "custom"
        assert CANONICAL_ORDER.index("retry") < CANONICAL_ORDER.index("breaker")
        assert CANONICAL_ORDER.index("deadline") < CANONICAL_ORDER.index("retry")
        assert CANONICAL_ORDER.index("backpressure") < CANONICAL_ORDER.index("retry")

    def test_rejects_breaker_outside_retry(self):
        with pytest.raises(PipelineConfigError):
            Pipeline([_K("b", "breaker"), _K("r", "retry")])

    def test_rejects_duplicates_even_non_strict(self):
        with pytest.raises(PipelineConfigError):
            Pipeline([_K("x", "retry"), _K("x", "breaker")], strict=False)

    def test_rejects_unknown_kind_and_missing_name(self):
        with pytest.raises(PipelineConfigError):
            Pipeline([_K("x", "bogus")])
        with pytest.raises(PipelineConfigError):
            Pipeline([_K("", "retry")])

    def test_custom_must_be_innermost(self):
        with pytest.raises(PipelineConfigError):
            Pipeline([_K("c", "custom"), _K("r", "retry")])
        Pipeline([_K("r", "retry"), _K("c", "custom"), _K("d", "custom")])

    def test_non_strict_allows_reorder(self):
        p = Pipeline([_K("b", "breaker"), _K("r", "retry")], strict=False)
        assert [s["name"] for s in p.describe()] == ["b", "r"]

    def test_onion_execution_order(self):
        c = ManualClock()
        p = Pipeline([_K("t", "telemetry"), _K("r", "retry"), _K("c", "custom")], clock=c)
        ctx = p.new_context()
        p.run(GET, ok, ctx=ctx)
        assert ctx.event_names() == ["enter:t", "enter:r", "enter:c", "exit:c", "exit:r", "exit:t"]

    def test_with_stage_inserts_at_canonical_slot(self):
        p = Pipeline([_K("t", "telemetry"), _K("b", "breaker")])
        p2 = p.with_stage(_K("r", "retry"))
        assert [s["kind"] for s in p2.describe()] == ["telemetry", "retry", "breaker"]
        assert [s["kind"] for s in p.describe()] == ["telemetry", "breaker"]

    def test_function_stage(self):
        def fn(req, ctx, nxt):
            r = nxt(req, ctx)
            return PipelineResponse(r.status, {"wrapped": r.body})

        p = Pipeline([FunctionStage("wrap", fn)])
        assert p.run(GET, ok).body == {"wrapped": {"ok": True}}

    def test_empty_pipeline_calls_handler(self):
        assert Pipeline().run(GET, ok).status == 200


# --------------------------------------------------------------------------- stages
class TestDeadlineStage:
    def test_passes_fast_call(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(1.0)], clock=c)
        assert p.run(GET, Scripted(c, [200], latency=0.5)).status == 200

    def test_slow_idempotent_call_fails(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(1.0)], clock=c)
        with pytest.raises(DeadlineExceeded):
            p.run(GET, Scripted(c, [200], latency=2.0))

    def test_slow_write_keeps_response(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(1.0)], clock=c)
        ctx = p.new_context()
        r = p.run(POST, Scripted(c, [201], latency=2.0), ctx=ctx)
        assert r.status == 201
        assert "deadline_overrun" in ctx.event_names()

    def test_inherited_earlier_deadline_wins(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(10.0)], clock=c)
        ctx = p.new_context(Deadline.after(1.0, c))
        with pytest.raises(DeadlineExceeded):
            p.run(GET, Scripted(c, [200], latency=1.5), ctx=ctx)

    def test_expired_on_entry(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(10.0)], clock=c)
        ctx = p.new_context(Deadline.after(1.0, c))
        c.advance(2)
        h = Scripted(c, [200])
        with pytest.raises(DeadlineExceeded):
            p.run(GET, h, ctx=ctx)
        assert h.calls == 0

    def test_validation_and_stats(self):
        with pytest.raises(ValueError):
            DeadlineStage(0)
        st = DeadlineStage(1.0)
        assert st.stats()["timeout_s"] == 1.0


class TestAttemptTimeoutStage:
    def test_cooperative_timeout(self):
        c = ManualClock()
        p = Pipeline([AttemptTimeoutStage(0.5)], clock=c)
        with pytest.raises(AttemptTimeout):
            p.run(GET, Scripted(c, [200], latency=0.6))

    def test_sets_attempt_deadline_attr(self):
        c = ManualClock()
        p = Pipeline([AttemptTimeoutStage(0.5)], clock=c)
        seen = {}

        def h(req, ctx):
            seen["rem"] = ctx.attrs["attempt_deadline"].remaining()
            return PipelineResponse(200)

        p.run(GET, h)
        assert seen["rem"] == pytest.approx(0.5)

    def test_capped_by_total_deadline(self):
        c = ManualClock()
        p = Pipeline([DeadlineStage(0.2), AttemptTimeoutStage(5.0)], clock=c)
        with pytest.raises(DeadlineExceeded):
            p.run(GET, Scripted(c, [200], latency=0.3))

    def test_enforced_mode_real_executor(self):
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            p = Pipeline([AttemptTimeoutStage(0.05, executor=ex)])
            release = threading.Event()

            def slow(req, ctx):
                release.wait(2.0)
                return PipelineResponse(200)

            t0 = time.monotonic()
            with pytest.raises(AttemptTimeout):
                p.run(GET, slow)
            assert time.monotonic() - t0 < 1.0
            release.set()
            assert p.run(GET, ok).status == 200
        finally:
            ex.shutdown(wait=True)

    def test_validation(self):
        with pytest.raises(ValueError):
            AttemptTimeoutStage(0)


class TestBreakerStage:
    def test_accounting(self):
        c = ManualClock()
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=2, min_calls=10, window_size=10), clock=c)
        p = Pipeline([BreakerStage(b)], clock=c)
        assert p.run(GET, Scripted(c, [404])).status == 404
        assert p.run(GET, Scripted(c, [429])).status == 429
        assert b.stats()["success"] == 1 and b.stats()["ignored"] == 1
        p.run(GET, Scripted(c, [503]))
        with pytest.raises(ConnectionError):
            p.run(GET, Scripted(c, [ConnectionError()]))
        assert b.state is BreakerState.OPEN
        h = Scripted(c, [200])
        with pytest.raises(BreakerOpenError):
            p.run(GET, h)
        assert h.calls == 0

    def test_attempt_timeout_counts_as_failure(self):
        c = ManualClock()
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1), clock=c)
        p = Pipeline([BreakerStage(b), AttemptTimeoutStage(0.1)], clock=c)
        with pytest.raises(AttemptTimeout):
            p.run(GET, Scripted(c, [200], latency=0.2))
        assert b.state is BreakerState.OPEN

    def test_inner_pipeline_error_is_ignored(self):
        c = ManualClock()
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1), clock=c)
        p = Pipeline([BreakerStage(b)], clock=c)
        with pytest.raises(DeadlineExceeded):
            p.run(GET, Scripted(c, [DeadlineExceeded()]))
        assert b.state is BreakerState.CLOSED
        assert b.stats()["ignored"] == 1

    def test_base_exception_releases_permit(self):
        c = ManualClock()
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1), clock=c)
        b.force_open()
        c.advance(30)
        p = Pipeline([BreakerStage(b)], clock=c)
        with pytest.raises(KeyboardInterrupt):
            p.run(GET, Scripted(c, [KeyboardInterrupt()]))
        assert b.try_acquire()


class TestRetryStage:
    def test_retries_until_success(self):
        c = ManualClock()
        st = RetryStage(RetrySpec(max_attempts=3, jitter=0.0, base_backoff_s=0.1), rng=random.Random(1))
        p = Pipeline([st], clock=c)
        h = Scripted(c, [503, 502, 200])
        ctx = p.new_context()
        assert p.run(GET, h, ctx=ctx).status == 200
        assert h.calls == 3
        assert c.sleeps == [0.1, 0.2]
        assert ctx.attrs["attempts"] == 3
        assert ctx.event_names().count("retry") == 2

    def test_attempts_exhausted_returns_last(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=2, jitter=0.0))], clock=c)
        ctx = p.new_context()
        assert p.run(GET, Scripted(c, [503, 504]), ctx=ctx).status == 504
        assert ctx.events[-1]["reason"] == "attempts_exhausted"

    def test_exception_reraised_after_exhaustion(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=2, jitter=0.0))], clock=c)
        with pytest.raises(ConnectionError):
            p.run(GET, Scripted(c, [ConnectionError("a"), ConnectionError("b")]))

    def test_no_retry_on_fatal_or_client(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=5))], clock=c)
        h = Scripted(c, [500])
        assert p.run(GET, h).status == 500 and h.calls == 1
        h = Scripted(c, [400])
        assert p.run(GET, h).status == 400 and h.calls == 1
        h = Scripted(c, [ValueError("bug")])
        with pytest.raises(ValueError):
            p.run(GET, h)
        assert h.calls == 1

    def test_unsafe_post_not_retried(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=3))], clock=c)
        h = Scripted(c, [503, 200])
        ctx = p.new_context()
        assert p.run(POST, h, ctx=ctx).status == 503
        assert h.calls == 1
        assert ctx.events[-1]["reason"] == "unsafe_method"

    def test_post_with_idempotency_key_retried(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=3, jitter=0))], clock=c)
        h = Scripted(c, [503, 201])
        assert p.run(POST_IDEM, h).status == 201

    def test_honors_retry_after(self):
        c = ManualClock()
        p = Pipeline([RetryStage(RetrySpec(max_attempts=2, jitter=0))], clock=c)
        p.run(GET, Scripted(c, [PipelineResponse(503, headers=(("Retry-After", "1.5"),)), 200]))
        assert c.sleeps == [1.5]

    def test_deadline_stops_retry_before_sleep(self):
        c = ManualClock()
        p = Pipeline(
            [DeadlineStage(0.15), RetryStage(RetrySpec(max_attempts=5, base_backoff_s=0.1, jitter=0))], clock=c
        )
        ctx = p.new_context()
        r = p.run(GET, Scripted(c, [503, 503, 503, 503, 200]), ctx=ctx)
        assert r.status == 503
        assert c.sleeps == [0.1]
        assert ctx.events[-1]["reason"] == "deadline"

    def test_budget_exhaustion_stops_retry_without_spending(self):
        c = ManualClock()
        budget = RetryBudget(retry_ratio=0.0, min_retries_per_s=0.1, window_s=10, clock=c)
        p = Pipeline([RetryStage(RetrySpec(max_attempts=5, jitter=0), budget=budget)], clock=c)
        ctx = p.new_context()
        r = p.run(GET, Scripted(c, [503] * 5), ctx=ctx)
        assert r.status == 503
        assert ctx.events[-1]["reason"] == "budget_exhausted"
        assert budget.stats()["withdrawals"] == 1
        assert budget.stats()["deposits"] == 1

    def test_unsafe_method_does_not_spend_budget(self):
        c = ManualClock()
        budget = RetryBudget(retry_ratio=0.0, min_retries_per_s=1, window_s=10, clock=c)
        p = Pipeline([RetryStage(RetrySpec(max_attempts=5), budget=budget)], clock=c)
        p.run(POST, Scripted(c, [503]))
        assert budget.stats()["withdrawals"] == 0

    def test_breaker_open_not_retried(self):
        c = ManualClock()
        b = CircuitBreaker("up", BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1), clock=c)
        p = Pipeline([RetryStage(RetrySpec(max_attempts=5, jitter=0)), BreakerStage(b)], clock=c)
        h = Scripted(c, [503, 200])
        with pytest.raises(BreakerOpenError):
            p.run(GET, h)
        assert h.calls == 1  # retry hit the open breaker instead of the upstream

    def test_attempt_timeout_retried(self):
        c = ManualClock()
        p = Pipeline(
            [
                DeadlineStage(5.0),
                RetryStage(RetrySpec(max_attempts=3, jitter=0, base_backoff_s=0.01)),
                AttemptTimeoutStage(0.5),
            ],
            clock=c,
        )

        calls = {"n": 0}

        def h(req, ctx):
            calls["n"] += 1
            if calls["n"] == 1:
                c.advance(1.0)
            return PipelineResponse(200)

        assert p.run(GET, h).status == 200
        assert calls["n"] == 2

    def test_stats(self):
        c = ManualClock()
        st = RetryStage(RetrySpec(max_attempts=2, jitter=0), budget=RetryBudget(clock=c))
        Pipeline([st], clock=c).run(GET, Scripted(c, [503, 200]))
        s = st.stats()
        assert s["attempts"] == 2 and s["retries"] == 1
        assert "budget" in s


# --------------------------------------------------------------------------- routing
class TestRoutes:
    def test_route_config_validation(self):
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="", pattern="/x", upstream="u")
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="/x", upstream="")
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="nope", upstream="u")
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="/x", upstream="u", methods=frozenset({"BREW"}))
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="/x", upstream="u", timeout_s=0)
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="/x", upstream="u", timeout_s=1, attempt_timeout_s=2)
        with pytest.raises(PipelineConfigError):
            RouteConfig(name="r", pattern="/x", upstream="u", attempt_timeout_s=0)

    def test_methods_normalised(self):
        r = RouteConfig(name="r", pattern="/x", upstream="u", methods=frozenset({"get"}))
        assert r.methods == frozenset({"GET"})

    def test_worst_case(self):
        assert RouteConfig(name="r", pattern="/x", upstream="u", timeout_s=3).worst_case_s() == 3
        r = RouteConfig(
            name="r", pattern="/x", upstream="u", timeout_s=None, attempt_timeout_s=1,
            retry=RetrySpec(max_attempts=2, base_backoff_s=0.5, jitter=0),
        )
        assert r.worst_case_s() == pytest.approx(2.5)
        assert RouteConfig(name="r", pattern="/x", upstream="u", timeout_s=None).worst_case_s() is None

    def test_most_specific_wins(self):
        t = RouteTable(
            [
                RouteConfig(name="all", pattern="/api/**", upstream="u"),
                RouteConfig(name="items", pattern="/api/items/{id}", upstream="u"),
                RouteConfig(name="star", pattern="/api/*/{id}", upstream="u"),
            ]
        )
        assert t.match("GET", "/api/items/3").name == "items"
        assert t.match("GET", "/api/other/3").name == "star"
        assert t.match("GET", "/api/x").name == "all"
        assert t.match("GET", "/nope") is None

    def test_method_filtering(self):
        t = RouteTable(
            [
                RouteConfig(name="r", pattern="/x", upstream="u", methods=frozenset({"GET"})),
                RouteConfig(name="w", pattern="/x", upstream="u", methods=frozenset({"POST"})),
            ]
        )
        assert t.match("get", "/x").name == "r"
        assert t.match("POST", "/x").name == "w"
        assert t.match("PATCH", "/x") is None

    def test_overlap_and_duplicate_rejected(self):
        t = RouteTable([RouteConfig(name="a", pattern="/x/{id}", upstream="u")])
        with pytest.raises(PipelineConfigError):
            t.add(RouteConfig(name="b", pattern="/x/{other}", upstream="u"))
        with pytest.raises(PipelineConfigError):
            t.add(RouteConfig(name="a", pattern="/y", upstream="u"))

    def test_router_builds_canonical_stages(self):
        c = ManualClock()
        router = PipelineRouter(default_s2s_routes(), clock=c)
        desc = {d["name"]: [s["kind"] for s in d["stages"]] for d in router.describe()}
        assert desc["s2s-read"] == ["deadline", "retry", "breaker", "attempt_timeout"]

    def test_router_no_retry_stage_when_single_attempt(self):
        c = ManualClock()
        t = RouteTable([RouteConfig(name="r", pattern="/x", upstream="u", retry=RetrySpec.no_retry(), breaker=None)])
        router = PipelineRouter(t, clock=c)
        assert [s["kind"] for s in router.pipeline_for(t.routes()[0]).describe()] == ["deadline"]

    def test_router_shares_breaker_and_budget_per_upstream(self):
        c = ManualClock()
        t = RouteTable(
            [
                RouteConfig(name="a", pattern="/a", upstream="shared", breaker=BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1)),
                RouteConfig(name="b", pattern="/b", upstream="shared", breaker=BreakerConfig(consecutive_failures=1, min_calls=1, window_size=1)),
            ]
        )
        router = PipelineRouter(t, clock=c)
        resp, _ = router.call(PipelineRequest("POST", "/a"), Scripted(c, [503]))
        assert resp.status == 503
        with pytest.raises(BreakerOpenError):
            router.call(PipelineRequest("GET", "/b"), ok)
        # one budget for the shared upstream, built once for both routes
        assert router.budgets.names() == ["shared"]
        assert router.breakers.states() == {"shared": "open"}

    def test_router_caches_and_invalidates(self):
        c = ManualClock()
        router = PipelineRouter(default_s2s_routes(), clock=c)
        r = router.table.routes()[0]
        p = router.pipeline_for(r)
        assert router.pipeline_for(r) is p
        router.invalidate()
        assert router.pipeline_for(r) is not p

    def test_unmatched_fails_closed_or_default(self):
        c = ManualClock()
        router = PipelineRouter(RouteTable(), clock=c)
        with pytest.raises(PipelineConfigError):
            router.call(GET, ok)
        router = PipelineRouter(RouteTable(), clock=c, default_route=RouteConfig(name="d", pattern="/**", upstream="u"))
        resp, ctx = router.call(GET, ok)
        assert resp.status == 200 and ctx.route == "d"

    def test_stage_factories_plugged_in(self):
        c = ManualClock()
        made = []

        def tele(route):
            made.append(route.name)
            return _K(f"tele-{route.name}", "telemetry")

        router = PipelineRouter(
            default_s2s_routes(), clock=c,
            stage_factories={"telemetry": tele, "backpressure": lambda r: None, "custom": lambda r: _K("c", "custom")},
        )
        kinds = [s["kind"] for s in router.pipeline_for(router.table.routes()[0]).describe()]
        assert kinds[0] == "telemetry" and kinds[-1] == "custom"
        assert made == ["s2s-read"]

    def test_admit_pressure_route_matches_with_and_without_tenant(self):
        t = default_s2s_routes()
        assert t.match("GET", "/api/v1/admit/pressure").name == "s2s-admit-pressure"
        assert t.match("GET", "/api/v1/admit/pressure/t-1").name == "s2s-admit-pressure"
        assert t.match("GET", "/api/v1/things").name == "s2s-read"
        assert t.match("POST", "/api/v1/things").name == "s2s-write"

    def test_router_deadline_propagation(self):
        c = ManualClock()
        router = PipelineRouter(default_s2s_routes(), clock=c)
        with pytest.raises(DeadlineExceeded):
            router.call(GET, Scripted(c, [200], latency=0.5), deadline=Deadline.after(0.1, c))
